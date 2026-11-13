"""Real Qt subprocess lifecycle tests with tiny, model-free child processes."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtTest import QTest
    from nexus_ui.app import NexusWindow, make_application
    from nexus_ui.local_model import LocalRunner, LocalModelPage, windows_prompt
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    LocalRunner = None


if LocalRunner is not None:
    class FixtureRunner(LocalRunner):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            # The test child reads raw stdin rather than llama.cpp's Windows console protocol.
            self.windows = False
            self.verify_code = 'print(\'{"header_ok": true}\')'
            self.generate_code = (
                'import sys,time; p=sys.stdin.read(); '
                'sys.stderr.write("PRIVATE_PATH SECRET_LOG\\n"); '
                'prefix="Gr\\u00fc\\u00dfe: ".encode(); '
                'sys.stdout.buffer.write(prefix[:3]); sys.stdout.flush(); '
                'time.sleep(.05); '
                'sys.stdout.buffer.write(prefix[3:]+p.encode()); sys.stdout.flush()'
            )
            self.phases = []
            self.fail_to_start = False

        def unavailable_reason(self):
            return ""

        def _spawn(self, phase, program, arguments):
            self.phases.append(phase)
            if self.fail_to_start:
                return super()._spawn(phase, str(self.root / "missing-test-runtime"), [])
            code = self.verify_code if phase == "verify" else self.generate_code
            super()._spawn(phase, sys.executable, ["-u", "-c", code])


@unittest.skipIf(LocalRunner is None, "Install requirements-ui.txt for Qt tests")
class LocalModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, _ = make_application()

    def setUp(self):
        self.runner = FixtureRunner(timeout_ms=10000)
        self.output = []
        self.results = []
        self.runner.output.connect(self.output.append)
        self.runner.finished.connect(self.results.append)

    def wait(self, predicate, timeout=4000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def tearDown(self):
        if self.runner.busy:
            self.runner.stop()
            self.wait(lambda: not self.runner.busy)
        self.runner.deleteLater()
        self.app.processEvents()

    def test_streaming_unicode_stdin_and_no_raw_logs(self):
        prompt = 'Mehrzeilig\n"$()" & <Test> ä'
        self.assertTrue(self.runner.start(prompt))
        self.wait(lambda: not self.runner.busy)
        self.assertEqual("".join(self.output), "Grüße: " + prompt)
        self.assertEqual(self.runner.phases, ["verify", "generate"])
        self.assertEqual(len(self.results), 1)
        self.assertNotIn("SECRET", str(self.output) + str(self.results))
        self.assertEqual(self.runner.prompt, "")

    def test_invalid_gguf_never_launches_runtime(self):
        self.runner.verify_code = 'print(\'{"header_ok": false, "error": "truncated"}\')'
        self.runner.start("test")
        self.wait(lambda: not self.runner.busy)
        self.assertEqual(self.runner.phases, ["verify"])
        self.assertIn("unvollständig", self.results[0])

    def test_stop_during_verification_and_manual_restart(self):
        self.runner.verify_code = 'import time; time.sleep(30)'
        self.runner.start("test")
        self.assertFalse(self.runner.start("second"))
        self.runner.stop()
        self.wait(lambda: not self.runner.busy)
        self.assertEqual(self.runner.phases, ["verify"])
        self.assertIsNone(self.runner.process)
        self.runner.verify_code = 'print(\'{"header_ok": true}\')'
        self.runner.start("again")
        self.wait(lambda: not self.runner.busy)
        self.assertIn("again", "".join(self.output))

    def test_stop_generation_discards_late_output(self):
        self.runner.generate_code = 'import time; print("first",flush=True); time.sleep(30); print("late")'
        self.runner.start("test")
        self.wait(lambda: bool(self.output))
        self.runner.stop()
        self.wait(lambda: not self.runner.busy)
        previous = "".join(self.output)
        QTest.qWait(100)
        self.assertEqual(previous, "".join(self.output))
        self.assertNotIn("late", previous)
        self.assertIsNone(self.runner.process)

    def test_timeout_and_start_failure_finish_once(self):
        self.runner.timer.setInterval(100)
        self.runner.verify_code = 'import time; time.sleep(30)'
        self.runner.start("test")
        self.wait(lambda: not self.runner.busy)
        self.assertIn("Zeitlimit", self.results[0])
        self.runner.fail_to_start = True
        self.runner.start("test")
        self.wait(lambda: not self.runner.busy)
        self.assertEqual(len(self.results), 2)
        self.assertIn("konnte nicht starten", self.results[-1])

    def test_runtime_failure_does_not_expose_raw_errors(self):
        self.runner.generate_code = 'import sys; sys.stderr.write("SECRET PRIVATE_PATH"); sys.exit(3)'
        self.runner.start("test")
        self.wait(lambda: not self.runner.busy)
        self.assertIn("fehlgeschlagen", self.results[0])
        self.assertNotIn("SECRET", self.results[0])

    def test_window_close_kills_child_and_keeps_ui_responsive(self):
        self.runner.generate_code = 'import time; print("first",flush=True); time.sleep(30)'
        window = NexusWindow(local_runner=self.runner)
        window.show()
        window.navigate(4)
        page = window.local_model
        page.prompt.setPlainText("test")
        page.start.click()
        self.wait(lambda: "first" in page.output.toPlainText())
        self.assertFalse(page.start.isEnabled())
        self.assertTrue(page.stop.isEnabled())
        window.navigate(0)
        self.assertEqual(window.stack.currentIndex(), 0)
        window.close()
        self.wait(lambda: not self.runner.busy and not window.isVisible())
        self.assertEqual(page.prompt.toPlainText(), "test")
        self.assertIsNone(self.runner.process)
        window.deleteLater()

    def test_platform_guard_and_missing_runtime(self):
        real = LocalRunner()
        with patch("nexus_ui.local_model.platform.system", return_value="Linux"):
            real.windows = False
            self.assertIn("macOS", real.unavailable_reason())
            self.assertFalse(real.start("test"))
            self.assertIsNone(real.process)
        with patch("nexus_ui.local_model.platform.system", return_value="Darwin"), patch("nexus_ui.local_model.platform.machine", return_value="arm64"):
            real.runtime = real.root / "missing-test-runtime"
            self.assertIn("Runtime fehlt", real.unavailable_reason())
        real.deleteLater()

    def test_windows_model_selection_persists_and_forgetting_keeps_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
            first, second = root / "Erstes Modell.gguf", root / "Zweites Modell.gguf"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            settings.setValue("local_model_path", str(first))
            with patch("nexus_ui.local_model.QSettings", return_value=settings), \
                 patch("nexus_ui.local_model.platform.system", return_value="Windows"), \
                 patch("nexus_ui.local_model.platform.machine", return_value="AMD64"):
                runner = LocalRunner(root=root)
                runner.runtime = Path(sys.executable)
                page = LocalModelPage(runner=runner)
                self.assertEqual(page.model_list.count(), 1)
                with patch("nexus_ui.local_model.QFileDialog.getOpenFileNames",
                           return_value=([str(first), str(second)], "")):
                    page.choose_model.click()
                self.assertEqual(page.model_list.count(), 2)
                self.assertEqual(runner.model, second)
                page.model_list.setCurrentIndex(0)
                self.assertEqual(runner.model, first)
                with patch.object(runner, "_spawn") as spawn:
                    self.assertTrue(runner.start("Test"))
                    self.assertEqual(spawn.call_args.args[2][-2:], [str(first), "--gguf"])
                    self.assertFalse(page.choose_model.isEnabled())
                    runner.stop()
                page.remove_model.click()
                self.assertTrue(first.is_file())
                self.assertEqual(runner.model, second)
                reloaded = LocalRunner(root=root)
                self.assertEqual(reloaded.models, [str(second)])
                self.assertEqual(reloaded.model, second)
                second.unlink()
                page.prompt.setPlainText("Test")
                self.assertFalse(page.start.isEnabled())
                self.assertIn("Modelldatei fehlt", runner.unavailable_reason())
                page.deleteLater()
                runner.deleteLater()
                reloaded.deleteLater()

    def test_windows_prompt_stays_on_one_line_and_preserves_escapes(self):
        import re

        prompt = 'Grüße\r\nC:\\new\\test\nLiterales \\x2f und URL https://example.test/'
        wire = windows_prompt(prompt).decode("utf-8")
        self.assertEqual(wire.count("\n"), 1)
        self.assertNotIn("/", wire)
        # Decode with the escape sequences supported by the pinned completion binary.
        decoded = re.sub(r"\\(?:x([0-9a-f]{2})|([rn]))",
                         lambda m: chr(int(m[1], 16)) if m[1] else {"r": "\r", "n": "\n"}[m[2]],
                         wire[:-1])
        self.assertEqual(decoded, prompt)
