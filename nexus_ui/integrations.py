"""Persistent Markdown skills and user-invoked MCP tools for a chat."""
import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
from queue import Queue, Empty
from threading import Event
from urllib.parse import urlsplit
import uuid

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLineEdit, QPlainTextEdit, QPushButton, QFileDialog,
    QMessageBox, QComboBox, QLabel, QFormLayout)

MAX_SKILL_BYTES = 128 * 1024


class IntegrationStore:
    def __init__(self, db, settings):
        self.db = db
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS skills (id TEXT PRIMARY KEY, name TEXT NOT NULL, markdown TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS mcps (id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS chat_integrations (chat TEXT, kind TEXT, item TEXT, PRIMARY KEY(chat,kind,item))')
            db.execute('CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)')
            if not db.execute("SELECT 1 FROM migrations WHERE name='skill_text'").fetchone():
                legacy = settings.value('skill_text', '', type=str)
                if legacy.strip():
                    db.execute('INSERT INTO skills VALUES (?,?,?)', ('legacy', 'Bisherige Anweisungen', legacy))
                    db.execute("INSERT INTO chat_integrations SELECT id,'skills','legacy' FROM chats")
                db.execute("INSERT INTO migrations VALUES ('skill_text')")

    def skills(self):
        return self.db.execute('SELECT id,name,markdown FROM skills ORDER BY name').fetchall()

    def save_skill(self, identifier, name, markdown):
        if not name.strip() or not markdown.strip():
            raise ValueError('Name und Markdown dürfen nicht leer sein.')
        if len(markdown.encode('utf-8')) > MAX_SKILL_BYTES:
            raise ValueError('Ein Skill darf höchstens 128 KiB enthalten.')
        identifier = identifier or uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO skills VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, markdown=excluded.markdown', (identifier, name.strip()[:100], markdown))
        return identifier

    def active(self, chat, kind):
        return {row[0] for row in self.db.execute('SELECT item FROM chat_integrations WHERE chat=? AND kind=?', (chat, kind))}

    def activate(self, chat, kind, identifier, enabled):
        with self.db:
            if enabled:
                self.db.execute('INSERT OR IGNORE INTO chat_integrations VALUES (?,?,?)', (chat, kind, identifier))
            else:
                self.db.execute('DELETE FROM chat_integrations WHERE chat=? AND kind=? AND item=?', (chat, kind, identifier))

    def remove(self, kind, identifier):
        if kind not in ('skills', 'mcps'):
            raise ValueError('Invalid integration kind')
        with self.db:
            self.db.execute(f'DELETE FROM {kind} WHERE id=?', (identifier,))
            self.db.execute('DELETE FROM chat_integrations WHERE kind=? AND item=?', (kind, identifier))

    def skill_prompt(self, chat):
        active = self.active(chat, 'skills')
        return '\n\n'.join(f'# Skill: {name}\n{body}' for identifier, name, body in self.skills() if identifier in active)


def button(text, callback, layout):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    layout.addWidget(widget)
    return widget


class SkillEditor(QWidget):
    changed = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.identifier = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        library = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Skills suchen …')
        self.search.setAccessibleName('Skills suchen')
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip('Nach Name und Markdown-Inhalt suchen')
        library.addWidget(self.search)
        self.search.returnPressed.connect(self.select_first_result)
        focus_search = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        focus_search.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        focus_search.activated.connect(self.focus_search)
        clear_search = QShortcut(QKeySequence('Escape'), self.search)
        clear_search.setContext(Qt.ShortcutContext.WidgetShortcut)
        clear_search.activated.connect(self.search.clear)
        self.search.textChanged.connect(lambda text: clear_search.setEnabled(bool(text)))
        clear_search.setEnabled(False)
        self.list = QListWidget()
        self.list.setObjectName('skillList')
        self.list.setAccessibleName('Skillbibliothek')
        library.addWidget(self.list, 1)
        self.results = QLabel()
        self.results.setObjectName('libraryStatus')
        self.results.setAccessibleName('Suchergebnisse')
        self.results.setWordWrap(True)
        library.addWidget(self.results)
        library_actions = QHBoxLayout()
        button('Neu', self.new, library_actions)
        button('Importieren …', self.import_file, library_actions)
        library.addLayout(library_actions)
        layout.addLayout(library, 2)

        detail = QVBoxLayout()
        name_label = QLabel('Name')
        name_label.setObjectName('libraryLabel')
        detail.addWidget(name_label)
        self.name = QLineEdit()
        self.name.setPlaceholderText('Name des Skills')
        self.name.setMaxLength(100)
        self.name.setAccessibleName('Skillname')
        name_label.setBuddy(self.name)
        detail.addWidget(self.name)
        markdown_label = QLabel('Markdown')
        markdown_label.setObjectName('libraryLabel')
        detail.addWidget(markdown_label)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.editor.setPlaceholderText('# Mein Skill\n\nAnweisungen für das Modell …')
        self.editor.setAccessibleName('Skill als Markdown')
        markdown_label.setBuddy(self.editor)
        detail.addWidget(self.editor, 1)
        actions = QHBoxLayout()
        self.delete_button = button('Löschen', self.remove, actions)
        self.delete_button.setProperty('quiet', True)
        self.delete_button.setProperty('danger', True)
        actions.addStretch()
        self.save_button = button('Speichern', self.save, actions)
        self.save_button.setProperty('primary', True)
        detail.addLayout(actions)
        layout.addLayout(detail, 3)
        self.search.textChanged.connect(self.filter_list)
        self.name.textChanged.connect(self.refresh_actions)
        self.editor.textChanged.connect(self.refresh_actions)
        self.list.currentItemChanged.connect(self.select)
        self.reload()

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def select_first_result(self):
        for index in range(self.list.count()):
            item = self.list.item(index)
            if not item.isHidden():
                self.list.setCurrentItem(item)
                self.list.setFocus()
                break

    def reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for identifier, name, markdown in self.store.skills():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, (identifier, name, markdown))
            self.list.addItem(item)
            if identifier == self.identifier:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.filter_list(self.search.text())
        self.refresh_actions()

    def filter_list(self, text):
        terms = text.casefold().split()
        visible = 0
        self.list.blockSignals(True)
        for index in range(self.list.count()):
            item = self.list.item(index)
            identifier, name, markdown = item.data(Qt.ItemDataRole.UserRole)
            haystack = (name + '\n' + markdown).casefold()
            matches = all(term in haystack for term in terms)
            item.setHidden(not matches)
            if matches:
                visible += 1
                if identifier == self.identifier:
                    self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if not self.list.count():
            self.results.setText('Noch keine Skills vorhanden.')
        elif not visible:
            self.results.setText('Keine passenden Skills.')
        elif terms:
            self.results.setText(f'{visible} von {self.list.count()} Skills')
        else:
            self.results.setText('1 Skill' if visible == 1 else f'{visible} Skills')

    def refresh_actions(self):
        self.save_button.setEnabled(bool(self.name.text().strip() and self.editor.toPlainText().strip()))
        self.delete_button.setEnabled(self.identifier is not None)

    def select(self, item, previous):
        if item:
            identifier, name, markdown = item.data(Qt.ItemDataRole.UserRole)
            if identifier == self.identifier:
                return
            self.identifier = identifier
            self.name.setText(name)
            self.editor.setPlainText(markdown)
            self.refresh_actions()

    def new(self):
        self.identifier = None
        self.list.setCurrentRow(-1)
        self.name.clear()
        self.editor.clear()
        self.refresh_actions()
        self.name.setFocus()

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Skill importieren', '', 'Markdown (*.md *.markdown)')
        if path:
            try:
                with open(path, 'rb') as stream:
                    data = stream.read(MAX_SKILL_BYTES + 1)
                if len(data) > MAX_SKILL_BYTES:
                    raise ValueError('Die Datei überschreitet 128 KiB.')
                markdown = data.decode('utf-8-sig')
                self.identifier = self.store.save_skill(None, Path(path).stem, markdown)
            except (OSError, UnicodeError, ValueError):
                QMessageBox.warning(self, 'Skillimport', 'Datei konnte nicht importiert werden. UTF-8-Markdown bis 128 KiB wird unterstützt.')
                return
            self.name.setText(Path(path).stem)
            self.editor.setPlainText(markdown)
            self.reload()
            self.changed.emit()

    def save(self):
        try:
            self.identifier = self.store.save_skill(self.identifier, self.name.text(), self.editor.toPlainText())
        except ValueError as error:
            QMessageBox.warning(self, 'Skill speichern', str(error))
            return
        self.reload()
        self.changed.emit()

    def remove(self):
        if self.identifier and QMessageBox.question(self, 'Skill löschen', 'Diesen Skill aus der Bibliothek und allen Chat-Auswahlen entfernen?') == QMessageBox.StandardButton.Yes:
            self.store.remove('skills', self.identifier)
            self.new()
            self.reload()
            self.changed.emit()


def validate_config(transport, endpoint, arguments):
    if transport == 'stdio':
        if not Path(endpoint).is_file() or Path(endpoint).suffix.lower() in ('.bat', '.cmd'):
            raise ValueError('Wähle eine vorhandene ausführbare Datei, etwa Python oder Node.')
        args = json.loads(arguments)
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ValueError('Argumente müssen ein JSON-Array aus Strings sein.')
        return {'transport': transport, 'command': endpoint, 'args': args}
    url = urlsplit(endpoint)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise ValueError('Verwende eine MCP-URL ohne Zugangsdaten, Query oder Fragment.')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('HTTPS erforderlich. Lokale Loopback-Server dürfen HTTP verwenden.')
    return {'transport': 'http', 'url': endpoint}


class McpConnection(QThread):
    tools_ready = Signal(list)
    result = Signal(str, str, bool)
    problem = Signal(str)

    def __init__(self, config, token='', parent=None):
        super().__init__(parent)
        self.config = config
        self.token = token
        self.queue = Queue()
        self.stopped = Event()
        self.loop = None
        self.task = None

    def stop(self):
        self.stopped.set()
        if self.loop and self.task:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass

    def run(self):
        try:
            asyncio.run(self.serve())
        except asyncio.CancelledError:
            pass
        except Exception:
            self.problem.emit('MCP-Verbindung fehlgeschlagen. Adresse, Programm, Berechtigung und Server prüfen.')
        finally:
            self.token = ''
            self.loop = None
            self.task = None

    async def serve(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamable_http_client
        import httpx2
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        if self.stopped.is_set():
            return
        async with AsyncExitStack() as stack:
            if self.config['transport'] == 'stdio':
                log = stack.enter_context(open(os.devnull, 'w'))
                transport = stdio_client(StdioServerParameters(command=self.config['command'], args=self.config['args']), errlog=log)
            else:
                headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
                http = await stack.enter_async_context(httpx2.AsyncClient(headers=headers, timeout=30, follow_redirects=False))
                transport = streamable_http_client(self.config['url'], http_client=http)
            client = Client(transport, raise_exceptions=True, read_timeout_seconds=30)
            async with client:
                tools, cursor = [], None
                for _ in range(20):
                    page = await client.list_tools(cursor=cursor)
                    tools.extend(t.model_dump(mode='json') for t in page.tools)
                    cursor = page.next_cursor
                    if not cursor:
                        break
                if cursor:
                    raise ValueError('Tool catalogue too large')
                self.tools_ready.emit(tools)
                while not self.stopped.is_set():
                    try:
                        name, arguments = self.queue.get_nowait()
                    except Empty:
                        await asyncio.sleep(.05)
                        continue
                    try:
                        result = await client.call_tool(name, arguments, read_timeout_seconds=30)
                        text = '\n'.join(c.text for c in result.content if c.type == 'text')
                        if result.structured_content is not None:
                            text += '\n' + json.dumps(result.structured_content, ensure_ascii=False)
                        if not text:
                            text = 'Das Werkzeug lieferte keine Textdaten.'
                        if len(text) > 20000:
                            text = text[:20000] + '\n[Ergebnis auf 20000 Zeichen gekürzt]'
                        self.result.emit(name, text, result.is_error)
                    except Exception:
                        self.problem.emit('Werkzeugaufruf fehlgeschlagen oder Zeitlimit erreicht. Prüfe den Server vor einem erneuten Aufruf.')


class McpPanel(QWidget):
    context_ready = Signal(str)
    changed = Signal()
    idle = Signal()

    def __init__(self, store, chat_id, can_act):
        super().__init__()
        self.store, self.chat_id, self.can_act = store, chat_id, can_act
        self.connection = None
        self.call_pending = False
        self.call_chat = None
        self.catalogue = []
        layout = QVBoxLayout(self)
        self.servers = QComboBox()
        layout.addWidget(self.servers)
        form = QFormLayout()
        self.name = QLineEdit()
        self.transport = QComboBox()
        self.transport.addItems(['stdio', 'http'])
        self.endpoint = QLineEdit()
        self.endpoint.setPlaceholderText('Vollständiger Programmpfad oder https://…/mcp')
        self.args = QLineEdit('[]')
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        for label, widget in [('Name', self.name), ('Transport', self.transport), ('Programm / MCP-URL', self.endpoint), ('Argumente als JSON', self.args), ('Bearer-Token (nur diese Sitzung)', self.token)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.new_button = button('Neu', self.new, actions)
        self.save_button = button('Speichern', self.save, actions)
        self.remove_button = button('Löschen', self.remove, actions)
        self.connect_button = button('Verbinden', self.connect_server, actions)
        self.disconnect_button = button('Trennen', self.disconnect, actions)
        layout.addLayout(actions)
        self.status = QLabel('Server konfigurieren und verbinden.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tools = QComboBox()
        self.description = QPlainTextEdit()
        self.description.setReadOnly(True)
        self.description.setMaximumHeight(120)
        self.description.setPlaceholderText('Nach dem Verbinden: Werkzeugbeschreibung und Eingabeschema')
        self.arguments = QPlainTextEdit('{}')
        self.arguments.setMaximumHeight(100)
        self.arguments.setPlaceholderText('Werkzeugargumente als JSON-Objekt')
        self.arguments.setAccessibleName('Werkzeugargumente als JSON')
        for widget in (self.tools, self.description, self.arguments):
            layout.addWidget(widget)
        self.call_button = button('Werkzeug mit diesen Argumenten aufrufen', self.call_tool, layout)
        self.output = QPlainTextEdit()
        self.output.setPlaceholderText('Werkzeugergebnis · vor der Übernahme bei Bedarf kürzen')
        layout.addWidget(self.output, 1)
        self.use_button = button('Ergebnis als Kontext in diesen Chat übernehmen', self.use_result, layout)
        self.servers.currentIndexChanged.connect(self.select)
        self.output.textChanged.connect(self.refresh)
        self.tools.currentIndexChanged.connect(self.show_tool)
        self.reload()
        self.refresh()

    def reload(self):
        selected = self.servers.currentData()
        self.servers.blockSignals(True)
        self.servers.clear()
        for identifier, name in self.store.db.execute('SELECT id,name FROM mcps ORDER BY name'):
            self.servers.addItem(name, identifier)
        self.servers.setCurrentIndex(self.servers.findData(selected))
        self.servers.blockSignals(False)
        self.select()

    def new(self):
        self.servers.setCurrentIndex(-1)
        self.name.clear()
        self.endpoint.clear()
        self.args.setText('[]')
        self.token.clear()

    def select(self, *_):
        self.call_chat = None
        self.output.clear()
        row = self.store.db.execute('SELECT name,config FROM mcps WHERE id=?', (self.servers.currentData(),)).fetchone()
        if row:
            name, encoded = row
            config = json.loads(encoded)
            self.name.setText(name)
            self.transport.setCurrentText(config['transport'])
            self.endpoint.setText(config.get('command', config.get('url', '')))
            self.args.setText(json.dumps(config.get('args', [])))
        self.token.clear()

    def save(self):
        try:
            config = validate_config(self.transport.currentText(), self.endpoint.text().strip(), self.args.text())
            if not self.name.text().strip():
                raise ValueError('Gib einen Namen ein.')
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            return
        identifier = self.servers.currentData() or uuid.uuid4().hex
        token = self.token.text()
        with self.store.db:
            self.store.db.execute('INSERT INTO mcps VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, config=excluded.config', (identifier, self.name.text().strip(), json.dumps(config)))
        self.reload()
        self.servers.setCurrentIndex(self.servers.findData(identifier))
        self.token.setText(token)
        self.changed.emit()

    def remove(self):
        identifier = self.servers.currentData()
        if identifier and QMessageBox.question(self, 'MCP entfernen', 'Verbindung aus den Einstellungen und Chats entfernen?') == QMessageBox.StandardButton.Yes:
            self.store.remove('mcps', identifier)
            self.reload()
            self.changed.emit()

    def connect_server(self):
        row = self.store.db.execute('SELECT config FROM mcps WHERE id=?', (self.servers.currentData(),)).fetchone()
        if not row or self.connection:
            return
        config = json.loads(row[0])
        self.connection = McpConnection(config, self.token.text(), self)
        self.connection.tools_ready.connect(self.ready)
        self.connection.result.connect(self.result)
        self.connection.problem.connect(self.failed)
        self.connection.finished.connect(self.disconnected)
        self.status.setText('Verbindung wird aufgebaut …')
        self.connection.start()
        self.refresh()

    def ready(self, tools):
        self.catalogue = tools
        self.tools.clear()
        self.tools.addItems([t['name'] for t in tools])
        self.status.setText(f'Verbunden · {len(tools)} Werkzeuge')
        self.refresh()

    def show_tool(self, index):
        if index >= 0:
            tool = self.catalogue[index]
            self.description.setPlainText((tool.get('description') or '') + '\n\n' + json.dumps(tool['input_schema'], ensure_ascii=False, indent=2))
            self.arguments.setPlainText('{}')

    def call_tool(self):
        if not self.connection or self.call_pending or not self.catalogue:
            return
        identifier = self.servers.currentData()
        chat = self.chat_id()
        if not self.can_act() or identifier not in self.store.active(chat, 'mcps'):
            self.status.setText('Aktiviere diese MCP-Verbindung unter dem Chat und beende laufende Generierungen.')
            return
        try:
            arguments = json.loads(self.arguments.toPlainText())
            if not isinstance(arguments, dict):
                raise ValueError
            from jsonschema import validate
            validate(arguments, self.catalogue[self.tools.currentIndex()]['input_schema'])
        except Exception:
            self.status.setText('Argumente passen nicht zum angezeigten JSON-Schema.')
            return
        self.call_chat = chat
        self.call_pending = True
        self.output.clear()
        self.connection.queue.put((self.tools.currentText(), arguments))
        self.status.setText('Werkzeug wird aufgerufen …')
        self.refresh()

    def result(self, name, text, error):
        self.call_pending = False
        self.output.setPlainText(text)
        self.status.setText(('Werkzeug meldet einen Fehler · ' if error else 'Ergebnis · ') + name)
        self.refresh()

    def failed(self, message):
        self.call_pending = False
        self.status.setText(message)
        self.refresh()

    def use_result(self):
        if self.can_act() and self.call_chat == self.chat_id() and self.servers.currentData() in self.store.active(self.chat_id(), 'mcps'):
            self.context_ready.emit('MCP-Ergebnis (externe Daten):\n' + self.output.toPlainText())

    def disconnect(self):
        if self.connection:
            self.connection.stop()

    def disconnected(self):
        self.connection.deleteLater()
        self.connection = None
        self.call_pending = False
        self.call_chat = None
        self.output.clear()
        self.catalogue = []
        self.tools.clear()
        self.token.clear()
        self.status.setText('Verbindung getrennt.')
        self.refresh()
        self.idle.emit()

    def refresh(self):
        connected = self.connection is not None
        for widget in (self.servers, self.name, self.transport, self.endpoint, self.args, self.token, self.save_button, self.remove_button, self.new_button, self.connect_button):
            widget.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.call_button.setEnabled(connected and bool(self.catalogue) and not self.call_pending)
        self.tools.setEnabled(not self.call_pending)
        self.arguments.setReadOnly(self.call_pending)
        self.output.setReadOnly(self.call_pending)
        self.use_button.setEnabled(bool(self.output.toPlainText()) and self.call_chat is not None and not self.call_pending)
