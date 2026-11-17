# Chat und Einstellungen · NX-067

Ab Version 0.1.73:

- **Neuer Chat:** Chat-Icon rechts neben „Cedexia Nexus“. Ein neues Projekt
  beginnt mit einem Chat. **Auswahl löschen** entfernt den gewählten Chat oder
  nach Bestätigung das Projekt mit allen Chats und deren Skill-/MCP-Auswahl.
  Die Bibliotheken und ursprünglichen Dateien bleiben erhalten. Während
  Berechnung, Dateilesen oder Terminalausführung ist der Wechsel gesperrt.
- **Sidebar:** Icon links neben der Chatüberschrift, kurze Ein-/Ausklappanimation;
  Zustand bleibt nach Neustart erhalten.
- **Einstellungen → Allgemein:** Version, Commit und Deutsch/Englisch. Die
  Bedienoberfläche wechselt unmittelbar; eigene Chattexte, Projektnamen und
  Modellnamen werden nicht übersetzt. Einige technische Backend-Diagnosen und
  die separate frühe Demo bleiben deutsch.
- **Einstellungen → Modelle:** Bibliothekseintrag wählen und **Als Standardmodell
  verwenden**. Der Standard gilt beim Appstart und für neue Chats. Eine temporäre
  Modellauswahl ändert ihn nicht. Entfernen des Eintrags entfernt auch den
  Standardverweis, niemals die GGUF-Datei.
- **Antwort kopieren:** kleines Icon direkt unter jeder fertigen Antwort.
  Es kopiert Markdown ohne Denktext. Codeblöcke haben eigene Kopieraktionen.
- **Thinking:** standardmäßig geschlossen, beim Öffnen in gedämpfter Schrift.
  `<think>` und Ministrals `[THINK]` werden über Streaminggrenzen erkannt;
  `--special` erhält die dafür nötigen Runtime-Tokens. Literale Tags in
  Markdown-Code bleiben erhalten. Alte Antworten, bei denen die Runtime die
  Trennmarkierungen bereits entfernt hat, lassen sich nicht zuverlässig
  rückwirkend aufteilen.

## Dateianhänge

Das **Plus-Icon** unter dem Eingabefeld öffnet die Dateiauswahl. Maximal acht
Dateien mit jeweils 20 MiB. Vor dem Versand lassen sie sich einzeln entfernen.
Dateinamen werden im Chat angezeigt. UTF-8-Textdateien (u. a. TXT, Markdown,
JSON, CSV, Quelltext) und textbasierte PDFs werden lokal ausgelesen. Pro Datei
maximal 8000 Zeichen, bei PDFs maximal 50 Seiten; ein gekürzter Auszug wird
am Anhang gekennzeichnet. Das gemeinsame Eingabelimit inklusive Verlauf bleibt
12000 Zeichen, bei Überschreitung bleibt der Entwurf erhalten.

Bilder, gescannte PDFs und andere Binärformate können angehängt werden, **werden
von der aktuellen Text-Runtime nicht analysiert**. Dies steht vor dem Versand
am Anhang und wird auch dem Modell als Einschränkung übergeben. Es gibt kein
OCR und keinen heimlichen Upload. Für Bildverständnis sind eine gesondert
validierte multimodale Runtime und passende Projektionsgewichte erforderlich.

Dateiname, ursprünglicher lokaler Pfad und gelesener Textauszug werden in der
lokalen Chatdatenbank gespeichert; Originaldateien werden weder geändert noch
kopiert. Bei gemeinsamer Inferenz gelten dieselben Vertrauensgrenzen wie für
sonstigen Chatkontext. Anhänge sind externe Daten, keine Befehlsfreigabe.

## Befehlsfreigaben und lokales Terminal

Das **Schild-Icon** unter dem Chat zeigt ein Menü mit vier gespeicherten Stufen:

| Stufe | Verhalten |
| --- | --- |
| Aus | Keine neuen Terminalbefehle, MCP-Verbindungen oder MCP-Werkzeugaufrufe. |
| Jeden Befehl prüfen (Vorgabe) | Zeigt den konkreten Aufruf und verlangt eine einmalige Bestätigung. |
| Automatische Prüfung | Das gewählte lokale Modell bewertet den konkreten Aufruf. Nur ein vollständig beendeter Lauf mit exakt positivem JSON-Urteil erlaubt ihn. Fehler, Abbruch und unklare Antworten verweigern. |
| Auto | Führt ausdrücklich angestoßene Aufrufe ohne zusätzliche Rückfrage aus. |

Der Modus gilt appweit und wird im Tooltip des Schild-Icons angezeigt. Die
Agent-Prüfung soll nur eindeutig lesende lokale Operationen zulassen. Sie ist
experimentell und kann sich irren; sie ersetzt keine Sandbox oder menschliche
Prüfung. Ein fehlendes/ungeeignetes Modell führt zu keiner Freigabe.

**Lokales Terminal** im selben Menü zeigt Befehl, Arbeitsordner, Ausgabe und
Exit-Code. Auf macOS läuft Bash, auf Windows Windows PowerShell ohne Profil
und ohne interaktive Eingabe. Normale Benutzerrechte, keine automatische
Erhöhung; 60 Sekunden Zeitlimit und 64 KiB Ausgabelimit. **Stoppen** beendet den
Prozess (auf macOS die gestartete Prozessgruppe, auf Windows `taskkill /T /F`).
Dies ist keine Isolation gegen bewusst abgekoppelte Hintergrundprozesse.

Shell-Codeblöcke bieten **Im Terminal öffnen** als explizite Übernahme; diese
Aktion führt noch nichts aus. Erst **Ausführen** geht durch die gewählte
Freigabestufe. Terminalausgabe kann bewusst als Kontext in denselben Chat
übernommen werden. Es gibt keinen autonomen Werkzeug-Loop, keine Remote-Shell
und keine Ausgabe-/Befehlshistorie auf Disk. Nach Übernahme in eine Nachricht
ist das ausgewählte Ergebnis Teil des lokal gespeicherten Chats.

## Prüfstand

Mac, Python 3.13, Qt 6.8.3: 99 Tests bestanden. Neue Nachweise umfassen
Projekt-Löschkaskade/Abbruch, Standardmodell/Neustart, echten PDF-Text,
Anhang-Persistenz/Chatwechsel, alle Freigabestufen mit synthetischen
Modellurteilen, echten harmlosen Terminalaufruf, Sprachwechsel,
Sidebaranimation, Antwortkopie und Ministral-Streamingmarker.

Ein echter lokaler Ministral-3-3B-Reasoning-Q8_0-Metal-Lauf mit `--special`
lieferte getrennten Denktext und die finale Antwort „OK“, vollständigen
Endmarker und Exit-Code 0. Sichtprüfung des dunklen Chats bestätigte Icons,
zugeklapptes Thinking und lesbaren ausgeklappten Denktext. Physische
Windows-UI-/GPU- und Zwei-Geräte-Abnahme bleiben gesonderte Nachweise.

## Native Nachprüfung · 0.1.74

Bei der tatsächlichen Mac-Prüfung mit vorhandenen Chats und aktivem
Accessibility-Zugriff stürzte 0.1.73 beim Öffnen der Einstellungen im
Cocoa-Plugin ab. Ein leerer Testchat reproduzierte das nicht. Das
Einstellungsfenster übernimmt jetzt das vorhandene Stylesheet, ohne den
bestehenden Chat beim Öffnen global neu zu formatieren. Mit derselben isolierten
Kopie der vorhandenen Chats blieb der native Dialog danach stabil. Der
Paket-Smoke-Test öffnet ebenfalls die Einstellungen; Dropdown-Views werden
nicht mehr unnötig ersetzt. Das ist kein allgemeiner Nachweis für alle
Screenreader-/Accessibility-Flüsse.
