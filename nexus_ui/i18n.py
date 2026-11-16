"""Small explicit German/English UI catalogue; user content and protocol values stay untouched."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (QWidget, QLabel, QAbstractButton, QLineEdit, QPlainTextEdit,
                               QComboBox, QListWidget)

_language = 'de'
EN = {'Neuer Chat': 'New chat',
 'Neues Projekt': 'New project',
 'Projektname': 'Project name',
 '+ Projekt': '+ Project',
 'Meine Chats': 'My chats',
 'Projekte und Chats': 'Projects and chats',
 'Auswahl löschen': 'Delete selection',
 'Chat löschen': 'Delete chat',
 'Projekt löschen': 'Delete project',
 'Diesen lokal gespeicherten Chat löschen?': 'Delete this locally stored chat?',
 'Projekt „{name}“ und alle {count} Chats dauerhaft löschen?': 'Permanently delete project “{name}” and all {count} '
                                                               'chats?',
 'Einstellungen': 'Settings',
 'Allgemein': 'General',
 'App-Version': 'App version',
 'App-Sprache': 'App language',
 'Einstellungen · Cedexia Nexus': 'Settings · Cedexia Nexus',
 'Einstellungsbereiche': 'Settings categories',
 'Erscheinungsbild': 'Appearance',
 'Schriftgröße': 'Font size',
 'Dunkles Erscheinungsbild': 'Dark appearance',
 'Modelle': 'Models',
 'Spracheingabe': 'Voice input',
 'Geräte': 'Devices',
 'Prüfung und Demo': 'Diagnostics and demo',
 'Einzelgerät': 'Single device',
 'Mehrgeräte': 'Multiple devices',
 'Ausführungsmodus': 'Execution mode',
 'Modell lokal auf diesem Gerät ausführen': 'Run the model locally on this device',
 'Ein zweites Gerät koppeln und Modelle abgleichen': 'Pair another device and compare model weights',
 'Geräte verbinden …': 'Connect devices …',
 'Geräte verbinden · Cedexia Nexus': 'Connect devices · Cedexia Nexus',
 'Sidebar ein- oder ausblenden': 'Show or hide sidebar',
 'Modell für diesen Chat': 'Model for this chat',
 'Modell auswählen': 'Choose model',
 'Nachricht schreiben …': 'Write a message …',
 'Nachricht': 'Message',
 'Senden': 'Send',
 'Stoppen': 'Stop',
 'Diktieren': 'Dictate',
 'Lokal · Bereit': 'Local · Ready',
 'Zu Einzelgerät wechseln': 'Switch to single device',
 'Beide Geräte bereit · Lastverteilung automatisch': 'Both devices ready · Automatic workload allocation',
 'Automatische Lastverteilung · beide Geräte rechnen.': 'Automatic workload allocation · Both devices are computing.',
 'Antwort kopieren': 'Copy response',
 'Du': 'You',
 'Antwort': 'Response',
 'Chatverlauf': 'Chat history',
 'Wähle unten ein Modell und schreibe eine Nachricht.': 'Choose a model below and write a message.',
 'Denktext': 'Thinking',
 'Denktext anzeigen': 'Show thinking',
 'Denktext ausblenden': 'Hide thinking',
 'Antwort wird erstellt …': 'Generating response …',
 'Code kopieren': 'Copy code',
 'Dateien anhängen': 'Attach files',
 'Anhänge': 'Attachments',
 'Anhang entfernen': 'Remove attachment',
 'Höchstens 8 Dateien pro Nachricht.': 'A maximum of 8 files per message.',
 'Dateien werden gelesen …': 'Reading files …',
 'Dateien angehängt. Hinweise an den Anhängen beachten.': 'Files attached. Check the notes on each attachment.',
 ' · Text wird mitgesendet': ' · Text will be included',
 'Datei fehlt oder ist größer als 20 MiB.': 'File is missing or exceeds 20 MiB.',
 'PDF ist geschützt oder nicht lesbar.': 'PDF is protected or unreadable.',
 'Kein auslesbarer Text · gescannte PDFs benötigen OCR.': 'No extractable text · Scanned PDFs require OCR.',
 'Textauszug · auf 8000 Zeichen / 50 Seiten begrenzt.': 'Excerpt · Limited to 8000 characters / 50 pages.',
 'Textauszug · auf 8000 Zeichen begrenzt.': 'Excerpt · Limited to 8000 characters.',
 'Textdatei muss UTF-8 verwenden.': 'Text files must use UTF-8.',
 'Binärdatei kann nicht als Text gelesen werden.': 'Binary file cannot be read as text.',
 'Bild angehängt · dieses Textmodell kann Bilder nicht analysieren.': 'Image attached · This text model cannot analyse '
                                                                      'images.',
 'Datei angehängt · Inhalt wird von dieser Runtime nicht ausgewertet.': 'File attached · This runtime cannot interpret '
                                                                        'its contents.',
 'Befehlsfreigabe': 'Command permissions',
 'Befehlsfreigabe: ': 'Command permissions: ',
 'Aus · Befehle verboten': 'Off · Commands prohibited',
 'Jeden Befehl prüfen': 'Review every command',
 'Automatische Prüfung · Agent prüft': 'Automatic review · Agent checks',
 'Auto · Alles erlaubt': 'Auto · Allow all',
 'Lokales Terminal …': 'Local terminal …',
 'Lokales Terminal · Cedexia Nexus': 'Local terminal · Cedexia Nexus',
 'Befehle sind ausgeschaltet.': 'Commands are disabled.',
 'Befehl freigeben': 'Approve command',
 'Diesen Aufruf einmal ausführen?': 'Run this invocation once?',
 'Befehl nicht freigegeben.': 'Command not approved.',
 'Agent-Prüfung: freigegeben.': 'Agent review: approved.',
 'Agent-Prüfung: nicht freigegeben.': 'Agent review: not approved.',
 'Arbeitsordner': 'Working directory',
 'Ordner …': 'Folder …',
 'Lokalen Terminalbefehl eingeben …': 'Enter a local terminal command …',
 'Bereit': 'Ready',
 'Ausführen': 'Run',
 'Ergebnis im Chat verwenden': 'Use result in chat',
 'Befehl und vorhandenen Arbeitsordner angeben.': 'Enter a command and an existing working directory.',
 'Befehl läuft …': 'Command running …',
 'Beendet · Exit-Code {code}': 'Finished · Exit code {code}',
 'Befehle laufen mit deinen Benutzerrechten auf diesem Gerät. Prüfe Befehl und Ordner vor der Freigabe. Keine erhöhte Berechtigung. Zeitlimit: 60 Sekunden.': 'Commands '
                                                                                                                                                              'run '
                                                                                                                                                              'with '
                                                                                                                                                              'your '
                                                                                                                                                              'user '
                                                                                                                                                              'permissions '
                                                                                                                                                              'on '
                                                                                                                                                              'this '
                                                                                                                                                              'device. '
                                                                                                                                                              'Check '
                                                                                                                                                              'the '
                                                                                                                                                              'command '
                                                                                                                                                              'and '
                                                                                                                                                              'directory '
                                                                                                                                                              'before '
                                                                                                                                                              'approval. '
                                                                                                                                                              'No '
                                                                                                                                                              'elevated '
                                                                                                                                                              'privileges. '
                                                                                                                                                              'Time '
                                                                                                                                                              'limit: '
                                                                                                                                                              '60 '
                                                                                                                                                              'seconds.',
 'Modellbibliothek': 'Model library',
 'GGUF hinzufügen …': 'Add GGUF …',
 'Auswahl entfernen': 'Remove selection',
 'Für Chat und Geräteabgleich verwenden': 'Use for chat and device matching',
 'Als Standardmodell verwenden': 'Set as default model',
 ' · Standard': ' · Default',
 'Lokale Modelle': 'Local models',
 'Kontexttokens': 'Context tokens',
 'Ausgabetokens': 'Output tokens',
 'Bis Kontextgrenze': 'Until context limit',
 'Reasoning anfordern (modellabhängig)': 'Request reasoning (model dependent)',
 'CPU statt NVIDIA-GPU verwenden': 'Use CPU instead of NVIDIA GPU',
 'Änderungen gelten ab dem nächsten Modellstart.': 'Changes apply on the next model run.',
 'Füge eine lokale GGUF-Datei hinzu.': 'Add a local GGUF file.',
 'Systemdiktat verwenden': 'Use system dictation',
 'Geräteverbindung verwalten': 'Manage device connection',
 'Verwalten …': 'Manage …',
 'Werkzeuge aufrufen …': 'Call tools …',
 'MCP-Ergebnis wird bei der nächsten Nachricht mitgesendet.': 'The tool result will be included in the next message.',
 'Der vorherige Lauf wurde unterbrochen.': 'The previous run was interrupted.',
 'Die Eingabe mit Verlauf überschreitet 12000 Zeichen. Kürze den Entwurf oder beginne einen neuen Chat.': 'Input '
                                                                                                          'including '
                                                                                                          'history '
                                                                                                          'exceeds '
                                                                                                          '12000 '
                                                                                                          'characters. '
                                                                                                          'Shorten the '
                                                                                                          'draft or '
                                                                                                          'start a new '
                                                                                                          'chat.',
 'Denktext ohne finale Antwort.': 'Thinking without a final response.',
 'Keine Textantwort erhalten.': 'No text response received.',
 'Denktext wurde vor dem Abschluss unterbrochen.': 'Thinking was interrupted before completion.',
 'Link öffnen': 'Open link',
 'Antwort gestoppt.': 'Response stopped.',
 'Werkzeug nicht freigegeben.': 'Tool invocation not approved.',
 'Werkzeug wird aufgerufen …': 'Calling tool …',
 'Argumente passen nicht zum angezeigten JSON-Schema.': 'Arguments do not match the displayed JSON schema.',
 'Skills suchen …': 'Search skills …',
 'Skills suchen': 'Search skills',
 'Nach Name und Markdown-Inhalt suchen': 'Search by name and Markdown content',
 'Skillbibliothek': 'Skill library',
 'Neu': 'New',
 'Name des Skills': 'Skill name',
 'Skillname': 'Skill name',
 'Skill als Markdown': 'Skill Markdown',
 'Löschen': 'Delete',
 'Skill importieren': 'Import skill',
 'Importieren …': 'Import …',
 'Speichern': 'Save',
 'Suchergebnisse': 'Search results',
 'Abbrechen': 'Cancel',
 'Verbinden': 'Connect',
 'Trennen': 'Disconnect',
 'Adresse / Programm': 'Address / program',
 'Argumente (JSON)': 'Arguments (JSON)',
 'Token (nur Sitzung)': 'Token (session only)',
 'Vollständiger Programmpfad oder https://…/mcp': 'Full program path or https://…/mcp',
 'Nach dem Verbinden: Werkzeugbeschreibung und Eingabeschema': 'After connecting: tool description and input schema',
 'Werkzeugargumente als JSON-Objekt': 'Tool arguments as a JSON object',
 'Werkzeugargumente als JSON': 'Tool arguments as JSON',
 'Werkzeug mit diesen Argumenten aufrufen': 'Call tool with these arguments',
 'Werkzeugergebnis · vor der Übernahme bei Bedarf kürzen': 'Tool result · Shorten before using if needed',
 'Ergebnis als Kontext in diesen Chat übernehmen': 'Use result as context in this chat',
 'Verbindung wird aufgebaut …': 'Connecting …',
 'Verbindung getrennt.': 'Disconnected.',
 'Verbindung nicht freigegeben.': 'Connection not approved.',
 'Name und Markdown dürfen nicht leer sein.': 'Name and Markdown must not be empty.',
 'Ein Skill darf höchstens 128 KiB enthalten.': 'A skill must not exceed 128 KiB.',
 'Noch keine Skills vorhanden.': 'No skills yet.',
 'Keine passenden Skills.': 'No matching skills.',
 'Skill speichern': 'Save skill',
 'Skill löschen': 'Delete skill',
 'Diesen Skill aus der Bibliothek und allen Chat-Auswahlen entfernen?': 'Remove this skill from the library and all '
                                                                        'chats?',
 'Gib einen Namen ein.': 'Enter a name.',
 'MCP entfernen': 'Remove MCP',
 'Verbindung aus den Einstellungen und Chats entfernen?': 'Remove this connection from settings and chats?',
 'Die Datei überschreitet 128 KiB.': 'The file exceeds 128 KiB.',
 'Skillimport': 'Skill import',
 'Datei konnte nicht importiert werden. UTF-8-Markdown bis 128 KiB wird unterstützt.': 'Could not import file. UTF-8 '
                                                                                       'Markdown up to 128 KiB is '
                                                                                       'supported.',
 'Aktiviere diese MCP-Verbindung unter dem Chat und beende laufende Generierungen.': 'Enable this MCP connection below '
                                                                                     'the chat and finish any running '
                                                                                     'generation.',
 'Wähle eine vorhandene ausführbare Datei, etwa Python oder Node.': 'Select an existing executable, such as Python or '
                                                                    'Node.',
 'Argumente müssen ein JSON-Array aus Strings sein.': 'Arguments must be a JSON array of strings.',
 'HTTPS erforderlich. Lokale Loopback-Server dürfen HTTP verwenden.': 'HTTPS required. Local loopback servers may use '
                                                                      'HTTP.',
 'MCP-Verbindung fehlgeschlagen. Adresse, Programm, Berechtigung und Server prüfen.': 'MCP connection failed. Check '
                                                                                      'address, program, permissions '
                                                                                      'and server.',
 'Das Werkzeug lieferte keine Textdaten.': 'The tool returned no text data.',
 'Werkzeugaufruf fehlgeschlagen oder Zeitlimit erreicht. Prüfe den Server vor einem erneuten Aufruf.': 'Tool '
                                                                                                       'invocation '
                                                                                                       'failed or '
                                                                                                       'timed out. '
                                                                                                       'Check the '
                                                                                                       'server before '
                                                                                                       'retrying.',
 'Verbindung': 'Connection',
 'Netzwerkverbindung': 'Network connection',
 'Lokale Netzwerkadresse': 'Local network address',
 'Einladung erstellen': 'Create invitation',
 'Aktualisieren': 'Refresh',
 'Netzwerkadapter neu einlesen': 'Refresh network adapters',
 'WLAN-Namen freigeben …': 'Allow Wi-Fi name access …',
 'Geräte im Netz suchen': 'Find devices on network',
 'Cedexia-Geräte im lokalen Netz': 'Cedexia devices on local network',
 'Noch kein anderes Gerät gefunden': 'No other devices found',
 'Kopplung anfragen': 'Request pairing',
 'Code stimmt überein': 'Code matches',
 'Ablehnen': 'Decline',
 'Gefundene Geräte': 'Discovered devices',
 'Einladungscode': 'Invitation code',
 'Code vom einladenden Gerät': 'Code from inviting device',
 'Code anzeigen': 'Show code',
 'Code verbergen': 'Hide code',
 'Beitreten': 'Join',
 'Lokales Modell auswählen …': 'Select local model …',
 'Gewichte erneut prüfen': 'Recheck weights',
 'HTTPS-Bezugsquelle für dieses GGUF': 'HTTPS download source for this GGUF',
 'HTTPS-Bezugsquelle für genau diese GGUF-Datei': 'HTTPS download source for this exact GGUF file',
 'Bezugsquelle im Browser öffnen': 'Open download source in browser',
 'Geräte verbinden': 'Connect devices',
 'Gemeinsames Rechnen aktivieren': 'Enable shared computing',
 'Gemeinsames Rechnen beenden': 'Stop shared computing',
 'Einladungscode anzeigen oder kopieren und auf dem zweiten Gerät eingeben. Die Einladung gilt fünf Minuten.': 'Show '
                                                                                                               'or '
                                                                                                               'copy '
                                                                                                               'the '
                                                                                                               'invitation '
                                                                                                               'code '
                                                                                                               'and '
                                                                                                               'enter '
                                                                                                               'it on '
                                                                                                               'the '
                                                                                                               'other '
                                                                                                               'device. '
                                                                                                               'The '
                                                                                                               'invitation '
                                                                                                               'expires '
                                                                                                               'after '
                                                                                                               'five '
                                                                                                               'minutes.',
 'Verbinde beide Geräte mit demselben lokalen Netz über Ethernet oder WLAN. Wähle auf jedem Gerät seine Netzwerkverbindung.': 'Connect '
                                                                                                                              'both '
                                                                                                                              'devices '
                                                                                                                              'to '
                                                                                                                              'the '
                                                                                                                              'same '
                                                                                                                              'local '
                                                                                                                              'network '
                                                                                                                              'using '
                                                                                                                              'Ethernet '
                                                                                                                              'or '
                                                                                                                              'Wi-Fi. '
                                                                                                                              'Select '
                                                                                                                              'the '
                                                                                                                              'network '
                                                                                                                              'connection '
                                                                                                                              'on '
                                                                                                                              'each '
                                                                                                                              'device.',
 'WLAN verbunden. Der Netzwerkname ist vom System nicht verfügbar.': 'Wi-Fi connected. The network name is unavailable '
                                                                     'from the system.',
 'Kein aktives WLAN erkannt. Verbinde dieses Gerät in den Systemeinstellungen mit einem WLAN und klicke dann auf „Aktualisieren“.': 'No '
                                                                                                                                    'active '
                                                                                                                                    'Wi-Fi '
                                                                                                                                    'detected. '
                                                                                                                                    'Connect '
                                                                                                                                    'this '
                                                                                                                                    'device '
                                                                                                                                    'to '
                                                                                                                                    'Wi-Fi '
                                                                                                                                    'in '
                                                                                                                                    'system '
                                                                                                                                    'settings, '
                                                                                                                                    'then '
                                                                                                                                    'click '
                                                                                                                                    'Refresh.',
 'Geräteerkennung wird gestartet …': 'Starting device discovery …',
 'Einladung kopiert. Füge sie auf dem zweiten Gerät ein.': 'Invitation copied. Paste it on the other device.',
 'Dieses Gerät · Kein Modell ausgewählt.': 'This device · No model selected.',
 'Die ausgewählten GGUF-Gewichte unterscheiden sich.': 'The selected GGUF weights differ.',
 'Warte auf den Modellstatus des zweiten Geräts.': 'Waiting for the other device’s model status.',
 'GGUF-Gewichte werden im Hintergrund geprüft.': 'Checking GGUF weights in the background.',
 'Auf beiden Geräten fehlt ein prüfbares GGUF-Modell.': 'Both devices lack a verifiable GGUF model.',
 'Dieses Gerät kann sein GGUF-Modell nicht prüfen.': 'This device cannot verify its GGUF model.',
 'Das zweite Gerät kann sein GGUF-Modell nicht prüfen.': 'The other device cannot verify its GGUF model.',
 'Identische GGUF-Gewichte auf beiden Geräten.': 'Identical GGUF weights on both devices.',
 'Eine Einladung erstellen oder eine erhaltene Einladung einfügen.': 'Create an invitation or paste a received '
                                                                     'invitation.',
 'Der Einladungscode ist ungültig. Kopiere ihn erneut auf dem anderen Gerät.': 'Invalid invitation code. Copy it again '
                                                                               'on the other device.',
 'Hier ausgewählt · ': 'Selected here · ',
 'Zweites Gerät · ': 'Other device · ',
 'Dieses Gerät · ': 'This device · ',
 'Geräte verbunden · ': 'Devices connected · ',
 ' · verschlüsselt': ' · encrypted',
 'Experimentelle gemeinsame Inferenz: nur eigene Geräte und Testdaten. Auf beiden Geräten aktivieren. Der Kurztest ermittelt GPU-Leistung; WLAN kann die gemeinsame Berechnung verlangsamen.': 'Experimental '
                                                                                                                                                                                               'shared '
                                                                                                                                                                                               'inference: '
                                                                                                                                                                                               'use '
                                                                                                                                                                                               'your '
                                                                                                                                                                                               'own '
                                                                                                                                                                                               'devices '
                                                                                                                                                                                               'and '
                                                                                                                                                                                               'test '
                                                                                                                                                                                               'data '
                                                                                                                                                                                               'only. '
                                                                                                                                                                                               'Enable '
                                                                                                                                                                                               'on '
                                                                                                                                                                                               'both '
                                                                                                                                                                                               'devices. '
                                                                                                                                                                                               'The '
                                                                                                                                                                                               'quick '
                                                                                                                                                                                               'test '
                                                                                                                                                                                               'measures '
                                                                                                                                                                                               'GPU '
                                                                                                                                                                                               'performance; '
                                                                                                                                                                                               'Wi-Fi '
                                                                                                                                                                                               'can '
                                                                                                                                                                                               'slow '
                                                                                                                                                                                               'down '
                                                                                                                                                                                               'shared '
                                                                                                                                                                                               'computation.',
 'Im Terminal öffnen': 'Open in terminal',
 'Agent-Prüfung ist experimentell und kann sich irren. Auto führt freigegebene Aufrufe ohne Rückfrage aus.': 'Agent '
                                                                                                             'review '
                                                                                                             'is '
                                                                                                             'experimental '
                                                                                                             'and can '
                                                                                                             'make '
                                                                                                             'mistakes. '
                                                                                                             'Auto '
                                                                                                             'executes '
                                                                                                             'invocations '
                                                                                                             'without '
                                                                                                             'asking.',
 'Modelldatei wird geprüft … Die Oberfläche bleibt bedienbar.': 'Checking model file … The interface remains '
                                                                'responsive.',
 'Lokales Modell wird geladen …': 'Loading local model …',
 'Lokaler Lauf beendet.': 'Local run complete.',
 'Die Ausgabe endete vorzeitig. Die Antwort kann abgeschnitten sein.': 'Output ended early. The response may be '
                                                                       'truncated.'}


def set_language(language):
    global _language
    _language = language if language in ('de', 'en') else 'de'


def t(source):
    source = next((key for key, value in EN.items() if value == source), source) if source not in EN else source
    return EN.get(source, source) if _language == 'en' else source


def translate_widgets(root):
    """Refresh known UI labels only; never translate editors, chat content or project names."""
    reverse = {value: key for key, value in EN.items()}

    def translated(value):
        return t(reverse.get(value, value))

    for widget in [root, *root.findChildren(QWidget)]:
        with QSignalBlocker(widget):
            if isinstance(widget, (QLabel, QAbstractButton)):
                widget.setText(translated(widget.text()))
            if isinstance(widget, (QLineEdit, QPlainTextEdit)):
                widget.setPlaceholderText(translated(widget.placeholderText()))
            if isinstance(widget, QComboBox) and widget.accessibleName() not in ('Modell für diesen Chat', 'Model for this chat'):
                for index in range(widget.count()):
                    widget.setItemText(index, translated(widget.itemText(index)))
            if isinstance(widget, QListWidget) and widget.objectName() == 'settingsNavigation':
                for index in range(widget.count()):
                    item = widget.item(index)
                    item.setText(translated(item.text()))
            widget.setToolTip(translated(widget.toolTip()))
            widget.setAccessibleName(translated(widget.accessibleName()))
            widget.setWindowTitle(translated(widget.windowTitle()))
