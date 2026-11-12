# NX-002 · Inventur des aktuellen Macs

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
