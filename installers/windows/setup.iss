#ifndef AppVersion
  #define AppVersion "0.1.58"
#endif
[Setup]
AppId={{A64CB32E-B30B-4CB9-9FC8-69B28B3AE058}
AppName=Cedexia Nexus
AppVersion={#AppVersion}
AppPublisher=Cedexia
DefaultDirName={localappdata}\Programs\Cedexia Nexus
DefaultGroupName=Cedexia Nexus
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
InfoBeforeFile=welcome.txt
InfoAfterFile=finished.txt
OutputDir=..\..\dist\installers
OutputBaseFilename=CedexiaNexus-Windows-x64-Setup
Compression=lzma2/fast
SolidCompression=yes
UninstallDisplayIcon={app}\CedexiaNexus.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=no
[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked
[Files]
Source: "..\..\dist\CedexiaNexus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Cedexia Nexus"; Filename: "{app}\CedexiaNexus.exe"
Name: "{autodesktop}\Cedexia Nexus"; Filename: "{app}\CedexiaNexus.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\CedexiaNexus.exe"; Description: "Cedexia Nexus starten"; Flags: nowait postinstall skipifsilent
