# cedexiaNexus

Cedexia Nexus ist eine geplante Plattform für sichere, quelloffene, verteilte
LLM-Inferenz. Der erste Prototyp soll `Qwen/Qwen3.8-27B` für Text-Inferenz
gemeinsam auf einem Windows-PC mit CUDA und einem MacBook mit Metal ausführen.
Beide Hosts müssen an derselben Modellberechnung beteiligt sein.

## Status

**Installation ohne Entwicklungsumgebung:** Geführte Installer für macOS
(Apple Silicon) und Windows x64 stehen unter
[GitHub Releases](https://github.com/Ceda1998/cedexiaNexus/releases) bereit.
Sie enthalten App und Laufzeiten, aber keine GGUF-Modelle.
[Installationsanleitung, Voraussetzungen und Deinstallation](docs/installation.md).

Die Desktop-App startet mit Projekten und Chats, einklappbarer Sidebar,
Moduswahl und separaten Einstellungen. Der lokale Composer verwendet die
vorhandene Runtime. [Bedienung und Funktionsstand](docs/desktop.md#projekt--und-chatoberfläche).

NX-037 ergänzt eine **Offline-Desktop-Demo** mit PySide6: Übersicht, Einrichtung,
Geräte, Ressourcenentwurf und simulierter Sitzungsablauf. Dunkelblau, eckige
Komponenten, lokal installierte Satoshi und Tabler-Outline-SVGs.
[Start für Windows/macOS, Schriftinstallation und Grenzen](docs/desktop.md).
Lokale UI-Tests unter Linux/macOS bestanden; sichtbarer Mac-Start bestätigt.
Vollständige Windows-/Mac-Abnahme (u. a. High-DPI) bleibt offen.
NX-042 ergänzt **„Lokales Modell“**: echte Mac-Inferenz mit Eingabe, laufender
Ausgabe und Stopp. Start: `.venv/bin/python -m nexus_ui`. Die Ansicht öffnet sich
direkt; Voraussetzungen und Grenzen stehen in [docs/desktop.md](docs/desktop.md).
NX-052 liefert ein [startbares Windows-Paket](docs/windows-app.md) mit CUDA
und Auswahl lokaler GGUF-Textmodelle. NX-046 ergänzt auf Mac und Windows eine
gespeicherte Liste für eigene GGUF-Dateien. Der Paketstart ist unter Windows geprüft.
Die CUDA-Inferenz auf dem physischen Zielgerät steht zur Abnahme aus.

NX-053 ergänzt **Geräte verbinden**. Zwei Desktop-Apps können sich im selben
LAN per Einmalcode verbinden, ihre ausgewählten GGUF-Gewichte vergleichen und
bei einer Abweichung eine Bezugsquelle teilen. [Ablauf und Grenzen](docs/desktop.md#geräte-im-lan-verbinden).

NX-005: Qwen3.8-27B Q4_K_M generiert lokal auf dem bestätigten M5-Mac Text mit
Metal (65/65 Layer auf GPU). [Start und Nachweis](docs/mac-metal.md):
`sh scripts/run_mac_model.sh "Deine kurze Frage"`. Dies ist ein begrenzter
Terminal-Test; CUDA und gemeinsame Inferenz bleiben ungeprüft.

NX-040 stellt die Repository-Grundlage mit Dokumentation, lokaler Diagnose,
Unit-Tests und GPU-unabhängiger CI bereit. Der gemeinsame CUDA-/Metal-Lauf
bleibt ein separates Prototypziel.

## Installation und lokale Prüfung

Voraussetzung: Git und Python **3.11 oder neuer**. Keine Python-Zusatzpakete,
Installer, Modelle oder GPU-Treiber werden für den Bootstrap benötigt.

macOS-Terminal:

```sh
git clone git@github.com:Ceda1998/cedexiaNexus.git
cd cedexiaNexus
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
```

Windows PowerShell mit installiertem Python-Launcher:

```powershell
git clone git@github.com:Ceda1998/cedexiaNexus.git
Set-Location cedexiaNexus
py -3 scripts/doctor.py
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q scripts tests
```

Falls der Launcher fehlt, kann `python` verwendet werden; die Version zuerst mit
`python --version` prüfen. Im bereits vorhandenen Checkout den Clone-Schritt
überspringen. Ein separates Build oder eine virtuelle Umgebung ist für die
Standardbibliothek-Skripte nicht erforderlich.

`doctor.py` schreibt ausschließlich JSON auf stdout und legt keine Dateien an.
Es prüft OS, Architektur, CPU, physischen RAM, GPU-Indizien und Werkzeuge.
Nicht ermittelbare Werte heißen `unknown`; fehlende Werkzeuge erscheinen als
`false`. Exitcode 0 bedeutet nur, dass der Bericht erstellt wurde. Metal- und
CUDA-Ausführung werden nicht getestet. Die Tests verwenden auch simulierte
Plattformantworten; das ersetzt keine Ausführung auf der Zielhardware.

## Orientierung

- [Agent-Einstieg](AGENTS.md)
- [Architektur und offene Entscheidungen](docs/architecture.md)
- [Sicherheit und Vertrauensgrenzen](docs/security.md)
- [Prototyp, Abnahmekriterien und Bootstrap-Testnachweis](docs/prototype.md)
- [Mac-Inventur und Toolchain-Voraussetzungen](docs/hardware.md):
  `python3 -m scripts.inventory_mac`
- [Windows-Inventur auf dem Home-PC (NX-001)](docs/hardware.md#nx-001--windows-pc-erfassen):
  `py -3 -m scripts.inventory_windows`
- [Nativer Windows-CUDA-Build und Smoke-Test (NX-006)](docs/windows-cuda.md)
- [Startbares Windows-Paket mit CedexiaNexus.exe (NX-052)](docs/windows-app.md)
- [Festgelegtes Modellartefakt und lokale Hashprüfung](docs/model.md):
  `python3 -m scripts.verify_model /pfad/zur/Modelldatei.gguf`
- [Mac-Solo-Baseline (NX-007)](docs/mac-baseline.md):
  `python3 -m scripts.benchmark_mac`
- [Diagnoseskript](scripts/doctor.py), [Tests](tests/test_doctor.py),
  [GitHub Actions](.github/workflows/ci.yml)

## Nächste Tickets

NX-002 (Inventur des bestätigten M5-Macs) und NX-004 (Modellmetadaten und
Integritätsprüfung) sind umgesetzt. Das Q4_K_M-Testmodell wurde auf ausdrücklichen
Nutzerauftrag lokal heruntergeladen und verifiziert; es ist nicht Teil von Git.

1. NX-006: Den [nativen Windows-CUDA-Build](docs/windows-cuda.md) nach der
   abgeschlossenen NX-001-Inventur auf dem Home-PC bauen und prüfen.
2. NX-003: Die [LAN-Messung](docs/lan-benchmark.md) auf beiden Zielgeräten ausführen.
3. NX-009: Den [Metal-/CUDA-Verbindungstest](docs/rpc-spike.md) nach LAN-Messung
   und Windows-CUDA-Nachweis durchführen. NX-011/012 prüfen die gemeinsame
   Berechnung. NX-008 erfasst separat die Windows-Solo-Baseline nach NX-006.

## Grenzen und Lizenz

Keine automatischen Modell-Downloads, Portfreigaben oder RPC-Starts.
Experimentelles llama.cpp RPC niemals ungeschützt öffentlich betreiben; Details
stehen in [docs/security.md](docs/security.md). Keine privaten IPs, Hostnamen,
Zugangsdaten oder ungeprüften Rohlogs committen.

Die endgültige Projektlizenz ist noch offen. Apache-2.0 ist eine Option und
wurde hier nicht festgelegt; deshalb gibt es noch keine `LICENSE`-Datei.
Modell- und Drittanbieter-Lizenzen sind unabhängig davon zu prüfen.

Projektplanung: [Notion-Projekt](https://app.notion.com/p/41672966d10d8059ac8efce57a8886c8),
[Development Board](https://app.notion.com/p/cb7d37612f644b35880db4fb005b69c7).
