"""NX-067: destructive actions, permission boundaries, attachments and preference persistence."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QPdfWriter, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from nexus_ui.app import make_application
    from nexus_ui.workspace import Workspace
    from nexus_ui.attachments import read_attachment, attachment_context, MAX_BYTES
    from nexus_ui.command_access import review_allows
    from nexus_ui.chat_output import split_reply
    from nexus_ui.i18n import set_language
    from test_local_model import FixtureRunner
except ModuleNotFoundError as exc:
    if exc.name != 'PySide6':
        raise
    Workspace = None


@unittest.skipIf(Workspace is None, 'Install requirements-ui.txt')
class QualityOfLifeTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_application()
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        self.settings.setValue('local_model_paths', [])
        with patch('nexus_ui.local_model.QSettings', return_value=self.settings):
            self.runner = FixtureRunner()
        self.window = Workspace(self.runner, self.root / 'chats.db')
        self.addCleanup(self.finish)

    def finish(self):
        self.window.close()
        self.wait_until(lambda: not self.runner.busy and not self.window.terminal.process)
        self.window.close()
        set_language('de')

    def wait_until(self, condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(condition())

    def test_project_deletion_confirm_cancel_cascade_and_other_project(self):
        w = self.window
        w.create_chat()
        project = w.tree.topLevelItem(0)
        identifier = project.data(0, Qt.ItemDataRole.UserRole)[1]
        skill = w.integrations.save_skill(None, 'Test', 'Test')
        w.activate_integration('skills', skill, True)
        other = w.store.project('Keep')
        kept = w.store.chat(other)
        w.tree.setCurrentItem(project)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            w.remove_selected()
        self.assertEqual(w.store.db.execute('SELECT count(*) FROM projects').fetchone()[0], 2)
        self.runner.external_busy = True
        with patch.object(QMessageBox, 'question') as question:
            w.remove_selected()
            question.assert_not_called()
        self.runner.external_busy = False
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            w.remove_selected()
        self.assertIsNone(w.chat_id)
        self.assertFalse(w.store.db.execute('SELECT 1 FROM projects WHERE id=?', (identifier,)).fetchone())
        self.assertTrue(w.store.db.execute('SELECT 1 FROM chats WHERE id=?', (kept,)).fetchone())
        self.assertEqual(w.store.db.execute('SELECT count(*) FROM chat_integrations').fetchone()[0], 0)
        self.assertEqual(len(w.integrations.skills()), 1)

    def test_default_model_applies_on_new_chat_and_restart_and_can_be_removed(self):
        first, second = self.root / 'one.gguf', self.root / 'two.gguf'
        self.runner.select_model(first)
        self.runner.add_models([second])
        self.runner.set_default_model(second)
        self.assertEqual(self.runner.model, first)
        self.window.create_chat()
        self.assertEqual(self.runner.model, second)
        self.runner.select_model(first)
        with patch('nexus_ui.local_model.QSettings', return_value=self.settings):
            restarted = FixtureRunner()
        self.assertEqual(restarted.model, second)
        self.runner.remove_model(second)
        self.assertFalse(self.settings.contains('default_model_path'))
        self.assertEqual(self.runner.model, first)

    def test_text_pdf_binary_and_attachment_history(self):
        file = self.root / 'note.txt'
        file.write_text('Attachment fact: the restaurant is called Linden.', encoding='utf-8')
        item = read_attachment(file)
        pdf = self.root / 'document.pdf'
        writer = QPdfWriter(str(pdf))
        painter = QPainter(writer)
        painter.drawText(100, 1000, 'PDF attachment fact')
        painter.end()
        del writer
        self.assertIn('PDF attachment fact', read_attachment(pdf)['text'])
        image = self.root / 'example.png'
        image.write_bytes(b'not a decoded image')
        binary = read_attachment(image)
        self.assertEqual(binary['text'], '')
        self.assertIn('nicht analysieren', attachment_context([binary]))
        self.window.attachments = [item]
        self.window.prompt.setPlainText('What is its name?')
        self.window.submit()
        self.wait_until(lambda: not self.runner.busy)
        self.assertIn('Linden', self.window.messages[-1]['text'])
        chat = self.window.chat_id
        self.window.load_chat(chat)
        self.assertEqual(self.window.messages[0]['attachments'][0]['text'], item['text'])
        self.assertEqual(self.window.attachments, [])
        file.write_bytes(b'\x00binary')
        with self.assertRaises(ValueError):
            read_attachment(file)
        with file.open('wb') as output:
            output.truncate(MAX_BYTES + 1)
        with self.assertRaises(ValueError):
            read_attachment(file)

    def test_attachment_loading_locks_chat_until_finished(self):
        file = self.root / 'note.txt'
        file.write_text('Hello')
        self.window.create_chat()
        chat = self.window.chat_id
        with patch('nexus_ui.workspace.QFileDialog.getOpenFileNames', return_value=([str(file)], '')):
            self.window.attach_files()
        self.window.create_chat()
        self.assertEqual(chat, self.window.chat_id)
        self.wait_until(lambda: self.window.attachment_reader is None)
        self.assertEqual(self.window.attachments[0]['text'], 'Hello')

    def test_off_ask_and_auto_control_real_terminal_execution(self):
        w = self.window
        w.open_terminal()
        terminal = w.terminal
        terminal.command.setPlainText('echo NEXUS_COMMAND_TEST')
        terminal.directory.setText(str(self.root))
        for mode in ('off', 'ask'):
            w.set_permission_mode(mode)
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.No):
                terminal.run_command()
            self.assertIsNone(terminal.process)
            self.assertEqual(terminal.output.toPlainText(), '')
        w.set_permission_mode('auto')
        terminal.run_command()
        self.assertIsNotNone(terminal.process)
        self.wait_until(lambda: terminal.process is None)
        self.assertIn('NEXUS_COMMAND_TEST', terminal.output.toPlainText())
        self.assertIn('0', terminal.status.text())

    def test_agent_review_requires_strict_successful_verdict_and_no_chat_message(self):
        w = self.window
        w.set_permission_mode('agent')
        for answer, allowed in (('{"allow":true}', True), ('{"allow":1}', False),
                                ('{"allow":true,"extra":0}', False), ('maybe', False), ('{"allow":false}', False)):
            self.assertEqual(review_allows(answer), allowed)
            self.runner.generate_code = 'import sys; sys.stdin.read(); print(' + repr(answer + ' [end of text]') + ')'
            result = []
            w.authorize_command({'kind': 'terminal', 'command': 'echo hello'}, result.append)
            self.wait_until(lambda: bool(result))
            self.assertEqual(result, [allowed])
            self.assertEqual(w.messages, [])
        self.runner.generate_code = 'import time; time.sleep(30)'
        result = []
        w.authorize_command({'kind': 'terminal', 'command': 'echo hello'}, result.append)
        w.stop_run()
        self.wait_until(lambda: bool(result))
        self.assertEqual(result, [False])

    def test_language_sidebar_and_response_copy(self):
        w = self.window
        w.show()
        w.open_settings()
        w.language.setCurrentIndex(w.language.findData('en'))
        self.assertEqual(w.send.text(), 'Send')
        self.assertEqual(w.settings_button.text(), 'Settings')
        self.assertEqual(w.settings_navigation.item(0).text(), 'General')
        self.assertEqual(self.settings.value('app_language'), 'en')
        w.messages = [{'role': 'assistant', 'text': 'Final', 'thinking': 'Private draft'}]
        w.render()
        row = w.transcript.rows[-1]
        self.assertTrue(row.thinking.isHidden())
        row.copy_reply.click()
        self.assertEqual(QApplication.clipboard().text(), 'Final')
        w.toggle_sidebar()
        QTest.qWait(230)
        self.assertEqual(w.sidebar.width(), 0)
        w.toggle_sidebar()
        QTest.qWait(230)
        self.assertEqual(w.sidebar.width(), 230)
        w.language.setCurrentIndex(w.language.findData('de'))
        self.assertEqual(w.send.text(), 'Senden')

    def test_ministral_thinking_hidden_at_all_stream_boundaries(self):
        stream = '[THINK]Plan privately[/THINK]Final answer</s>'
        for index in range(len(stream) + 1):
            reply = split_reply(stream[:index])
            self.assertNotIn('privately', reply.answer)
            if index <= stream.index('Final'):
                self.assertEqual(reply.answer, '')
        self.assertEqual(split_reply(stream, complete=True).answer, 'Final answer')
        literal = '`[THINK]`\n```text\n[/THINK]\n```'
        self.assertEqual(split_reply(literal).answer, literal)
