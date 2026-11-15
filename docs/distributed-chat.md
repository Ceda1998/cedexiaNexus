# NX-011 · Gemeinsamer Desktop-Chat

Ab Version 0.1.71 enthält die App den experimentellen Zwei-Geräte-Pfad. Er
verwendet dieselbe llama.cpp-Revision auf beiden Hosts und verteilt Schichten
**eines** Modelllaufs über die lokale GPU und den entfernten RPC-Worker.
Der Rechner mit dem geöffneten Chat koordiniert; er muss nicht der stärkere sein.

## Bedienung

1. Auf **beiden** Geräten Version 0.1.71 oder neuer installieren. Ältere Apps
   unterstützen die neuen Rechennachrichten nicht und können die Verbindung beenden.
2. Dasselbe GGUF auswählen, über LAN oder WLAN koppeln und den bestätigten
   Gewichte-Abgleich abwarten. Modelle während des Laufs nicht extern ersetzen.
3. Auf beiden Geräten im Gerätefenster **Gemeinsames Rechnen aktivieren** wählen.
   Ein kurzer synthetischer GPU-Test mit dem ausgewählten Modell ermittelt eine
   Tokenrate. Er verwendet keine Chatdaten. Er benötigt Zeit zum Laden des GGUF.
4. Sobald beide GPUs vorbereitet sind, im **Mehrgeräte**-Modus senden. Die
   Statuszeile zeigt den automatischen Schichtplan und den Fortschritt.
   Erst werden Gewichte an den Worker übertragen; auch bei identischen lokalen
   GGUF-Dateien benötigt llama.cpp diese Tensorübertragung. Gerade WLAN kann
   deshalb den ersten Start deutlich verlängern. Es gibt keinen Download.
5. **Stoppen** auf einem Gerät stoppt den gemeinsamen Lauf. **Gemeinsames Rechnen
   beenden**, Trennen, Modellwechsel oder App-Schließen beendet die Freigabe und
   die dazu gestarteten Prozesse. Es werden keine Hintergrunddienste installiert.

Beide Geräte müssen eigene, vertrauenswürdige Rechner sein. Der Pfad bleibt ein
experimenteller Testbetrieb; keine sensiblen Eingaben verwenden. Der Installer
ändert keine Firewall- oder Routerregeln. Nur die geschützte Verbindung wird an
den gewählten privaten Netzwerkadapter gebunden; der rohe RPC-Worker bindet
an Loopback. Siehe [Sicherheitsgrenzen](security.md).

## Automatische Verteilung

- Die Runtime meldet verfügbare CUDA-/Metal-Geräte und deren freien Speicher.
  Bei mehreren lokalen GPUs wird zunächst die mit dem größten freien Speicher
  verwendet. Mehr als eine GPU pro Host ist hier noch nicht Teil des Plans.
- Der Kurztest verwendet `llama-bench`, volle GPU-Offload-Anforderung, 16
  generierte Tokens, eine Wiederholung und vier CPU-Threads. Die schnellere
  gemessene GPU erhält proportional mehr Schichten, begrenzt durch den Speicher.
  Es handelt sich um eine **Schätzung**, keinen Durchsatzbenchmark des Gesamtsystems.
- Passt das ganze Modell nicht auf eine einzelne GPU oder scheitert deren
  Kurztest, wird keine scheinbare GPU-Leistung aus CPU-Auslagerung abgeleitet.
  Ohne zwei gültige Messungen wird der Plan ausdrücklich als Speicherschätzung
  angezeigt. Die Anwendung behauptet dann nicht, das stärkere Rechengerät zu kennen.
- Vor jedem Lauf wird der aktuelle freie Speicher über den Rechenkanal erneut
  geprüft. Der Plan reserviert 15 Prozent, 1 GiB Arbeitspuffer, zehn Prozent
  Modellüberhang pro Gerät und eine konservative KV-Cache-Schätzung abhängig
  vom eingestellten Kontext. Diese Schätzung kann einen möglichen Lauf ablehnen;
  sie garantiert keine Vermeidung aller Speicherfehler.
- Jede GPU erhält wiederholende Modellschichten; nur den Ausgabekopf auf den
  Worker zu legen reicht nicht. Die Schichtzahl in der UI enthält den Ausgabekopf.
  Unzureichender Speicher, fehlende Metadaten oder eine fehlende GPU stoppen den
  Lauf. Es gibt keinen stillen Wechsel auf ein einzelnes Gerät oder eine CPU.
- Kontext, Ausgabetokens und Reasoning stammen aus dem Modellprofil des
  initiierenden Geräts. Die lokale CPU-Option gilt nur für Einzelgeräteläufe.

## Nachweis und Grenzen

Der Client liest die Runtime-Zuweisung aller Modellschichten. Ausgabe wird erst
angezeigt, wenn beide ausgewählten GPUs einschließlich wiederholender Schichten
nachweisbar zugewiesen sind. Der Worker zählt seine `graph_compute`- und
`graph_recompute`-Aufrufe und meldet nur die Anzahl für die aktuelle Sitzung.
Im Gerätefenster erscheint dieser Zähler nach dem Lauf. Das sind Runtime-
Nachweise; sie sind keine unabhängigen GPU-Auslastungsmessungen.

Lokal geprüft auf Apple M5: Zwei getrennte Runtime-Prozesse über den echten
TLS-Tunnel, vorhandenes Ministral-3-3B-Reasoning Q8_0, Kontext 1024, maximal
128 Ausgabetokens. Ein Lauf endete mit Modellantwort und Endmarker, 13 Schichten
auf `MTL0`, 14 auf `RPC0` und 70 vom Worker gemeldeten Rechengraphen.
**Beide Prozesse liefen auf demselben Mac.** Dies prüft den vollständigen
Softwarepfad, belegt jedoch weder zwei physische Hosts noch CUDA-/Metal-
Kompatibilität oder WLAN-Leistung. Die physische Abnahme bleibt NX-011/NX-012.

Für den nächsten Zielgerätetest: Auf Mac und Windows dieselbe App installieren,
mit dem bereits abgeglichenen Ministral zunächst Kontext 1024 und eine kurze
Testfrage verwenden. In der Geräteansicht müssen eine Metal-GPU und eine CUDA-GPU
stehen, nach dem Lauf eine positive Worker-Graphzahl und in der Antwort der
Schichtplan. Anschließend kann Qwen aus dem ursprünglichen Prototypziel geprüft
werden. Fehlschläge mit UI-Fehlerklasse, Modellname und bereinigtem Schichtplan
dokumentieren; keine IPs, Pfade oder Runtime-Rohlogs veröffentlichen.
