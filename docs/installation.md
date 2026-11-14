# Cedexia Nexus installieren

Fertige Installationsdateien stehen unter den
[GitHub-Releases dieses Repositorys](https://github.com/Ceda1998/cedexiaNexus/releases).
Die Installerquellen liegen in `installers/`, die Builds in `scripts/`.
Binärdateien werden als Release-Downloads bereitgestellt, nicht in Git eingecheckt.

## macOS · Apple Silicon

1. `CedexiaNexus-macOS-arm64.pkg` herunterladen und doppelklicken.
2. Einführung und Hinweise lesen, mit **Fortfahren** bestätigen und für das
   eigene Benutzerkonto installieren. Ziel ist `~/Applications/Cedexia Nexus.app`.
3. Die App im Finder aus diesem Ordner starten.
4. **Einstellungen → Modelle → GGUF hinzufügen** öffnen. Eine vorhandene
   GGUF-Datei auswählen, anschließend das Modell unter dem Chat wählen.

macOS 14 oder neuer und ein Apple-Silicon-Mac sind erforderlich. Python, Qt und
llama.cpp mit Metal sind enthalten. Kein Homebrew, Xcode oder Compiler nötig.
Intel-Macs werden derzeit nicht unterstützt. Die App besitzt eine lokale
Ad-hoc-Signatur, das Paket keine Apple-Developer-ID oder Notarisierung. macOS
kann den Download deshalb blockieren. Nur bei bewusst vertrauter Herkunft den
Apple-Dialog unter **Systemeinstellungen → Datenschutz & Sicherheit** verwenden;
die Installer deaktivieren Gatekeeper nicht.

Zum Entfernen die App beenden und aus dem eigenen Programme-Ordner in den
Papierkorb verschieben. Chats, Einstellungen und Modelldateien bleiben erhalten.

## Windows · x64

1. `CedexiaNexus-Windows-x64-Setup.exe` herunterladen und starten.
2. Hinweise lesen, Zielordner wählen und optional eine Desktop-Verknüpfung anlegen.
3. Nach der Installation **Cedexia Nexus starten** auswählen oder das Startmenü nutzen.
4. Unter **Einstellungen → Modelle → GGUF hinzufügen** das eigene Modell hinzufügen.

Python, Qt, MCP-Client, llama.cpp und die CUDA-Laufzeitbibliotheken sind enthalten.
Python, Visual Studio und das CUDA-Toolkit müssen nicht separat installiert werden.
Die App installiert sich standardmäßig unter `%LOCALAPPDATA%\Programs\Cedexia Nexus`
für das aktuelle Konto, ohne Administratorrechte. Windows 10/11 x64 ist das Ziel.
Lokale GPU-Inferenz benötigt einen passenden NVIDIA-Treiber für CUDA 13.5; dieser
hardwareabhängige Systemtreiber ist kein Bestandteil des Installers. Falls nötig
über [NVIDIA](https://www.nvidia.com/drivers/) installieren und Windows neu starten.
Der Build ist unsigniert; Windows kann eine Herausgeberwarnung anzeigen.

Deinstallation über **Windows-Einstellungen → Apps → Cedexia Nexus**.
Persönliche Chats, Einstellungen und GGUFs werden nicht gelöscht.

## Umfang und Updates

Die Installation funktioniert nach dem Download offline. Sie lädt keine
GGUF-Gewichte und installiert keine fremden MCP-Serverprogramme, keine Dienste
und keine Firewall-Regeln. Ein Modell muss zur gebündelten llama.cpp-Version
passen und ausreichend Speicher vorfinden. Bei geteilten GGUFs den ersten Teil
wählen und alle Teile im selben Ordner belassen. Nach Modellimport sind Skills,
MCPs und Geräte über die Einstellungen erreichbar.

Vor Updates die App schließen, dann den neuen Installer ausführen. Die App-Dateien
werden aktualisiert; Daten außerhalb des Installationsordners bleiben erhalten.
Bei selbst ersetzten Qt-Bibliotheken vor einem Update eigene Kopien sichern.
SHA-256-Dateien neben den Downloads erlauben einen Integritätsvergleich. Sie sind
kein Ersatz für eine Herausgebersignatur. Drittlizenzen liegen bei; die eigene
Projektlizenz bleibt offen.

## Installer bauen und prüfen

Die CI `.github/workflows/installers.yml` baut beide Plattformen, prüft Installation
und Appstart und veröffentlicht bei Erfolg ein gemeinsames GitHub-Prerelease.
Die Modellruntime stammt aus llama.cpp b12347, Revision
`8ca5a8008b57aa39f2601546c0d07912045080a5`; Archivhashes stehen in den Buildskripten.
Satoshi und GGUFs sind nicht Teil der Pakete.

macOS auf Apple Silicon:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt pyinstaller==6.22.3
.venv/bin/python -m scripts.package_macos
```

Windows x64, mit Inno Setup 6 auf dem Buildrechner:

```powershell
py -3 -m pip install -r requirements-ui.txt pyinstaller==6.22.3
py -3 -m scripts.package_installers
```

Ausgaben: `dist/installers/`. Windows prüft Erstinstallation, erneute Installation,
Appstart, Modellverifier und Deinstallation. macOS prüft Appsignatur, Start und
Modellverifier; die CI installiert zusätzlich das PKG im Benutzerordner und startet
die installierte App. Diese Prüfungen enthalten keine Gewichte und belegen keine
Windows-GPU-Inferenz oder verteilte Modellberechnung. Installer auf dem physischen
Windows-Zielgerät und Gatekeeper/SmartScreen auf frischen Downloads sind separat
abzunehmen.
