# Desktop-Prototyp · NX-037 Demo / NX-042 lokales Modell

Die UI verwendet Python/PySide6 und läuft ohne Netzwerkverbindung. Übersicht,
Einrichtung, Geräte und Demo-Sitzung sind ausdrücklich simuliert. Die getrennte
Ansicht **Lokales Modell** aus NX-042 führt echte Textinferenz auf dem Mac aus.
Es gibt keine persistierten Nutzereingaben und keine Hardwarediagnose,
Windows-Inferenz oder Dual-Host-Anbindung.

## Lokales Modell in der UI testen

Auf dem in NX-005 eingerichteten Mac `.venv/bin/python -m nexus_ui` starten.
Die App öffnet „Lokales Modell“. Eine kurze Frage eingeben und **Lokal starten**
wählen. Die Datei wird vor jedem Lauf vollständig gegen Größe/SHA-256 geprüft,
danach geladen; die Antwort erscheint schrittweise. **Stoppen** funktioniert
auch während der Prüfung und beim Laden. Schließen des Fensters beendet den
lokalen Prozess. Nach Abschluss oder Fehler ist ein manueller Neustart möglich.

Voraussetzungen: nativer Apple-Silicon-Mac, der [NX-005-Build](mac-metal.md) unter
`local/build/llama-metal/bin/llama-completion`, das gepinnte Modell unter `models/`
und `config/model-manifest.json`. Fehlende Voraussetzungen werden angezeigt;
es erfolgt weder Installation noch Download. Windows zeigt die Einschränkung.

Grenzen: einzelne Fragen ohne Gesprächshistorie, 1024 Kontexttokens, höchstens
4000 Eingabezeichen und 128 Ausgabetokens; der Tokenbedarf kann je nach Text schon
vor 4000 Zeichen das Kontextfenster überschreiten. Zeitlimit 240 Sekunden für
Prüfung plus Modelllauf. Lange Antworten können abbrechen. Denktext kann trotz
der Runtime-Option `--reasoning off` sichtbar bleiben. Keine erfundenen
Geschwindigkeits-/TTFT-Werte. Für wiederholbare Benchmarks gilt NX-007.

Technik: `nexus_ui/local_model.py` verwaltet jeweils einen asynchronen QProcess.
Erst Hashprüfung, dann direkte Runtime-Ausführung ohne Shell. Der Prompt wird
über stdin übergeben, nicht als Prozessargument oder temporäre Datei. Runtime-
Logs werden verworfen, Fehler als allgemeine verständliche Meldungen angezeigt.
Keine Prompt-/Antwortpersistenz, kein HTTP-/RPC-Server. Demo-Aktionen verändern
den lokalen Modellprozess nicht.

### NX-042-Nachweis vom 12.11.2026

39 lokale Tests bestanden: 25 Standardbibliothek, 6 Demo-Interaktionstests und
8 neue Qt-Prozesstests. Letztere verwenden echte kleine Kindprozesse ohne Modell
für Unicode-Streaming/stdin, fehlgeschlagene Hashprüfung, Stopp in beiden Phasen,
manuellen Neustart, Timeout, Start-/Runtimefehler und Fensterschließen. Rohfehler
werden nicht in die Oberfläche übernommen. Compileall und Whitespace geprüft.

Auf dem physischen Apple-M5-Mac mit macOS 27.2, Python 3.13.15 und PySide6 6.8.3
die native UI geöffnet und tatsächlich geprüft: Abbruch während SHA-Prüfung,
Abbruch beim Modellladen, Navigation während des Laufs, manueller Neustart und
echte Antwort `Hallo aus Nexus.`. Nach Abschluss kein aktiver Kindprozess.
Die fertige lokale Ansicht visuell geprüft; Satoshi fehlt auf diesem Mac,
Systemschrift-Fallback aktiv. Windows-/Linux-CI testet Prozesssteuerung mit
Testprozessen, keine dortige Inferenz. High-DPI/Screenreader-Abnahme bleibt NX-037.

## Start

Python 3.11–3.13; Windows x64 oder macOS Apple Silicon als Zielplattformen.
Die Python-/Qt-Kombination muss auf beiden Zielgeräten noch abgenommen werden.

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt
.venv/bin/python -m nexus_ui
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m nexus_ui
```

Aus dem Repository-Root starten. Kein Build/Installer erforderlich. Native
Fensterrahmen bleiben erhalten. Alle Inhaltsseiten sind scrollbar.

## Satoshi lokal einrichten

Satoshi bei https://www.fontshare.com/fonts/satoshi selbst als ZIP herunterladen
und die beigefügte Lizenz lesen. Dann mit dem Python der virtuellen Umgebung:

```sh
python scripts/install_satoshi.py /pfad/zum/Satoshi.zip
```

Das Skript importiert ausschließlich die drei unveränderten OTFs Regular,
Medium und Bold in `nexus_ui/assets/fonts/`. Kein Netzwerkzugriff. Die Dateien
sind Git-ignoriert. Bei fehlenden Fonts zeigt die App einen sichtbaren Hinweis
und verwendet die Systemschrift.

Die geprüfte offizielle FFL 2.0 vom 17.08.2026 erlaubt persönliche/kommerzielle
Nutzung und Desktop-App-Einbettung (Abschnitt 01), untersagt jedoch die freie
Weiterverteilung der Fontdateien über Repositories (Abschnitt 02). Daher keine
OTFs im öffentlichen Git. Vor einer verteilten App-Paketierung die konkrete
Einbettung gegen diese Bedingungen prüfen. Keine Fontänderung oder Subsetting.
Prüfquelle: https://api.fontshare.com/v2/fonts/download/satoshi, 12.11.2026.
SHA-256 des geprüften Archivs:
`476fee84de48af8bbf1af339c728a6ea69c8f49c742c3e115fd4f8ffddf51add`.

## Icons und Drittanbieter

Tabler Icons Outline v3.35.0, Commit
`147130cd0e67a9cfc70538f8b3a14a48a695d90b`, lokal als SVG. Originale MIT-Lizenz
unter `nexus_ui/assets/icons/LICENSE`, Quellpfad und Einzeldatei-Hashes im
benachbarten `manifest.json`. In der App über „Über Nexus → Tabler-Lizenz“
abrufbar. Bei Paketierung Assets und Lizenz gemeinsam ausliefern.

PySide6/Qt wird als Entwicklungsabhängigkeit aus offiziellen Wheels installiert.
Für die spätere App-Verteilung LGPL-/Drittanbieterpflichten und verwendete
Module separat dokumentieren; diese Demo erstellt keinen Installer. Die
Projektlizenz bleibt offen.

## Bedienpfad der Demo

1. Einrichtung: Geräteprüfung und Modellprüfung simulieren.
2. Geräte: gegenseitige Freigabe simulieren; RAM-Limit als unwirksamen Entwurf ändern.
3. Sitzung: einen Modus wählen und eine Nachricht eingeben.
4. Demo starten; feste Ausgabe erscheint zeitgesteuert. Stopp und simulierter
   Speicherfehler beenden den Lauf. Eingaben bleiben für manuellen Neustart erhalten.
5. Im Dual-Modus während eines Laufs das zweite Gerät trennen: verständlicher
   Fehler, kein automatischer Neustart. Erneute Freigabe und manueller Start nötig.

Ressourcen sind pro Gerät getrennt. Kein gemeinsamer Speicherwert und keine
erfundenen Leistungsmetriken. Ein Solo-Lauf hängt nicht vom zweiten Gerät ab.

## Tests und Grenzen

```sh
python -m unittest discover -s tests -v
python -m compileall -q scripts tests nexus_ui
git diff --check
```

Qt-Tests laufen offscreen; ohne UI-Abhängigkeit werden ausschließlich diese
Tests übersprungen. Bootstrap-Tests bleiben unabhängig von Qt.
Die Plattformmatrix in CI prüft alle drei Betriebssysteme offscreen.
Physische Zielgeräte, Screenreader,
200-%-Textskalierung und High-DPI benötigen manuelle Abnahme. NX-037 erst nach
diesen Nachweisen abschließen.

## Testnachweis vom 12.11.2026

Linux x86_64, Python 3.12.14, PySide6 6.8.3, Qt-Offscreen-Plattform:
23 Tests bestanden (17 Bootstrap + 6 UI). Geprüft: Tastaturnavigation,
Startbedingungen einschließlich Peer-Freigabe, zeitgesteuerter Abschluss,
Stopp ohne Folgeausgabe, Speicherfehler, Peer-Abbruch mit manuellem Neustart
und SVG-Hashes/Rendering. Satoshi wurde aus den lokalen OTFs erfolgreich geladen.
Compileall und `git diff --check` erfolgreich. Ein Fontconfig-Cachehinweis der
Sandbox verhinderte weder Fontladen noch Rendering.

Die folgenden Screenshots stammen aus dem tatsächlichen Qt-Rendering unter
Linux; sie sind keine Windows-/Mac-Nachweise. Ticketstatus: Review,
vollständige Plattformabnahme offen.

Ergänzung vom 12.11.2026: Auf dem physischen Mac (Apple M5, arm64,
macOS 27.2, Python 3.13.15, PySide6 6.8.3) wurde die Demo als sichtbares
Cocoa-Fenster gestartet. Satoshi fehlt lokal; die App nutzt die Systemschrift.
Die vollständige Suite mit den neuen Inventur-/Integritätsprüfungen bestand
mit 31 Tests, davon 6 Qt-Interaktionstests offscreen. Dies ersetzt keine
manuelle High-DPI-, Screenreader- oder Windows-Abnahme.

Der erste [CI-Lauf](https://github.com/Ceda1998/cedexiaNexus/actions/runs/43292374820)
zeigte zwei konkrete Fehler: Windows wandelte SVG-Zeilenenden um und verletzte
damit die gepinnten Hashes; Linux fehlte `libEGL.so.1`. `.gitattributes` erzwingt
nun LF für die SVGs, der Linux-Desktopjob installiert `libegl1` und `libopengl0`.
Die strengen Icon-Hashes bleiben unverändert. Den Nachweis des korrigierten
Commits liefern die [GitHub Actions](https://github.com/Ceda1998/cedexiaNexus/actions).

![Übersicht, Qt-Offscreen unter Linux](images/nx-037-overview.png)

![Simulierte Sitzung, Qt-Offscreen unter Linux](images/nx-037-session.png)

## Roadmap-Prüfung

Für das Nutzerziel ist der technische Kern sinnvoll: NX-001/002/004,
NX-005/006, NX-007/008 und NX-003/009 führen zu NX-011/012. NX-037 liefert
die frühe Bedienoberfläche. Eine reine Client/Server-Chat-Verbindung reicht
für den geforderten gemeinsamen Rechennachweis nicht.

Linux-Docker, externe Community-Installation, B2B und Multi-Household sind
spätere Ausbaustufen. Für den lokalen Prototyp muss keine vollständige
Alpha-Plattform fertiggestellt sein. Sichere Live-Anbindung bleibt erforderlich,
ein eigener REST-Server ist für die Qt-Oberfläche jedoch kein Selbstzweck.
NX-010 (alternative Runtime) sollte nur bei Bedarf zum Engpass werden;
die bestehende NX-016-Abhängigkeit ist bei späterer Planung zu überprüfen.
Diese Desktop-Demo gehört zu NX-037; Inventur und Modellfestlegung sind
separat in NX-002 und NX-004 dokumentiert.
