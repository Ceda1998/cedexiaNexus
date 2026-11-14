"""Native chat controls and Markdown rendering without external resources."""
from PySide6.QtCore import Qt, QTimer
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
        self.resize_timer = QTimer(self, interval=0, singleShot=True)
        self.resize_timer.timeout.connect(self.fit_height)
        self.document().documentLayout().documentSizeChanged.connect(lambda _: self.resize_timer.start())

    def loadResource(self, kind, url):
        return None

    def fit_height(self):
        height = self.document().documentLayout().documentSize().height()
        self.setFixedHeight(max(24, int(height + 1)))

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
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 10)
        heading = 'Du' if role == 'user' else 'Nexus'
        title = QLabel(heading)
        title.setObjectName('messageAuthor')
        layout.addWidget(title)
        if role == 'assistant':
            self.toggle = QPushButton()
            self.toggle.setObjectName('thinkingToggle')
            self.toggle.setProperty('quiet', True)
            self.toggle.setCheckable(True)
            self.toggle.toggled.connect(self.toggle_thinking)
            layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
            self.thinking = MarkdownText(open_link, 'Denktext')
            self.thinking.setObjectName('thinkingText')
            layout.addWidget(self.thinking)
        self.answer = MarkdownText(open_link, 'Nachricht' if role == 'user' else 'Antwort')
        layout.addWidget(self.answer)
        self.state = QLabel()
        self.state.setObjectName('messageState')
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
                copy.setProperty('quiet', True)
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
        frame = QHBoxLayout(self.body)
        frame.setContentsMargins(4, 0, 4, 0)
        column = QWidget()
        column.setMaximumWidth(860)
        frame.addStretch()
        frame.addWidget(column, 100)
        frame.addStretch()
        self.layout = QVBoxLayout(column)
        self.layout.setContentsMargins(0, 8, 0, 10)
        self.layout.setSpacing(13)
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(12, 22, 12, 0)
        heading = QLabel('Neuer Chat')
        heading.setObjectName('transcriptHeading')
        empty_layout.addWidget(heading)
        hint = QLabel('Wähle unten ein Modell und schreibe eine Nachricht.')
        hint.setObjectName('transcriptHint')
        hint.setWordWrap(True)
        empty_layout.addWidget(hint)
        self.layout.addWidget(self.empty)
        self.layout.addStretch()
        self.setWidget(self.body)
        self.rows = []
        self.follow_scroll = True
        self.verticalScrollBar().valueChanged.connect(self.update_scroll_follow)
        self.verticalScrollBar().rangeChanged.connect(self.follow_latest)

    def update_scroll_follow(self, value):
        self.follow_scroll = value >= self.verticalScrollBar().maximum() - 8

    def follow_latest(self, minimum, maximum):
        if self.follow_scroll:
            self.verticalScrollBar().setValue(maximum)

    def clear(self):
        for row in self.rows:
            self.layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows.clear()
        self.follow_scroll = True

    def render(self, messages, running):
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
