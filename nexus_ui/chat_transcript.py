"""Native chat controls and Markdown rendering without external resources."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument, QTextFormat, QTextOption
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .chat_output import code_blocks


class MarkdownText(QTextBrowser):
    def __init__(self, open_link, label):
        super().__init__()
        self.setAccessibleName(label)
        self.setOpenLinks(False)
        self.anchorClicked.connect(open_link)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_height)

    def loadResource(self, kind, url):
        return None

    def fit_height(self, size):
        self.setFixedHeight(max(24, int(size.height() + 1)))

    def set_text(self, text):
        if getattr(self, '_markdown', None) != text:
            self._markdown = text
            self.document().setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownNoHTML)
            block = self.document().firstBlock()
            while block.isValid():
                formatting = block.blockFormat()
                if formatting.nonBreakableLines() or formatting.hasProperty(QTextFormat.Property.BlockCodeLanguage):
                    formatting.setNonBreakableLines(False)
                    QTextCursor(block).setBlockFormat(formatting)
                block = block.next()


class ChatMessage(QWidget):
    def __init__(self, role, open_link):
        super().__init__()
        self.setObjectName('chatMessage')
        self.setProperty('role', role)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 10)
        heading = 'Du' if role == 'user' else 'Nexus'
        title = QLabel(heading)
        title.setObjectName('messageAuthor')
        layout.addWidget(title)
        if role == 'assistant':
            self.toggle = QPushButton()
            self.toggle.setObjectName('thinkingToggle')
            self.toggle.setCheckable(True)
            self.toggle.toggled.connect(self.toggle_thinking)
            layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
            self.thinking = MarkdownText(open_link, 'Denktext')
            layout.addWidget(self.thinking)
        self.answer = MarkdownText(open_link, 'Nachricht' if role == 'user' else 'Antwort')
        layout.addWidget(self.answer)
        self.state = QLabel()
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.copy_actions = QHBoxLayout()
        layout.addLayout(self.copy_actions)
        self.codes = ()

    def toggle_thinking(self, expanded):
        self.toggle.setText('Denktext ausblenden' if expanded else 'Denktext anzeigen')
        self.thinking.setVisible(expanded and not self.toggle.isHidden())

    def update_message(self, message, running):
        answer = message['text']
        self.answer.set_text(answer)
        self.answer.setVisible(bool(answer.strip()))
        if message['role'] == 'assistant':
            thinking = message.get('thinking', '')
            self.toggle.setVisible(bool(thinking))
            self.thinking.set_text(thinking)
            self.toggle_thinking(self.toggle.isChecked())
        state = ('Antwort wird erstellt …' if running else message.get('status', ''))
        self.state.setText(state)
        self.state.setVisible(bool(state))
        codes = tuple(code_blocks(answer)) if message['role'] == 'assistant' and not running else ()
        if self.codes != codes:
            self.codes = codes
            while self.copy_actions.count():
                self.copy_actions.takeAt(0).widget().deleteLater()
            for index, code in enumerate(codes, 1):
                label = 'Code kopieren' if len(codes) == 1 else f'Codeblock {index} kopieren'
                copy = QPushButton(label)
                copy.clicked.connect(lambda checked=False, source=code: QApplication.clipboard().setText(source))
                self.copy_actions.addWidget(copy, alignment=Qt.AlignmentFlag.AlignLeft)


class ChatTranscript(QScrollArea):
    def __init__(self, open_link):
        super().__init__()
        self.open_link = open_link
        self.setObjectName('chatTranscript')
        self.setAccessibleName('Chatverlauf')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.layout.setSpacing(12)
        self.empty = QLabel('Womit möchtest du beginnen?\n\nWähle ein lokales Modell und schreibe eine Nachricht.')
        self.empty.setWordWrap(True)
        self.layout.addWidget(self.empty)
        self.layout.addStretch()
        self.setWidget(self.body)
        self.rows = []

    def clear(self):
        for row in self.rows:
            self.layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows.clear()

    def render(self, messages, running):
        scroll = self.verticalScrollBar()
        follow = scroll.value() >= scroll.maximum() - 8
        self.empty.setVisible(not messages)
        # Existing turns are immutable except for the last reply.
        start = max(0, len(self.rows) - 1)
        for index in range(start, len(messages)):
            message = messages[index]
            if index == len(self.rows):
                row = ChatMessage(message['role'], self.open_link)
                self.rows.append(row)
                self.layout.insertWidget(self.layout.count() - 1, row)
            self.rows[index].update_message(message, running and index == len(messages) - 1)
        self.layout.activate()
        if follow:
            scroll.setValue(scroll.maximum())
