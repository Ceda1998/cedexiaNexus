"""Desktop controls for pairing devices and comparing their selected GGUFs."""

import json
import sys
from urllib.parse import quote

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from .pairing_transport import PairingThread, lan_address, valid_source

MISSING_MODEL = {"type": "model", "state": "missing"}


def lan_interfaces():
    addresses = {}
    for interface in QNetworkInterface.allInterfaces():
        if not interface.flags() & QNetworkInterface.InterfaceFlag.IsRunning:
            continue
        for entry in interface.addressEntries():
            address = entry.ip().toString()
            try:
                lan_address(address)
            except ValueError:
                continue
            addresses[address] = interface.humanReadableName()
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

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.thread = None
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
        layout.addWidget(plain_label("Auf beiden Geräten Cedexia Nexus öffnen. Beide müssen im selben LAN sein."))
        self.status = plain_label("Eine Einladung erstellen oder eine erhaltene Einladung einfügen.", "banner")
        layout.addWidget(self.status)

        form = QFormLayout()
        self.interfaces = QComboBox()
        self.interfaces.setAccessibleName("Lokale LAN-Adresse")
        self.reload_interfaces()
        self.host = action("Einladung erstellen", self.start_host)
        self.reload = action("Adressen aktualisieren", self.reload_interfaces)
        host_row = QHBoxLayout()
        for widget in (self.interfaces, self.reload, self.host):
            host_row.addWidget(widget)
        form.addRow("LAN-Adresse", host_row)
        self.code = QLineEdit()
        self.code.setMaxLength(128)
        self.code.setAccessibleName("Einladungscode")
        self.code.setPlaceholderText("Code vom einladenden Gerät")
        self.code.setEchoMode(QLineEdit.EchoMode.Password)
        self.copy = action("Code kopieren", self.copy_invitation)
        self.join = action("Beitreten", self.start_join)
        code_row = QHBoxLayout()
        for widget in (self.code, self.copy, self.join):
            code_row.addWidget(widget)
        form.addRow("Einladungscode", code_row)
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
        self.code.textChanged.connect(self.refresh)
        self.source.textChanged.connect(self.source_changed)
        self.runner.model_changed.connect(self.selection_changed)
        self.refresh()

    def reload_interfaces(self):
        previous = self.interfaces.currentData()
        self.interfaces.clear()
        for address, name in lan_interfaces().items():
            self.interfaces.addItem(f"{name} · {address}", address)
        if previous and (index := self.interfaces.findData(previous)) >= 0:
            self.interfaces.setCurrentIndex(index)
        if hasattr(self, "host"):
            self.refresh()

    def start_host(self):
        if self.thread is None and (address := self.interfaces.currentData()):
            self.begin(PairingThread(address=address, parent=self), hosting=True)

    def start_join(self):
        if self.thread is not None:
            return
        code = self.code.text().strip()
        try:
            thread = PairingThread(code=code, parent=self)
        except ValueError:
            self.status.setText("Der Einladungscode ist ungültig. Kopiere ihn erneut auf dem anderen Gerät.")
            return
        self.clear_invitation()
        self.begin(thread, hosting=False)

    def begin(self, thread, hosting):
        self.thread = thread
        self.hosting = hosting
        self.status.setText("Einladung wird erstellt …" if hosting else "Verbindung wird aufgebaut …")
        thread.invitation.connect(self.invitation_ready)
        thread.connected.connect(self.peer_connected)
        thread.message.connect(self.receive_message)
        thread.ended.connect(self.status.setText)
        thread.finished.connect(self.session_finished)
        self.code.clear()
        self.refresh()
        thread.start()

    def invitation_ready(self, code):
        if self.thread is None or self.thread.cancelled.is_set():
            return
        self.code.setText(code)
        self.status.setText("Code kopieren und auf dem zweiten Gerät einfügen. Die Einladung gilt fünf Minuten.")
        self.refresh()

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
        self.clear_invitation()
        self.status.setText("Geräte verbunden · verschlüsselte LAN-Sitzung")
        self.check_model()

    def close_session(self):
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
        if state == "ready" and self.hosting and model["sha256"] != self.offer_digest:
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
        self.interfaces.setEnabled(not active)
        self.reload.setEnabled(not active)
        self.host.setEnabled(not active and self.interfaces.count() > 0)
        self.code.setReadOnly(active)
        self.join.setEnabled(not active and bool(self.code.text().strip()))
        self.copy.setVisible(active and self.hosting and not self.connected)
        self.copy.setEnabled(active and bool(self.code.text()))
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
        can_offer = self.connected and self.hosting and local_ready and not peer_waiting and not matching
        self.source.setVisible(can_offer)
        self.share.setVisible(can_offer)
        self.share.setEnabled(can_offer and not self.source_sent and valid_source(self.source.text().strip()))
        show_source = self.connected and not self.hosting and bool(self.received_source) and not matching
        self.open_source.setVisible(show_source)
        self.notice.setVisible(show_source or (can_offer and self.source_sent))
        if show_source:
            self.notice.setText(f"Downloadhinweis vom einladenden Gerät für {peer['name']}:\n{self.received_source}")
        elif self.source_sent:
            self.notice.setText("Downloadhinweis wurde an das zweite Gerät gesendet.")
