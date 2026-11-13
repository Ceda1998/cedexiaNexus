# NX-009 · Metal und CUDA für den ersten Zwei-Geräte-Test vorbereiten

Der Mac soll das verifizierte Modell laden und über Metal rechnen. Der
Windows-PC stellt seine CUDA-GPU als Worker bereit. Beide Prozesse verwenden
llama.cpp-Revision `8ca5a8008b57aa39f2601546c0d07912045080a5`. Deren
RPC-Header definiert Protokoll **10.0.0**. Der erste Test verwendet TCP.
Das RPC-Backend bleibt getrennt von der Desktop-App und den Solo-Builds.

## Builds vorbereiten

Auf dem Mac den bestehenden [llama.cpp-Checkout mit fester Revision](mac-metal.md)
verwenden. Die Buildoptionen entsprechen NX-005 mit zusätzlichem RPC-Backend
und explizit deaktiviertem RDMA. Im Nexus-Repository:

```sh
.venv/bin/cmake -S local/vendor/llama.cpp -B local/build/llama-metal-rpc \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DGGML_METAL=ON -DGGML_RPC=ON -DGGML_RPC_RDMA=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_OPENSSL=OFF -DLLAMA_SUBPROCESS=OFF \
  -DGGML_CCACHE=OFF
.venv/bin/cmake --build local/build/llama-metal-rpc --config Release \
  --target llama-completion --parallel 6
local/build/llama-metal-rpc/bin/llama-completion --version
local/build/llama-metal-rpc/bin/llama-completion --offline --list-devices
```

Auf Windows aus der x64 Developer PowerShell mit der
[Toolchain und dem sauberen Checkout aus NX-006](windows-cuda.md):

```powershell
py -3 -m scripts.windows_cuda build-rpc
.\local\build\llama-cuda-rpc\bin\ggml-rpc-server.exe --help
```

Das Ziel `ggml-rpc-server` kompiliert den Worker. Die Befehle oben öffnen
keinen Dienst. Die Hilfe-Abfrage beendet sich vor dem Start des Listeners.
Beim Build bleibt der bestehende Ordner `local/build/llama-cuda` erhalten.
Für den Worker müssen die CUDA-Laufzeitbibliotheken der Build-Toolchain
verfügbar sein.

## Abnahme auf beiden Zielgeräten

1. [NX-003](lan-benchmark.md) zwischen Mac und PC messen und den bereinigten
   Bericht festhalten. CUDA- und CPU-Kurztest aus
   [NX-006](windows-cuda.md) auf Windows ausführen.
2. Vor dem RPC-Test das isolierte Test-LAN und die Einwahl der zwei
   vorgesehenen Geräte prüfen. Der Worker darf nur an die private
   Adresse der Windows-Testschnittstelle binden. TCP 50052 nur für
   den Mac zulassen, keine Router-Freigabe. Die Upstream-Runtime stuft
   diesen RPC-Pfad als experimentell und unsicher ein.
   [Upstream-RPC-Dokumentation](https://github.com/ggml-org/llama.cpp/blob/8ca5a8008b57aa39f2601546c0d07912045080a5/tools/rpc/README.md)
3. Im separat freigegebenen Versuch den Worker mit explizitem CUDA-Gerät
   starten. Auf dem Mac die Geräteliste mit diesem Worker abrufen.
   RPC-Version und Erkennung von lokalem Metal und entferntem CUDA
   festhalten. Beide Prozesse nach dem Versuch beenden.
4. Für den kurzen Modelltest eine feste Layer-Verteilung über beide
   Geräte und einen kleinen Kontext verwenden. Backend-Zuweisung und
   tatsächlich ausgeführte Rechenschritte auf beiden Hosts für denselben
   Lauf erfassen. Ein Handshake oder eine Geräteliste allein belegt
   keine gemeinsame Inferenz. NX-011 und NX-012 führen diesen Nachweis weiter.

Im Nachweis nur Runtime-Revision, Protokollversion, Backend-/Gerätenamen,
Fehlerklassen sowie bereinigte Zuweisungs- und Compute-Daten dokumentieren.
Private Adressen, Pfade und Rohlogs bleiben auf den Testgeräten.

## Lokaler Nachweis

Der separate Client wurde auf Apple M5 mit macOS 27.2 als Darwin-arm64-Build
kompiliert. Version 0.9.0-dev, Build 12347, Commit `8ca5a8008`. Die Hilfe
enthält die RPC-Option. Die lokale Geräteliste meldet `MTL0: Apple M5`.

Ein Kurzlauf mit SHA-256-geprüftem Qwen3.8-27B Q4_K_M, 1024 Kontexttokens und
acht Ausgabetokens lief mit Exitcode 0 und erzeugte Ausgabe. Die Runtime
meldete 65/65 Layer auf MTL0. Der Lauf verwendete ausschließlich den Mac.
Die vollständige lokale Testsuite bestand mit 55 Tests. Die Windows-Tests
prüfen die getrennten Buildprofile mit simulierten Werkzeugaufrufen.
Der CUDA-Worker und der Handshake zwischen beiden Geräten stehen aus.
