"""Desktop app with LAN pairing, local inference and separate demo pages."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QScrollArea, QFrame, QComboBox,
    QPlainTextEdit, QSpinBox, QMessageBox,
)
from .device_pairing import DevicePairingPage
from .local_model import LocalModelPage
from .pairing_transport import host_context

ASSETS = Path(__file__).parent / "assets"
STYLE = """
QWidget { color: #162033; background: #F5F6F8; }
QLabel { background: transparent; }
QFrame#panel { background: white; border: 1px solid #D8DEE8; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#subtitle { color: #526075; }
QLabel#banner { background: #EAF0F8; color: #173B70; padding: 12px; }
QPushButton { min-height: 28px; padding: 8px 16px; border: 1px solid #8B9DB5;
 background: white; color: #173B70; border-radius: 0px; }
QPushButton:hover { background: #EAF0F8; }
QPushButton:checked { background: #EAF0F8; border-left: 3px solid #173B70; }
QPushButton[primary="true"] { background: #173B70; color: white; }
QPushButton[primary="true"]:hover { background: #102C55; }
QPushButton:disabled { background: #EEF0F3; color: #626D7D; border-color: #C8CED8; }
QPushButton:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus, QLineEdit:focus {
 border: 2px solid #173B70; }
QComboBox, QSpinBox, QLineEdit { background: white; padding: 8px; min-height: 28px;
 border: 1px solid #8B9DB5; border-radius: 0px; }
QPlainTextEdit { background: white; border: 1px solid #8B9DB5; padding: 12px; }
"""


def icon(name, color="#173B70"):
    """Render the pinned SVG locally with an explicit Qt-compatible color."""
    data = (ASSETS / "icons" / f"{name}.svg").read_bytes()
    renderer = QSvgRenderer(data.replace(b"currentColor", color.encode()))
    result = QIcon()
    for size in (20, 40, 60):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result


def label(text, role=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setObjectName(role)
    return widget


def button(text, callback, name=None, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.setAccessibleName(text)
    if name:
        widget.setIcon(icon(name, "#FFFFFF" if primary else "#173B70"))
        widget.setIconSize(QSize(20, 20))
    widget.clicked.connect(callback)
    return widget


class NexusWindow(QMainWindow):
    def __init__(self, local_runner=None):
        super().__init__()
        self.setWindowTitle("Cedexia Nexus")
        self.closing = False
        self.resize(1200, 850)
        self.setMinimumSize(800, 600)
        self.checked = False
        self.paired = False
        self.model_ready = False
        self.running = False
        self.step = 0
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(label("CEDEXIA NEXUS", "title"))
        self.banner = label("", "banner")
        layout.addWidget(self.banner)
        self.font_notice = label("", "subtitle")
        layout.addWidget(self.font_notice)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        navigation = QVBoxLayout()
        body.addLayout(navigation)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.nav = []
        for i, (title, name) in enumerate([
            ("Übersicht", "layout-dashboard"), ("Einrichtung", "checklist"),
            ("Geräte verbinden", "devices"), ("Demo-Sitzung", "message"),
            ("Lokales Modell", "player-play"), ("Über Nexus", "settings"),
        ]):
            nav = button(title, lambda checked=False, index=i: self.navigate(index), name)
            nav.setCheckable(True)
            navigation.addWidget(nav)
            self.nav.append(nav)
        navigation.addStretch()
        self.overview()
        self.setup()
        self.local_model = LocalModelPage(runner=local_runner)
        self.pairing = DevicePairingPage(self.local_model.runner)
        self.pairing.select.clicked.connect(lambda: self.navigate(4))
        self.pairing.idle.connect(self.finish_closing)
        pairing_scroll = QScrollArea()
        pairing_scroll.setWidgetResizable(True)
        pairing_scroll.setFrameShape(QFrame.Shape.NoFrame)
        pairing_scroll.setWidget(self.pairing)
        self.stack.addWidget(pairing_scroll)
        self.session()
        self.stack.addWidget(self.local_model)
        self.local_model.runner.finished.connect(self.finish_closing)
        self.about()
        self.navigate(0)
        self.refresh()

    def page(self, title, subtitle):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 8, 12, 16)
        layout.setSpacing(16)
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(subtitle, "subtitle"))
        scroll.setWidget(content)
        self.stack.addWidget(scroll)
        return layout

    def panel(self, layout, title, text):
        frame = QFrame()
        frame.setObjectName("panel")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(24, 20, 24, 20)
        heading = label(title)
        heading.setFont(QFont(self.font().family(), 15, QFont.Weight.Bold))
        inner.addWidget(heading)
        value = label(text)
        inner.addWidget(value)
        layout.addWidget(frame)
        return value

    def overview(self):
        layout = self.page("Rechenleistung verbinden.", "Zwei Geräte. Eine lokale KI-Sitzung — als Ablaufvorschau.")
        self.summary = self.panel(layout, "Dein Arbeitsbereich", "")
        self.panel(layout, "Gemeinsame Berechnung", "Diese Vorschau ist simuliert. Die Einzelgeräte-Ansicht findest du unter ‚Lokales Modell‘.")
        layout.addWidget(button("Geräte verbinden", lambda: self.navigate(2), "devices"))
        layout.addWidget(button("Lokales Modell öffnen", lambda: self.navigate(4), "player-play", True))
        layout.addWidget(button("Einrichtung öffnen", lambda: self.navigate(1), "checklist", True))
        layout.addStretch()

    def setup(self):
        layout = self.page("In wenigen Schritten bereit.", "Geräte- und Modellprüfung auf dieser Seite sind simuliert.")
        self.setup_status = self.panel(layout, "01 / Dieses Gerät", "Noch nicht geprüft")
        layout.addWidget(button("Geräteprüfung simulieren", self.check_device, "checklist", True))
        self.model_status = self.panel(layout, "02 / Modell", "Kein Demo-Modell vorbereitet")
        layout.addWidget(button("Modellprüfung simulieren", self.prepare_model, "checklist"))
        layout.addWidget(button("03 / Zweites Gerät verbinden", lambda: self.navigate(2), "devices"))
        layout.addWidget(button("04 / Zur Sitzung", lambda: self.navigate(3), "message"))
        layout.addStretch()

    def session(self):
        layout = self.page("Eine Aufgabe. Dein Cluster.", "Eine feste Beispielausgabe zeigt den Ablauf. Deine Eingabe wird weder verarbeitet noch gespeichert.")
        self.mode = QComboBox()
        self.mode.addItems(["Dieses Gerät · Demo", "Zwei Geräte · Demo"])
        self.mode.currentIndexChanged.connect(self.mode_changed)
        mode_label = label("Ausführungsmodus")
        mode_label.setBuddy(self.mode)
        layout.addWidget(mode_label)
        layout.addWidget(self.mode)
        demo_devices = QHBoxLayout()
        demo_devices.addWidget(button("Freigabe simulieren", self.pair_peer, "devices"))
        demo_devices.addWidget(button("Trennen simulieren", self.disconnect_peer, "devices"))
        layout.addLayout(demo_devices)
        self.limit = QSpinBox()
        self.limit.setRange(1, 24)
        self.limit.setValue(16)
        self.limit.setSuffix(" GiB")
        caption = label("Geplantes RAM-Limit für Windows (Demo)")
        caption.setBuddy(self.limit)
        self.limit.setAccessibleName("Geplantes RAM-Limit, nur Demo")
        layout.addWidget(caption)
        layout.addWidget(self.limit)
        self.session_status = label("", "banner")
        layout.addWidget(self.session_status)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Beispiel: Erkläre verteilte Inferenz.")
        self.prompt.setMinimumHeight(100)
        self.prompt.setMaximumHeight(160)
        self.prompt.setAccessibleName("Nachricht für die Demo; wird nicht verarbeitet")
        self.prompt.textChanged.connect(self.refresh)
        layout.addWidget(self.prompt)
        actions = QHBoxLayout()
        self.start = button("Demo-Sitzung starten", self.start_session, "player-play", True)
        self.stop = button("Sitzung stoppen", self.stop_session, "player-stop")
        actions.addWidget(self.start)
        actions.addWidget(self.stop)
        layout.addLayout(actions)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName("Simulierter Sitzungsverlauf")
        self.output.setMinimumHeight(150)
        layout.addWidget(self.output)
        self.error_button = button("Speicherfehler simulieren", self.fail_session, "alert-triangle")
        layout.addWidget(self.error_button)
        layout.addWidget(label("TTFT: Nicht gemessen · Tokens/s: Nicht gemessen · Beteiligung beider Geräte: Nicht nachgewiesen", "subtitle"))

    def about(self):
        layout = self.page("Über Nexus.", "Desktop-Demo und lokaler Modelltest")
        self.panel(layout, "Darstellung", "Dunkelblau #173B70 · Eckige Komponenten · Satoshi lokal\nTabler Icons Outline v3.35.0 · MIT")
        layout.addWidget(button("Tabler-Lizenz anzeigen", self.show_license, "settings"))
        self.panel(layout, "Daten", "‚Lokales Modell‘ verarbeitet Eingaben offline. ‚Geräte verbinden‘ tauscht Modellstatus und optionale Bezugsquellen mit dem eingeladenen Gerät im LAN aus.")
        layout.addStretch()

    def show_license(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Tabler Icons · MIT-Lizenz")
        dialog.setText("Tabler Icons — Copyright und Lizenz")
        dialog.setDetailedText((ASSETS / "icons" / "LICENSE").read_text())
        dialog.exec()

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        self.banner.setText({
            2: "LAN · Geräte koppeln und GGUF-Gewichte abgleichen",
            4: "LOKAL · Modelltest auf diesem Gerät",
            5: "INFO · Cedexia Nexus",
        }.get(index, "DEMO · Simulierter Ablauf"))
        for i, nav in enumerate(self.nav):
            nav.setChecked(index == i)

    def check_device(self):
        self.checked = True
        self.refresh()

    def prepare_model(self):
        self.model_ready = True
        self.refresh()

    def pair_peer(self):
        self.paired = True
        self.refresh()

    def disconnect_peer(self):
        self.paired = False
        if self.running and self.mode.currentIndex() == 1:
            self.finish("Fehler (simuliert): Zweites Gerät getrennt. Erneut freigeben und Sitzung manuell starten.")
        self.refresh()

    def mode_changed(self):
        self.refresh()

    def blockers(self):
        missing = []
        if not self.checked:
            missing.append("Geräteprüfung simulieren")
        if not self.model_ready:
            missing.append("Modellprüfung simulieren")
        if self.mode.currentIndex() == 1 and not self.paired:
            missing.append("zweites Gerät in der Demo freigeben")
        if not self.prompt.toPlainText().strip():
            missing.append("eine Nachricht eingeben")
        return missing

    def refresh(self):
        self.summary.setText(f"Geräteprüfung: {'simuliert' if self.checked else 'ausstehend'}\n"
                             f"Zweites Gerät: {'Freigabe simuliert' if self.paired else 'nicht freigegeben'}\n"
                             f"Modell: {'Prüfung simuliert' if self.model_ready else 'nicht vorbereitet'}")
        self.setup_status.setText("Prüfung simuliert. Keine realen Hardwarewerte erhoben." if self.checked else "Noch nicht geprüft")
        self.model_status.setText("Demo-Modell vorbereitet. Keine Datei geladen oder geprüft." if self.model_ready else "Kein Demo-Modell vorbereitet")
        missing = self.blockers()
        self.start.setEnabled(not missing and not self.running)
        self.stop.setEnabled(self.running)
        self.error_button.setEnabled(self.running)
        self.mode.setEnabled(not self.running)
        self.prompt.setReadOnly(self.running)
        self.session_status.setText("Demo läuft · feste Beispielausgabe" if self.running else
                                    ("Zum Start: " + "; ".join(missing) if missing else "Bereit für eine simulierte Sitzung"))

    def start_session(self):
        if self.running or self.blockers():
            return
        self.running = True
        self.step = 0
        self.output.setPlainText("DEMO — keine Modellantwort.\nSitzung wird vorbereitet …")
        self.timer.start()
        self.refresh()

    def tick(self):
        lines = ["Beispiel: Ein lokales Modell kann Rechenschritte auf mehrere Geräte verteilen.",
                 "Dafür müssen Backend, Modell und Verbindung zusammenpassen.",
                 "Diese UI simuliert nur den Ablauf; sie berechnet keine Antwort."]
        if self.step < len(lines):
            self.output.appendPlainText(lines[self.step])
            self.step += 1
        else:
            self.finish("Demo abgeschlossen. Keine Inferenzmesswerte vorhanden.")

    def finish(self, message):
        self.timer.stop()
        self.running = False
        self.output.appendPlainText(message)
        self.refresh()

    def stop_session(self):
        if self.running:
            self.finish("Demo gestoppt. Eingabe bleibt für einen manuellen Neustart erhalten.")

    def fail_session(self):
        if self.running:
            self.finish("Fehler (simuliert): Speicher reicht nicht. Modell oder Ressourcenbudget prüfen und manuell erneut starten.")

    def closeEvent(self, event):
        self.timer.stop()
        if self.local_model.runner.busy or self.pairing.busy:
            self.closing = True
            event.ignore()
            self.pairing.close_session()
            self.local_model.runner.stop("Fenster geschlossen; lokaler Prozess beendet.")
            return
        super().closeEvent(event)

    def finish_closing(self, *_):
        if self.closing and not self.pairing.busy and not self.local_model.runner.busy:
            self.close()


def make_application():
    app = QApplication.instance() or QApplication(sys.argv)
    loaded = []
    for path in sorted((ASSETS / "fonts").glob("Satoshi-*.otf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    if loaded:
        app.setFont(QFont(loaded[0], 11))
    app.setStyleSheet(STYLE)
    return app, bool(loaded)


def main(smoke=False):
    app, font_loaded = make_application()
    if smoke:
        host_context()
        from mcp import Client
        Client('https://example.invalid/mcp')
    from .workspace import Workspace
    window = Workspace()
    if smoke and getattr(sys, 'frozen', False):
        import subprocess
        subprocess.run([str(window.runner.runtime), '--version'], check=True, timeout=30)
    window.show()
    if smoke:
        QTimer.singleShot(100, app.quit)
    sys.exit(app.exec())
