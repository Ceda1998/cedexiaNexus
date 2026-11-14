"""Colors and control styling shared by the desktop workspace and its dialogs."""

LIGHT = {
    'canvas': '#FBFCFE', 'surface': '#FFFFFF', 'sidebar': '#EDF1F6',
    'line': '#D9E1EC', 'text': '#172538', 'muted': '#52657C',
    'hover': '#E4EBF5', 'selection': '#DCE8F8', 'selected_text': '#173B70',
    'focus': '#326BC0', 'accent': '#173B70', 'accent_hover': '#24558D',
    'disabled': '#748299', 'danger': '#A1283D',
}

DARK = {
    'canvas': '#191F29', 'surface': '#222B38', 'sidebar': '#161C26',
    'line': '#38475C', 'text': '#EFF3FA', 'muted': '#A9B8CB',
    'hover': '#2A384A', 'selection': '#294364', 'selected_text': '#E9F2FF',
    'focus': '#8AB7F7', 'accent': '#376EAD', 'accent_hover': '#436FAB',
    'disabled': '#8695AA', 'danger': '#FDA4AE',
}


def workspace_style(c):
    return f"""
        QWidget {{ background: {c['canvas']}; color: {c['text']}; }}
        QLabel {{ background: transparent; }}
        QWidget#sidebar, QWidget#settingsSidebar, QTreeWidget#chatTree,
        QListWidget#settingsNavigation {{ background: {c['sidebar']}; }}
        QWidget#sidebar, QWidget#settingsSidebar {{ border-right: 1px solid {c['line']}; }}
        QWidget#composer {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 9px; }}
        QLabel#workspaceBrand {{ font-size: 17px; font-weight: 700; }}
        QLabel#workspaceTitle, QLabel#settingsTitle {{ font-size: 20px; font-weight: 700; }}
        QLabel#transcriptHeading {{ font-size: 23px; font-weight: 700; }}
        QLabel#sidebarLabel, QLabel#libraryLabel, QLabel#messageAuthor {{ font-weight: 600; }}
        QLabel#sidebarLabel, QLabel#workspaceStatus, QLabel#libraryStatus, QLabel#transcriptHint,
        QLabel#messageState {{ color: {c['muted']}; }}
        QTreeWidget, QListWidget {{
            border: 0; padding: 2px; outline: 0;
            alternate-background-color: {c['canvas']};
        }}
        QTreeWidget::item, QListWidget::item {{ min-height: 24px; padding: 3px 5px; margin: 1px 0; border-radius: 5px; }}
        QTreeWidget#chatTree::branch:selected {{ background: {c['sidebar']}; }}
        QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['hover']}; }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {c['selection']}; color: {c['selected_text']};
        }}
        QListWidget#skillList {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 7px; }}
        QTreeWidget:focus, QListWidget:focus {{ border: 1px solid {c['focus']}; padding: 1px; }}
        QScrollArea, QTextBrowser {{ border: 0; padding: 0; }}
        QWidget#chatMessage[role="user"], QWidget#chatMessage[role="user"] QTextBrowser,
        QTextBrowser#thinkingText {{ background: {c['surface']}; }}
        QWidget#chatMessage[role="user"] {{ border: 1px solid {c['line']}; border-radius: 8px; }}
        QTextBrowser#thinkingText {{ border-left: 2px solid {c['line']}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
            background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 6px;
            min-height: 22px; padding: 5px 8px; selection-background-color: {c['selection']};
            selection-color: {c['selected_text']};
        }}
        QComboBox {{ padding-right: 22px; }}
        QComboBox QAbstractItemView, QMenu {{
            background: {c['surface']}; border: 1px solid {c['line']};
            selection-background-color: {c['selection']}; selection-color: {c['selected_text']};
        }}
        QMenu::item {{ padding: 5px 18px; }}
        QMenu::item:selected {{ background: {c['selection']}; color: {c['selected_text']}; }}
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {c['focus']}; }}
        QPlainTextEdit#chatPrompt {{ border-color: transparent; padding: 5px; }}
        QPlainTextEdit#chatPrompt:focus {{ border-color: {c['focus']}; }}
        QPushButton {{
            min-height: 20px; padding: 5px 10px; border-radius: 6px;
            border: 1px solid {c['line']}; background: {c['surface']}; color: {c['text']};
        }}
        QPushButton[quiet="true"] {{ background: transparent; border-color: transparent; }}
        QPushButton[sidebarAction="true"] {{ text-align: left; }}
        QPushButton[danger="true"] {{ color: {c['danger']}; }}
        QPushButton:hover, QPushButton:checked, QPushButton:pressed {{ background: {c['hover']}; }}
        QPushButton[primary="true"] {{ background: {c['accent']}; border-color: {c['accent']}; color: white; font-weight: 600; }}
        QPushButton[primary="true"]:hover, QPushButton[primary="true"]:pressed {{ background: {c['accent_hover']}; }}
        QPushButton:disabled, QPushButton[primary="true"]:disabled {{
            background: transparent; color: {c['disabled']}; border-color: {c['line']};
        }}
        QPushButton:focus, QPushButton[primary="true"]:focus {{ border: 1px solid {c['focus']}; }}
        QCheckBox:focus {{ outline: 1px solid {c['focus']}; }}
    """
