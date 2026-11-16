**0.1.73 · Chatkomfort, Anhänge und Befehlsfreigaben**

Projekte mit ihren Chats löschen, neuer Chat per Icon, animierte Sidebar,
Standardmodell und Allgemein-Einstellungen mit Version sowie Deutsch/Englisch.
Antworten haben ein Kopiericon direkt am Text. Thinking ist standardmäßig
zugeklappt; Ministrals spezielle Trennmarkierungen werden jetzt korrekt erkannt.
Dunkle Bedienelemente und Dropdowns sind besser lesbar.

Das Plus-Icon fügt lokale Dateien hinzu. Text und PDFs werden begrenzt als Kontext
ausgelesen; Bilder können angehängt, von dieser Text-Runtime aber noch nicht
analysiert werden. Das steht direkt am Anhang. Kein automatischer Upload.

Das Schild-Icon steuert Terminal- und MCP-Freigaben: Aus, Einzelfreigabe (Standard),
experimentelle lokale Agent-Prüfung und Auto. Das lokale Terminal zeigt Befehl,
Arbeitsordner, Ausgabe und Exit-Code; normale Benutzerrechte, Zeit-/Ausgabelimit.
Agent-Prüfung ist keine Sandbox. Shell-Code aus Antworten lässt sich ins Terminal
übernehmen und erst nach explizitem Ausführen prüfen. Kein autonomer Werkzeug-Loop.

99 Tests auf dem Mac bestanden; echter Ministral-Metal-Test mit getrennter
finaler Antwort erfolgreich. [Bedienung und Grenzen](https://github.com/Ceda1998/cedexiaNexus/blob/main/docs/chat-workspace.md).

**Weiterhin enthalten: Rechenfreigabe und Verbindungsdiagnose aus 0.1.72**

Beide Geräte aktualisieren und neu koppeln. Die Rechenfähigkeit wird jetzt vor der Aktivierung innerhalb von TLS ausgehandelt. Ein älterer Peer bleibt für den Gewichte-Abgleich verbunden und erhält auf der neuen App einen klaren Updatehinweis. Abgelehnte Rechennachrichten beenden die Rechenfreigabe, nicht die Kopplung. Chat und Gerätefenster zeigen, welches Gerät noch nicht bereit ist; echte Verbindungsabbrüche erhalten bereinigte Fehlercodes.

Der konkret gemeldete Mac-/Windows-Abbruch in 0.1.71 ist lokal noch nicht reproduziert. Der vollständige Zwei-Workspace-Ablauf über echte Kopplung ist auf einem Mac geprüft; die physische CUDA-/Metal-Abnahme bleibt offen.

Geführte Installation von Cedexia Nexus mit Python, Qt und llama.cpp. Keine GGUF-Gewichte enthalten, keine Downloads während der Installation.

Einzelgerät und Mehrgeräte sind direkt in der Seitenleiste sichtbar. Für die Kopplung zeigt WLAN nur WLAN-Adapter sowie den verbundenen Netzwerknamen, wenn das Betriebssystem ihn freigibt. Scrollleisten sind im dunklen Design besser erkennbar.

**Geräte im Netz suchen** zeigt andere Cedexia-Nexus-Instanzen, die dieselbe Suche im lokalen Netz gestartet haben. Kopplungsanfragen werden auf beiden Geräten bestätigt. Unter **Einstellungen → Modelle** lassen sich Kontext, Ausgabelimit und Reasoning pro Modell einstellen.

Bei einer manuellen Einladung lässt sich der Einladungscode über **Code anzeigen** einblenden und danach wieder ausblenden.

Beim GGUF-Abgleich zeigt der Gerätedialog, auf welcher Seite eine Modelldatei fehlt oder die Prüfung fehlschlägt.

**Neu: experimenteller gemeinsamer Chat.** Auf beiden aktualisierten Apps identische GGUF-Gewichte abgleichen und im Gerätefenster **Gemeinsames Rechnen aktivieren** wählen. Ein kurzer GPU-Test und der freie Speicher bestimmen die automatische Schichtverteilung. Beide GPUs müssen Anteile übernehmen. Der Rechenkanal nutzt gepinntes TLS; rohe RPC-Worker bleiben auf Loopback. Stoppen und Trennen beenden den Lauf. Die Geräteansicht zeigt Worker-Rechenmeldungen.

Der Softwarepfad wurde mit zwei Prozessen auf einem Mac geprüft. Der physische CUDA-/Metal-Lauf und ein Geschwindigkeitsvorteil über WLAN sind noch nicht nachgewiesen. Bitte zunächst Kontext 1024 und eine kurze Testfrage verwenden. Alte Apps unterstützen das Rechenprotokoll nicht; beide Geräte aktualisieren. [Ablauf und Grenzen](https://github.com/Ceda1998/cedexiaNexus/blob/main/docs/distributed-chat.md).

- **macOS:** `CedexiaNexus-macOS-arm64-<Version>.pkg` für Apple Silicon, macOS 14+. Installation ins eigene Benutzerkonto unter `~/Applications`.
- **Windows:** `CedexiaNexus-Windows-x64-Setup-<Version>.exe` für Windows 10/11 x64. Der Installer liefert die zuvor fehlende `libomp.dll` mit, die llama.cpp zum Start braucht. Die App passt GPU-Layer automatisch an den Speicher an und bietet in den Modelleinstellungen einen CPU-Gegencheck. Für GPU-Inferenz ist ein kompatibler NVIDIA-Treiber erforderlich. Die CUDA-Laufzeitbibliotheken sind enthalten.

Nach der Installation zeigt die Titelleiste Version und Kurz-Commit. Unter Einstellungen → Modelle → GGUF hinzufügen eine vorhandene Datei wählen, dann das Modell unter dem Chat auswählen. Bestehende Chats, Einstellungen und Modelldateien bleiben erhalten. Die SHA-256-Dateien ermöglichen einen Integritätsvergleich.

Testbuild: ohne Herausgebersignatur / Apple-Notarisierung. Windows und macOS können Warnungen anzeigen. Die CI prüft Installation, erneute Installation, Appstart und Modellverifier; sie belegt keine Inferenz auf dem Windows-Zielgerät.

Anleitung, Quellen, Grenzen und Deinstallation: [docs/installation.md](https://github.com/Ceda1998/cedexiaNexus/blob/main/docs/installation.md).
