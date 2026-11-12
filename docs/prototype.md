# Qwen-Prototyp und NX-040-Nachweis

## Ziel und Ausgangsdaten

`Qwen/Qwen3.8-27B` soll Text auf zwei Hosts gemeinsam generieren. Beide Geräte
müssen während derselben Inferenz nachweisbar Modelloperationen ausführen;
ein Client auf einem Gerät und alleinige Inferenz auf dem anderen genügen nicht.

| Gerät | Nutzerangabe, noch keine vollständige Inventur |
| --- | --- |
| Home-PC | Windows; AMD Ryzen 7 (etwa vier Jahre alt); RTX 5070 Ti, 16 GB VRAM; 32 GB DDR4 RAM |
| MacBook | Apple M5 Pro; 32 GB Unified Memory; macOS |
| Netzwerk | Beide Geräte können Ethernet/WLAN; reale LAN-Geschwindigkeit offen |

Der Modellkandidat ist multimodal; zunächst wird nur Text untersucht.
GGUF Q4_K_M mit ungefähr 19,4 GB ist die Planungsannahme aus dem Auftrag.
Konkrete Datei, Revision und SHA-256 müssen in NX-004 verifiziert werden.
Gewichtgröße ist kein Laufzeit-Speicherbedarf: OS, Runtime und KV-Cache benötigen
zusätzliche Reserve. Zwei Hosts mit nominell je 32 GB ergeben keine Garantie,
dass eine bestimmte Quantisierung gemeinsam passt.

## Reihenfolge für nachfolgende Tickets

1. **NX-001:** Diagnose auf dem Windows-PC ausführen. Genaue CPU, OS, RAM,
   GPU-/Treiberangaben und CUDA-Toolchain prüfen. Fehlende Werte separat lokal
   nachmessen; keine Hostnamen oder privaten Netzwerkdaten veröffentlichen.
2. **NX-002:** Diagnose auf dem MacBook ausführen. macOS, Unified Memory und
   Apple-Silicon-/Metal-Indizien prüfen. Ein Werkzeugfund ist kein Backend-Test.
3. **NX-003:** Ethernet bevorzugen und tatsächliche LAN-RTT, Linkrate und
   Nettodurchsatz messen. Internet-Tarif nicht mit LAN-Bandbreite gleichsetzen.
4. **NX-004:** GGUF-Quelle, Dateiname, Quantisierung, Revision und SHA-256 sowie
   Runtime-Commit festlegen; Modelllizenz prüfen. Downloads sind ein separater
   Auftrag und werden durch diesen Bootstrap nicht ausgeführt.
5. Native Einzelhost-Baselines mit derselben Datei, Kontextgröße und Promptfolge
   erstellen. CUDA unter Windows und Metal unter macOS tatsächlich nachweisen.
6. Nach Sicherheitsprüfung einen begrenzten llama.cpp-RPC-Spike im isolierten
   LAN durchführen; Cross-Backend-Kompatibilität und Hostrollen testen.
7. Dual-Host-Inferenz mit expliziter Device-/Layer-Zuweisung ausführen.
   Bereinigte Allocation-/Backend-Nachweise plus RAM-/VRAM-Messungen für beide
   Hosts erfassen. Bloße Netzwerkaktivität oder GPU-Auslastung genügt nicht.
8. Worker-Abbruch, Restart und Timeouts testen. Bei Inkompatibilität oder
   unbrauchbarer Leistung den Blocker dokumentieren und Alternativen prüfen.

## Erfolg und Messprotokoll

Pass: Textgenerierung funktioniert und beide Hosts rechnen am selben Lauf;
Speicherverbrauch und Token-Durchsatz sind belegt. Zusätzlich die Notwendigkeit
kombinierter Kapazität mit größerem Quant oder kontrollierten Speicherbudgets
prüfen, falls Q4 auf einem Einzelgerät passt. Niemals absichtlich das OS durch
unkontrollierte Speicherüberlastung gefährden.

Für Mac-only, PC-only und Dual dieselbe GGUF-Datei, Promptfolge, Kontextgröße,
Seed und Sampling-Parameter verwenden, soweit unterstützt. Pro Szenario nach
Warm-up mindestens drei Messungen; Median und Fehler ausweisen. Erfassen:
Runtime-Commit, Modellhash, Device-/Layer-Verteilung, Eingabe-/Ausgabe-Tokenzahl,
TTFT, Prefill-/Decode-Token/s, Peak-RAM/VRAM, LAN-Bytes und Fehler. Backendbedingte
Abweichungen offen dokumentieren. Es liegen noch keine Inferenzmesswerte vor.

## NX-040: lokaler Testnachweis

Geprüft am **12. November 2026** auf macOS/Darwin 27.2.0, arm64, mit Python
3.13.15 und Git 2.55.0. Es wurden ausschließlich die neun in README.md
verlinkten Bootstrap-Dateien angelegt; keine zusätzlichen Pakete oder Modelle.

| Befehl / Prüfung | Tatsächliches Ergebnis |
| --- | --- |
| `python3 scripts/doctor.py` | Exit 0; gültiges JSON; Apple M5, 34.359.738.368 Byte RAM (32 GiB), Metal-Indiz `spdisplays_metal4` |
| `python3 -m unittest discover -s tests -v` | `Ran 17 tests in 0.014s` / `OK` |
| Gesamte Testsuite mit simuliert fehlendem `os.sysconf` | `Ran 17 tests in 0.008s` / `OK`; POSIX-Mocks funktionieren auch ohne das Windows-fremde Attribut |
| `python3 -m compileall -q scripts tests` | Exit 0; keine Syntaxfehler |
| CI-YAML mit Ruby-Standardbibliothek geparst | Gültiges YAML; Jobdefinition vorhanden |
| `git check-ignore` mit neun Beispielpfaden | Secrets, Modelle, lokale Berichte, Caches und Build-Binärdateien ausgeschlossen |
| `git diff --cached --check` | Exit 0; vorgemerkte Bootstrap-Dateien ohne Whitespace-Fehler |
| `len(Path("AGENTS.md").read_text(encoding="utf-8"))` | Bootstrap: 3.278 Zeichen; nach NX-041: 3.489 Zeichen, jeweils im Zielbereich |

Die Sandbox blockierte die sysctl-Abfragen: Der Bericht gab dort CPU/RAM
korrekt als `unknown` aus. Die obigen Hardwarewerte stammen aus der ausdrücklich
freigegebenen Ausführung außerhalb der Sandbox. Der aktuelle Rechner meldet
**Apple M5**, abweichend von der geplanten Hardware **M5 Pro**. Diese Abweichung
ist bei NX-002 zu klären. Git, clang und xcrun wurden gefunden; cmake, ninja,
nvcc und nvidia-smi nicht im PATH. Es fand keine Metal-Inferenz statt.

Der lokale Projektordner war leer und noch kein Git-Checkout. Auf ausdrücklichen
Nutzerauftrag wurde `main` initialisiert, das SSH-Remote
`git@github.com:Ceda1998/cedexiaNexus.git` eingetragen und mit `git ls-remote`
erreichbar und leer vorgefunden. Der Nutzer hat den ersten Commit und Push
ausdrücklich beauftragt. Der finale Commit und Git-Status werden im
Übergabebericht genannt. NX-040 ist in Notion mit den Bootstrap-Nachweisen
abgeschlossen; Dokumentationspflege, Ticketpflicht und Commitformat werden in
[NX-041](https://app.notion.com/p/41672966d10d81a39bbdd4c845d09e42) nachgeführt.

Windows-/Linux-Hardware, CUDA, Metal-Ausführung, Modellladen und verteilte
Inferenz sind durch diese lokalen Tests nicht validiert. Die CI ist für
Python 3.11 auf Linux, Windows und macOS sowie Python 3.13 auf Linux konfiguriert;
ihre Läufe werden separat auf GitHub ausgeführt. Die simulierten Plattformtests
ersetzen keine Inventur der tatsächlichen Zielgeräte. Verbindliche Ergebnisse
des jeweiligen Commits stehen unter [GitHub Actions](https://github.com/Ceda1998/cedexiaNexus/actions).

## Referenzen

- [Qwen-Modellkarte](https://huggingface.co/Qwen/Qwen3.8-27B)
- [GGUF-Kandidat](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF)
- [llama.cpp RPC](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md)
- [Notion-Prototyp](https://app.notion.com/p/41672966d10d817c8c49f80696d760e2)
- [NX-040](https://app.notion.com/p/41672966d10d8132b186c4a64960ff77)
