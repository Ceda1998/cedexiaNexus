"""Exercise the real TLS transport and model verifier through two desktop windows."""

import ipaddress
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtNetwork import QNetworkInterface
    from PySide6.QtWidgets import QLineEdit
    from nexus_ui.app import NexusWindow, make_application
    from nexus_ui.device_pairing import pinned_source
    from nexus_ui.device_discovery import ANNOUNCEMENT, DiscoveredPeer, parse_announcement
    from nexus_ui.local_model import LocalRunner
    from nexus_ui.pairing_transport import PairingThread, make_invitation, read_invitation, valid_source
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    NexusWindow = None


@unittest.skipIf(NexusWindow is None, "Install requirements-ui.txt for Qt tests")
class DevicePairingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, _ = make_application()

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def window(self, directory, name):
        settings = QSettings(str(directory / (name + ".ini")), QSettings.Format.IniFormat)
        settings.setValue("local_model_paths", [])
        with patch("nexus_ui.local_model.QSettings", return_value=settings):
            window = NexusWindow(LocalRunner())
        self.addCleanup(self.close_window, window)
        window.navigate(2)
        window.show()
        return window

    def close_window(self, window):
        window.close()
        self.wait_for(lambda: not window.pairing.busy and not window.isVisible())
        window.deleteLater()
        self.app.processEvents()

    def test_invitation_validates_lan_and_source_requires_https(self):
        code = make_invitation("192.168.3.4", 49152, bytes(32), bytes(32))
        self.assertEqual(read_invitation(code), ("192.168.3.4", 49152, bytes(32), bytes(32)))
        for bad in ("", code[:-1], code.replace("nexus1", "nexus2")):
            with self.assertRaises(ValueError):
                read_invitation(bad)
        with self.assertRaises(ValueError):
            make_invitation("8.8.8.8", 49152, bytes(32), bytes(32))
        self.assertTrue(valid_source("https://huggingface.co/author/model?download=true"))
        for bad in ("file:///tmp/test", "http://example.com/test", "https://user@example.com/test",
                    "https://example.com/test?token=private", "https://127.0.0.1/test"):
            self.assertFalse(valid_source(bad))
        root = Path(__file__).resolve().parents[1]
        artifact = json.loads((root / "config/model-manifest.json").read_text(encoding="utf-8"))["artifact"]
        model = {"sha256": artifact["sha256"], "size": artifact["size_bytes"], "parts": 1}
        self.assertIn(artifact["revision"], pinned_source(root, model))
        self.assertEqual(pinned_source(root, {**model, "sha256": "0" * 64}), "")

    def test_discovery_announcement_is_scoped_to_subnet(self):
        network = ipaddress.ip_network("192.168.1.0/24")
        fingerprint = bytes(range(32))
        wire = ANNOUNCEMENT.pack(b"CN01", 2, 49200, fingerprint)
        peer = parse_announcement(wire, "192.168.1.25", network, bytes(32))
        self.assertIn("Windows", peer.label)
        self.assertEqual(peer.target, ("192.168.1.25", 49200, fingerprint, None))
        for data, address, own in ((wire, "192.168.2.25", bytes(32)),
                                   (wire, "192.168.1.25", fingerprint),
                                   (wire + b"x", "192.168.1.25", bytes(32))):
            with self.assertRaises(ValueError):
                parse_announcement(data, address, network, own)

    def test_discovery_tls_requires_both_devices_to_accept(self):
        network = ipaddress.ip_network("127.0.0.0/8")
        self.enterContext(patch("nexus_ui.pairing_transport.LAN_NETWORKS", (network,)))
        offered, codes, received = [], [], []
        host = PairingThread(address="127.0.0.1", discovery_network=network)
        host.advertised.connect(lambda port, pin: offered.append((port, pin)))
        host.approval_requested.connect(lambda code: codes.append(("host", code)))
        host.message.connect(received.append)

        def stop(thread):
            thread.stop()
            self.wait_for(thread.isFinished)

        host.start()
        self.addCleanup(stop, host)
        self.wait_for(lambda: bool(offered))
        port, pin = offered[0]
        for approve in (False, True):
            codes.clear()
            client = PairingThread(discovered_peer=("127.0.0.1", port, pin, None), source_address="127.0.0.1")
            client.approval_requested.connect(lambda code: codes.append(("client", code)))
            client.start()
            self.addCleanup(stop, client)
            self.wait_for(lambda: len(codes) == 2)
            self.assertEqual(codes[0][1], codes[1][1])
            self.assertFalse(client.joined)
            self.assertFalse(host.joined)
            host.decide(approve)
            if not approve:
                # A refusal wakes the other device without waiting for a second click.
                self.wait_for(client.isFinished)
                self.assertFalse(client.joined)
                self.assertFalse(host.joined)
                continue
            client.decide(True)
            self.wait_for(lambda: host.joined and client.joined)
            message = {"type": "model", "state": "missing"}
            client.send(message)
            self.wait_for(lambda: received == [message])

    def test_discovery_dialog_selects_peer_and_shows_confirmation(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        network = ipaddress.ip_network("127.0.0.0/8")
        self.enterContext(patch("nexus_ui.pairing_transport.LAN_NETWORKS", (network,)))
        self.enterContext(patch("nexus_ui.device_pairing.lan_interfaces", return_value={
            "127.0.0.1": ("WLAN", QNetworkInterface.InterfaceType.Wifi, "Testnetz"),
        }))
        self.enterContext(patch("nexus_ui.device_pairing.network_interface", return_value=(None, network)))
        source, target = [self.window(root, name).pairing for name in ("source", "target")]
        with patch.object(source.discovery, "start", return_value=True), patch.object(target.discovery, "start", return_value=True):
            published = []
            target.search.click()
            target.thread.advertised.connect(lambda port, pin: published.append((port, pin)))
            source.search.click()
            self.wait_for(lambda: bool(published) and "Dieses Gerät" in source.status.text())
            port, pin = published[0]
            peer = DiscoveredPeer("127.0.0.1", port, pin, 2)
            source.discovery.peers[pin] = (peer, time.monotonic() + 5)
            source.refresh_peers()
            self.assertEqual(source.peers.currentData(), peer)
            source.discovery.timer.start(60000)
            source.refresh()
            source.request.click()
            self.wait_for(lambda: source.approving and target.approving)
            self.assertEqual(source.approval_code.text(), target.approval_code.text())
            source.accept.click()
            self.assertFalse(source.connected)
            self.assertFalse(target.connected)
            target.accept.click()
            self.wait_for(lambda: source.connected and target.connected)
            self.assertFalse(source.discovery.timer.isActive())
            self.assertFalse(target.discovery.timer.isActive())

    def test_two_windows_authenticate_compare_and_share_download(self):
        # Use loopback only in CI so no listener is exposed to the test machine's LAN.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        mac_model, windows_model = root / "Modell Mac.gguf", root / "Andere Datei.gguf"
        header = struct.pack("<4sIQQ", b"GGUF", 3, 1, 0)
        mac_model.write_bytes(header + b"A" * 128)
        windows_model.write_bytes(header + b"B" * 128)
        addresses = patch("nexus_ui.pairing_transport.LAN_NETWORKS", (ipaddress.ip_network("127.0.0.0/8"),))
        addresses.start()
        self.addCleanup(addresses.stop)
        wifi = {"127.0.0.1": ("WLAN-Testadapter", QNetworkInterface.InterfaceType.Wifi, "Testnetz")}
        adapters = patch("nexus_ui.device_pairing.lan_interfaces", return_value=wifi)
        adapters.start()
        self.addCleanup(adapters.stop)
        host_window = self.window(root, "host")
        peer_window = self.window(root, "peer")
        host, peer = host_window.pairing, peer_window.pairing
        host.runner.select_model(mac_model)
        self.assertEqual(host.connection_type.currentText(), "WLAN")
        self.assertEqual(peer.connection_type.currentText(), "WLAN")
        self.assertTrue(host.host.isEnabled())
        host.host.click()
        self.wait_for(lambda: bool(host.code.text()) or host.thread is None)
        self.assertTrue(host.code.text(), host.status.text())
        code = host.code.text()
        self.assertEqual(host.code.echoMode(), QLineEdit.EchoMode.Password)
        self.assertTrue(host.reveal_code.isVisible())
        host.reveal_code.click()
        self.assertTrue(host.code_preview.isVisible())
        self.assertEqual(host.code_preview.toPlainText(), code)
        self.assertEqual(host.reveal_code.text(), "Code ausblenden")
        host.reveal_code.click()
        self.assertFalse(host.code_preview.isVisible())
        self.assertFalse(host.code_preview.toPlainText())
        host.reveal_code.click()
        host_window.hide()
        self.assertFalse(host.code_preview.toPlainText())
        host_window.show()
        self.assertTrue(host.reveal_code.isVisible())
        host.reveal_code.click()
        address, port, fingerprint, secret = read_invitation(code)
        for wrong in (make_invitation(address, port, bytes(32), secret),
                      make_invitation(address, port, fingerprint, bytes(32))):
            peer.code.setText(wrong)
            peer.join.click()
            self.wait_for(lambda: peer.thread is None)
            self.assertFalse(host.connected)
            self.assertIn("fehlgeschlagen", peer.status.text())
        peer.code.setText(code)
        peer.join.click()
        self.assertEqual(peer.thread.source_address, "127.0.0.1")
        self.wait_for(lambda: host.local_model["state"] in ("ready", "error") and peer.connected)
        self.assertEqual(host.local_model["state"], "ready", host.selected.text())
        self.wait_for(lambda: host.share.isVisible())
        self.assertIn("fehlt", host.comparison.text())
        self.assertEqual(host.code.text(), "")
        self.assertFalse(host.code_preview.toPlainText())
        self.assertFalse(host.reveal_code.isVisible())
        peer.runner.select_model(windows_model)
        self.wait_for(lambda: "unterscheiden" in host.comparison.text())
        self.wait_for(lambda: "unterscheiden" in peer.comparison.text())
        url = "https://huggingface.co/author/model"
        host.source.setText(url)
        host.share.click()
        self.wait_for(lambda: peer.open_source.isVisible())
        self.assertIn(url, peer.notice.text())
        with patch("nexus_ui.device_pairing.QDesktopServices.openUrl", return_value=True) as browser:
            peer.open_source.click()
            self.assertEqual(browser.call_args.args[0].toString(), url)

        windows_model.write_bytes(mac_model.read_bytes())
        peer.recheck.click()
        self.wait_for(lambda: all("Identische" in page.comparison.text() for page in (host, peer)))
        self.assertFalse(peer.open_source.isVisible())
        self.assertFalse(host.share.isVisible())
        host_window.close()
        self.wait_for(lambda: host.thread is None and peer.thread is None and not host_window.isVisible())
        self.assertFalse(peer.connected)

    def test_connection_type_filters_addresses_and_gates_join(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        interface = QNetworkInterface.InterfaceType
        ethernet, wifi, unknown = "192.0.2.10", "192.0.2.20", "192.0.2.30"
        detected = {
            ethernet: ("Kabel", interface.Ethernet, ""),
            wifi: ("Funk", interface.Wifi, "Testnetz"),
            unknown: ("Sonstiger Adapter", interface.Unknown, ""),
        }
        with patch("nexus_ui.device_pairing.lan_interfaces", return_value=detected):
            page = self.window(root, "network-options").pairing
            self.assertEqual(page.connection_type.currentText(), "Ethernet (LAN)")
            self.assertEqual(page.interfaces.currentData(), ethernet)
            page.connection_type.setCurrentText("WLAN")
            self.assertEqual(page.interfaces.currentData(), wifi)
            self.assertEqual(page.interfaces.count(), 1)
            self.assertEqual(page.wifi_name.text(), "Verbundenes WLAN: Testnetz")
            detected[wifi] = ("Funk", interface.Wifi, "")
            page.reload_interfaces()
            self.assertIn("nicht verfügbar", page.wifi_name.text())
            self.assertTrue(page.host.isEnabled())
            page.connection_type.setCurrentText("Manuelle Auswahl")
            self.assertEqual(page.interfaces.count(), 3)
            page.interfaces.setCurrentIndex(page.interfaces.findData(unknown))
            self.assertEqual(page.interfaces.currentData(), unknown)

            detected.pop(wifi)
            page.connection_type.setCurrentText("WLAN")
            page.code.setText("Einladung")
            self.assertFalse(page.join.isEnabled())
            self.assertFalse(page.host.isEnabled())
            self.assertIn("Kein aktives WLAN", page.network_hint.text())
