# Sicherheitsgrundlage

## Vertrauensgrenzen

| Grenze | Risiko | Vorgabe für spätere Versuche |
| --- | --- | --- |
| Quellcode/CI zu Drittanbieter-Code | Manipulierte Abhängigkeiten oder Actions | Wenige Abhängigkeiten, feste Action-Commits, Review |
| Modellquelle zum lokalen Artefakt | Manipulierte oder inkompatible Gewichte | Quelle, Revision und SHA-256 prüfen; keine automatischen Downloads |
| Koordinator zu Worker | Datenabfluss, manipulierte Antworten, unsicherer RPC-Code | Nur eigene identifizierte Geräte im abgeschotteten Testnetz |
| Prozess zum Host | Zugriff auf Dateien und privilegierte Schnittstellen | Ohne Adminrechte, keine Remote-Shells oder Host-/Docker-Socket-Freigaben |
| Diagnose zu Git/CI | Offenlegung lokaler Identität und Zugangsdaten | Nur ausgewählte Felder; keine Rohlogs oder sensiblen Artefakte |

## Bootstrap-Verhalten

`doctor.py` startet keine Server, öffnet keine Netzwerkverbindungen, installiert
nichts und lädt keine Gewichte. Es startet ausschließlich lokale
Diagnoseprogramme mit Argumentlisten, ohne Shell und mit Zeitlimit. CPU/RAM
werden über sysctl, Windows-CIM oder POSIX-Systemwerte ermittelt. GPU-Namen und
Metal-Indizien kommen unter macOS aus ausgewählten Display-Feldern; NVIDIA-
Angaben werden auf Name, VRAM und Treiberversion begrenzt. Prozesse, Seriennummern,
Rechnernamen, IP-Adressen, Umgebungsvariablen und Werkzeugpfade werden nicht
ausgegeben. Fehlerausgaben bleiben unveröffentlicht.

Programme im lokalen PATH und OS-Werkzeuge werden als vertrauenswürdig
vorausgesetzt; die Diagnose ist keine Sandbox und keine Sicherheitszertifizierung.
Vorhandene Werkzeuge sind nur Indizien. Ihr Fund beweist weder CUDA-/Metal-
Ausführbarkeit noch korrekte Treiber oder Modellkompatibilität.

`.gitignore` schließt typische Secrets, Modellgewichte, Binärdateien und lokale
Berichte aus. Vor jedem Commit trotzdem den Inhalt prüfen. Keine sensiblen
Prompts, Tokens, privaten IPs, Hostnamen oder Rohlogs in das Repository aufnehmen.
CI hat nur `contents: read`, speichert keine Checkout-Zugangsdaten und lädt keine
Diagnose-Artefakte hoch. Öffentliche Fork-PRs erhalten keinen privilegierten
`pull_request_target`-Workflow.

## Bekannte Risiken und späteres Freigabekriterium

Die [llama.cpp-RPC-Dokumentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md)
stuft den RPC-Pfad als fragilen, unsicheren Proof of Concept ein. Niemals
ungeschützt öffentlich oder in einer sensiblen Umgebung betreiben. Ein Heimnetz
ist nicht automatisch isoliert. Vor einem separaten RPC-Test müssen Peer-
Begrenzung, Firewall, Bind-Adresse, fehlende Router-Portweiterleitungen und
Testdaten geprüft sein. Hier werden keine Ports oder Firewallregeln geändert.

Für Internetkopplung oder fremde Nodes sind ein separates Threat Model und ein
Security-Review nötig, einschließlich Authentisierung, Transportverschlüsselung,
Ressourcenlimits und Datenvertraulichkeit. Ein Tunnel allein macht den
experimentellen Backend-Code nicht produktionssicher. Es gibt bisher keine
validierten Aussagen über Produktionssicherheit oder Inferenzleistung.
