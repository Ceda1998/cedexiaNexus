# NX-003 · LAN zwischen Mac und Windows messen

Beide Geräte im selben vertrauenswürdigen LAN anschließen. Für die
Referenzmessung beide per Ethernet verbinden. Die aktuelle IPv4-Adresse und
Linkrate am jeweils verwendeten Adapter in den Netzwerkeinstellungen ablesen.
Bei mehreren aktiven Adaptern prüfen, dass die beiden angegebenen IPv4-Adressen
zu den gewünschten Verbindungen gehören. Die Adressen bleiben lokal.

Das [Messskript](../scripts/benchmark_lan.py) benötigt Python ab 3.11.
Es lässt sich auch als einzelne Datei auf den anderen Rechner kopieren.
Die beiden folgenden Befehle gehen vom Repository-Ordner aus.

1. Auf dem Mac die Messstelle starten. In PowerShell und im Mac-Terminal
   die Platzhalter durch die privaten IPv4-Adressen ersetzen.

   ```sh
   python3 scripts/benchmark_lan.py listen --bind MAC_IPV4 --peer WINDOWS_IPV4
   ```

2. Sobald der Mac `LAN listener ready` meldet, auf Windows in PowerShell
   messen. Linkraten optional mit `--windows-link-mbps` und
   `--mac-link-mbps` angeben. Bei WLAN den jeweiligen Wert `ethernet`
   durch `wi-fi` ersetzen. Eine gemischte Verbindung ist im Bericht sichtbar.

   ```powershell
   New-Item -ItemType Directory -Force reports | Out-Null
   py -3 scripts/benchmark_lan.py measure --peer MAC_IPV4 --windows-connection ethernet --mac-connection ethernet > reports/nx-003-ethernet.json
   ```

3. Für die WLAN-Messung die gewünschte Verbindung auf beiden Geräten
   herstellen und die Messstelle mit den neuen IPv4-Adressen erneut starten.
   Den zweiten Bericht als `reports/nx-003-wifi.json` speichern. Falls nur
   eine Verbindung verfügbar ist, im Ticket vermerken.

## Was der Bericht misst

- 20 ICMP-Echos von Windows zum Mac. Median und P95 (Nearest Rank) beziehen
  sich auf empfangene Antworten. Der Bericht enthält die Verlustrate.
  Windows liefert Millisekunden als Ganzzahl. Eine Anzeige von 0 ms kann
  daher bei Verbindungen unter einer Millisekunde auftreten.
- Je drei Übertragungen von 64 MiB synthetischen Daten pro TCP-Richtung.
  Ausgegeben werden die Einzelwerte und der Median in Mbit/s. Die Zeit
  beginnt nach dem TCP-Verbindungsaufbau. Windows misst beide Richtungen.
  Beim Upload bestätigt der Mac den vollständigen Empfang.
- Verbindungstyp und Linkraten stammen aus den Angaben beim Aufruf.
  Die TCP-Messung zeigt den Nutzdatendurchsatz im LAN.

Die Daten werden im Speicher erzeugt und verworfen. Der Bericht enthält
Messwerte und Verbindungsarten. Die JSON-Dateien können nach Durchsicht für
die Ticketabnahme geteilt werden. Fehlende Ping-Antworten erscheinen mit
`null` für Median und P95, auch wenn TCP funktioniert.

## Port und Firewall

Der Mac bindet TCP 5201 an die angegebene private IPv4-Adresse und akzeptiert
Messungen von der angegebenen Windows-IP. Windows stellt die ausgehende
Verbindung her. Der Listener endet nach sechs Transfers, spätestens nach
fünf Minuten oder bei Strg+C. Den Test im eigenen LAN durchführen und den
Port am Router geschlossen lassen.

Wenn macOS den eingehenden Verkehr blockiert, die Firewall eingeschaltet
lassen und nur bei Bedarf den verwendeten Python-Prozess vorübergehend für
den Test erlauben. Die Freigabe danach zurücknehmen. ICMP kann im Tarnmodus
blockiert sein. Falls das eintritt, den Ping als nicht messbar dokumentieren
und TCP separat auswerten.
[macOS-Firewall-Einstellungen](https://support.apple.com/en-gb/guide/mac-help/-mh11783/mac)

Für die Abnahme von NX-003 den Bericht der Messung zwischen den beiden
physischen Geräten bereitstellen.
