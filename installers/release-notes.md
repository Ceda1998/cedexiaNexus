Geführte Installation von Cedexia Nexus mit Python, Qt und llama.cpp. Keine GGUF-Gewichte enthalten, keine Downloads während der Installation.

Einzelgerät und Mehrgeräte sind direkt in der Seitenleiste sichtbar. Für die Kopplung zeigt WLAN nur WLAN-Adapter sowie den verbundenen Netzwerknamen, wenn das Betriebssystem ihn freigibt. Scrollleisten sind im dunklen Design besser erkennbar.

- **macOS:** `CedexiaNexus-macOS-arm64-<Version>.pkg` für Apple Silicon, macOS 14+. Installation ins eigene Benutzerkonto unter `~/Applications`.
- **Windows:** `CedexiaNexus-Windows-x64-Setup-<Version>.exe` für Windows 10/11 x64. Die App passt GPU-Layer automatisch an den Speicher an und bietet in den Modelleinstellungen einen CPU-Gegencheck. Für GPU-Inferenz ist ein kompatibler NVIDIA-Treiber erforderlich. Die CUDA-Laufzeitbibliotheken sind enthalten.

Nach der Installation zeigt die Titelleiste Version und Kurz-Commit. Unter Einstellungen → Modelle → GGUF hinzufügen eine vorhandene Datei wählen, dann das Modell unter dem Chat auswählen. Bestehende Chats, Einstellungen und Modelldateien bleiben erhalten. Die SHA-256-Dateien ermöglichen einen Integritätsvergleich.

Testbuild: ohne Herausgebersignatur / Apple-Notarisierung. Windows und macOS können Warnungen anzeigen. Die CI prüft Installation, erneute Installation, Appstart und Modellverifier; sie belegt keine Inferenz auf dem Windows-Zielgerät.

Anleitung, Quellen, Grenzen und Deinstallation: [docs/installation.md](https://github.com/Ceda1998/cedexiaNexus/blob/main/docs/installation.md).
