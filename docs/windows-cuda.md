# NX-006 · Windows-Build mit CUDA und CPU-Test

Für den Start der Desktop-App steht das [Windows-EXE-Paket](windows-app.md)
bereit, sobald sein GitHub-Workflow erfolgreich abgeschlossen ist. Diese
Anleitung dient der getrennten Abnahme des nativen Entwickler-Builds.

Der Home-PC aus [NX-001](hardware.md) hat eine RTX 5070 Ti mit 16.303 MiB
VRAM und meldete NVIDIA-Treiber 621.01. Der erste Pfad ist natives
Windows x64 mit CUDA. Die RTX 5070 Ti hat Compute Capability 12.0. Der
gepinnte llama.cpp-Stand baut dafür den Blackwell-Code `sm_120a`. Der
CPU-Pfad desselben Builds dient als Gegenprobe. WSL2 bleibt die
Fallback-Option für einen separaten Test.

Quellen: [NVIDIA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus),
[NVIDIA Windows CUDA Installation Guide](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/),
[NVIDIA Blackwell Compatibility Guide](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/).

## Toolchain auf dem Windows-PC prüfen

In einer **Developer PowerShell für Visual Studio mit x64-Ziel** den
Nexus-Projektordner öffnen. Benötigt werden Python ab 3.11, Git, CMake
3.31.8 oder neuer in der 3.x-Reihe (bzw. 4.0.2 oder neuer), Ninja, MSVC
mit Windows SDK und ein CUDA Toolkit, dessen `nvcc`
`sm_120a` unterstützt (ab CUDA 12.8). Die CUDA-Installationsanleitung
enthält die jeweils unterstützten MSVC-Versionen. NX-001 fand `cl`,
`nvcc`, `cmake` und `ninja` in der damaligen Shell nicht im PATH.

```powershell
Get-Command git, cmake, ninja, cl, nvcc, nvidia-smi
cmake --version
nvcc --version
```

`nvcc --list-gpu-code` zeigt nur Ziele ohne architekturspezifischen Zusatz.
Wenn dort `sm_120` steht, prüft der anschließende Build, ob der Compiler
auch das von llama.cpp verwendete `sm_120a` erzeugen kann.
[NVIDIA-Dokumentation zu nvcc](https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/index.html#list-gpu-code-list-gpu-code).

Falls die Werkzeuge fehlen, die C++-Desktopentwicklung mit Windows SDK
über [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio)
und das Toolkit über [NVIDIA](https://developer.nvidia.com/cuda-downloads)
bereitstellen. Die tatsächlich verwendete CMake-/MSVC-/CUDA-Kombination
bei einem Buildfehler mit angeben. Ein vorhandener Treiber und
`nvidia-smi` zeigen die GPU an; der Compiler kommt aus dem Toolkit.

## Festgelegte Revision bauen

Einmalig aus dem Nexus-Projektordner, falls `local/vendor/llama.cpp`
noch nicht existiert:

```powershell
New-Item -ItemType Directory -Force local/vendor | Out-Null
git clone --no-checkout https://github.com/ggml-org/llama.cpp.git local/vendor/llama.cpp
git -C local/vendor/llama.cpp checkout --detach 8ca5a8008b57aa39f2601546c0d07912045080a5
```

Bei einem vorhandenen Checkout zuerst Revision und lokale Änderungen
prüfen. Der Build setzt einen sauberen Checkout an der im Modellmanifest
festgelegten Revision voraus.

```powershell
py -3 -m scripts.windows_cuda build
```

Das Skript baut `llama-completion.exe` unter `local/build/llama-cuda/bin`.
Es verwendet Ninja, MSVC, Release, CUDA `120a-real` und den CPU-Backend.
Die vollständigen Flags stehen in [windows_cuda.py](../scripts/windows_cuda.py)
und im Smoke-Report. RPC, Server und OpenSSL sind im Buildprofil deaktiviert.
Falls CMake einen Generator- oder Compilerwechsel meldet, den bestehenden
lokalen Buildordner umbenennen und erneut bauen.

## Auf CUDA und CPU prüfen

Die [in NX-004 festgelegte GGUF-Datei](model.md) unter
`models/Qwen3.8-27B-Q4_K_M.gguf` bereitstellen. Eine vorhandene lokale Kopie
kann über `--model` angegeben werden. Das Skript verifiziert Größe und
SHA-256 vor jedem Lauf.

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
py -3 -m scripts.windows_cuda smoke cuda > reports/nx-006-cuda.json
if ($LASTEXITCODE -ne 0) { throw 'CUDA smoke test failed' }
py -3 -m scripts.windows_cuda smoke cpu > reports/nx-006-cpu.json
if ($LASTEXITCODE -ne 0) { throw 'CPU smoke test failed' }
```

Das Modellartefakt belegt etwa 18,07 GiB und überschreitet schon als Datei
den VRAM des PCs. Der CUDA-Test verwendet `CUDA0` und startet mit
32 GPU-Layern. Bei einem Speicherfehler zunächst andere GPU-Last schließen
oder mit `--layers 16` wiederholen. Die restlichen Layer liegen im RAM.
Der CPU-Test fordert null GPU-Layer an. Beide Läufe verwenden 1024
Kontexttokens, einen festen synthetischen Prompt und acht Ausgabetokens.
Tokenzähler und GPU-Platzierung werden aus der Runtime-Ausgabe geprüft.
Ein Testlauf hat maximal 180 Sekunden für Laden und Generierung.

Die Berichte enthalten Runtime-Revision, Build-Flags, erkannte CUDA-Geräte,
Treiber, Modellhash und Offload-Nachweis. Sie enthalten weder lokale
Dateipfade noch die Modellausgabe. Die beiden JSON-Berichte zur Abnahme
bereitstellen. Die Windows-Hardwareabnahme und die separate Windows-Baseline
NX-008 stehen aus.

Die lokale Prüfung auf macOS umfasste 49 Tests, darunter die Erkennung
korrekter und fehlerhafter CPU-/CUDA-Platzierung. Ein CPU-Kurzlauf mit dem
vorhandenen gepinnten Mac-Build bestätigte zusätzlich das Logformat und
acht erzeugte Tokens bei null GPU-Layern.
