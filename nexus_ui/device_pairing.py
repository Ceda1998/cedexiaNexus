"""Desktop controls for pairing devices and comparing their selected GGUFs."""

import json
import sys
from urllib.parse import quote

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .pairing_transport import PairingThread, lan_address, valid_source
from .device_discovery import DeviceDiscovery, network_interface
from .wifi_status import connected_wifi

MISSING_MODEL = {"type": "model", "state": "missing"}
CONNECTION_TYPES = (
    (QNetworkInterface.InterfaceType.Ethernet, "Ethernet (LAN)"),
    (QNetworkInterface.InterfaceType.Wifi, "WLAN"),
    (None, "Manuelle Auswahl"),
)


def lan_interfaces():
    addresses = {}
    wifi = connected_wifi()
    for interface in QNetworkInterface.allInterfaces():
        if not interface.flags() & QNetworkInterface.InterfaceFlag.IsRunning:
            continue
        for entry in interface.addressEntries():
            address = entry.ip().toString()
            try:
                lan_address(address)
            except ValueError:
                continue
            adapter = interface.name().strip("{}").lower()
            kind = QNetworkInterface.InterfaceType.Wifi if adapter in wifi else interface.type()
            addresses[address] = (interface.humanReadableName(), kind, wifi.get(adapter, ""))
    return addresses


def pinned_source(root, model):
    try:
        artifact = json.loads((root / "config/model-manifest.json").read_text(encoding="utf-8"))["artifact"]
        if model["parts"] != 1 or (model["sha256"], model["size"]) != (artifact["sha256"], artifact["size_bytes"]):
            return ""
        return (f"https://huggingface.co/{artifact['repository']}/resolve/"
                f"{artifact['revision']}/{quote(artifact['filename'])}")
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def plain_label(text, name=""):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def action(text, handler):
    button = QPushButton(text)
    button.clicked.connect(handler)
    return button


def same_weights(local, peer):
    return local["state"] == peer["state"] == "ready" and all(
        local[key] == peer[key] for key in ("sha256", "size", "parts"))


def compare_models(local, peer):
    if peer is None:
        return "Warte auf den Modellstatus des zweiten Geräts."
    if "checking" in (local["state"], peer["state"]):
        return "GGUF-Gewichte werden im Hintergrund geprüft."
    if local["state"] != "ready" or peer["state"] != "ready":
        return "Mindestens einem Gerät fehlt ein prüfbares GGUF-Modell."
    if same_weights(local, peer):
        return "Identische GGUF-Gewichte auf beiden Geräten."
    return "Die ausgewählten GGUF-Gewichte unterscheiden sich."


class DevicePairingPage(QWidget):
    idle = Signal()
    discovery_failure = "Geräteerkennung fehlgeschlagen. Prüfe das lokale Netzwerk oder verwende einen Einladungscode."

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.thread = None
        self.discovery = DeviceDiscovery(self)
        self.discovery.changed.connect(self.refresh_peers)
        self.discovery.interrupted.connect(self.discovery_interrupted)
        self.pending_peer = None
        self.discovery_interface = None
        self.discovery_network = None
        self.approving = False
        self.approval_sent = False
        self.hosting = False
        self.connected = False
        self.local_model = MISSING_MODEL
        self.peer_model = None
        self.received_source = ""
        self.source_sent = False
        self.offer_digest = None
        self.probe_path = None
        self.probe = QProcess(self)
        self.probe.finished.connect(self.probe_finished)
        self.probe.errorOccurred.connect(self.probe_error)
        self.probe_timeout = QTimer(self, singleShot=True, interval=600000)
        self.probe_timeout.timeout.connect(self.probe.kill)

        layout = QVBoxLayout(self)
        layout.addWidget(plain_label("Geräte verbinden", "title"))
        layout.addWidget(plain_label(
            "Verbinde beide Geräte mit demselben lokalen Netz über Ethernet oder WLAN. "
            "Wähle auf jedem Gerät seine Netzwerkverbindung."
        ))
        self.status = plain_label("Eine Einladung erstellen oder eine erhaltene Einladung einfügen.", "banner")
        layout.addWidget(self.status)

        form = QFormLayout()
        self.connection_type = QComboBox()
        self.connection_type.setAccessibleName("Netzwerkverbindung")
        for _, label in CONNECTION_TYPES:
            self.connection_type.addItem(label)
        self.connection_type.setCurrentIndex(-1)
        form.addRow("Verbindung", self.connection_type)
        self.interfaces = QComboBox()
        self.interfaces.setAccessibleName("Lokale Netzwerkadresse")
        self.interfaces.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.interfaces.setMinimumContentsLength(14)
        self.network_hint = plain_label("")
        self.wifi_name = plain_label("")
        self.wifi_names = {}
        self.location_manager = None
        self.host = action("Einladung erstellen", self.start_host)
        self.reload = action("Aktualisieren", self.reload_interfaces)
        self.reload.setToolTip("Netzwerkadapter neu einlesen")
        host_row = QHBoxLayout()
        host_row.addWidget(self.interfaces, 1)
        host_row.addWidget(self.reload)
        form.addRow("Adapter", host_row)
        form.addRow(self.wifi_name)
        self.read_wifi = action("WLAN-Namen freigeben …", self.request_wifi_name)
        form.addRow(self.read_wifi)
        form.addRow(self.network_hint)
        self.search = action("Geräte im Netz suchen", self.start_discovery)
        self.peers = QComboBox()
        self.peers.setAccessibleName("Cedexia-Geräte im lokalen Netz")
        self.peers.setPlaceholderText("Noch kein anderes Gerät gefunden")
        self.request = action("Kopplung anfragen", self.request_pairing)
        peer_row = QHBoxLayout()
        peer_row.addWidget(self.peers, 1)
        peer_row.addWidget(self.request)
        self.approval_code = plain_label("", "banner")
        self.accept = action("Code stimmt überein", lambda: self.approve(True))
        self.decline = action("Ablehnen", lambda: self.approve(False))
        approval_row = QHBoxLayout()
        approval_row.addWidget(self.accept)
        approval_row.addWidget(self.decline)
        form.addRow(self.search)
        form.addRow("Gefundene Geräte", peer_row)
        form.addRow(self.approval_code)
        form.addRow(approval_row)
        form.addRow(self.host)
        self.code = QLineEdit()
        self.code.setMaxLength(128)
        self.code.setAccessibleName("Einladungscode")
        self.code.setPlaceholderText("Code vom einladenden Gerät")
        self.code.setEchoMode(QLineEdit.EchoMode.Password)
        self.reveal_code = QPushButton("Code anzeigen")
        self.reveal_code.setCheckable(True)
        self.reveal_code.toggled.connect(self.show_invitation_code)
        self.copy = action("Code kopieren", self.copy_invitation)
        self.join = action("Beitreten", self.start_join)
        code_row = QHBoxLayout()
        code_row.addWidget(self.code, 1)
        code_row.addWidget(self.join)
        form.addRow("Einladungscode", code_row)
        self.code_preview = QPlainTextEdit()
        self.code_preview.setAccessibleName("Sichtbarer Einladungscode")
        self.code_preview.setReadOnly(True)
        self.code_preview.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.code_preview.setMaximumHeight(90)
        self.code_preview.hide()
        form.addRow(self.code_preview)
        code_actions = QHBoxLayout()
        code_actions.addWidget(self.reveal_code)
        code_actions.addWidget(self.copy)
        code_actions.addStretch()
        form.addRow("", code_actions)
        layout.addLayout(form)
        self.disconnect = action("Trennen", self.close_session)
        layout.addWidget(self.disconnect)

        self.comparison = plain_label("", "banner")
        self.selected = plain_label("")
        self.remote = plain_label("")
        for widget in (self.comparison, self.selected, self.remote):
            layout.addWidget(widget)
        model_row = QHBoxLayout()
        self.select = QPushButton("Lokales Modell auswählen …")
        self.recheck = action("Gewichte erneut prüfen", self.check_model)
        model_row.addWidget(self.select)
        model_row.addWidget(self.recheck)
        layout.addLayout(model_row)

        self.source = QLineEdit()
        self.source.setMaxLength(1600)
        self.source.setAccessibleName("HTTPS-Bezugsquelle für dieses GGUF")
        self.source.setPlaceholderText("HTTPS-Bezugsquelle für genau diese GGUF-Datei")
        self.share = action("Downloadhinweis senden", self.send_source)
        self.notice = plain_label("")
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.open_source = action("Bezugsquelle im Browser öffnen", self.visit_source)
        for widget in (self.source, self.share, self.notice, self.open_source):
            layout.addWidget(widget)
        layout.addStretch()
        self.interfaces.currentIndexChanged.connect(self.refresh)
        self.interfaces.currentIndexChanged.connect(self.show_wifi_name)
        self.connection_type.currentIndexChanged.connect(self.reload_interfaces)
        self.code.textChanged.connect(self.refresh)
        self.peers.currentIndexChanged.connect(self.refresh)
        self.source.textChanged.connect(self.source_changed)
        self.runner.model_changed.connect(self.selection_changed)
        self.reload_interfaces()

    def reload_interfaces(self):
        previous = self.interfaces.currentData()
        adapters = lan_interfaces()
        if self.connection_type.currentIndex() < 0:
            known = [kind for _, kind, _ in adapters.values()]
            first = next((index for index, (kind, _) in enumerate(CONNECTION_TYPES[:-1])
                          if kind in known), len(CONNECTION_TYPES) - 1)
            self.connection_type.blockSignals(True)
            self.connection_type.setCurrentIndex(first)
            self.connection_type.blockSignals(False)
        kind, label = CONNECTION_TYPES[self.connection_type.currentIndex()]
        self.interfaces.blockSignals(True)
        self.interfaces.clear()
        self.wifi_names = {}
        for address, (name, detected, ssid) in adapters.items():
            if kind is None or kind == detected:
                self.interfaces.addItem(f"{name} · {address}", address)
                self.wifi_names[address] = ssid
        if previous and (index := self.interfaces.findData(previous)) >= 0:
            self.interfaces.setCurrentIndex(index)
        self.interfaces.blockSignals(False)
        if self.interfaces.count() == 0:
            self.network_hint.setText(f"Keine aktive IPv4-Adresse für {label}. Netzwerk prüfen und aktualisieren.")
        elif kind is None:
            self.network_hint.setText("Wähle den Adapter, der mit dem Netz des anderen Geräts verbunden ist.")
        else:
            self.network_hint.clear()
        if kind == QNetworkInterface.InterfaceType.Wifi and self.interfaces.count() == 0:
            self.network_hint.setText("Kein aktives WLAN erkannt. Verbinde dieses Gerät in den Systemeinstellungen mit einem WLAN und klicke dann auf „Aktualisieren“.")
        elif kind is not None and self.interfaces.count() == 0 and adapters:
            self.network_hint.setText(f"Kein Adapter für {label} erkannt. Wähle bei Bedarf „Manuelle Auswahl“.")
        self.network_hint.setVisible(bool(self.network_hint.text()))
        self.show_wifi_name()
        self.refresh()

    def show_wifi_name(self):
        wifi_selected = self.connection_type.currentText() == "WLAN" and bool(self.interfaces.currentData())
        name = self.wifi_names.get(self.interfaces.currentData(), "")
        self.wifi_name.setText(f"Verbundenes WLAN: {name}" if name else
                               "WLAN verbunden. Der Netzwerkname ist vom System nicht verfügbar.")
        self.wifi_name.setVisible(wifi_selected)
        self.read_wifi.setVisible(wifi_selected and not name and sys.platform == "darwin")

    def request_wifi_name(self):
        try:
            from CoreLocation import CLLocationManager, kCLAuthorizationStatusDenied, kCLAuthorizationStatusRestricted

            if self.location_manager is None:
                self.location_manager = CLLocationManager.alloc().init()
            denied = (kCLAuthorizationStatusDenied, kCLAuthorizationStatusRestricted)
            if self.location_manager.authorizationStatus() in denied:
                self.wifi_name.setText("Prüfe den Zugriff unter Systemeinstellungen → Datenschutz & Sicherheit → Ortungsdienste.")
            else:
                self.location_manager.requestWhenInUseAuthorization()
                self.wifi_name.setText("WLAN-Name: Nach der macOS-Freigabe auf „Aktualisieren“ klicken.")
        except (ImportError, RuntimeError):
            self.wifi_name.setText("WLAN-Name ist in diesem Build nicht verfügbar.")

    def start_host(self):
        if self.thread is None and (address := self.interfaces.currentData()):
            self.begin(PairingThread(address=address, parent=self), hosting=True)

    def start_discovery(self):
        address = self.interfaces.currentData()
        if self.thread is not None or not address:
            return
        try:
            self.discovery_interface, self.discovery_network = network_interface(address)
        except ValueError:
            self.status.setText("Der Adapter hat kein nutzbares IPv4-Subnetz. Aktualisiere die Adapterliste.")
            return
        thread = PairingThread(address=address, discovery_network=self.discovery_network, parent=self)
        self.begin(thread, hosting=True, status="Geräteerkennung wird gestartet …")

    def discovery_ready(self, port, fingerprint):
        if self.thread is None or not self.isVisible() or self.thread.cancelled.is_set():
            return
        system = {"darwin": 1, "win32": 2}.get(sys.platform, 0)
        if self.discovery.start(self.thread.address, self.discovery_interface, self.discovery_network,
                                system, port, fingerprint):
            identifier = fingerprint.hex()[:8].upper()
            self.status.setText(f"Dieses Gerät: {identifier}. Starte die Suche auch auf dem anderen Gerät.")
        else:
            self.discovery_interrupted()

    def discovery_interrupted(self):
        self.close_session()
        self.status.setText(self.discovery_failure)

    def refresh_peers(self):
        previous = self.peers.currentData()
        self.peers.blockSignals(True)
        self.peers.clear()
        for peer, _ in self.discovery.peers.values():
            self.peers.addItem(peer.label, peer)
        if previous is not None and (index := self.peers.findData(previous)) >= 0:
            self.peers.setCurrentIndex(index)
        elif self.peers.count():
            self.peers.setCurrentIndex(0)
        self.peers.blockSignals(False)
        self.refresh()

    def request_pairing(self):
        if self.request.isEnabled():
            self.pending_peer = self.peers.currentData()
            self.discovery.close()
            self.thread.stop()
            self.refresh()

    def show_approval(self, code):
        if self.thread is None or self.thread.cancelled.is_set():
            return
        self.approving = True
        self.approval_sent = False
        self.approval_code.setText(
            f"Kopplungsanfrage · {code}\nVergleiche diesen Code auf beiden Geräten und bestätige auf beiden Seiten."
        )
        self.refresh()

    def hide_approval(self):
        self.approving = False
        self.approval_sent = False
        self.refresh()

    def approve(self, accepted):
        if self.approving and not self.approval_sent and self.thread is not None:
            self.thread.decide(accepted)
            self.approval_sent = True
            if accepted:
                heading = self.approval_code.text().partition("\n")[0]
                self.approval_code.setText(f"{heading}\nWarte auf die Bestätigung des anderen Geräts.")
            else:
                self.hide_approval()
            self.refresh()

    def hideEvent(self, event):
        self.reveal_code.setChecked(False)
        if self.thread is not None and self.thread.uses_discovery and not self.connected:
            self.close_session()
        super().hideEvent(event)

    def start_join(self):
        if self.thread is not None or not (address := self.interfaces.currentData()):
            return
        code = self.code.text().strip()
        try:
            thread = PairingThread(code=code, source_address=address, parent=self)
        except ValueError:
            self.status.setText("Der Einladungscode ist ungültig. Kopiere ihn erneut auf dem anderen Gerät.")
            return
        self.clear_invitation()
        self.begin(thread, hosting=False)

    def begin(self, thread, hosting, status=None):
        self.thread = thread
        self.hosting = hosting
        self.status.setText(status or ("Einladung wird erstellt …" if hosting else "Verbindung wird aufgebaut …"))
        thread.invitation.connect(self.invitation_ready)
        thread.advertised.connect(self.discovery_ready)
        thread.approval_requested.connect(self.show_approval)
        thread.approval_ended.connect(self.hide_approval)
        thread.connected.connect(self.peer_connected)
        thread.message.connect(self.receive_message)
        thread.ended.connect(self.show_session_end)
        thread.finished.connect(self.session_finished)
        self.code.clear()
        self.refresh()
        thread.start()

    def invitation_ready(self, code):
        if self.thread is None or self.thread.cancelled.is_set():
            return
        self.code.setText(code)
        self.status.setText("Einladungscode anzeigen oder kopieren und auf dem zweiten Gerät eingeben. Die Einladung gilt fünf Minuten.")
        self.refresh()

    def show_invitation_code(self, visible):
        self.code_preview.setPlainText(self.code.text() if visible else "")
        self.code_preview.setVisible(visible)
        self.reveal_code.setText("Code ausblenden" if visible else "Code anzeigen")

    def copy_invitation(self):
        if self.copy.isEnabled():
            QApplication.clipboard().setText(self.code.text())
            self.status.setText("Einladung kopiert. Füge sie auf dem zweiten Gerät ein.")

    def clear_invitation(self):
        code = self.code.text()
        self.code.clear()
        if code and QApplication.clipboard().text() == code:
            QApplication.clipboard().clear()

    def peer_connected(self):
        if self.thread is None or self.thread.cancelled.is_set():
            return
        self.connected = True
        self.discovery.close()
        self.clear_invitation()
        label = self.connection_type.currentText()
        self.status.setText(f"Geräte verbunden · {label} · verschlüsselt")
        self.check_model()

    def show_session_end(self, status):
        if self.pending_peer is None and self.status.text() != self.discovery_failure:
            self.status.setText(status)

    def close_session(self):
        self.pending_peer = None
        self.discovery.close()
        self.hide_approval()
        if self.thread is not None:
            self.connected = False
            self.thread.stop()
            self.clear_invitation()
        self.cancel_probe()
        self.refresh()

    @property
    def busy(self):
        return self.thread is not None or self.probe.state() != QProcess.ProcessState.NotRunning

    def session_finished(self):
        self.discovery.close()
        self.clear_invitation()
        self.thread.deleteLater()
        self.thread = None
        self.connected = False
        self.hosting = False
        self.local_model = MISSING_MODEL
        self.peer_model = None
        self.received_source = ""
        self.source_sent = False
        self.offer_digest = None
        self.source.clear()
        self.cancel_probe()
        self.hide_approval()
        peer, self.pending_peer = self.pending_peer, None
        if peer is not None and self.isVisible():
            thread = PairingThread(discovered_peer=peer.target, source_address=self.interfaces.currentData(), parent=self)
            self.begin(thread, hosting=False, status=f"Kopplungsanfrage an {peer.label} wird gesendet …")
            return
        self.refresh()
        if not self.busy:
            self.idle.emit()

    def selection_changed(self):
        if self.connected:
            self.check_model()
        else:
            self.refresh()

    def source_changed(self):
        self.source_sent = False
        self.refresh()

    def cancel_probe(self):
        self.probe_path = None
        self.probe_timeout.stop()
        if self.probe.state() != QProcess.ProcessState.NotRunning:
            self.probe.kill()

    def check_model(self):
        if not self.connected:
            return
        path = self.runner.model
        self.source_sent = False
        self.send_model("checking" if path and path.is_file() else "missing")
        if self.probe.state() != QProcess.ProcessState.NotRunning:
            self.cancel_probe()
            return  # The finished handler restarts against the current selection.
        if not path or not path.is_file():
            return
        self.probe_path = path
        self.probe.setWorkingDirectory(str(self.runner.root))
        self.probe_timeout.start()
        self.probe.start(sys.executable, self.runner.verifier_arguments("--fingerprint-gguf"))

    def probe_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.probe_timeout.stop()
            if self.connected:
                self.send_model("error")
            elif not self.busy:
                self.idle.emit()

    def probe_finished(self, code, exit_status):
        self.probe_timeout.stop()
        output = bytes(self.probe.readAllStandardOutput())
        self.probe.readAllStandardError()
        if not self.connected:
            if not self.busy:
                self.idle.emit()
            return
        if self.probe_path is None or self.probe_path != self.runner.model:
            self.check_model()
            return
        if code or exit_status != QProcess.ExitStatus.NormalExit:
            self.send_model("error")
            return
        try:
            result = json.loads(output)
            self.send_model("ready", name=self.probe_path.name, **result)
        except (AttributeError, TypeError, ValueError):
            self.send_model("error")

    def send_model(self, state, **fields):
        model = {"type": "model", "state": state, **fields}
        self.thread.send(model)
        self.local_model = model
        if state == "ready" and self.thread.can_offer and model["sha256"] != self.offer_digest:
            self.offer_digest = model["sha256"]
            self.source.setText(pinned_source(self.runner.root, model))
        self.refresh()

    def receive_message(self, message):
        if not self.connected:
            return
        if message["type"] == "model":
            if self.peer_model is None or self.peer_model.get("sha256") != message.get("sha256"):
                self.received_source = ""
                self.source_sent = False
            self.peer_model = message
        elif self.peer_model and message["sha256"] == self.peer_model.get("sha256"):
            self.received_source = message["url"]
        self.refresh()

    def send_source(self):
        if self.share.isEnabled():
            self.thread.send({"type": "source", "sha256": self.local_model["sha256"],
                              "url": self.source.text().strip()})
            self.source_sent = True
            self.refresh()

    def visit_source(self):
        if self.open_source.isVisible() and valid_source(self.received_source):
            if not QDesktopServices.openUrl(QUrl(self.received_source)):
                self.status.setText("Browser konnte nicht geöffnet werden. Kopiere den Link aus dem Downloadhinweis.")

    def refresh(self):
        active = self.thread is not None
        has_address = bool(self.interfaces.currentData())
        self.connection_type.setEnabled(not active)
        self.interfaces.setEnabled(not active)
        self.reload.setEnabled(not active)
        self.host.setEnabled(not active and has_address)
        self.search.setEnabled(not active and has_address)
        browsing = (active and self.discovery.timer.isActive() and not self.approving
                    and not self.thread.cancelled.is_set())
        self.peers.setEnabled(browsing and bool(self.peers.count()))
        self.request.setEnabled(browsing and self.peers.currentData() is not None)
        for widget in (self.approval_code, self.accept, self.decline):
            widget.setVisible(self.approving)
        self.accept.setEnabled(not self.approval_sent)
        self.decline.setEnabled(not self.approval_sent)
        self.code.setReadOnly(active)
        self.join.setVisible(not active)
        self.join.setEnabled(not active and has_address and bool(self.code.text().strip()))
        has_invitation = (active and self.hosting and not self.thread.cancelled.is_set()
                          and not self.connected and bool(self.code.text()))
        if not has_invitation:
            self.reveal_code.setChecked(False)
        self.reveal_code.setVisible(has_invitation)
        self.copy.setVisible(has_invitation)
        self.copy.setEnabled(has_invitation)
        self.disconnect.setEnabled(active)
        self.recheck.setEnabled(self.probe.state() == QProcess.ProcessState.NotRunning
                                and self.local_model["state"] != "checking")
        for widget in (self.comparison, self.selected, self.remote, self.select, self.recheck):
            widget.setVisible(self.connected)
        path = self.runner.model
        self.selected.setText(f"Hier ausgewählt · {path.name}" if path else "Hier ist kein Modell ausgewählt.")
        self.comparison.setText(compare_models(self.local_model, self.peer_model))
        peer = self.peer_model or {}
        if peer.get("state") == "ready":
            self.remote.setText(f"Zweites Gerät · {peer['name']} · {peer['size'] / 1024**3:.2f} GiB · {peer['parts']} Datei(en)")
        elif peer.get("state") == "error":
            self.remote.setText("GGUF konnte nicht geprüft werden. Datei und bei Split-GGUF alle Teile prüfen.")
        else:
            self.remote.clear()
        if self.local_model["state"] == "error":
            self.selected.setText("Lokales GGUF konnte nicht geprüft werden. Datei und bei Split-GGUF alle Teile prüfen.")
        local_ready = self.local_model["state"] == "ready"
        peer_waiting = not peer or peer["state"] == "checking"
        matching = bool(peer and same_weights(self.local_model, peer))
        can_offer = self.connected and self.thread.can_offer and local_ready and not peer_waiting and not matching
        self.source.setVisible(can_offer)
        self.share.setVisible(can_offer)
        self.share.setEnabled(can_offer and not self.source_sent and valid_source(self.source.text().strip()))
        show_source = self.connected and not self.thread.can_offer and bool(self.received_source) and not matching
        self.open_source.setVisible(show_source)
        self.notice.setVisible(show_source or (can_offer and self.source_sent))
        if show_source:
            self.notice.setText(f"Downloadhinweis vom einladenden Gerät für {peer['name']}:\n{self.received_source}")
        elif self.source_sent:
            self.notice.setText("Downloadhinweis wurde an das zweite Gerät gesendet.")
