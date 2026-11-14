"""Persistence and runtime integration of the desktop chat entry point."""
import os
from pathlib import Path
import json
import tempfile
import time
import unittest
from unicodedata import normalize
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from nexus_ui.app import make_application
    from nexus_ui.workspace import Workspace, ChatStore
    from nexus_ui.model_settings import ModelSettings
    from test_local_model import FixtureRunner
except ModuleNotFoundError as exc:
    if exc.name != 'PySide6':
        raise
    Workspace = None


@unittest.skipIf(Workspace is None, 'Install requirements-ui.txt')
class WorkspaceTests(unittest.TestCase):
    def close_workspace(self, window):
        window.close()
        deadline = time.monotonic() + 5
        while window.runner.busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(window.runner.busy)

    def test_model_library_settings_are_independent_from_chat_selection(self):
        make_application()
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('local_model_paths', [])
        settings.setValue('context', 6144)
        with patch('nexus_ui.local_model.QSettings', return_value=settings):
            runner = FixtureRunner()
            first, second = root / 'a' / 'model.gguf', root / 'b' / 'model.gguf'
            runner.select_model(first)
            runner.add_models([second])
            window = Workspace(runner, root / 'chats.db')
            self.addCleanup(self.close_workspace, window)
            window.open_settings('Modelle')
            panel = window.preferences.findChild(ModelSettings)
            self.assertEqual(panel.library.count(), 2)
            panel.select_path(second)
            self.assertEqual(panel.path.text(), str(second))
            self.assertEqual(runner.model, first)
            self.assertEqual(panel.fields['context'].value(), 6144)
            panel.fields['context'].setValue(2048)
            panel.fields['reasoning'].setChecked(True)
            self.assertEqual(runner.model_setting(first, 'context'), 6144)
            restarted = FixtureRunner()
            restarted.select_model(second)
            _, args = restarted._runtime_command()
            self.assertEqual(args[args.index('--ctx-size') + 1], '2048')
            self.assertEqual(args[args.index('--reasoning') + 1], 'on')
            panel.remove.click()
            self.assertEqual(runner.models, [str(first)])
            self.assertEqual(runner.model, first)

    def test_thinking_is_collapsed_across_streaming_and_restart(self):
        app, _ = make_application()
        path = Path(self.enterContext(tempfile.TemporaryDirectory()))
        settings = QSettings(str(path / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('nexus_ui.local_model.QSettings', return_value=settings):
            runner = FixtureRunner()
        runner.verify_code = 'print(\'{"header_ok":true,"thinking_prefilled":true}\')'
        runner.generate_code = (
            'import sys,time; sys.stdin.read(); '
            'raw="Gr\\u00fc\\u00dfe </think>\\n\\n```html\\n<main>Restaurant</main>\\n``` [end of text]\\n".encode(); '
            'sys.stdout.buffer.write(raw[:3]); sys.stdout.flush(); time.sleep(.15); '
            'sys.stdout.buffer.write(raw[3:9]); sys.stdout.flush(); time.sleep(.15); '
            'sys.stdout.buffer.write(raw[9:]); sys.stdout.flush()'
        )
        window = Workspace(runner, path / 'chats.db')
        self.addCleanup(self.close_workspace, window)
        window.show()
        window.prompt.setPlainText('Baue eine Restaurant-Website.')
        window.submit()
        deadline = time.monotonic() + 5
        while runner.busy and time.monotonic() < deadline:
            app.processEvents()
            if window.stream and '</think>' not in ''.join(window.stream):
                self.assertEqual(window.transcript.rows[-1].answer.toPlainText(), '')
            time.sleep(.01)
        self.assertFalse(runner.busy)
        row = window.transcript.rows[-1]
        self.assertIn('<main>Restaurant</main>', row.answer.toPlainText())
        self.assertTrue(row.thinking.isHidden())
        QTest.keyClick(row.toggle, Qt.Key.Key_Space)
        self.assertFalse(row.thinking.isHidden())
        self.assertEqual(normalize('NFC', row.thinking.toPlainText()), 'Grüße')
        row.copy_actions.itemAt(0).widget().click()
        self.assertEqual(QApplication.clipboard().text(), '<main>Restaurant</main>\n')
        window.copy_answer()
        self.assertNotIn('Grüße', QApplication.clipboard().text())
        stored = window.store.db.execute('SELECT messages FROM chats WHERE id=?', (window.chat_id,)).fetchone()
        self.assertEqual(json.loads(stored[0])[-1]['thinking'], 'Grüße')
        window.load_chat(window.chat_id)
        self.assertTrue(window.transcript.rows[-1].thinking.isHidden())
        window.create_chat()
        self.assertEqual(window.transcript.rows, [])

    def test_chat_survives_restart_and_streams_to_selected_chat(self):
        app, _ = make_application()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = QSettings(str(path / 'settings.ini'), QSettings.Format.IniFormat)
            with patch('nexus_ui.local_model.QSettings', return_value=settings):
                runner = FixtureRunner()
            window = Workspace(runner, str(path / 'chats.db'))
            window.create_chat()
            identifier = window.chat_id
            skill = window.integrations.save_skill(None, 'Testskill', 'Nutze das Wort Nexus.')
            window.activate_integration('skills', skill, True)
            self.assertFalse(hasattr(window, 'import_model'))
            window.prompt.setPlainText('Hallo Welt')
            window.send.click()
            self.assertFalse(window.tree.isEnabled())
            deadline = time.monotonic() + 5
            while runner.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            self.assertFalse(runner.busy)
            self.assertIn('Hallo Welt', window.messages[-1]['text'])
            self.assertIn('Nutze das Wort Nexus.', window.messages[-1]['text'])
            window.open_settings()
            window.multi_mode.setChecked(True)
            self.assertFalse(window.add_device.isHidden())
            window.prompt.setPlainText('Test')
            self.assertFalse(window.send.isEnabled())
            window.close()
            restored = ChatStore(path / 'chats.db')
            row = restored.db.execute('SELECT messages FROM chats WHERE id=?', (identifier,)).fetchone()
            self.assertIn('Hallo Welt', row[0])
            restored.db.close()
            window.deleteLater()
            app.processEvents()
