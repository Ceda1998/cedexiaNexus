"""Persistence and runtime integration of the desktop chat entry point."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings
    from nexus_ui.app import make_application
    from nexus_ui.workspace import Workspace, ChatStore
    from test_local_model import FixtureRunner
except ModuleNotFoundError as exc:
    if exc.name != 'PySide6':
        raise
    Workspace = None


@unittest.skipIf(Workspace is None, 'Install requirements-ui.txt')
class WorkspaceTests(unittest.TestCase):
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
            window.mode.setCurrentIndex(1)
            window.prompt.setPlainText('Test')
            self.assertFalse(window.send.isEnabled())
            window.close()
            restored = ChatStore(path / 'chats.db')
            row = restored.db.execute('SELECT messages FROM chats WHERE id=?', (identifier,)).fetchone()
            self.assertIn('Hallo Welt', row[0])
            restored.db.close()
            window.deleteLater()
            app.processEvents()
