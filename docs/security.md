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

Die Desktop-Kopplung aus NX-053 öffnet nach **Einladung erstellen** einen
temporären TCP-Listener auf der ausgewählten privaten IPv4-Adresse. Der
Einmalcode enthält einen zufälligen 256-Bit-Schlüssel und den Fingerabdruck
eines frisch erzeugten TLS-Zertifikats. Das zweite Gerät prüft den Fingerabdruck
vor dem Senden des Schlüssels über TLS 1.3. Einladungen verfallen nach fünf
Minuten. Nach erfolgreichem Beitritt schließt der Listener. Zertifikat, Schlüssel
und Einladung werden nicht in Dateien gespeichert. Wenn möglich entfernt die
App den kopierten Code nach Beitritt oder Ablauf aus der Zwischenablage.

**Geräte im Netz suchen** startet zusätzlich UDP-Multicast mit Hop-Limit eins
auf dem gewählten Adapter. Ankündigungen enthalten die Plattform, den
temporären TCP-Port und den Zertifikatfingerabdruck. Der Absender muss im
gleichen privaten IPv4-Subnetz liegen. Die Suche gibt weder Rechnernamen,
SSID noch Einladungsschlüssel bekannt. Fingerabdrücke aus Discovery dienen
zum Ansprechen des gefundenen Geräts. Die eigentliche Bestätigung erfolgt
durch Vergleich eines aus der TLS-Sitzung abgeleiteten Prüfcodes auf beiden
Geräten. Erst danach werden Modelldaten ausgetauscht. Lokale Teilnehmer können
gefälschte Ankündigungen oder unerwünschte Anfragen senden. Schließen des
Dialogs beendet die Suche.

Beim reinen Gewichte-Abgleich werden Modellstatus, Dateiname, Größe, Anzahl der Teile,
SHA-256 und auf Klick eine HTTPS-Bezugsquelle übertragen. Die App überträgt
keine lokalen Pfade, Modellgewichte oder Prompts. Sie lädt keine Gewichte
automatisch und ändert keine Firewallregeln. Wer die Einladung erhält, kann
damit beitreten. Das Betriebssystem oder ein von ihm verwalteter
Zwischenablageverlauf kann kopierte Inhalte länger behalten.

## Experimenteller Desktop-Rechenkanal (NX-011)

**Gemeinsames Rechnen aktivieren** auf beiden aktualisierten Apps erweitert
die gekoppelte Sitzung ausdrücklich um Inferenz. Ein GPU-Kurztest verwendet
synthetische Eingaben. Die App tauscht Runtime-Revision, GPU-Name, gemeldeten
freien Speicher und die gemessene Kurztest-Tokenrate aus. Keine Hardware-
Seriennummern, Rechnernamen oder lokalen Modellpfade werden übertragen.

Der rohe `ggml-rpc-server` bindet ausschließlich an `127.0.0.1`. Ein separater
TLS-1.3-Listener bindet an den bereits gewählten privaten Adapter. Sein neuer
Zertifikatfingerabdruck und sein zufälliger 256-Bit-Schlüssel werden nur über
die bestätigte Kopplung ausgetauscht. Der Tunnel akzeptiert ausschließlich die
Adresse des gekoppelten Peers, prüft den Schlüssel nach dem TLS-Handshake und
öffnet den Weg zum Worker nur während einer reservierten Inferenz. Der Client
prüft den Zertifikatfingerabdruck vor dem Senden des Schlüssels. Ziele werden
an die Adresse des gekoppelten Peers gebunden. Höchstens acht Verbindungen,
begrenzte Übertragungspuffer und Zeitlimits begrenzen den Transport.

Über diesen Kanal fließen Modell-Tensoren und Zwischenergebnisse der
Berechnung. Sie können Informationen über Eingaben enthalten. Daher nur eigene
vertrauenswürdige Geräte und Testdaten verwenden. TLS schützt den Transport;
es beseitigt keine Schwachstellen des experimentellen RPC-Parsers. Lokale
Prozesse könnten den Loopback-Worker ansprechen; dies ist keine Sandbox gegen
andere Prozesse im selben Benutzer-/Host-Vertrauensbereich.

Stoppen widerruft die laufende Reservierung und schließt ihre Tunnelstreams.
Trennen, Modellwechsel, Ende der Freigabe oder Schließen der App beendet auch
Worker und Listener. Inaktivitäts- und Laufzeitlimits ergänzen den manuellen
Stopp. Abbruch bei einem abrupt unterbrochenen Netzwerk kann bis zum TCP-/
Tunnel-Zeitlimit dauern. Keine Firewalländerungen, Routerfreigaben, Remote-Shells,
persistenten Zugangsschlüssel oder installierten Hintergrunddienste.
RPC-Rohdiagnosen bleiben nur in begrenzten Arbeitsspeicherpuffern; nach außen
gehen ausschließlich Fehlerklassen, Schichtzahlen und Rechengraph-Zähler.

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
