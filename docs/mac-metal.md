# NX-005 · Lokaler Qwen-Texttest auf macOS/Metal

Am 12.11.2026 auf dem bestätigten Apple M5 (Mac17,2), 32 GiB Unified Memory,
macOS 27.2/SDK 27.2, arm64 geprüft. **Nativer Build, GPU-Erkennung und kurze
Textgenerierung erfolgreich.** CUDA und Dual-Host sind damit nicht nachgewiesen.
Die nachfolgende [Desktop-Anbindung NX-042](desktop.md) erlaubt den lokalen UI-Test.

## Auf diesem Mac starten

Im Repository-Root:

```sh
sh scripts/run_mac_model.sh
sh scripts/run_mac_model.sh "Was ist die Hauptstadt von Frankreich?"
```

Die lokale Modelldatei wurde bereits vollständig gegen das Manifest geprüft.
Das Skript startet einen einzelnen Terminal-Lauf, beendet ihn nach Antwortende
oder spätestens 8192 generierten Tokens und öffnet keinen Server. Abbruch mit
Ctrl+C. Seit NX-043: Kontext 16384 Tokens, Batch/UBatch 128, vier CPU-Threads,
alle möglichen Layer auf `MTL0`, Offline-Modus, Jinja-Template aus dem GGUF,
greedy Sampling.
Die Demo-Seiten bleiben simuliert; „Lokales Modell“ erlaubt einen separaten
echten Modelllauf über die UI.

Bekannte Grenze dieses upstream `llama-completion`-Pfads: Trotz `--reasoning off`
enthielt die Ausgabe einen Thinking-Abschnitt vor der abschließenden Antwort.
Die Option ist daher **kein verlässlich nachgewiesener Thinking-Schalter**.
Mit längeren Prompts kann auch das 8192-Token-Limit eine Antwort abschneiden. Der
Starthelfer ist ein begrenzter Funktionstest, noch kein allgemeiner Chatclient.

## Reproduzierbarer Build

Runtime: [llama.cpp 8ca5a8008b57aa39f2601546c0d07912045080a5](https://github.com/ggml-org/llama.cpp/tree/8ca5a8008b57aa39f2601546c0d07912045080a5),
Version `0.9.0-dev`, Build 12347. Compiler AppleClang 21.0.0.21000401.
Modellrevision, Datei und SHA-256 stehen in [model.md](model.md).

CMake 3.31.6 wurde ausschließlich in `.venv` installiert. Quelle:
[CMake Python Distributions auf PyPI](https://pypi.org/project/cmake/3.31.6/),
Wheel `cmake-3.31.6-py3-none-macosx_10_10_universal2.whl`, SHA-256
`da9d4fd9abd571fd016ddb27da0428b10277010b23bb21e3678f8b9e96e1686e`.
Das Wheel wurde mit diesem Hash geprüft; keine globale Installation erforderlich.

Für einen frischen Checkout zunächst eine virtuelle Umgebung anlegen, dann:

```sh
.venv/bin/python -m pip install --no-deps --only-binary=:all: \
  'https://files.pythonhosted.org/packages/7f/09/516b0d709672bc430eb13278f0316acd34869269447744f5d136daeef689/cmake-3.31.6-py3-none-macosx_10_10_universal2.whl#sha256=da9d4fd9abd571fd016ddb27da0428b10277010b23bb21e3678f8b9e96e1686e'
mkdir -p local/vendor
git clone --no-checkout --filter=blob:none https://github.com/ggml-org/llama.cpp.git local/vendor/llama.cpp
git -C local/vendor/llama.cpp checkout --detach 8ca5a8008b57aa39f2601546c0d07912045080a5
.venv/bin/cmake -S local/vendor/llama.cpp -B local/build/llama-metal \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DGGML_METAL=ON -DGGML_RPC=OFF -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_OPENSSL=OFF -DLLAMA_SUBPROCESS=OFF -DGGML_CCACHE=OFF
.venv/bin/cmake --build local/build/llama-metal --config Release \
  --target llama-completion --parallel 6
local/build/llama-metal/bin/llama-completion --version
local/build/llama-metal/bin/llama-completion --list-devices
```

Quellcheckout und Build bleiben unter dem ignorierten `local/`. Ein vorhandener
Quellcheckout darf nicht ungeprüft überschrieben werden. Für neue Checkouts ist
die Modelldatei separat bereitzustellen und mit `scripts.verify_model` zu prüfen.
Der getestete Commit stellt `llama-completion` ohne Server-Build bereit;
`llama-cli` hängt in dieser Revision vom Server-Build ab. Der standalone
Completion-Pfad genügt für NX-005. CMake-Warnungen zu fehlendem OpenMP und
ARM-Erkennung verhinderten den Metal-Build nicht; kein OpenMP installiert.

## Tatsächlicher Nachweis

Die folgenden NX-005-Messungen verwendeten die damaligen Grenzen von 1024
Kontexttokens und 128 Ausgabetokens. Der spätere NX-043-Test mit erhöhten Grenzen
ist in [desktop.md](desktop.md) separat dokumentiert.

Zwei kurze Läufe mit synthetischem Prompt `Antworte nur mit: Hallo vom Mac.`
beendeten sich mit Exit 0 und der abschließenden Ausgabe `Hallo vom Mac.`.
Der zweite Lauf verwendete zusätzlich `--verbosity 4`, um die tatsächliche
Backend-Zuordnung zu protokollieren. Bereinigte Auszüge:

```text
version: 0.9.0-dev (build 12347, commit 8ca5a8008)
MTL0: Apple M5 (25559 MiB, 25558 MiB free)
using device MTL0 (Apple M5)
offloaded 65/65 layers to GPU
CPU_Mapped model buffer size = 682.03 MiB
MTL0_Mapped model buffer size = 1288.30 MiB
MTL0_Mapped model buffer size = 16523.98 MiB
MTL0 KV buffer size = 64.00 MiB
MTL0 RS buffer size = 149.62 MiB
MTL0 compute buffer size = 131.51 MiB
```

Runtime-Speicheraufschlüsselung des zweiten Laufs: MTL0 insgesamt 18.157 MiB
für Modell/Cache/Compute. `/usr/bin/time -l` meldete maximal 19.403.948.032 Byte
Resident Set und 0 Swaps. Diese Anzeigen sind unterschiedliche Messgrößen;
Mapped- und GPU-Puffer nicht zu einem vermeintlichen Gesamtverbrauch addieren.
Es wurde keine vollständige systemweite Peak-Messung vorgenommen.

Beobachtete Decode-Rate: 5,97 bzw. 6,10 Token/s; zweiter Lauf 62 Prompttokens,
42 Decode-Schritte, 1,60 s Ladezeit und 9,35 s gesamte Prozessdauer.
Das sind **Smoke-Test-Beobachtungen, kein Benchmark**: Cachezustand und
Begleitlast unterschieden sich; keine drei Wiederholungen oder Medianbildung.
Reproduzierbare Solo-Baselines, Kontext-/Speicherbudget und längere Stabilität
bleiben NX-007. Beide Hosts zusammen müssen später separat geprüft werden.

Repository-Prüfung: 31 Tests einschließlich 6 Qt-Tests bestanden, Compileall,
Shell-Syntax und Whitespace-Prüfung erfolgreich. Der Starthelfer wurde zusätzlich
als dritter echter Modelllauf geprüft: Exit 0, abschließend `Hallo vom Mac.`.
Rohprotokolle und Modellgewichte sind nicht in Git.
