"""Project-oriented desktop workspace built on the existing local runtime and pairing UI."""
import json
from pathlib import Path
import platform
import sqlite3
import uuid

from PySide6.QtCore import Qt, QStandardPaths, QTimer
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QTextBrowser, QDialog, QTabWidget, QFormLayout, QSpinBox, QCheckBox,
    QInputDialog, QMessageBox, QFileDialog)

from .local_model import LocalRunner
from .device_pairing import DevicePairingPage


class ChatBrowser(QTextBrowser):
    def loadResource(self, kind, url):
        # Model-generated Markdown may contain local or remote image references.
        return None


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
        self.chat_id = None
        self.messages = []
        self.closing = False
        self.advanced = None
        self.render_timer = QTimer(self, interval=100, singleShot=True)
        self.render_timer.timeout.connect(self.render)
        body = QWidget()
        self.setCentralWidget(body)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(270)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(20, 24, 20, 20)
        side.addWidget(QLabel('CEDEXIA NEXUS'))
        self.mode = QComboBox()
        self.mode.addItems(['Lokal · Einzelmodell', 'Verbundene Geräte'])
        self.mode.setAccessibleName('Ausführungsmodus')
        side.addWidget(self.mode)
        self.add_device = self.button('+ Gerät hinzufügen', self.open_devices, side)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Projekte und Chats')
        side.addWidget(self.tree, 1)
        self.new_project = self.button('+ Projekt', self.create_project, side)
        self.new_chat = self.button('+ Chat', self.create_chat, side)
        self.delete_chat = self.button('Chat löschen', self.remove_chat, side)
        self.button('⚙  Einstellungen', self.open_settings, side)
        from .app import icon
        side.itemAt(side.count() - 1).widget().setIcon(icon('settings'))
        side.itemAt(side.count() - 1).widget().setText('Einstellungen')
        outer.addWidget(self.sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(28, 20, 28, 22)
        outer.addLayout(main, 1)
        header = QHBoxLayout()
        self.toggle = self.button('☰', self.toggle_sidebar, header)
        self.toggle.setAccessibleName('Sidebar ein- oder ausblenden')
        self.title = QLabel('Neuer Chat')
        header.addWidget(self.title, 1)
        self.button('Antwort kopieren', self.copy_answer, header)
        main.addLayout(header)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        main.addWidget(self.status)
        self.transcript = ChatBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(self.open_link)
        main.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText('Stelle deinem Modell eine Aufgabe …')
        self.prompt.setMaximumHeight(140)
        self.prompt.setAccessibleName('Nachricht')
        main.addWidget(self.prompt)
        composer = QHBoxLayout()
        self.models = QComboBox()
        self.models.setAccessibleName('Modell für diesen Chat')
        composer.addWidget(self.models, 1)
        self.import_model = self.button('+ GGUF', self.pick_model, composer)
        self.dictate = self.button('Diktieren', self.dictation, composer)
        self.send = self.button('Senden', self.submit, composer)
        self.send.setProperty('primary', True)
        self.stop = self.button('Stoppen', self.runner.stop, composer)
        main.addLayout(composer)
        self.devices = QDialog(self)
        self.devices.setWindowTitle('Gerät hinzufügen · Cedexia Nexus')
        self.devices.resize(820, 760)
        device_layout = QVBoxLayout(self.devices)
        self.pairing = DevicePairingPage(self.runner)
        device_layout.addWidget(self.pairing)
        self.pairing.select.clicked.connect(self.pick_model)
        self.pairing.idle.connect(self.finish_close)
        self.device_timer = QTimer(self, interval=500)
        self.device_timer.timeout.connect(self.connection_state)
        self.device_timer.start()
        self.was_connected = False
        self.preferences = None
        self.runner.output.connect(self.append_output)
        self.runner.finished.connect(self.finished)
        self.runner.status.connect(self.status.setText)
        self.runner.busy_changed.connect(self.refresh)
        self.runner.model_changed.connect(self.refresh_models)
        self.models.currentIndexChanged.connect(self.choose_model)
        self.tree.currentItemChanged.connect(self.select_chat)
        self.mode.currentIndexChanged.connect(self.change_mode)
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
        self.prompt.clear()
        self.refresh_tree()
        self.render()

    def select_chat(self, current, previous):
        if current and current.data(0, Qt.ItemDataRole.UserRole)[0] == 'chat':
            self.load_chat(current.data(0, Qt.ItemDataRole.UserRole)[1])

    def remove_chat(self):
        if self.chat_id and QMessageBox.question(self, 'Chat löschen', 'Diesen lokal gespeicherten Chat löschen?') == QMessageBox.StandardButton.Yes:
            with self.store.db:
                self.store.db.execute('DELETE FROM chats WHERE id=?', (self.chat_id,))
            self.chat_id = None
            self.messages = []
            self.refresh_tree()
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
        paths, _ = QFileDialog.getOpenFileNames(self, 'Lokale Modelle', '', 'GGUF (*.gguf)')
        for path in paths:
            self.runner.select_model(path)
        self.refresh_models()

    def change_mode(self):
        self.add_device.setVisible(self.mode.currentIndex() == 1)
        self.status.setText('Lokal · Bereit' if self.mode.currentIndex() == 0 else 'Gerätemodus · Verbindung und Modellabgleich verfügbar. Gemeinsame Inferenz folgt mit NX-011.')
        self.refresh()

    def open_devices(self):
        self.devices.show()
        self.devices.raise_()

    def connection_state(self):
        connected = self.pairing.connected
        if connected and not self.was_connected:
            self.devices.hide()
            self.status.setText('Geräte verbunden · Modellabgleich in den Geräteeinstellungen. Gemeinsame Inferenz folgt mit NX-011.')
        if self.was_connected and not connected:
            self.status.setText('Geräteverbindung beendet.')
        self.was_connected = connected

    def submit(self):
        if self.runner.busy or self.mode.currentIndex() == 1:
            return
        text = self.prompt.toPlainText().strip()
        if not text:
            return
        skill = self.settings.value('skill_text', '', type=str)
        history = '\n\n'.join(('Nutzer' if m['role'] == 'user' else 'Assistent') + ': ' + m['text'] for m in self.messages)
        prompt = '\n\n'.join(part for part in (skill, history, 'Nutzer: ' + text) if part)
        if len(prompt) > 12000:
            self.status.setText('Der Verlauf überschreitet 12000 Zeichen. Beginne einen neuen Chat.')
            return
        if not self.chat_id:
            self.create_chat()
            self.prompt.setPlainText(text)
        self.messages.extend([{'role': 'user', 'text': text}, {'role': 'assistant', 'text': ''}])
        if not self.runner.start(prompt):
            del self.messages[-2:]
            return
        self.prompt.clear()
        self.store.save(self.chat_id, self.messages)
        self.render()

    def append_output(self, text):
        self.messages[-1]['text'] += text
        if not self.render_timer.isActive():
            self.render_timer.start()

    def render(self):
        if not self.messages:
            self.transcript.setPlainText('Womit möchtest du beginnen?\n\nWähle ein lokales Modell und schreibe eine Nachricht.')
            return
        # QTextDocument renders Markdown without executing code or loading external resources.
        html = []
        for message in self.messages:
            document = QTextDocument()
            document.setMarkdown(message['text'], QTextDocument.MarkdownFeature.MarkdownNoHTML)
            html.append('<h3>' + ('Du' if message['role'] == 'user' else 'Nexus') + '</h3>' + document.toHtml())
        self.transcript.setHtml(''.join(html))
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def finished(self, status):
        self.render_timer.stop()
        if self.chat_id:
            self.store.save(self.chat_id, self.messages)
            self.title.setText(self.store.db.execute('SELECT name FROM chats WHERE id=?', (self.chat_id,)).fetchone()[0])
        self.refresh_tree()
        self.render()
        self.finish_close()

    def refresh(self, *_):
        busy = self.runner.busy
        for widget in (self.tree, self.new_project, self.new_chat, self.delete_chat, self.models, self.import_model, self.mode):
            widget.setEnabled(not busy)
        self.prompt.setReadOnly(busy)
        self.send.setEnabled(not busy and self.mode.currentIndex() == 0 and bool(self.prompt.toPlainText().strip()) and not self.runner.unavailable_reason())
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)

    def copy_answer(self):
        for message in reversed(self.messages):
            if message['role'] == 'assistant':
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
        dark = self.settings.value('dark_theme', False, type=bool)
        background, panel, foreground, border = ('#141D2B', '#1D293B', '#E9EEF6', '#41516B') if dark else ('#F5F6F8', '#FFFFFF', '#162033', '#D8DEE8')
        self.setStyleSheet(f'''QWidget {{ background: {background}; color: {foreground}; }}
            QWidget#sidebar {{ background: {panel}; border-right: 1px solid {border}; }}
            QTreeWidget, QTextBrowser {{ background: {background}; border: 0; padding: 12px; }}
            QPlainTextEdit, QComboBox {{ background: {panel}; border: 1px solid {border}; padding: 10px; }}
            QPushButton {{ background: {panel}; border: 1px solid {border}; padding: 9px 12px; }}
            QPushButton[primary="true"] {{ background: #173B70; color: white; }}
            QTreeWidget::item:selected {{ background: #173B70; color: white; }}
            QTreeWidget::item {{ padding: 8px; }}''')

    def open_settings(self):
        if self.preferences is None:
            self.preferences = QDialog(self)
            self.preferences.setWindowTitle('Einstellungen · Cedexia Nexus')
            self.preferences.resize(860, 680)
            layout = QVBoxLayout(self.preferences)
            tabs = QTabWidget()
            layout.addWidget(tabs)
            appearance = QWidget()
            form = QFormLayout(appearance)
            size = QSpinBox()
            size.setRange(9, 20)
            size.setValue(self.settings.value('font_size', 11, type=int))
            size.valueChanged.connect(lambda value: (self.settings.setValue('font_size', value), self.apply_font()))
            form.addRow('Schriftgröße', size)
            dark = QCheckBox('Dunkles Erscheinungsbild')
            dark.setChecked(self.settings.value('dark_theme', False, type=bool))
            dark.toggled.connect(lambda value: (self.settings.setValue('dark_theme', value), self.apply_theme()))
            form.addRow(dark)
            tabs.addTab(appearance, 'Erscheinungsbild')
            models = QWidget()
            form = QFormLayout(models)
            form.addRow(QLabel('Gilt ab dem nächsten Modellstart. Ein größerer Kontext benötigt mehr Speicher.'))
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
            self.button('Modelle hinzufügen', self.pick_model, form)
            self.button('Ausgewähltes Modell aus Liste entfernen', self.forget_model, form)
            tabs.addTab(models, 'Modelle')
            speech = QWidget()
            speech_layout = QVBoxLayout(speech)
            self.button('Systemdiktat verwenden', self.dictation, speech_layout)
            speech_layout.addStretch()
            tabs.addTab(speech, 'Spracheingabe')
            skills = QWidget()
            skills_layout = QVBoxLayout(skills)
            skills_layout.addWidget(QLabel('Lokale Anweisungen für neue Nachrichten'))
            instructions = QPlainTextEdit(self.settings.value('skill_text', '', type=str))
            instructions.textChanged.connect(lambda: self.settings.setValue('skill_text', instructions.toPlainText()[:4000]))
            skills_layout.addWidget(instructions)
            tabs.addTab(skills, 'Skills')
            devices = QWidget()
            devices_layout = QVBoxLayout(devices)
            self.button('Geräteverbindung verwalten', self.open_devices, devices_layout)
            devices_layout.addStretch()
            tabs.addTab(devices, 'Geräte')
            self.button('Erweiterte Modellprüfung und Demo öffnen', self.open_advanced, layout)
        self.preferences.show()
        self.preferences.raise_()

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
        if self.runner.busy or self.pairing.busy:
            self.closing = True
            self.runner.stop()
            self.pairing.close_session()
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
        if self.closing and not self.runner.busy and not self.pairing.busy:
            self.close()
