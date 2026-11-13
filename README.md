# cedexiaNexus

Cedexia Nexus ist eine geplante Plattform für sichere, quelloffene, verteilte
LLM-Inferenz. Der erste Prototyp soll `Qwen/Qwen3.8-27B` für Text-Inferenz
gemeinsam auf einem Windows-PC mit CUDA und einem MacBook mit Metal ausführen.
Beide Hosts müssen an derselben Modellberechnung beteiligt sein.

## Status

NX-037 ergänzt eine **Offline-Desktop-Demo** mit PySide6: Übersicht, Einrichtung,
Geräte, Ressourcenentwurf und simulierter Sitzungsablauf. Dunkelblau, eckige
Komponenten, lokal installierte Satoshi und Tabler-Outline-SVGs.
[Start für Windows/macOS, Schriftinstallation und Grenzen](docs/desktop.md).
Lokale UI-Tests unter Linux/macOS bestanden; sichtbarer Mac-Start bestätigt.
Vollständige Windows-/Mac-Abnahme (u. a. High-DPI) bleibt offen.
NX-042 ergänzt **„Lokales Modell“**: echte Mac-Inferenz mit Eingabe, laufender
Ausgabe und Stopp. Start: `.venv/bin/python -m nexus_ui`. Die Ansicht öffnet sich
direkt; Voraussetzungen und Grenzen stehen in [docs/desktop.md](docs/desktop.md).
Hardwarediagnose, Windows-Inferenz und Dual-Host sind noch nicht angebunden.

NX-005: Qwen3.8-27B Q4_K_M generiert lokal auf dem bestätigten M5-Mac Text mit
Metal (65/65 Layer auf GPU). [Start und Nachweis](docs/mac-metal.md):
`sh scripts/run_mac_model.sh "Deine kurze Frage"`. Dies ist ein begrenzter
Terminal-Test; CUDA und gemeinsame Inferenz bleiben ungeprüft.

NX-040 stellt die Repository-Grundlage bereit: Dokumentation, lokale Diagnose,
Unit-Tests und GPU-unabhängige CI. Der lokale llama.cpp-Test ist noch nicht in
Nexus integriert; es gibt keinen Server und keinen nachgewiesenen
CUDA-/Metal-Verbund. Ein erfolgreicher
Hardwarecheck bestätigt keine Backend- oder Modellkompatibilität.

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

1. NX-001: Windows-PC, genaue CPU, RAM, Treiber und CUDA-Werkzeuge inventarisieren;
   anschließend NX-006 für den nativen CUDA-Build.
2. NX-003: Tatsächliche LAN-Latenz und Bandbreite zwischen beiden Geräten messen.
3. NX-008: Nach NX-006 die Windows-Solo-Baseline messen; danach NX-009 und
   NX-011/012 für den gemeinsamen Rechennachweis.

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
