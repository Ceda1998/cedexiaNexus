"""NX-042: asynchronous, single-process local inference; no server or shell."""
import codecs
import json
import os
from pathlib import Path
import platform
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QComboBox, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit


ROOT = Path(__file__).resolve().parents[1]
VERIFY_FLAG = "--verify-local-model"
GGUF_ERRORS = {
    "not_gguf": "Die Datei ist kein GGUF-Modell.",
    "truncated": "Die GGUF-Datei ist unvollständig.",
    "unsupported_version": "Diese GGUF-Version wird von der Runtime nicht unterstützt.",
    "no_tensors": "Diese GGUF-Datei enthält keine Modellgewichte.",
    "missing_or_unreadable": "Die GGUF-Datei fehlt oder ist nicht lesbar.",
}


def windows_prompt(prompt):
    # Completion's Windows console reads one line, then decodes its escapes.
    return (prompt.replace("\\", r"\x5c").replace("/", r"\x2f")
            .replace("\r", r"\r").replace("\n", r"\n") + "\n").encode("utf-8")


class LocalRunner(QObject):
    status = Signal(str)
    output = Signal(str)
    finished = Signal(str)
    busy_changed = Signal(bool)
    model_changed = Signal()

    def __init__(self, parent=None, root=ROOT, timeout_ms=1800000):
        super().__init__(parent)
        self.root = Path(root)
        self.windows = platform.system() == "Windows"
        self.frozen = getattr(sys, "frozen", False)
        self.settings = QSettings("Cedexia", "Nexus")
        if self.windows:
            runtime_dir = self.root / "runtime" if self.frozen else self.root / "local/build/llama-cuda/bin"
            self.runtime = runtime_dir / "llama-completion.exe"
            model_dir = Path(sys.executable).parent if self.frozen else self.root
        else:
            runtime_dir = self.root / "runtime" if self.frozen else self.root / "local/build/llama-metal/bin"
            self.runtime = runtime_dir / "llama-completion"
            model_dir = self.root
        self.models = list(dict.fromkeys(self.settings.value("local_model_paths", [], type=list)))
        saved_model = self.settings.value("local_model_path", "", type=str)
        if saved_model and saved_model not in self.models:
            self.models.append(saved_model)
        default_model = model_dir / "models/Qwen3.8-27B-Q4_K_M.gguf"
        if not self.settings.contains("local_model_paths") and not self.models and default_model.is_file():
            self.models.append(str(default_model))
        self.model = Path(saved_model or self.models[0]) if self.models else None
        self.busy = False
        self.process = None
        self.phase = ""
        self.stop_reason = ""
        self.prompt = ""
        self.received = 0
        self.proof = bytearray()
        self.diagnostics = bytearray()
        self.thinking_prefilled = False
        self.output_tail = ""
        self.input_truncated = False
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(timeout_ms)
        self.timer.timeout.connect(lambda: self.stop("Zeitlimit erreicht. Lauf beendet; bitte erneut versuchen."))

    def unavailable_reason(self):
        if self.windows:
            if platform.machine().upper() not in ("AMD64", "X86_64"):
                return "Das CUDA-Paket benötigt Windows x64."
        elif platform.system() != "Darwin" or platform.machine() != "arm64":
            return "Lokale Inferenz ist für macOS mit Apple Silicon oder Windows x64 vorgesehen."
        if not self.runtime.is_file() or not os.access(self.runtime, os.X_OK):
            if self.windows:
                return "CUDA-Runtime fehlt. Entpacke das vollständige Windows-Paket."
            return "Lokale Runtime fehlt. Installiere die App erneut oder richte den Metal-Build aus NX-005 ein."
        if self.windows and self.frozen and not self.runtime.with_name("libomp.dll").is_file():
            return "Die Windows-Runtime ist unvollständig: libomp.dll fehlt. Installiere Cedexia Nexus erneut."
        if self.model is None:
            return "Füge eine lokale GGUF-Datei hinzu."
        if not self.model.is_file():
            return "Diese Modelldatei fehlt. Wähle eine vorhandene GGUF-Datei aus."
        return ""

    def select_model(self, path):
        if not self.busy:
            previous = self.model
            path = str(Path(path).absolute()) if path else ""
            if path and path not in self.models:
                self.models.append(path)
            self.model = Path(path) if path else None
            self.settings.setValue("local_model_paths", self.models)
            self.settings.setValue("local_model_path", path)
            if self.model != previous:
                self.model_changed.emit()

    def remove_model(self):
        if not self.busy and self.model is not None:
            self.models.remove(str(self.model))
            self.select_model(self.models[0] if self.models else "")

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
        self.diagnostics.clear()
        self.thinking_prefilled = False
        self.output_tail = ""
        self.input_truncated = False
        self.decoder.reset()
        self.busy_changed.emit(True)
        self.status.emit("Modelldatei wird geprüft … Die Oberfläche bleibt bedienbar.")
        self.timer.start()
        self._spawn("verify", sys.executable, [*self.verifier_arguments("--gguf"), "--chat-format"])
        return True

    def verifier_arguments(self, mode):
        entry = [VERIFY_FLAG] if self.frozen else ["-m", "scripts.verify_model"]
        return [*entry, str(self.model), mode]

    def _runtime_command(self):
        device, layers, context, predict = (
            ("CUDA0", "auto", "4096", "-2") if self.windows else ("MTL0", "all", "16384", "8192")
        )
        fit = "on" if self.windows else "off"
        if self.windows and self.settings.value("windows_cpu", False, type=bool):
            device, layers, fit = "none", "0", "off"
        input_args = ["--simple-io", "--escape"] if self.windows else ["--file", "/dev/stdin"]
        context = str(self.settings.value("context", int(context), type=int))
        predict = str(self.settings.value("predict", int(predict), type=int))
        reasoning = "on" if self.settings.value("reasoning", False, type=bool) else "off"
        return str(self.runtime), [
            "--model", str(self.model), "--offline", "--device", device,
            "--n-gpu-layers", layers, "--fit", fit, "--ctx-size", context,
            "--batch-size", "128", "--ubatch-size", "128", "--threads", "4",
            "--predict", predict, "--seed", "42", "--temp", "0", "--jinja",
            "--conversation", "--single-turn", "--reasoning", reasoning,
            "--no-display-prompt", "--no-context-shift", "--color", "off", *input_args,
        ]

    def _spawn(self, phase, program, arguments):
        self.phase = phase
        proc = QProcess(self)
        self.process = proc
        proc.setWorkingDirectory(str(self.runtime.parent if self.windows and phase == "generate" else self.root))
        env = QProcessEnvironment.systemEnvironment()
        for key in env.keys():
            if key.startswith(("LLAMA_", "GGML_")):
                env.remove(key)
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        proc.setProgram(program)
        proc.setArguments(arguments)
        proc.readyReadStandardOutput.connect(lambda: self._read_output(proc))
        proc.readyReadStandardError.connect(lambda: self._read_diagnostics(proc))
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
            proc.write(windows_prompt(self.prompt) if self.windows else self.prompt.encode("utf-8"))
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
            chunk = self.decoder.decode(data)
            self.output_tail = (self.output_tail + chunk)[-128:]
            self.output.emit(chunk)

    def _error(self, proc, error):
        if proc is self.process and error == QProcess.ProcessError.FailedToStart:
            self._dispose(proc)
            self._finish(self.stop_reason or "Lokaler Prozess konnte nicht starten. Build und Zugriffsrechte prüfen.")

    def _read_diagnostics(self, proc):
        data = bytes(proc.readAllStandardError())
        if proc is self.process and self.phase == "generate":
            recent = self.diagnostics + data
            self.diagnostics[:] = recent[-8192:]
            if b"input too long: skipped" in recent or b"prompt is too long" in recent:
                self.input_truncated = True
                self.stop("Der Kontext reicht für diese Eingabe nicht aus. Kürze den Verlauf oder erhöhe die Kontextgröße.")

    def _load_error(self):
        log = self.diagnostics.lower()
        if b"unknown model architecture" in log:
            return "Die Architektur dieses GGUF-Modells wird von der gebündelten Runtime nicht unterstützt."
        if any(message in log for message in (b"out of memory", b"failed to allocate", b"bad_alloc")):
            return "Nicht genug freier Speicher. Verkleinere den Kontext oder wähle eine kleinere Quantisierung."
        if self.windows and any(message in log for message in (
            b"invalid device", b"failed to initialize cuda", b"cuda error", b"no kernel image",
        )):
            return ("CUDA konnte das Modell nicht ausführen. Prüfe den NVIDIA-Treiber. "
                    "Zum Gegencheck kannst du unter Einstellungen → Modelle die CPU wählen.")
        if b"failed to open gguf file" in log or b"failed to open file" in log:
            return "Die Runtime konnte eine Modelldatei nicht öffnen. Prüfe Zugriffsrechte und alle Teile einer geteilten GGUF."
        if b"gguf_init_from_file" in log or b"gguf_init_from_reader" in log or b"wrong number of tensors" in log:
            return "Die Runtime konnte die GGUF-Daten nicht lesen. Prüfe, ob der Download vollständig ist."
        if self.windows and b"error loading model" not in log and not self.received:
            return ("Windows-Runtime fehlgeschlagen. Prüfe den NVIDIA-Treiber oder "
                    "teste unter Einstellungen → Modelle mit der CPU.")
        return "Modelllauf fehlgeschlagen, nachdem der GGUF-Dateikopf geprüft wurde."

    def _dispose(self, proc):
        self.process = None
        proc.deleteLater()

    def _exited(self, proc, code, status):
        if proc is not self.process:
            return
        self._read_output(proc)
        self._read_diagnostics(proc)
        self._dispose(proc)
        if self.stop_reason:
            self._finish(self.stop_reason)
        elif self.phase == "verify":
            try:
                proof = json.loads(self.proof)
                valid = code == 0 and proof.get("header_ok") is True
                error = GGUF_ERRORS.get(proof.get("error"))
                self.thinking_prefilled = proof.get("thinking_prefilled") is True
            except (ValueError, AttributeError, TypeError):
                valid, error = False, None
            self.proof.clear()
            if not valid:
                self._finish(error or "Die App konnte die Modellprüfung nicht abschließen. Prüfe den installierten Build.")
            else:
                self.status.emit("Lokales Modell wird geladen …")
                self._spawn("generate", *self._runtime_command())
        elif code != 0 or status != QProcess.ExitStatus.NormalExit:
            self._finish(self._load_error())
        else:
            self.output.emit(self.decoder.decode(b"", final=True))
            if b"context full" in self.diagnostics:
                self._finish("Kontextlimit erreicht. Die Antwort kann abgeschnitten sein.")
            elif not self.received:
                self._finish("Der lokale Lauf endete ohne Ausgabe.")
            elif not self.output_tail.rstrip().endswith("[end of text]"):
                self._finish("Die Ausgabe endete vorzeitig. Die Antwort kann abgeschnitten sein.")
            else:
                self._finish("Lokaler Lauf beendet.")

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
        self.diagnostics.clear()
        self.busy = False
        self.busy_changed.emit(False)
        self.status.emit(message)
        self.finished.emit(message)


class LocalModelPage(QWidget):
    def __init__(self, parent=None, runner=None):
        super().__init__(parent)
        self.runner = runner or LocalRunner(self)
        layout = QVBoxLayout(self)
        heading = QLabel("Dein Modell. Auf diesem PC." if self.runner.windows else "Dein Modell. Auf diesem Mac.")
        heading.setObjectName("title")
        layout.addWidget(heading)
        description = QLabel("Textgenerierung mit lokalen GGUF-Modellen")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel(self.runner.unavailable_reason() or "Bereit. Die Modelldatei wird vor jedem Start geprüft.")
        self.status.setObjectName("banner")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        models = QHBoxLayout()
        self.model_list = QComboBox()
        self.model_list.setAccessibleName("Lokales GGUF-Modell")
        self.model_list.setPlaceholderText("Kein GGUF-Modell ausgewählt")
        models.addWidget(self.model_list, 1)
        self.choose_model = QPushButton("GGUF hinzufügen …")
        self.choose_model.clicked.connect(self.pick_model)
        models.addWidget(self.choose_model)
        self.remove_model = QPushButton("Eintrag entfernen")
        self.remove_model.clicked.connect(self.forget_model)
        models.addWidget(self.remove_model)
        layout.addLayout(models)
        self.model_info = QLabel()
        self.model_info.setTextFormat(Qt.TextFormat.PlainText)
        self.model_info.setWordWrap(True)
        layout.addWidget(self.model_info)
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
        context_hint = ("4096 Kontexttokens für Eingabe und Ausgabe · 32 GPU-Layer (CUDA)"
                        if self.runner.windows else "16384 Kontexttokens · maximal 8192 Ausgabetokens")
        hint = QLabel(f"Einzelne Aufgaben ohne Gesprächsverlauf · {context_hint}\n"
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
        self.update_model_list()
        self.model_list.currentIndexChanged.connect(self.change_model)
        self.update_selection()

    def refresh(self, *_):
        self.start.setEnabled(not self.runner.busy and bool(self.prompt.toPlainText().strip())
                              and not self.runner.unavailable_reason())
        self.stop.setEnabled(self.runner.busy)
        self.prompt.setReadOnly(self.runner.busy)
        self.model_list.setEnabled(not self.runner.busy)
        self.choose_model.setEnabled(not self.runner.busy)
        self.remove_model.setEnabled(not self.runner.busy and self.runner.model is not None)

    def update_model_list(self):
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for path in self.runner.models:
            self.model_list.addItem(Path(path).name, path)
        self.model_list.setCurrentIndex(self.model_list.findData(str(self.runner.model)))
        self.model_list.blockSignals(False)

    def update_model_info(self):
        model = self.runner.model
        if model is None:
            self.model_info.clear()
            return
        try:
            size = model.stat().st_size
        except OSError:
            self.model_info.setText(f"{model.name} · Datei nicht gefunden")
        else:
            self.model_info.setText(f"{model.name} · {size / 1024**3:.2f} GiB")

    def change_model(self, index):
        if index >= 0:
            self.runner.select_model(self.model_list.itemData(index))
            self.update_selection()

    def update_selection(self):
        self.output.clear()
        self.update_model_info()
        self.status.setText(self.runner.unavailable_reason() or "Bereit. Die GGUF-Datei wird beim Start geprüft.")
        self.refresh()

    def forget_model(self):
        self.runner.remove_model()
        self.update_model_list()
        self.update_selection()

    def pick_model(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Lokale GGUF-Modelle hinzufügen", "", "GGUF (*.gguf)")
        if paths:
            for path in paths:
                self.runner.select_model(path)
            self.update_model_list()
            self.update_selection()

    def start_run(self):
        if self.runner.busy:
            return
        self.output.clear()
        self.runner.start(self.prompt.toPlainText())

    def append_output(self, text):
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()
