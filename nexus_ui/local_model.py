"""NX-042: asynchronous, single-process local inference; no server or shell."""
import codecs
import json
import os
from pathlib import Path
import platform
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit


ROOT = Path(__file__).resolve().parents[1]


class LocalRunner(QObject):
    status = Signal(str)
    output = Signal(str)
    finished = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None, root=ROOT, timeout_ms=1800000):
        super().__init__(parent)
        self.root = Path(root)
        self.runtime = self.root / "local/build/llama-metal/bin/llama-completion"
        self.model = self.root / "models/Qwen3.8-27B-Q4_K_M.gguf"
        self.manifest = self.root / "config/model-manifest.json"
        self.busy = False
        self.process = None
        self.phase = ""
        self.stop_reason = ""
        self.prompt = ""
        self.received = 0
        self.proof = bytearray()
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(timeout_ms)
        self.timer.timeout.connect(lambda: self.stop("Zeitlimit erreicht. Lauf beendet; bitte erneut versuchen."))

    def unavailable_reason(self):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return "Lokale Inferenz ist bisher nur auf macOS mit Apple Silicon geprüft."
        if not self.runtime.is_file() or not os.access(self.runtime, os.X_OK):
            return "Lokale Runtime fehlt. Zuerst den Metal-Build aus NX-005 einrichten."
        try:
            manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
            expected = manifest["artifact"]["size_bytes"]
            if self.model.stat().st_size != expected:
                return "Die Modelldatei ist unvollständig oder hat die falsche Größe."
        except (OSError, ValueError, KeyError, TypeError):
            return "Modelldatei oder Modellmanifest fehlt bzw. ist nicht lesbar."
        return ""

    def start(self, prompt):
        if self.busy:
            return False
        reason = self.unavailable_reason()
        if reason or not prompt.strip() or len(prompt) > 12000:
            self.status.emit(reason or "Bitte eine Aufgabe mit höchstens 12000 Zeichen eingeben.")
            return False
        self.busy = True
        self.stop_reason = ""
        self.prompt = prompt
        self.received = 0
        self.proof.clear()
        self.decoder.reset()
        self.busy_changed.emit(True)
        self.status.emit("Modelldatei wird geprüft … Die Oberfläche bleibt bedienbar.")
        self.timer.start()
        self._spawn("verify", sys.executable, [
            "-m", "scripts.verify_model", str(self.model), "--manifest", str(self.manifest),
        ])
        return True

    def _runtime_command(self):
        return str(self.runtime), [
            "--model", str(self.model), "--offline", "--device", "MTL0",
            "--n-gpu-layers", "all", "--fit", "off", "--ctx-size", "16384",
            "--batch-size", "128", "--ubatch-size", "128", "--threads", "4",
            "--predict", "8192", "--seed", "42", "--temp", "0", "--jinja",
            "--conversation", "--single-turn", "--reasoning", "off",
            "--no-display-prompt", "--color", "off", "--file", "/dev/stdin",
        ]

    def _spawn(self, phase, program, arguments):
        self.phase = phase
        proc = QProcess(self)
        self.process = proc
        proc.setWorkingDirectory(str(self.root))
        env = QProcessEnvironment.systemEnvironment()
        for key in env.keys():
            if key.startswith("LLAMA_"):
                env.remove(key)
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        proc.setProgram(program)
        proc.setArguments(arguments)
        proc.readyReadStandardOutput.connect(lambda: self._read_output(proc))
        # Drain logs, but never display or retain raw runtime paths or prompts.
        proc.readyReadStandardError.connect(lambda: proc.readAllStandardError())
        proc.started.connect(lambda: self._started(proc))
        proc.errorOccurred.connect(lambda error: self._error(proc, error))
        proc.finished.connect(lambda code, status: self._exited(proc, code, status))
        proc.start()

    def _started(self, proc):
        if proc is not self.process:
            return
        if self.stop_reason:
            proc.kill()
        elif self.phase == "generate":
            # Prompt travels through stdin, not shell/argv, files or logs.
            proc.write(self.prompt.encode("utf-8"))
            proc.closeWriteChannel()
            self.prompt = ""
        else:
            proc.closeWriteChannel()

    def _read_output(self, proc):
        data = bytes(proc.readAllStandardOutput())
        if proc is not self.process or self.stop_reason:
            return
        if self.phase == "verify":
            if len(self.proof) + len(data) > 8192:
                self.stop("Modellprüfung lieferte eine ungültige Antwort.")
            else:
                self.proof.extend(data)
        else:
            self.received += len(data)
            if self.received > 1024 * 1024:
                self.stop("Ausgabelimit erreicht. Lauf beendet.")
                return
            self.status.emit("Lokale Antwort läuft …")
            self.output.emit(self.decoder.decode(data))

    def _error(self, proc, error):
        if proc is self.process and error == QProcess.ProcessError.FailedToStart:
            self._dispose(proc)
            self._finish(self.stop_reason or "Lokaler Prozess konnte nicht starten. Build und Zugriffsrechte prüfen.")

    def _dispose(self, proc):
        self.process = None
        proc.deleteLater()

    def _exited(self, proc, code, status):
        if proc is not self.process:
            return
        self._read_output(proc)
        proc.readAllStandardError()
        self._dispose(proc)
        if self.stop_reason:
            self._finish(self.stop_reason)
        elif self.phase == "verify":
            try:
                valid = code == 0 and json.loads(self.proof).get("verified") is True
            except (ValueError, AttributeError):
                valid = False
            self.proof.clear()
            if not valid:
                self._finish("Modellprüfung fehlgeschlagen. Datei und SHA-256 prüfen; es wurde keine Inferenz gestartet.")
            else:
                self.status.emit("Modell wird auf diesem Mac geladen …")
                self._spawn("generate", *self._runtime_command())
        elif code != 0 or status != QProcess.ExitStatus.NormalExit:
            self._finish("Lokaler Modelllauf fehlgeschlagen. Freien Speicher, kurze Eingabe und Metal-Build prüfen.")
        else:
            self.output.emit(self.decoder.decode(b"", final=True))
            self._finish("Lokaler Lauf beendet · maximal 8192 Ausgabetokens." if self.received else
                         "Der lokale Lauf endete ohne Ausgabe.")

    def stop(self, reason="Gestoppt. Eingabe bleibt für einen manuellen Neustart erhalten."):
        if not self.busy or self.stop_reason:
            return
        self.stop_reason = reason
        self.status.emit("Lokaler Prozess wird beendet …")
        if self.process is not None:
            self.process.kill()
        else:
            self._finish(reason)

    def _finish(self, message):
        if not self.busy:
            return
        self.timer.stop()
        self.prompt = ""
        self.proof.clear()
        self.busy = False
        self.busy_changed.emit(False)
        self.status.emit(message)
        self.finished.emit(message)


class LocalModelPage(QWidget):
    def __init__(self, parent=None, runner=None):
        super().__init__(parent)
        self.runner = runner or LocalRunner(self)
        layout = QVBoxLayout(self)
        heading = QLabel("Dein Modell. Auf diesem Mac.")
        heading.setObjectName("title")
        layout.addWidget(heading)
        description = QLabel("Qwen3.8-27B · Echte lokale Textgenerierung · Keine Verbindung zu anderen Geräten")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel(self.runner.unavailable_reason() or "Bereit. Die Modelldatei wird vor jedem Start geprüft.")
        self.status.setObjectName("banner")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Zum Beispiel: Baue mir eine kleine HTML-Website für ein Restaurant …")
        self.prompt.setAccessibleName("Frage an das lokale Modell")
        self.prompt.setMaximumHeight(150)
        layout.addWidget(self.prompt)
        actions = QHBoxLayout()
        self.start = QPushButton("Lokal starten")
        self.start.setProperty("primary", True)
        self.stop = QPushButton("Stoppen")
        actions.addWidget(self.start)
        actions.addWidget(self.stop)
        layout.addLayout(actions)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName("Echte lokale Modellausgabe, einschließlich möglichem Denktext")
        layout.addWidget(self.output, 1)
        hint = QLabel("Einzelne Aufgaben ohne Gesprächsverlauf · 16384 Kontexttokens · maximal 8192 Ausgabetokens\n"
                      "Bis 12000 Eingabezeichen · Zeitlimit 30 Minuten einschließlich Modellprüfung\n"
                      "Längere Antworten können abbrechen. Denktext kann sichtbar sein. Eingaben und Antworten werden nicht gespeichert.")
        hint.setWordWrap(True)
        hint.setObjectName("subtitle")
        layout.addWidget(hint)
        self.prompt.textChanged.connect(self.refresh)
        self.start.clicked.connect(self.start_run)
        self.stop.clicked.connect(lambda: self.runner.stop())
        self.runner.busy_changed.connect(self.refresh)
        self.runner.status.connect(self.status.setText)
        self.runner.output.connect(self.append_output)
        self.refresh()

    def refresh(self, *_):
        self.start.setEnabled(not self.runner.busy and bool(self.prompt.toPlainText().strip())
                              and not self.runner.unavailable_reason())
        self.stop.setEnabled(self.runner.busy)
        self.prompt.setReadOnly(self.runner.busy)

    def start_run(self):
        if self.runner.busy:
            return
        self.output.clear()
        self.runner.start(self.prompt.toPlainText())

    def append_output(self, text):
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()
