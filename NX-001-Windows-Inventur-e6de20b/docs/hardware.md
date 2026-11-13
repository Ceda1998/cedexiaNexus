# Hardwareinventur der Zielgeräte

## NX-001 · Windows-PC erfassen

Auf dem physischen Windows-PC in PowerShell aus dem Projektordner ausführen.
Voraussetzung: Python ab 3.11. Das Skript benötigt keine zusätzlichen
Python-Pakete oder Administratorrechte.

```powershell
py -3 -m scripts.inventory_windows
```

Falls der Python-Launcher fehlt, `python -m scripts.inventory_windows`
verwenden. Der JSON-Bericht erscheint im Terminal. Falls eine Datei gebraucht
wird, im Projektordner unter dem ignorierten Verzeichnis `reports/` ablegen:

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
py -3 -m scripts.inventory_windows > reports/nx-001-windows.json
```

| Berichtsfeld | Bedeutung |
| --- | --- |
| OS, CPU, RAM | Windows-Edition, Version, Build inklusive Update-Revision (soweit lesbar), CPU-Modell und physischer RAM; freier physischer RAM als Momentaufnahme |
| GPU | Windows-CIM-Gerät und dessen Treiber; NVIDIA-Modell, Treiber und VRAM in MiB separat aus `nvidia-smi`, wenn verfügbar. CIM-Treiberversion und NVIDIA-Versionsnummer haben unterschiedliche Formate. |
| Datenträger | Freie Bytes auf dem Laufwerk des Repositorys bzw. des entpackten Diagnosepakets; bei einem anderen Modelllaufwerk dort separat prüfen |
| Netzwerkschnittstellen | Physische Adapter nach Typ, Verbindungsstatus und gemeldeter RX-/TX-Linkrate; Linkrate ist kein gemessener Durchsatz zum Mac (NX-003). |
| CUDA und WSL | Werkzeuge im PATH, CUDA-Toolkit-Release aus `nvcc --version`, Zustand der Windows-Funktionen für WSL und Virtual Machine Platform, soweit abfragbar |

Der Bericht enthält keine Hostnamen, Benutzerpfade, Adapter-Aliasse, IP- oder
MAC-Adressen, Seriennummern oder WSL-Distributionsnamen. Fehlende Messwerte
erscheinen als `unknown`. Ein `false` unter `tools_on_path` bedeutet, dass das
Werkzeug in dieser Shell nicht gefunden wurde; insbesondere kann `cl` erst
in einer Visual-Studio-Entwicklerkonsole sichtbar sein.

**Backend-Pfade:** Zuerst nativer Windows-CUDA-Build in NX-006. WSL2 ist eine
Fallback-Option, falls der native Pfad ungeeignet ist; dafür sind der Windows-Treiber
und die CUDA-Umgebung in WSL getrennt zu prüfen. WSL-Funktionsstatus und
Werkzeugfunde belegen keinen funktionierenden Build oder eine lauffähige
Distribution. Natives Linux bleibt ein separater, bisher ungeprüfter Pfad.
Keine Distribution wird gestartet und keine Konfiguration geändert.

Quellen: [Windows-Speicherdaten](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-operatingsystem),
[Windows-Adapterfelder](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/hh968170(v=vs.85)),
[Windows-Funktionsstatus](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-optionalfeature),
[NVIDIA: CUDA unter WSL](https://docs.nvidia.com/cuda/wsl-user-guide/).

**Abnahme:** Die Erfassung ist implementiert; die Messung auf dem Home-PC
steht aus. Die Angaben Ryzen 7, RTX 5070 Ti (16 GB VRAM) und 32 GB RAM
stammen bisher vom Nutzer. Den erzeugten Bericht zur Prüfung bereitstellen,
bevor NX-001 als abgeschlossen gilt.

Lokal auf macOS: 46 Tests bestanden, darunter vier gezielte Tests mit
simulierten Windows-Antworten. Der direkte Aufruf auf macOS meldet
`Windows required` mit Exitcode 2. Die GitHub-CI enthält einen zusätzlichen
CIM-Smoke-Test für Windows; er ersetzt die Inventur des Home-PCs nicht.

## NX-002 · Inventur des aktuellen Macs

Erfasst am 12.11.2026 mit `python3 -m scripts.inventory_mac` auf dem lokalen
Mac. Das Skript schreibt nur ausgewählte Felder auf stdout; keine Seriennummern,
Hostnamen, IP-/MAC-Adressen oder Rohlogs. Fehlgeschlagene Abfragen ergeben
`unknown` beziehungsweise bei Werkzeugfunden `false`.

| Feld | Beobachtung |
| --- | --- |
| Modellkennung / Chip | Mac17,2 / Apple M5, arm64 |
| Physischer Unified Memory | 34.359.738.368 Byte = 32 GiB |
| macOS / Build | 27.2 / 26B123; Kernel Darwin 27.2.0 |
| Momentan unbenutzte RAM-Seiten | 247.693.312 Byte; keine Aussage über insgesamt verfügbaren oder zurückgewinnbaren Speicher |
| Freier Platz auf dem Repository-Volume | 732.642.414.592 Byte; Momentaufnahme |
| GPU-Indiz | Apple M5; `spdisplays_metal4` |
| Werkzeuge gefunden | Python 3.13.15, Git, clang, xcrun, Metal-Compiler; macOS SDK 27.2 |
| Nicht im PATH gefunden | CMake, Ninja, nvcc, nvidia-smi |
| Netzwerkadapter | Wi-Fi: en0; Ethernet: en4/en5/en6; Thunderbolt: en1/en2/en3/bridge0; en8: Kategorie unbekannt |

Adapterpräsenz bestätigt weder angeschlossene Kabel noch Linkrate oder
Erreichbarkeit des Windows-PCs. Diese Messungen gehören zu NX-003.
Ein gefundener Compiler bestätigt keinen erfolgreichen Build und keine
Metal-Inferenz. Nach dieser Inventur wurde CMake 3.31.6 lokal in `.venv`
bereitgestellt und ein nativer Metal-Lauf in [NX-005](mac-metal.md) nachgewiesen.
Ninja wird für den getesteten Makefile-Build nicht benötigt.

**Bestätigtes Zielgerät:** Der Nutzer hat am 12.11.2026 ausdrücklich diesen
M5-Mac als Zielgerät bestätigt. Die frühere Annahme M5 Pro ist damit korrigiert.
NX-002 ist für die Inventur erfüllt. Windows-Inventur NX-001 und die gemeinsame
LAN-Messung lassen sich auf diesem Mac allein nicht abschließen.

Vier isolierte Tests in `tests/test_inventory_mac.py` prüfen freie Seiten,
Filterung von Netzwerkdaten, fehlende Messwerte und das Verhalten auf Windows.
Die gesamte lokale Suite bestand mit 31 Tests (25 Standardbibliothek + 6 Qt)
unter Python 3.13.15; Compileall und Whitespace-Prüfung sind im Übergabenachweis
mit aufgeführt.
