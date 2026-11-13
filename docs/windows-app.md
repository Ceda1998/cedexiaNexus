# Cedexia Nexus auf Windows starten

1. Das Paket **CedexiaNexus-Windows-x64** aus dem erfolgreichen
   [Windows-Paketlauf](https://github.com/Ceda1998/cedexiaNexus/actions/workflows/windows-app.yml) herunterladen.
2. Das vollständige ZIP entpacken und im Ordner **CedexiaNexus**
   **CedexiaNexus.exe** doppelklicken. Der Ordner `_internal` gehört zur App.
3. Unter **Lokales Modell** deine vorhandene `Qwen3.8-27B-Q4_K_M.gguf`
   auswählen und eine kurze Frage starten. Die App merkt sich den Pfad
   und prüft die Datei vor dem Modelllauf.

Das Paket enthält Python, Qt, die vorgebaute llama.cpp-Runtime und die
CUDA-Laufzeitbibliotheken. Für die Inferenz brauchst du einen kompatiblen
[NVIDIA-Treiber für CUDA 13.5](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/)
und die [festgelegte Modelldatei](model.md). Windows x64 und eine RTX 5070 Ti
sind das erste Ziel. Der CUDA-Testpfad nutzt zunächst 32 GPU-Layer und
4096 Kontexttokens. Windows-CUDA-Inferenz muss auf dem Ziel-PC abgenommen werden.
Das Paket ist ein unsignierter Testbuild.

## Paket bauen

Der Windows-Workflow baut das Paket mit PyInstaller 6.22.3 und PySide6 6.8.3.
Die vorgebauten Windows-x64-Archive stammen aus
[llama.cpp b12347](https://github.com/ggml-org/llama.cpp/releases/tag/b12347)
und werden vor dem Entpacken gegen die gepinnten SHA-256-Werte geprüft.
Die App nutzt ausschließlich das lokale Completion-Programm.
Quellen und Lizenzdateien stehen im Paket unter `licenses`.
Qt- und PySide-DLLs bleiben als separate Dateien im Paket austauschbar.

Für einen lokalen Build auf Windows x64 aus dem Repository:

```powershell
py -3 -m pip install -r requirements-ui.txt pyinstaller==6.22.3
py -3 -m scripts.package_windows
```

Das Ergebnis liegt unter `dist/CedexiaNexus`. Der Build prüft die
Runtime-Version, die Geräteliste und das Starten des gebündelten Fensters.
Der GitHub-Runner prüft den Paketstart ohne Ziel-GPU oder Modellgewichte.
