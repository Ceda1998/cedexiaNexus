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
    from nexus_ui.app import NexusWindow, make_application
    from nexus_ui.device_pairing import pinned_source
    from nexus_ui.local_model import LocalRunner
    from nexus_ui.pairing_transport import make_invitation, read_invitation, valid_source
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
