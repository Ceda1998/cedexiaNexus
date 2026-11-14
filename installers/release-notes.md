Geführte Installation von Cedexia Nexus mit Python, Qt und llama.cpp. Keine GGUF-Gewichte enthalten, keine Downloads während der Installation.

- **macOS:** `CedexiaNexus-macOS-arm64.pkg` für Apple Silicon, macOS 14+. Installation ins eigene Benutzerkonto unter `~/Applications`.
- **Windows:** `CedexiaNexus-Windows-x64-Setup.exe` für Windows 10/11 x64. Für GPU-Inferenz ist ein kompatibler NVIDIA-Treiber erforderlich; CUDA-Laufzeitbibliotheken sind enthalten.

Nach der Installation: Einstellungen → Modelle → GGUF hinzufügen, dann Modell unter dem Chat auswählen. Bestehende Chats, Einstellungen und Modelldateien bleiben erhalten. Die SHA-256-Dateien ermöglichen einen Integritätsvergleich.

Testbuild: ohne Herausgebersignatur / Apple-Notarisierung. Windows und macOS können Warnungen anzeigen. Die CI prüft Installation, erneute Installation, Appstart und Modellverifier; sie belegt keine Inferenz auf dem Windows-Zielgerät.

Anleitung, Quellen, Grenzen und Deinstallation: [docs/installation.md](https://github.com/Ceda1998/cedexiaNexus/blob/main/docs/installation.md).
