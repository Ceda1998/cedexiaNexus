"""Skill migration and real MCP protocol exchange through a local child process."""
import os
from pathlib import Path
import sys
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings
    from nexus_ui.app import make_application
    from nexus_ui.integrations import IntegrationStore, McpConnection, McpPanel, SkillEditor
    from nexus_ui.workspace import ChatStore
except ModuleNotFoundError as error:
    if error.name != 'PySide6':
        raise
    IntegrationStore = None


@unittest.skipIf(IntegrationStore is None, 'Install requirements-ui.txt')
class IntegrationTests(unittest.TestCase):
    def test_tools_require_chat_activation_and_results_stay_with_chat(self):
        app, _ = make_application()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = QSettings(str(root / 's.ini'), QSettings.Format.IniFormat)
            store = ChatStore(root / 'chats.db')
            chat = [store.chat(store.project('Test'))]
            integrations = IntegrationStore(store.db, settings)
            panel = McpPanel(integrations, lambda: chat[0], lambda: True)
            panel.name.setText('Test server')
            panel.endpoint.setText(sys.executable)
            panel.save()
            identifier = panel.servers.currentData()
            panel.connection = Mock()
            panel.ready([{'name': 'echo', 'input_schema': {'type': 'object', 'properties': {}}}])
            panel.call_tool()
            panel.connection.queue.put.assert_not_called()
            integrations.activate(chat[0], 'mcps', identifier, True)
            panel.call_tool()
            panel.connection.queue.put.assert_called_once_with(('echo', {}))
            panel.result('echo', 'Werkzeugantwort', False)
            contexts = []
            panel.context_ready.connect(contexts.append)
            panel.use_result()
            self.assertIn('Werkzeugantwort', contexts[0])
            integrations.activate(chat[0], 'mcps', identifier, False)
            panel.use_result()
            self.assertEqual(len(contexts), 1)
            chat[0] = store.chat(store.project('Zweiter Chat'))
            integrations.activate(chat[0], 'mcps', identifier, True)
            panel.use_result()
            self.assertEqual(len(contexts), 1)
            panel.disconnected()
            self.assertEqual(panel.output.toPlainText(), '')
            store.db.close()
            panel.deleteLater()
            app.processEvents()

    def test_import_create_edit_and_chat_scoped_activation(self):
        app, _ = make_application()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = QSettings(str(root / 's.ini'), QSettings.Format.IniFormat)
            settings.setValue('skill_text', 'Alte Anweisung')
            store = ChatStore(root / 'chats.db')
            first = store.chat(store.project('Test'))
            integrations = IntegrationStore(store.db, settings)
            self.assertIn('Alte Anweisung', integrations.skill_prompt(first))
            IntegrationStore(store.db, settings)
            self.assertEqual(len(integrations.skills()), 1)
            second = store.chat(store.project('Anderes Projekt'))
            self.assertEqual(integrations.skill_prompt(second), '')
            skill_file = root / 'SKILL.md'
            skill_file.write_text('---\nname: example\n---\n# Test\nAntworte auf Deutsch.', encoding='utf-8')
            editor = SkillEditor(integrations)
            with patch('nexus_ui.integrations.QFileDialog.getOpenFileName', return_value=(str(skill_file), '')):
                editor.import_file()
            identifier = editor.identifier
            integrations.activate(second, 'skills', identifier, True)
            self.assertIn('Antworte auf Deutsch.', integrations.skill_prompt(second))
            editor.editor.setPlainText('# Geändert\nAntworte kurz.')
            editor.save()
            self.assertIn('Antworte kurz.', integrations.skill_prompt(second))
            self.assertNotIn('Antworte kurz.', integrations.skill_prompt(first))
            editor.new()
            editor.name.setText('Neuer Skill')
            editor.editor.setPlainText('Direkt erstellt')
            editor.save()
            integrations.activate(second, 'skills', identifier, False)
            self.assertEqual(integrations.skill_prompt(second), '')
            store.db.close()
            reopened = ChatStore(root / 'chats.db')
            self.assertEqual(len(IntegrationStore(reopened.db, settings).skills()), 3)
            reopened.db.close()
            editor.deleteLater()
            app.processEvents()

    def test_real_stdio_discovery_and_call(self):
        app, _ = make_application()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'server.py'
            script.write_text('from mcp.server import MCPServer\ns = MCPServer("Test")\n@s.tool()\ndef add(a: int, b: int) -> str:\n    return str(a+b)\ns.run()\n', encoding='utf-8')
            worker = McpConnection({'transport': 'stdio', 'command': sys.executable, 'args': [str(script)]})
            tools, results, errors = [], [], []
            worker.tools_ready.connect(tools.extend)
            worker.result.connect(lambda *args: results.append(args))
            worker.problem.connect(errors.append)
            worker.start()
            try:
                self.wait(app, lambda: bool(tools) or bool(errors))
                self.assertEqual(errors, [])
                self.assertEqual(tools[0]['name'], 'add')
                worker.queue.put(('add', {'a': 2, 'b': 3}))
                self.wait(app, lambda: bool(results) or bool(errors))
                self.assertEqual(errors, [])
                self.assertIn('5', results[0][1])
                self.assertFalse(results[0][2])
            finally:
                worker.stop()
                self.wait(app, lambda: not worker.isRunning())
                worker.deleteLater()

    def test_real_streamable_http_discovery_and_call(self):
        app, _ = make_application()
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            script = Path(directory) / 'http_server.py'
            script.write_text('from mcp.server import MCPServer\ns = MCPServer("HTTP Test")\n@s.tool()\ndef greet() -> str:\n    return "hello-http"\ns.run(transport="streamable-http", host="127.0.0.1", port=' + str(port) + ')\n', encoding='utf-8')
            server = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            worker = None
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2):
                            break
                    except OSError:
                        time.sleep(.05)
                worker = McpConnection({'transport': 'http', 'url': f'http://127.0.0.1:{port}/mcp'})
                tools, results, errors = [], [], []
                worker.tools_ready.connect(tools.extend)
                worker.result.connect(lambda *args: results.append(args))
                worker.problem.connect(errors.append)
                worker.start()
                self.wait(app, lambda: bool(tools) or bool(errors))
                self.assertEqual(errors, [])
                worker.queue.put(('greet', {}))
                self.wait(app, lambda: bool(results) or bool(errors))
                self.assertEqual(errors, [])
                self.assertIn('hello-http', results[0][1])
            finally:
                if worker:
                    worker.stop()
                    self.wait(app, lambda: not worker.isRunning())
                    worker.deleteLater()
                server.terminate()
                server.wait(timeout=5)

    def wait(self, app, predicate):
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())
