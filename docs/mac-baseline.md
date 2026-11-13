# NX-007 · Qwen-Baseline auf Apple Metal

## Messung wiederholen

Benötigt den nativen [NX-005-Build](mac-metal.md) und die vorhandene
[Qwen3.8-27B-Q4_K_M-GGUF-Datei](model.md). Im Repository-Root:

```sh
mkdir -p reports
python3 -m scripts.benchmark_mac > reports/nx-007-mac-baseline.json
```

Das Skript prüft die gemeldete Runtime-Revision sowie Dateigröße und SHA-256 des
Modells. Es startet dann einen verworfenen Warm-up-Lauf und drei Messläufe mit
jeweils einem neuen Prozess. Der Dateicache kann durch Hashprüfung und Warm-up
bereits warm sein; es ist kein Kaltstart-Test. Auch der interne Runtime-Warm-up
bleibt wie im NX-005-Build aktiv. Pro Lauf gilt ein Zeitlimit von 180 Sekunden.
Der JSON-Bericht enthält die vollständige Befehlszeile mit relativen Pfaden und
einem synthetischen Prompt; Rohlogs und Modellantworten werden nicht gespeichert.
Die Messung läuft offline ohne Server.

Festes Profil für den späteren Backend-Vergleich: 4096 Kontexttokens, 64
Ausgabetokens, Batch und Microbatch je 128, vier CPU-Threads, Seed 42, Temperatur
0 (greedy), GGUF-Chat-Template, kein Context Shift. Der Prompt lautet:
`Write the numbers 1 through 100 separated by commas. Do not add an introduction.`
`--ignore-eos` erzwingt eine vergleichbare Länge; diese Einstellung gilt nur
für den Benchmark. Das Skript lehnt Läufe ohne vollständiges GPU-Offload und
mit abweichenden Tokenzählern ab. Es prüft keine Antwortqualität; erzeugte
Tokens können auch Denktext enthalten.

## Bedeutung der Messwerte

- **TTFT:** Zeit vom Prozessstart bis zu den ersten nicht leeren
  Ausgabebytes auf stdout. Enthält Start, Modellladen und Prefill sowie die
  Ausgabe an die Pipe. Die einmalige Hashprüfung liegt davor.
- **Prefill / Decode:** Tokenraten aus den Runtime-Zählern. Der erste Token
  folgt direkt aus dem Prefill. Bei 64 erzeugten Tokens misst die Runtime daher
  63 einzelne Decode-Schritte. Prompt-Token zählen das Chat-Template mit.
- **Peak-RAM:** höchster Prozess-RSS von macOS `/usr/bin/time -l`, einschließlich
  residenter gemappter Seiten. Die Metal-Zahl ist separat die von der Runtime
  ausgewiesene Geräteallokation; beide Werte können dieselben Unified-Memory-Seiten
  erfassen. Weder ihre Summe noch der RSS allein ist eine systemweite Peak-Messung.

Die drei Läufe liefern eine lokale Referenz für dieses Profil. Sie erlauben
keine Aussage zu Langkontext, interaktiver UI-Leistung, CUDA oder gemeinsamem
Rechnen über zwei Hosts. Bei drei Stichproben werden die Einzelwerte und der
Median ausgewiesen; für einen belastbaren P95 wären mehr Wiederholungen nötig.

## Referenzmessung vom 13.11.2026

Apple M5 mit 32 GiB Unified Memory, macOS 27.2 (26B123), llama.cpp
`8ca5a8008b57aa39f2601546c0d07912045080a5` (0.9.0-dev, Build 12347).
Die [geprüfte Q4_K_M-Datei](model.md) blieb unverändert. Gemessen nach dem
Warm-up und nach Abschluss der Testsuite, ohne parallel gestarteten Modelllauf.

| Lauf | Laden (s) | TTFT (s) | Prefill (Tok/s) | Decode (Tok/s) | Peak-RSS (Byte) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,269 | 1,980 | 126,17 | 6,12 | 19.962.445.824 |
| 2 | 1,231 | 1,944 | 125,76 | 6,19 | 19.979.714.560 |
| 3 | 4,434 | 5,140 | 126,22 | 6,23 | 19.963.035.648 |
| Median | 1,269 | 1,980 | 126,17 | 6,19 | 19.963.035.648 |

Alle drei Läufe: Exit 0, 72 Prompttokens, 64 erzeugte Tokens, 63 Decode-Schritte,
65/65 Layer auf MTL0, 18.350 MiB von Metal ausgewiesene Allokation und 0
prozessbezogene Swaps. Maximaler Peak-RSS: **18,61 GiB**. Lauf 3 lud deutlich
länger, blieb aber in der Reihe; der Grund für die Schwankung wurde nicht
ermittelt. Prefill und Decode lagen weiterhin im Bereich der anderen Läufe.

Repository-Prüfung: 42 lokale Tests einschließlich Qt und Benchmark-Parser,
Compileall und Git-Whitespace-Prüfung erfolgreich.
