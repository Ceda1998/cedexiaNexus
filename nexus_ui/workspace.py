"""Project-oriented desktop workspace built on the existing local runtime and pairing UI."""
import json
from pathlib import Path
import platform
import sqlite3
import uuid

from .i18n import t

from PySide6.QtCore import QSize, Qt, QStandardPaths, QTimer, QPropertyAnimation, QEasingCurve, QTemporaryDir
from PySide6.QtGui import QDesktopServices, QPalette, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QDialog, QListWidget, QStackedWidget, QFormLayout, QSpinBox, QCheckBox, QButtonGroup,
    QInputDialog, QMessageBox, QMenu, QScrollArea, QFileDialog)

from .attachments import AttachmentReader, attachment_context
from .command_access import MODES, TerminalDialog, review_prompt, review_allows
from .local_model import LocalRunner
from .model_settings import ModelSettings
from .device_pairing import DevicePairingPage
from .distributed import DistributedSession
from .integrations import IntegrationStore, SkillEditor, McpPanel
from .chat_output import split_reply
from .chat_transcript import ChatTranscript
from .workspace_theme import DARK, LIGHT, workspace_style
from .build_info import build_info


class ChatStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, project TEXT NOT NULL, name TEXT NOT NULL, messages TEXT NOT NULL)')
        self.db.commit()

    def project(self, name):
        identifier = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO projects VALUES (?, ?)', (identifier, name))
        return identifier

    def chat(self, project):
        identifier = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', (identifier, project, t('Neuer Chat'), '[]'))
        return identifier

    def save(self, identifier, messages):
        title = next((m['text'][:45] for m in messages if m['role'] == 'user'), t('Neuer Chat'))
        with self.db:
            self.db.execute('UPDATE chats SET name=?, messages=? WHERE id=?', (title, json.dumps(messages), identifier))


class Workspace(QMainWindow):
    def __init__(self, runner=None, storage=None):
        super().__init__()
        build = build_info()
        self.setWindowTitle(f"Cedexia Nexus {build['version']} · {build['revision']}")
        self.resize(1240, 850)
        self.setMinimumSize(850, 650)
        self.runner = runner or LocalRunner(self)
        self.settings = self.runner.settings
        from .i18n import set_language
        set_language(self.settings.value('app_language', 'de'))
        path = storage or str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'CedexiaNexus' / 'chats.sqlite3')
        self.store = ChatStore(path)
        self.integrations = IntegrationStore(self.store.db, self.settings)
        self.pending_context = ''
        self.attachments = []
        self.attachment_reader = None
        self.review = None
        self.chat_id = None
        self.messages = []
        self.stream = None
        self.closing = False
        self.advanced = None
        self.icon_cache = QTemporaryDir()
        self.render_timer = QTimer(self, interval=100, singleShot=True)
        self.render_timer.timeout.connect(self.render)
        body = QWidget()
        self.setCentralWidget(body)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(230)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 20, 14, 14)
        side.setSpacing(7)
        brand = QLabel('Cedexia Nexus')
        brand.setObjectName('workspaceBrand')
        brand_row = QHBoxLayout()
        brand_row.addWidget(brand, 1)
        self.new_chat = self.button('', self.create_chat, brand_row)
        self.new_chat.setFixedSize(32, 32)
        self.new_chat.setAccessibleName(t('Neuer Chat'))
        self.new_chat.setToolTip(t('Neuer Chat'))
        self.new_chat.setProperty('quiet', True)
        side.addLayout(brand_row)
        self.mode = QWidget()
        self.mode.setAccessibleName(t('Ausführungsmodus'))
        modes = QHBoxLayout(self.mode)
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(4)
        self.mode_buttons = QButtonGroup(self.mode)
        self.local_mode = QPushButton(t('Einzelgerät'))
        self.multi_mode = QPushButton(t('Mehrgeräte'))
        for index, (button, hint) in enumerate((
            (self.local_mode, t('Modell lokal auf diesem Gerät ausführen')),
            (self.multi_mode, t('Ein zweites Gerät koppeln und Modelle abgleichen')),
        )):
            button.setCheckable(True)
            button.setProperty('modeChoice', True)
            button.setToolTip(hint)
            self.mode_buttons.addButton(button, index)
            modes.addWidget(button, 1)
        self.local_mode.setChecked(True)
        side.addWidget(self.mode)
        self.add_device = self.button(t('Geräte verbinden …'), self.open_devices, side)
        commands = QHBoxLayout()
        self.new_project = self.button(t('+ Projekt'), self.create_project, commands)
        side.addLayout(commands)
        projects = QLabel(t('Projekte und Chats'))
        projects.setObjectName('sidebarLabel')
        side.addSpacing(10)
        side.addWidget(projects)
        self.tree = QTreeWidget()
        self.tree.setObjectName('chatTree')
        self.tree.setIndentation(16)
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(t('Projekte und Chats'))
        side.addWidget(self.tree, 1)
        self.delete_chat = self.button(t('Auswahl löschen'), self.remove_selected, side)
        self.settings_button = self.button(t('Einstellungen'), self.open_settings, side)
        for action in (self.delete_chat, self.settings_button):
            action.setProperty('quiet', True)
            action.setProperty('sidebarAction', True)
        outer.addWidget(self.sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(24, 14, 24, 18)
        main.setSpacing(9)
        outer.addLayout(main, 1)
        header = QHBoxLayout()
        self.toggle = self.button('', self.toggle_sidebar, header)
        self.toggle.setFixedWidth(35)
        self.toggle.setProperty('quiet', True)
        self.toggle.setAccessibleName(t('Sidebar ein- oder ausblenden'))
        self.toggle.setToolTip(self.toggle.accessibleName())
        self.title = QLabel(t('Neuer Chat'))
        self.title.setObjectName('workspaceTitle')
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.status = QLabel('')
        self.status.setObjectName('workspaceStatus')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        title_group = QVBoxLayout()
        title_group.setSpacing(2)
        title_group.addWidget(self.title)
        title_group.addWidget(self.status)
        header.addLayout(title_group, 1)
        main.addLayout(header)
        self.transcript = ChatTranscript(self.open_link)
        self.transcript.command_requested.connect(self.open_terminal)
        main.addWidget(self.transcript, 1)
        composer_panel = QWidget()
        composer_panel.setObjectName('composer')
        composer_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        composer_panel.setMaximumWidth(860)
        entry = QVBoxLayout(composer_panel)
        entry.setContentsMargins(9, 8, 9, 9)
        entry.setSpacing(6)
        self.device_chat_notice = QWidget()
        device_chat_row = QHBoxLayout(self.device_chat_notice)
        device_chat_row.setContentsMargins(0, 0, 0, 0)
        self.device_chat_hint = QLabel('Der Mehrgeräte-Modus prüft die Modellgewichte. Chat-Antworten sind derzeit im Einzelgerät-Modus verfügbar.')
        self.device_chat_hint.setObjectName('libraryStatus')
        self.device_chat_hint.setWordWrap(True)
        device_chat_row.addWidget(self.device_chat_hint, 1)
        self.switch_to_local = self.button(t('Zu Einzelgerät wechseln'), self.focus_local_chat, device_chat_row)
        entry.addWidget(self.device_chat_notice)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName('chatPrompt')
        self.prompt.setPlaceholderText(t('Nachricht schreiben …'))
        self.prompt.setFixedHeight(84)
        self.prompt.setAccessibleName(t('Nachricht'))
        entry.addWidget(self.prompt)
        self.attachment_list = QWidget()
        self.attachment_layout = QVBoxLayout(self.attachment_list)
        self.attachment_layout.setContentsMargins(0, 0, 0, 0)
        entry.addWidget(self.attachment_list)
        composer = QHBoxLayout()
        self.attach_button = self.button('', self.attach_files, composer)
        self.attach_button.setAccessibleName(t('Dateien anhängen'))
        self.attach_button.setToolTip(t('Dateien anhängen'))
        self.permissions = self.button('', self.permission_menu, composer)
        self.permissions.setAccessibleName(t('Befehlsfreigabe'))
        for action in (self.attach_button, self.permissions):
            action.setFixedSize(32, 32)
            action.setProperty('quiet', True)
        self.models = QComboBox()
        self.models.setAccessibleName(t('Modell für diesen Chat'))
        self.models.setPlaceholderText(t('Modell auswählen'))
        self.models.setMinimumWidth(120)
        self.models.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        composer.addWidget(self.models, 1)
        self.mcp_button = self.button('MCPs', lambda: self.integration_menu('mcps'), composer)
        self.skill_button = self.button('Skills', lambda: self.integration_menu('skills'), composer)
        self.dictate = self.button(t('Diktieren'), self.dictation, composer)
        for action in (self.mcp_button, self.skill_button, self.dictate):
            action.setProperty('quiet', True)
        self.send = self.button(t('Senden'), self.submit, composer)
        self.send.setProperty('primary', True)
        self.stop = self.button(t('Stoppen'), self.stop_run, composer)
        entry.addLayout(composer)
        composer_row = QHBoxLayout()
        composer_row.addStretch()
        composer_row.addWidget(composer_panel, 100)
        composer_row.addStretch()
        main.addLayout(composer_row)
        self.devices = QDialog(self)
        self.devices.setWindowTitle(t('Geräte verbinden · Cedexia Nexus'))
        self.devices.resize(820, 760)
        device_layout = QVBoxLayout(self.devices)
        self.pairing = DevicePairingPage(self.runner)
        self.cluster = DistributedSession(self.runner, self.pairing)
        self.compute_hint = QLabel(t('Experimentelle gemeinsame Inferenz: nur eigene Geräte und Testdaten. '
                                   'Auf beiden Geräten aktivieren. Der Kurztest ermittelt GPU-Leistung; '
                                   'WLAN kann die gemeinsame Berechnung verlangsamen.'))
        self.compute_hint.setWordWrap(True)
        self.compute_status = QLabel(self.cluster.message)
        self.compute_status.setTextFormat(Qt.TextFormat.PlainText)
        self.compute_status.setWordWrap(True)
        self.compute_enable = QPushButton(t('Gemeinsames Rechnen aktivieren'))
        self.compute_enable.clicked.connect(self.cluster.enable)
        self.compute_disable = QPushButton(t('Gemeinsames Rechnen beenden'))
        self.compute_disable.setEnabled(False)
        self.compute_disable.clicked.connect(lambda: self.cluster.disable())
        for widget in (self.compute_hint, self.compute_status, self.compute_enable, self.compute_disable):
            self.pairing.layout().addWidget(widget)
        self.cluster.changed.connect(self.compute_changed)
        device_scroll = QScrollArea()
        device_scroll.setWidgetResizable(True)
        device_scroll.setWidget(self.pairing)
        device_layout.addWidget(device_scroll)
        self.pairing.select.clicked.connect(lambda: self.open_settings(t('Modelle')))
        self.pairing.idle.connect(self.finish_close)
        self.device_timer = QTimer(self, interval=500)
        self.device_timer.timeout.connect(self.connection_state)
        self.device_timer.start()
        self.was_connected = False
        self.preferences = None
        self.mcp_panel = McpPanel(self.integrations, lambda: self.chat_id, lambda: not self.runner.busy and not self.runner.external_busy and not self.closing)
        self.mcp_panel.authorize = self.authorize_command
        self.terminal = TerminalDialog(self.authorize_command,
            lambda: not (self.runner.busy or self.runner.external_busy or self.closing), self)
        self.terminal.context_ready.connect(lambda text: self.set_context(text) if self.terminal_chat == self.chat_id else None)
        self.terminal.idle.connect(self.finish_close)
        self.terminal.busy_changed.connect(self.refresh)
        self.terminal.cancel_review.connect(lambda: self.runner.stop() if self.review is not None else None)
        self.terminal_chat = None
        self.mcp_panel.context_ready.connect(self.set_context)
        self.mcp_panel.idle.connect(self.finish_close)
        self.mcp_panel.changed.connect(self.refresh_integrations)
        self.runner.output.connect(self.append_output)
        self.runner.finished.connect(self.finished)
        self.runner.status.connect(lambda status: self.status.setText(t(status)))
        self.runner.busy_changed.connect(self.refresh)
        self.runner.model_changed.connect(self.refresh_models)
        self.runner.library_changed.connect(self.refresh_models)
        self.models.currentIndexChanged.connect(self.choose_model)
        self.tree.currentItemChanged.connect(self.select_chat)
        self.mode_buttons.idToggled.connect(self.mode_toggled)
        self.prompt.textChanged.connect(self.refresh)
        self.refresh_tree()
        self.refresh_models()
        self.change_mode()
        self.apply_font()
        self.apply_theme()
        self.sidebar_expanded = self.settings.value('sidebar_visible', True, type=bool)
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(230 if self.sidebar_expanded else 0)
        self.sidebar_animation = QPropertyAnimation(self.sidebar, b'maximumWidth', self)
        self.sidebar_animation.setDuration(180)
        self.sidebar_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.update_permissions()
        self.render()
        latest = self.store.db.execute('SELECT id FROM chats ORDER BY rowid DESC LIMIT 1').fetchone()
        if latest:
            self.load_chat(latest[0])

    @staticmethod
    def button(text, handler, layout):
        button = QPushButton(text)
        button.clicked.connect(lambda: handler())
        layout.addWidget(button)
        return button

    def toggle_sidebar(self):
        self.sidebar_expanded = not self.sidebar_expanded
        self.sidebar_animation.stop()
        self.sidebar_animation.setStartValue(self.sidebar.width())
        self.sidebar_animation.setEndValue(230 if self.sidebar_expanded else 0)
        self.sidebar_animation.start()
        self.settings.setValue('sidebar_visible', self.sidebar_expanded)

    def refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        for identifier, name in self.store.db.execute('SELECT id,name FROM projects ORDER BY rowid'):
            project = QTreeWidgetItem(self.tree, [name])
            project.setData(0, Qt.ItemDataRole.UserRole, ('project', identifier))
            for chat_id, title in self.store.db.execute('SELECT id,name FROM chats WHERE project=? ORDER BY rowid', (identifier,)):
                chat = QTreeWidgetItem(project, [title])
                chat.setData(0, Qt.ItemDataRole.UserRole, ('chat', chat_id))
                if chat_id == self.chat_id:
                    self.tree.setCurrentItem(chat)
            project.setExpanded(True)
        self.tree.blockSignals(False)

    def create_project(self):
        if self.workspace_busy():
            return
        name, ok = QInputDialog.getText(self, t('Neues Projekt'), t('Projektname'))
        if ok and name.strip():
            project = self.store.project(name.strip()[:100])
            self.runner.select_default_model()
            self.load_chat(self.store.chat(project))

    def create_chat(self):
        if self.workspace_busy():
            return
        self.runner.select_default_model()
        item = self.tree.currentItem()
        if item:
            if item.parent():
                item = item.parent()
            project = item.data(0, Qt.ItemDataRole.UserRole)[1]
        else:
            row = self.store.db.execute('SELECT id FROM projects ORDER BY rowid LIMIT 1').fetchone()
            project = row[0] if row else self.store.project(t('Meine Chats'))
        self.load_chat(self.store.chat(project))

    def load_chat(self, identifier):
        if self.workspace_busy():
            return
        row = self.store.db.execute('SELECT name,messages FROM chats WHERE id=?', (identifier,)).fetchone()
        self.chat_id = identifier
        self.title.setText(row[0])
        self.messages = json.loads(row[1])
        for message in self.messages:
            if message['role'] == 'assistant' and ('thinking' not in message or '[THINK]' in message['text']):
                reply = split_reply(message['text'], complete=True, legacy=True)
                message.update(text=reply.answer, thinking=reply.thinking)
            if message.pop('pending', False):
                message['status'] = t('Der vorherige Lauf wurde unterbrochen.')
        self.transcript.clear()
        self.status.setText(t('Lokal · Bereit') if self.local_mode.isChecked() else self.device_mode_status())
        self.pending_context = ''
        self.attachments = []
        self.refresh_attachments()
        self.prompt.clear()
        self.refresh_tree()
        self.render()
        self.refresh_integrations()

    def select_chat(self, current, previous):
        if current and current.data(0, Qt.ItemDataRole.UserRole)[0] == 'chat':
            self.load_chat(current.data(0, Qt.ItemDataRole.UserRole)[1])

    def remove_selected(self):
        if self.workspace_busy():
            return
        item = self.tree.currentItem()
        if not item:
            return
        kind, identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == 'chat':
            self.remove_chat()
            return
        count = self.store.db.execute('SELECT count(*) FROM chats WHERE project=?', (identifier,)).fetchone()[0]
        if QMessageBox.question(self, t('Projekt löschen'),
                t('Projekt „{name}“ und alle {count} Chats dauerhaft löschen?').format(name=item.text(0), count=count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        active = self.store.db.execute('SELECT 1 FROM chats WHERE id=? AND project=?', (self.chat_id, identifier)).fetchone()
        with self.store.db:
            self.store.db.execute('DELETE FROM chat_integrations WHERE chat IN (SELECT id FROM chats WHERE project=?)', (identifier,))
            self.store.db.execute('DELETE FROM chats WHERE project=?', (identifier,))
            self.store.db.execute('DELETE FROM projects WHERE id=?', (identifier,))
        if active:
            self.reset_chat()
        self.refresh_tree()

    def reset_chat(self):
        self.chat_id = None
        self.messages = []
        self.attachments = []
        self.pending_context = ''
        self.prompt.clear()
        self.title.setText(t('Neuer Chat'))
        self.transcript.clear()
        self.refresh_attachments()
        self.refresh_integrations()
        self.render()

    def remove_chat(self):
        if self.workspace_busy():
            return
        if self.chat_id and QMessageBox.question(self, t('Chat löschen'), t('Diesen lokal gespeicherten Chat löschen?')) == QMessageBox.StandardButton.Yes:
            with self.store.db:
                self.store.db.execute('DELETE FROM chat_integrations WHERE chat=?', (self.chat_id,))
                self.store.db.execute('DELETE FROM chats WHERE id=?', (self.chat_id,))
            self.reset_chat()
            self.refresh_tree()

    def refresh_models(self):
        self.models.blockSignals(True)
        self.models.clear()
        for path in self.runner.models:
            self.models.addItem(Path(path).name, path)
        self.models.setCurrentIndex(self.models.findData(str(self.runner.model)))
        self.models.blockSignals(False)
        self.refresh()

    def choose_model(self, index):
        if index >= 0:
            self.runner.select_model(self.models.itemData(index))

    def mode_toggled(self, _mode, checked):
        if checked:
            self.change_mode()

    def change_mode(self):
        self.add_device.setVisible(self.multi_mode.isChecked())
        self.status.setText(t('Lokal · Bereit') if self.local_mode.isChecked() else self.device_mode_status())
        self.refresh()

    def focus_local_chat(self):
        self.local_mode.setChecked(True)
        self.prompt.setFocus()

    def device_mode_status(self):
        if self.cluster.ready:
            return t('Beide Geräte bereit · Lastverteilung automatisch')
        return self.cluster.blocked_reason()

    def open_devices(self):
        if not self.pairing.busy:
            self.pairing.reload_interfaces()
        self.devices.show()
        self.devices.raise_()
        self.devices.activateWindow()

    def connection_state(self):
        connected = self.pairing.connected
        if connected and not self.was_connected:
            self.devices.hide()
            if self.multi_mode.isChecked():
                self.status.setText(self.device_mode_status())
        if self.was_connected and not connected and self.multi_mode.isChecked():
            self.status.setText(self.device_mode_status())
        self.was_connected = connected

    def submit(self):
        if self.workspace_busy():
            return
        text = self.prompt.toPlainText().strip()
        if not text:
            return
        skill = self.integrations.skill_prompt(self.chat_id)
        history = '\n\n'.join(('Nutzer' if m['role'] == 'user' else 'Assistent') + ': ' + m['text'] + '\n' + attachment_context(m.get('attachments', []))
                              for m in self.messages if m['text'] and not m.get('excluded_from_history'))
        prompt = '\n\n'.join(part for part in (skill, history, self.pending_context, attachment_context(self.attachments), 'Nutzer: ' + text) if part)
        if len(prompt) > 12000:
            self.status.setText(t('Die Eingabe mit Verlauf überschreitet 12000 Zeichen. Kürze den Entwurf oder beginne einen neuen Chat.'))
            return
        attachments = self.attachments[:]
        if not self.chat_id:
            self.create_chat()
            self.prompt.setPlainText(text)
            self.attachments = attachments
        self.messages.extend([{'role': 'user', 'text': text, 'attachments': attachments},
                              {'role': 'assistant', 'text': '', 'thinking': '', 'pending': True}])
        self.stream = []
        start = self.runner.start if self.local_mode.isChecked() else self.cluster.start
        if not start(prompt):
            del self.messages[-2:]
            self.stream = None
            return
        self.prompt.clear()
        self.attachments = []
        self.refresh_attachments()
        self.pending_context = ''
        self.store.save(self.chat_id, self.messages)
        self.render()

    def append_output(self, text):
        if self.review is not None:
            self.review['output'].append(text)
            return
        if self.stream is not None and text:
            self.stream.append(text)
            if not self.render_timer.isActive():
                self.render_timer.start()

    def render(self):
        if self.stream is not None:
            reply = split_reply(''.join(self.stream), prefilled=self.runner.thinking_prefilled,
                                console_prompt=self.runner.windows)
            if not self.runner.input_truncated:
                self.messages[-1].update(text=reply.answer, thinking=reply.thinking)
        self.transcript.render(self.messages, self.stream is not None)

    def finished(self, status):
        if self.review is not None:
            review, self.review = self.review, None
            reply = split_reply(''.join(review['output']), prefilled=self.runner.thinking_prefilled, complete=True, console_prompt=self.runner.windows)
            allowed = (status == t('Lokaler Lauf beendet.') and not self.runner.input_truncated
                       and review['mode'] == self.permission_mode() and review['chat'] == self.chat_id
                       and review_allows(reply.answer))
            self.status.setText(t('Agent-Prüfung: freigegeben.') if allowed else t('Agent-Prüfung: nicht freigegeben.'))
            review['done'](allowed)
            self.finish_close()
            return
        self.render_timer.stop()
        if self.stream is not None:
            reply = split_reply(''.join(self.stream), prefilled=self.runner.thinking_prefilled,
                                complete=True, console_prompt=self.runner.windows)
            message = self.messages[-1]
            message.pop('pending', None)
            message.update(text=reply.answer, thinking=reply.thinking)
            if self.runner.input_truncated:
                message.update(text='', thinking='')
                self.messages[-2]['excluded_from_history'] = True
            if status != t('Lokaler Lauf beendet.'):
                message['status'] = status
                if reply.thinking_open and reply.thinking and not reply.answer and not self.runner.input_truncated:
                    message['status'] += ' Der Lauf hat nur Denktext geliefert.'
            elif not reply.answer:
                message['status'] = t('Denktext ohne finale Antwort.') if reply.thinking else t('Keine Textantwort erhalten.')
            elif reply.thinking_open:
                message['status'] = t('Denktext wurde vor dem Abschluss unterbrochen.')
            self.stream = None
        if self.chat_id:
            self.store.save(self.chat_id, self.messages)
            self.title.setText(self.store.db.execute('SELECT name FROM chats WHERE id=?', (self.chat_id,)).fetchone()[0])
        self.refresh_tree()
        self.render()
        self.finish_close()

    def workspace_busy(self):
        terminal = getattr(self, 'terminal', None)
        return bool(self.runner.busy or self.runner.external_busy or self.attachment_reader
                    or (terminal and (terminal.process or terminal.authorizing)))

    def refresh(self, *_):
        busy = self.workspace_busy()
        for widget in (self.tree, self.new_project, self.new_chat, self.delete_chat, self.models, self.skill_button, self.mcp_button, self.mode, self.attach_button, self.permissions):
            widget.setEnabled(not busy)
        local = self.local_mode.isChecked()
        self.device_chat_notice.setVisible(not local)
        self.prompt.setReadOnly(busy)
        self.prompt.setPlaceholderText(t('Nachricht schreiben …'))
        self.device_chat_hint.setText(t('Automatische Lastverteilung · beide Geräte rechnen.') if self.cluster.ready
                                     else self.cluster.blocked_reason())
        can_send = (not busy and not self.attachment_reader and (local or self.cluster.ready)
                    and bool(self.prompt.toPlainText().strip()) and not self.runner.unavailable_reason())
        self.send.setEnabled(can_send)
        self.send.setToolTip(self.runner.unavailable_reason() if local else self.cluster.blocked_reason())
        self.attachment_list.setEnabled(not busy and not self.attachment_reader)
        self.attach_button.setEnabled(not busy and not self.attachment_reader)
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)

    def compute_changed(self):
        self.compute_status.setText(self.cluster.message if self.cluster.ready else self.cluster.blocked_reason())
        self.compute_enable.setEnabled(not self.cluster.enabled and not self.cluster.busy and not self.runner.busy)
        self.compute_disable.setEnabled(self.cluster.enabled)
        self.runner.busy_changed.emit(self.runner.busy or self.runner.external_busy)
        self.refresh()
        if self.multi_mode.isChecked() and not self.runner.busy:
            self.status.setText(self.device_mode_status())
        self.finish_close()

    def stop_run(self):
        if self.cluster.pending or self.cluster.reservation:
            self.cluster.cancel()
        elif self.terminal.process:
            self.terminal.stop()
        elif self.runner.external_busy:
            self.cluster.disable()
        else:
            self.runner.stop(t('Antwort gestoppt.'))

    def copy_answer(self):
        for message in reversed(self.messages):
            if message['role'] == 'assistant' and message['text']:
                QApplication.clipboard().setText(message['text'])
                break

    def open_link(self, url):
        if url.scheme() in ('https', 'http') and QMessageBox.question(self, t('Link öffnen'), url.toString()) == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(url)

    def dictation(self):
        shortcut = 'die konfigurierte Diktier-Taste (häufig zweimal Fn)' if platform.system() == 'Darwin' else 'Windows + H'
        QMessageBox.information(self, t('Spracheingabe'), f'Klicke in das Nachrichtenfeld und verwende {shortcut}. Aktiviere Diktat bei Bedarf in den Systemeinstellungen. Die Verarbeitung richtet sich nach deinen Betriebssystem-Einstellungen.')
        self.prompt.setFocus()

    def apply_font(self):
        font = self.font()
        font.setPointSize(self.settings.value('font_size', 11, type=int))
        self.setFont(font)

    def apply_theme(self):
        from .app import icon
        dark = self.settings.value('dark_theme', False, type=bool)
        colors = DARK if dark else LIGHT
        palette = QPalette()
        for role, key in ((QPalette.ColorRole.Window, 'canvas'), (QPalette.ColorRole.WindowText, 'text'),
                          (QPalette.ColorRole.Base, 'surface'), (QPalette.ColorRole.Text, 'text'),
                          (QPalette.ColorRole.Button, 'surface'), (QPalette.ColorRole.ButtonText, 'text'),
                          (QPalette.ColorRole.Highlight, 'accent'), (QPalette.ColorRole.HighlightedText, None),
                          (QPalette.ColorRole.ToolTipBase, 'surface'), (QPalette.ColorRole.ToolTipText, 'text')):
            palette.setColor(role, QColor(colors[key] if key else '#FFFFFF'))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors['disabled']))
        self.setPalette(palette)
        for combo in self.findChildren(QComboBox):
            combo.setPalette(palette)
            combo.view().setPalette(palette)
        arrow = self.icon_cache.path() + ('/arrow-dark.png' if dark else '/arrow-light.png')
        icon('chevron-down', colors['text']).pixmap(16, 16).save(arrow)
        self.setStyleSheet(workspace_style(colors) + f'QComboBox::down-arrow {{ image: url("{arrow}"); width: 14px; height: 14px; }}')
        self.toggle.setIcon(icon('layout-sidebar', colors['text']))
        self.new_chat.setIcon(icon('message-plus', colors['text']))
        self.attach_button.setIcon(icon('plus', colors['text']))
        self.permissions.setIcon(icon('shield-check', colors['text']))
        self.transcript.set_colors(colors)
        self.settings_button.setIcon(icon('settings', colors['muted']))
        for action in (self.toggle, self.settings_button, self.new_chat, self.attach_button, self.permissions):
            action.setIconSize(QSize(16, 16))

    def open_settings(self, section=None):
        if self.preferences is None:
            self.preferences = QDialog(self)
            self.preferences.setWindowTitle(t('Einstellungen · Cedexia Nexus'))
            self.preferences.resize(960, 610)
            layout = QHBoxLayout(self.preferences)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            sidebar = QWidget()
            sidebar.setObjectName('settingsSidebar')
            sidebar.setFixedWidth(178)
            sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
            navigation = QVBoxLayout(sidebar)
            navigation.setContentsMargins(12, 20, 12, 12)
            label = QLabel(t('Einstellungen'))
            label.setObjectName('workspaceBrand')
            navigation.addWidget(label)
            self.settings_navigation = QListWidget()
            self.settings_navigation.setObjectName('settingsNavigation')
            self.settings_navigation.setAccessibleName(t('Einstellungsbereiche'))
            navigation.addWidget(self.settings_navigation, 1)
            advanced = self.button(t('Prüfung und Demo'), self.open_advanced, navigation)
            advanced.setProperty('quiet', True)
            layout.addWidget(sidebar)
            content = QVBoxLayout()
            content.setContentsMargins(22, 18, 22, 18)
            content.setSpacing(14)
            section_title = QLabel()
            section_title.setObjectName('settingsTitle')
            content.addWidget(section_title)
            pages = QStackedWidget()
            content.addWidget(pages, 1)
            layout.addLayout(content, 1)

            def add_page(page, title):
                self.settings_navigation.addItem(title)
                pages.addWidget(page)

            general = QWidget()
            general_form = QFormLayout(general)
            general_form.setContentsMargins(0, 0, 0, 0)
            build = build_info()
            general_form.addRow(t('App-Version'), QLabel(f"{build['version']} · {build['revision']}"))
            self.language = QComboBox()
            self.language.addItem('Deutsch', 'de')
            self.language.addItem('English', 'en')
            self.language.setCurrentIndex(self.language.findData(self.settings.value('app_language', 'de')))
            self.language.currentIndexChanged.connect(self.change_language)
            general_form.addRow(t('App-Sprache'), self.language)
            add_page(general, t('Allgemein'))
            appearance = QWidget()
            form = QFormLayout(appearance)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(12)
            size = QSpinBox()
            size.setRange(9, 20)
            size.setValue(self.settings.value('font_size', 11, type=int))
            size.valueChanged.connect(lambda value: (self.settings.setValue('font_size', value), self.apply_font()))
            form.addRow(t('Schriftgröße'), size)
            dark = QCheckBox(t('Dunkles Erscheinungsbild'))
            dark.setChecked(self.settings.value('dark_theme', False, type=bool))
            dark.toggled.connect(lambda value: (self.settings.setValue('dark_theme', value), self.apply_theme()))
            form.addRow(dark)
            add_page(appearance, t('Erscheinungsbild'))
            add_page(ModelSettings(self.runner), t('Modelle'))
            speech = QWidget()
            speech_layout = QVBoxLayout(speech)
            speech_layout.setContentsMargins(0, 0, 0, 0)
            speech_button = self.button(t('Systemdiktat verwenden'), self.dictation, speech_layout)
            speech_layout.setAlignment(speech_button, Qt.AlignmentFlag.AlignLeft)
            speech_layout.addStretch()
            add_page(speech, t('Spracheingabe'))
            skills = SkillEditor(self.integrations)
            skills.changed.connect(self.refresh_integrations)
            add_page(skills, 'Skills')
            mcp_scroll = QScrollArea()
            mcp_scroll.setWidgetResizable(True)
            mcp_scroll.setWidget(self.mcp_panel)
            add_page(mcp_scroll, 'MCPs')
            devices = QWidget()
            devices_layout = QVBoxLayout(devices)
            devices_layout.setContentsMargins(0, 0, 0, 0)
            device_button = self.button(t('Geräteverbindung verwalten'), self.open_devices, devices_layout)
            devices_layout.setAlignment(device_button, Qt.AlignmentFlag.AlignLeft)
            devices_layout.addStretch()
            add_page(devices, t('Geräte'))
            self.settings_navigation.currentRowChanged.connect(pages.setCurrentIndex)
            self.settings_navigation.currentTextChanged.connect(section_title.setText)
            self.settings_navigation.setCurrentRow(0)
        if section:
            matches = self.settings_navigation.findItems(section, Qt.MatchFlag.MatchExactly)
            if matches:
                self.settings_navigation.setCurrentItem(matches[0])
        self.preferences.show()
        self.preferences.raise_()
        if section == 'Skills':
            self.preferences.findChild(SkillEditor).focus_search()

    def refresh_integrations(self):
        self.skill_button.setText(f'Skills ({len(self.integrations.active(self.chat_id, "skills"))})')
        self.mcp_button.setText(f'MCPs ({len(self.integrations.active(self.chat_id, "mcps"))})')

    def integration_menu(self, kind):
        if not self.chat_id:
            draft = self.prompt.toPlainText()
            self.create_chat()
            self.prompt.setPlainText(draft)
        menu = QMenu(self)
        active = self.integrations.active(self.chat_id, kind)
        for identifier, name in self.store.db.execute(f'SELECT id,name FROM {kind} ORDER BY name'):
            item = menu.addAction(name)
            item.setCheckable(True)
            item.setChecked(identifier in active)
            item.toggled.connect(lambda enabled, i=identifier: self.activate_integration(kind, i, enabled))
        menu.addSeparator()
        menu.addAction(t('Verwalten …'), lambda: self.open_settings('Skills' if kind == 'skills' else 'MCPs'))
        if kind == 'mcps':
            menu.addAction(t('Werkzeuge aufrufen …'), lambda: self.open_settings('MCPs'))
        button = self.skill_button if kind == 'skills' else self.mcp_button
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def activate_integration(self, kind, identifier, enabled):
        self.integrations.activate(self.chat_id, kind, identifier, enabled)
        if kind == 'mcps' and not enabled:
            self.pending_context = ''
        self.refresh_integrations()

    def set_context(self, text):
        self.pending_context = text
        self.status.setText(t('MCP-Ergebnis wird bei der nächsten Nachricht mitgesendet.'))

    def attach_files(self):
        if self.workspace_busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, t('Dateien anhängen'), '', 'Dateien (*);;Dokumente (*.pdf *.txt *.md);;Bilder (*.png *.jpg *.webp)')
        if not paths:
            return
        if len(paths) + len(self.attachments) > 8:
            QMessageBox.information(self, t('Anhänge'), t('Höchstens 8 Dateien pro Nachricht.'))
            return
        self.attachment_reader = AttachmentReader(paths, self)
        self.attachment_reader.loaded.connect(self.attachments_loaded)
        self.attachment_reader.finished.connect(self.attachments_finished)
        self.attachment_reader.start()
        self.status.setText(t('Dateien werden gelesen …'))
        self.refresh()

    def attachments_loaded(self, attachments, errors):
        self.attachments.extend(attachments)
        self.refresh_attachments()
        if errors:
            QMessageBox.information(self, t('Anhänge'), '\n'.join(errors))
        self.status.setText(t('Dateien angehängt. Hinweise an den Anhängen beachten.'))

    def attachments_finished(self):
        self.attachment_reader.deleteLater()
        self.attachment_reader = None
        self.refresh()
        self.finish_close()

    def refresh_attachments(self):
        while self.attachment_layout.count():
            self.attachment_layout.takeAt(0).widget().deleteLater()
        for index, item in enumerate(self.attachments):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(item['name'] + (' · ' + t(item['note']) if item['note'] else t(' · Text wird mitgesendet')))
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label, 1)
            from .app import icon
            remove = QPushButton()
            remove.setIcon(icon('x', (DARK if self.settings.value('dark_theme', False, type=bool) else LIGHT)['text']))
            remove.setFixedSize(28, 28)
            remove.setAccessibleName(t('Anhang entfernen'))
            remove.clicked.connect(lambda checked=False, i=index: self.remove_attachment(i))
            layout.addWidget(remove)
            self.attachment_layout.addWidget(row)

    def remove_attachment(self, index):
        self.attachments.pop(index)
        self.refresh_attachments()

    def permission_mode(self):
        mode = self.settings.value('command_mode', 'ask', type=str)
        return mode if mode in MODES else 'off'

    def update_permissions(self):
        self.permissions.setToolTip(t('Befehlsfreigabe: ') + t(MODES[self.permission_mode()]))
        self.permissions.setAccessibleName(self.permissions.toolTip())

    def permission_menu(self):
        menu = QMenu(self)
        for mode, label in MODES.items():
            action = menu.addAction(t(label))
            action.setCheckable(True)
            action.setChecked(mode == self.permission_mode())
            action.triggered.connect(lambda checked=False, m=mode: self.set_permission_mode(m))
        menu.addSeparator()
        hint = menu.addAction(t('Agent-Prüfung ist experimentell und kann sich irren. Auto führt freigegebene Aufrufe ohne Rückfrage aus.'))
        hint.setEnabled(False)
        menu.addAction(t('Lokales Terminal …'), self.open_terminal)
        menu.exec(self.permissions.mapToGlobal(self.permissions.rect().bottomLeft()))

    def set_permission_mode(self, mode):
        if mode not in MODES:
            return
        self.settings.setValue('command_mode', mode)
        self.update_permissions()

    def open_terminal(self, command=None):
        if command and self.workspace_busy():
            return
        if command:
            self.terminal.command.setPlainText(command)
        if self.terminal_chat != self.chat_id:
            self.terminal.output.clear()
        self.terminal_chat = self.chat_id
        self.terminal.show()
        self.terminal.raise_()

    def authorize_command(self, request, done):
        if self.runner.busy or self.runner.external_busy or self.closing:
            done(False)
            return
        mode = self.permission_mode()
        if mode == 'off':
            self.status.setText(t('Befehle sind ausgeschaltet.'))
            done(False)
        elif mode == 'auto':
            done(True)
        elif mode == 'ask':
            box = QMessageBox(self)
            box.setWindowTitle(t('Befehl freigeben'))
            box.setText(t('Diesen Aufruf einmal ausführen?'))
            box.setInformativeText(json.dumps(request, ensure_ascii=False, indent=2))
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            done(box.exec() == QMessageBox.StandardButton.Yes)
        else:
            self.review = {'output': [], 'done': done, 'chat': self.chat_id, 'mode': mode}
            if not self.runner.start(review_prompt(request)):
                self.review = None
                done(False)

    def change_language(self):
        self.settings.setValue('app_language', self.language.currentData())
        from .i18n import set_language, translate_widgets
        set_language(self.language.currentData())
        translate_widgets(self)
        self.update_permissions()
        self.refresh_attachments()

    def open_advanced(self):
        if self.advanced is None:
            from .app import NexusWindow
            self.advanced = NexusWindow()
        self.advanced.show()
        self.advanced.raise_()

    def closeEvent(self, event):
        if self.runner.busy or self.pairing.busy or self.mcp_panel.connection or self.cluster.busy or self.terminal.process or self.attachment_reader:
            self.closing = True
            self.cluster.disable()
            self.terminal.stop()
            self.runner.stop()
            self.pairing.close_session()
            self.mcp_panel.disconnect()
            event.ignore()
            return
        self.terminal.close()
        self.devices.close()
        if self.preferences:
            self.preferences.close()
        if self.advanced:
            self.advanced.close()
        self.device_timer.stop()
        self.store.db.close()
        event.accept()

    def finish_close(self, *_):
        if self.closing and not self.runner.busy and not self.pairing.busy and not self.mcp_panel.connection and not self.cluster.busy and not self.terminal.process and not self.attachment_reader:
            self.close()
