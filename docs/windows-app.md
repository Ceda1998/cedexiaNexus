# Cedexia Nexus auf Windows starten

1. Das Paket **CedexiaNexus-Windows-x64** aus dem erfolgreichen
   [Windows-Paketlauf](https://github.com/Ceda1998/cedexiaNexus/actions/workflows/windows-app.yml) herunterladen.
2. Das vollständige ZIP entpacken und im Ordner **CedexiaNexus**
   **CedexiaNexus.exe** doppelklicken. Der Ordner `_internal` gehört zur App.
3. Unter **Lokales Modell** über **GGUF hinzufügen …** eine oder mehrere
   vorhandene `.gguf`-Dateien hinzufügen. Das Modell in der Liste wählen,
   eine Frage eingeben und **Lokal starten** klicken. Die App merkt sich die
   Dateipfade. **Eintrag entfernen** entfernt den Pfad aus der Liste.

Bei geteilten GGUFs den ersten Teil auswählen und alle Teile im selben Ordner
belassen. Die App prüft den GGUF-Dateikopf, danach lädt llama.cpp das Modell.
Die UI akzeptiert auch GGUF-Dateien anderer Modelle und Quantisierungen.
Die [Prüfung des festgelegten Benchmarkmodells](model.md) ist separat verfügbar.

Unter **Geräte verbinden** kann die App einem Mac im selben LAN beitreten und
den Downloadhinweis für die dort ausgewählte GGUF-Datei anzeigen.
[Schritte für Einladung und Modellabgleich](desktop.md#geräte-im-lan-verbinden).

Das Paket enthält Python, Qt, die vorgebaute llama.cpp-Runtime und die
CUDA-Laufzeitbibliotheken. Für die Inferenz brauchst du einen kompatiblen
[NVIDIA-Treiber für CUDA 13.5](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/)
und ein GGUF-Textmodell, dessen Architektur und Quantisierung die gebündelte
llama.cpp-Version unterstützt und das in den verfügbaren Speicher passt.
Windows x64 und eine RTX 5070 Ti sind das erste Ziel. Der CUDA-Testpfad nutzt 32 GPU-Layer und
4096 Kontexttokens. Windows-CUDA-Inferenz muss auf dem Ziel-PC abgenommen werden.
Das Paket ist ein unsignierter Testbuild.

Erster geprüfter Paketlauf für Commit `a6ccd6f`.
[GitHub Actions 43439544349](https://github.com/Ceda1998/cedexiaNexus/actions/runs/43439544349)
bestätigt den Start des Fensters, die geladene llama.cpp-Revision und die
gebündelte SHA-256-Prüfung. GitHub hält die ZIP-Datei 14 Tage vor.

## Paket bauen

Der Windows-Workflow baut das Paket mit PyInstaller 6.22.3 und PySide6 6.8.3.
Die vorgebauten Windows-x64-Archive stammen aus
[llama.cpp b12347](https://github.com/ggml-org/llama.cpp/releases/tag/b12347)
und werden vor dem Entpacken gegen die gepinnten SHA-256-Werte geprüft.
Die Modellansicht nutzt das lokale Completion-Programm. Die Geräteansicht
verwendet die gebündelten Python-TLS-Bibliotheken.
Quellen und Lizenzdateien stehen im Paket unter `licenses`.
Qt- und PySide-DLLs bleiben als separate Dateien im Paket austauschbar.

Für einen lokalen Build auf Windows x64 aus dem Repository:

```powershell
py -3 -m pip install -r requirements-ui.txt pyinstaller==6.22.3
py -3 -m scripts.package_windows
```

Das Ergebnis liegt unter `dist/CedexiaNexus`. Der Build prüft die
Runtime-Version, die Geräteliste, das Starten des gebündelten Fensters sowie
die GGUF-Kopfprüfung, den GGUF-Fingerprint und die separate
Benchmark-SHA-256-Prüfung in der EXE.
Der GitHub-Runner prüft den Paketstart ohne Ziel-GPU oder Modellgewichte.
