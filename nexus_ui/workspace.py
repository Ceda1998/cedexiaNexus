"""Project-oriented desktop workspace built on the existing local runtime and pairing UI."""
import json
from pathlib import Path
import platform
import sqlite3
import uuid

from PySide6.QtCore import QSize, Qt, QStandardPaths, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QDialog, QListWidget, QStackedWidget, QFormLayout, QSpinBox, QCheckBox, QButtonGroup,
    QInputDialog, QMessageBox, QFileDialog, QMenu, QScrollArea)

from .local_model import LocalRunner
from .device_pairing import DevicePairingPage
from .integrations import IntegrationStore, SkillEditor, McpPanel
from .chat_output import split_reply
from .chat_transcript import ChatTranscript
from .workspace_theme import DARK, LIGHT, workspace_style


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
            self.db.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', (identifier, project, 'Neuer Chat', '[]'))
        return identifier

    def save(self, identifier, messages):
        title = next((m['text'][:45] for m in messages if m['role'] == 'user'), 'Neuer Chat')
        with self.db:
            self.db.execute('UPDATE chats SET name=?, messages=? WHERE id=?', (title, json.dumps(messages), identifier))


class Workspace(QMainWindow):
    def __init__(self, runner=None, storage=None):
        super().__init__()
        self.setWindowTitle('Cedexia Nexus')
        self.resize(1240, 850)
        self.setMinimumSize(850, 650)
        self.runner = runner or LocalRunner(self)
        self.settings = self.runner.settings
        path = storage or str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'CedexiaNexus' / 'chats.sqlite3')
        self.store = ChatStore(path)
        self.integrations = IntegrationStore(self.store.db, self.settings)
        self.pending_context = ''
        self.chat_id = None
        self.messages = []
        self.stream = None
        self.closing = False
        self.advanced = None
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
        side.addWidget(brand)
        self.mode = QWidget()
        self.mode.setAccessibleName('Ausführungsmodus')
        modes = QHBoxLayout(self.mode)
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(4)
        self.mode_buttons = QButtonGroup(self.mode)
        self.local_mode = QPushButton('Einzelgerät')
        self.multi_mode = QPushButton('Mehrgeräte')
        for index, (button, hint) in enumerate((
            (self.local_mode, 'Modell lokal auf diesem Gerät ausführen'),
            (self.multi_mode, 'Ein zweites Gerät koppeln und Modelle abgleichen'),
        )):
            button.setCheckable(True)
            button.setProperty('modeChoice', True)
            button.setToolTip(hint)
            self.mode_buttons.addButton(button, index)
            modes.addWidget(button, 1)
        self.local_mode.setChecked(True)
        side.addWidget(self.mode)
        self.add_device = self.button('Geräte verbinden …', self.open_devices, side)
        commands = QHBoxLayout()
        self.new_project = self.button('+ Projekt', self.create_project, commands)
        self.new_chat = self.button('+ Chat', self.create_chat, commands)
        side.addLayout(commands)
        projects = QLabel('Projekte und Chats')
        projects.setObjectName('sidebarLabel')
        side.addSpacing(10)
        side.addWidget(projects)
        self.tree = QTreeWidget()
        self.tree.setObjectName('chatTree')
        self.tree.setIndentation(16)
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Projekte und Chats')
        side.addWidget(self.tree, 1)
        self.delete_chat = self.button('Chat löschen', self.remove_chat, side)
        self.settings_button = self.button('Einstellungen', self.open_settings, side)
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
        self.toggle.setAccessibleName('Sidebar ein- oder ausblenden')
        self.toggle.setToolTip(self.toggle.accessibleName())
        self.title = QLabel('Neuer Chat')
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
        self.copy_button = self.button('Antwort kopieren', self.copy_answer, header)
        self.copy_button.setProperty('quiet', True)
        main.addLayout(header)
        self.transcript = ChatTranscript(self.open_link)
        main.addWidget(self.transcript, 1)
        composer_panel = QWidget()
        composer_panel.setObjectName('composer')
        composer_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        composer_panel.setMaximumWidth(860)
        entry = QVBoxLayout(composer_panel)
        entry.setContentsMargins(9, 8, 9, 9)
        entry.setSpacing(6)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName('chatPrompt')
        self.prompt.setPlaceholderText('Nachricht schreiben …')
        self.prompt.setFixedHeight(84)
        self.prompt.setAccessibleName('Nachricht')
        entry.addWidget(self.prompt)
        composer = QHBoxLayout()
        self.models = QComboBox()
        self.models.setAccessibleName('Modell für diesen Chat')
        self.models.setPlaceholderText('Modell auswählen')
        self.models.setMinimumWidth(120)
        self.models.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        composer.addWidget(self.models, 1)
        self.mcp_button = self.button('MCPs', lambda: self.integration_menu('mcps'), composer)
        self.skill_button = self.button('Skills', lambda: self.integration_menu('skills'), composer)
        self.dictate = self.button('Diktieren', self.dictation, composer)
        for action in (self.mcp_button, self.skill_button, self.dictate):
            action.setProperty('quiet', True)
        self.send = self.button('Senden', self.submit, composer)
        self.send.setProperty('primary', True)
        self.stop = self.button('Stoppen', lambda: self.runner.stop('Antwort gestoppt.'), composer)
        entry.addLayout(composer)
        composer_row = QHBoxLayout()
        composer_row.addStretch()
        composer_row.addWidget(composer_panel, 100)
        composer_row.addStretch()
        main.addLayout(composer_row)
        self.devices = QDialog(self)
        self.devices.setWindowTitle('Geräte verbinden · Cedexia Nexus')
        self.devices.resize(820, 760)
        device_layout = QVBoxLayout(self.devices)
        self.pairing = DevicePairingPage(self.runner)
        device_layout.addWidget(self.pairing)
        self.pairing.select.clicked.connect(lambda: self.open_settings('Modelle'))
        self.pairing.idle.connect(self.finish_close)
        self.device_timer = QTimer(self, interval=500)
        self.device_timer.timeout.connect(self.connection_state)
        self.device_timer.start()
        self.was_connected = False
        self.preferences = None
        self.mcp_panel = McpPanel(self.integrations, lambda: self.chat_id, lambda: not self.runner.busy and not self.closing)
        self.mcp_panel.context_ready.connect(self.set_context)
        self.mcp_panel.idle.connect(self.finish_close)
        self.mcp_panel.changed.connect(self.refresh_integrations)
        self.runner.output.connect(self.append_output)
        self.runner.finished.connect(self.finished)
        self.runner.status.connect(self.status.setText)
        self.runner.busy_changed.connect(self.refresh)
        self.runner.model_changed.connect(self.refresh_models)
        self.models.currentIndexChanged.connect(self.choose_model)
        self.tree.currentItemChanged.connect(self.select_chat)
        self.mode_buttons.idClicked.connect(self.change_mode)
        self.prompt.textChanged.connect(self.refresh)
        self.refresh_tree()
        self.refresh_models()
        self.change_mode()
        self.apply_font()
        self.apply_theme()
        self.sidebar.setVisible(self.settings.value('sidebar_visible', True, type=bool))
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
        self.sidebar.setVisible(not self.sidebar.isVisible())
        self.settings.setValue('sidebar_visible', self.sidebar.isVisible())

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
        name, ok = QInputDialog.getText(self, 'Neues Projekt', 'Projektname')
        if ok and name.strip():
            project = self.store.project(name.strip()[:100])
            self.load_chat(self.store.chat(project))

    def create_chat(self):
        item = self.tree.currentItem()
        if item:
            if item.parent():
                item = item.parent()
            project = item.data(0, Qt.ItemDataRole.UserRole)[1]
        else:
            row = self.store.db.execute('SELECT id FROM projects ORDER BY rowid LIMIT 1').fetchone()
            project = row[0] if row else self.store.project('Meine Chats')
        self.load_chat(self.store.chat(project))

    def load_chat(self, identifier):
        if self.runner.busy:
            return
        row = self.store.db.execute('SELECT name,messages FROM chats WHERE id=?', (identifier,)).fetchone()
        self.chat_id = identifier
        self.title.setText(row[0])
        self.messages = json.loads(row[1])
        for message in self.messages:
            if message['role'] == 'assistant' and 'thinking' not in message:
                reply = split_reply(message['text'], complete=True, legacy=True)
                message.update(text=reply.answer, thinking=reply.thinking)
            if message.pop('pending', False):
                message['status'] = 'Der vorherige Lauf wurde unterbrochen.'
        self.transcript.clear()
        self.status.setText('Lokal · Bereit' if self.local_mode.isChecked() else self.device_mode_status())
        self.pending_context = ''
        self.prompt.clear()
        self.refresh_tree()
        self.render()
        self.refresh_integrations()

    def select_chat(self, current, previous):
        if current and current.data(0, Qt.ItemDataRole.UserRole)[0] == 'chat':
            self.load_chat(current.data(0, Qt.ItemDataRole.UserRole)[1])

    def remove_chat(self):
        if self.chat_id and QMessageBox.question(self, 'Chat löschen', 'Diesen lokal gespeicherten Chat löschen?') == QMessageBox.StandardButton.Yes:
            with self.store.db:
                self.store.db.execute('DELETE FROM chat_integrations WHERE chat=?', (self.chat_id,))
                self.store.db.execute('DELETE FROM chats WHERE id=?', (self.chat_id,))
            self.chat_id = None
            self.messages = []
            self.pending_context = ''
            self.title.setText('Neuer Chat')
            self.refresh_tree()
            self.transcript.clear()
            self.render()

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

    def pick_model(self):
        if self.runner.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, 'Lokale Modelle', '', 'GGUF (*.gguf)')
        for path in paths:
            self.runner.select_model(path)
        self.refresh_models()

    def change_mode(self):
        self.add_device.setVisible(self.multi_mode.isChecked())
        self.status.setText('Lokal · Bereit' if self.local_mode.isChecked() else self.device_mode_status())
        self.refresh()

    def device_mode_status(self):
        if self.pairing.connected:
            return 'Geräte verbunden · Modellabgleich im Gerätefenster'
        return 'Gerätemodus · Verbinde ein Gerät, um die Modelle abzugleichen.'

    def open_devices(self):
        if not self.pairing.busy:
            self.pairing.reload_interfaces()
        self.devices.show()
        self.devices.raise_()

    def connection_state(self):
        connected = self.pairing.connected
        if connected and not self.was_connected:
            self.devices.hide()
            if self.multi_mode.isChecked():
                self.status.setText(self.device_mode_status())
        if self.was_connected and not connected and self.multi_mode.isChecked():
            self.status.setText('Geräteverbindung beendet.')
        self.was_connected = connected

    def submit(self):
        if self.runner.busy or not self.local_mode.isChecked():
            return
        text = self.prompt.toPlainText().strip()
        if not text:
            return
        skill = self.integrations.skill_prompt(self.chat_id)
        history = '\n\n'.join(('Nutzer' if m['role'] == 'user' else 'Assistent') + ': ' + m['text']
                              for m in self.messages if m['text'] and not m.get('excluded_from_history'))
        prompt = '\n\n'.join(part for part in (skill, history, self.pending_context, 'Nutzer: ' + text) if part)
        if len(prompt) > 12000:
            self.status.setText('Die Eingabe mit Verlauf überschreitet 12000 Zeichen. Kürze den Entwurf oder beginne einen neuen Chat.')
            return
        if not self.chat_id:
            self.create_chat()
            self.prompt.setPlainText(text)
        self.messages.extend([{'role': 'user', 'text': text},
                              {'role': 'assistant', 'text': '', 'thinking': '', 'pending': True}])
        self.stream = []
        if not self.runner.start(prompt):
            del self.messages[-2:]
            self.stream = None
            return
        self.prompt.clear()
        self.pending_context = ''
        self.store.save(self.chat_id, self.messages)
        self.render()

    def append_output(self, text):
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
        self.copy_button.setEnabled(any(m['role'] == 'assistant' and m['text'] for m in self.messages))

    def finished(self, status):
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
            if status != 'Lokaler Lauf beendet.':
                message['status'] = status
                if reply.thinking_open and reply.thinking and not reply.answer and not self.runner.input_truncated:
                    message['status'] += ' Der Lauf hat nur Denktext geliefert.'
            elif not reply.answer:
                message['status'] = 'Denktext ohne finale Antwort.' if reply.thinking else 'Keine Textantwort erhalten.'
            elif reply.thinking_open:
                message['status'] = 'Denktext wurde vor dem Abschluss unterbrochen.'
            self.stream = None
        if self.chat_id:
            self.store.save(self.chat_id, self.messages)
            self.title.setText(self.store.db.execute('SELECT name FROM chats WHERE id=?', (self.chat_id,)).fetchone()[0])
        self.refresh_tree()
        self.render()
        self.finish_close()

    def refresh(self, *_):
        busy = self.runner.busy
        for widget in (self.tree, self.new_project, self.new_chat, self.delete_chat, self.models, self.skill_button, self.mcp_button, self.mode):
            widget.setEnabled(not busy)
        self.prompt.setReadOnly(busy)
        can_send = (not busy and self.local_mode.isChecked()
                    and bool(self.prompt.toPlainText().strip()) and not self.runner.unavailable_reason())
        self.send.setEnabled(can_send)
        self.send.setToolTip('' if self.local_mode.isChecked() else 'Zum Chatten Einzelgerät wählen.')
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)

    def copy_answer(self):
        for message in reversed(self.messages):
            if message['role'] == 'assistant' and message['text']:
                QApplication.clipboard().setText(message['text'])
                break

    def open_link(self, url):
        if url.scheme() in ('https', 'http') and QMessageBox.question(self, 'Link öffnen', url.toString()) == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(url)

    def dictation(self):
        shortcut = 'die konfigurierte Diktier-Taste (häufig zweimal Fn)' if platform.system() == 'Darwin' else 'Windows + H'
        QMessageBox.information(self, 'Spracheingabe', f'Klicke in das Nachrichtenfeld und verwende {shortcut}. Aktiviere Diktat bei Bedarf in den Systemeinstellungen. Die Verarbeitung richtet sich nach deinen Betriebssystem-Einstellungen.')
        self.prompt.setFocus()

    def apply_font(self):
        font = self.font()
        font.setPointSize(self.settings.value('font_size', 11, type=int))
        self.setFont(font)

    def apply_theme(self):
        from .app import icon
        dark = self.settings.value('dark_theme', False, type=bool)
        colors = DARK if dark else LIGHT
        self.setStyleSheet(workspace_style(colors))
        self.toggle.setIcon(icon('layout-dashboard', colors['muted']))
        self.settings_button.setIcon(icon('settings', colors['muted']))
        for action in (self.toggle, self.settings_button):
            action.setIconSize(QSize(16, 16))

    def open_settings(self, section=None):
        if self.preferences is None:
            self.preferences = QDialog(self)
            self.preferences.setWindowTitle('Einstellungen · Cedexia Nexus')
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
            label = QLabel('Einstellungen')
            label.setObjectName('workspaceBrand')
            navigation.addWidget(label)
            self.settings_navigation = QListWidget()
            self.settings_navigation.setObjectName('settingsNavigation')
            self.settings_navigation.setAccessibleName('Einstellungsbereiche')
            navigation.addWidget(self.settings_navigation, 1)
            advanced = self.button('Prüfung und Demo', self.open_advanced, navigation)
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

            appearance = QWidget()
            form = QFormLayout(appearance)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(12)
            size = QSpinBox()
            size.setRange(9, 20)
            size.setValue(self.settings.value('font_size', 11, type=int))
            size.valueChanged.connect(lambda value: (self.settings.setValue('font_size', value), self.apply_font()))
            form.addRow('Schriftgröße', size)
            dark = QCheckBox('Dunkles Erscheinungsbild')
            dark.setChecked(self.settings.value('dark_theme', False, type=bool))
            dark.toggled.connect(lambda value: (self.settings.setValue('dark_theme', value), self.apply_theme()))
            form.addRow(dark)
            add_page(appearance, 'Erscheinungsbild')
            models = QWidget()
            form = QFormLayout(models)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(12)
            notes = QLabel('Gilt ab dem nächsten Modellstart. Ein größerer Kontext benötigt mehr Speicher.')
            notes.setWordWrap(True)
            notes.setObjectName('libraryStatus')
            form.addRow(notes)
            for key, title, default, minimum, maximum in [('context', 'Kontexttokens', 4096 if self.runner.windows else 16384, 512, 131072), ('predict', 'Ausgabetokens', 2048, 1, 8192)]:
                field = QSpinBox()
                field.setRange(minimum, maximum)
                field.setValue(self.settings.value(key, default, type=int))
                field.valueChanged.connect(lambda value, k=key: self.settings.setValue(k, value))
                form.addRow(title, field)
            reasoning = QCheckBox('Reasoning anfordern (modellabhängig)')
            reasoning.setChecked(self.settings.value('reasoning', False, type=bool))
            reasoning.toggled.connect(lambda value: self.settings.setValue('reasoning', value))
            form.addRow(reasoning)
            actions = QHBoxLayout()
            self.button('Modelle hinzufügen …', self.pick_model, actions).setProperty('primary', True)
            self.button('Auswahl entfernen', self.forget_model, actions)
            actions.addStretch()
            form.addRow(actions)
            add_page(models, 'Modelle')
            speech = QWidget()
            speech_layout = QVBoxLayout(speech)
            speech_layout.setContentsMargins(0, 0, 0, 0)
            speech_button = self.button('Systemdiktat verwenden', self.dictation, speech_layout)
            speech_layout.setAlignment(speech_button, Qt.AlignmentFlag.AlignLeft)
            speech_layout.addStretch()
            add_page(speech, 'Spracheingabe')
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
            device_button = self.button('Geräteverbindung verwalten', self.open_devices, devices_layout)
            devices_layout.setAlignment(device_button, Qt.AlignmentFlag.AlignLeft)
            devices_layout.addStretch()
            add_page(devices, 'Geräte')
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
        menu.addAction('Verwalten …', lambda: self.open_settings('Skills' if kind == 'skills' else 'MCPs'))
        if kind == 'mcps':
            menu.addAction('Werkzeuge aufrufen …', lambda: self.open_settings('MCPs'))
        button = self.skill_button if kind == 'skills' else self.mcp_button
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def activate_integration(self, kind, identifier, enabled):
        self.integrations.activate(self.chat_id, kind, identifier, enabled)
        if kind == 'mcps' and not enabled:
            self.pending_context = ''
        self.refresh_integrations()

    def set_context(self, text):
        self.pending_context = text
        self.status.setText('MCP-Ergebnis wird bei der nächsten Nachricht mitgesendet.')

    def forget_model(self):
        self.runner.remove_model()
        self.refresh_models()

    def open_advanced(self):
        if self.advanced is None:
            from .app import NexusWindow
            self.advanced = NexusWindow()
        self.advanced.show()
        self.advanced.raise_()

    def closeEvent(self, event):
        if self.runner.busy or self.pairing.busy or self.mcp_panel.connection:
            self.closing = True
            self.runner.stop()
            self.pairing.close_session()
            self.mcp_panel.disconnect()
            event.ignore()
            return
        self.devices.close()
        if self.preferences:
            self.preferences.close()
        if self.advanced:
            self.advanced.close()
        self.device_timer.stop()
        self.store.db.close()
        event.accept()

    def finish_close(self, *_):
        if self.closing and not self.runner.busy and not self.pairing.busy and not self.mcp_panel.connection:
            self.close()
