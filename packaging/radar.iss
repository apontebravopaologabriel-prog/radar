; Inno Setup: instalador de Radar para Windows. Se compila con `iscc /DAppVersion=1.0.0 packaging\radar.iss`
; después de `pyinstaller packaging\radar.spec` (que crea dist\Radar\).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F2B8A3E-52C1-4D7A-9B51-0A1D2C3E4F50}
AppName=Radar
AppVersion={#AppVersion}
AppPublisher=Radar
DefaultDirName={autopf}\Radar
DefaultGroupName=Radar
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=Radar-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\Radar.exe
LicenseFile=..\LICENSE

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked
Name: "autostart"; Description: "Iniciar Radar con Windows (mantiene la captura semanal al día)"; Flags: unchecked

[Files]
Source: "..\dist\Radar\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Radar"; Filename: "{app}\Radar.exe"
Name: "{autodesktop}\Radar"; Filename: "{app}\Radar.exe"; Tasks: desktopicon
Name: "{userstartup}\Radar"; Filename: "{app}\Radar.exe"; Tasks: autostart

[Run]
Filename: "{app}\Radar.exe"; Description: "Abrir Radar"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Los datos personales (base, CV, claves) viven en %LOCALAPPDATA%\radar y NO se borran al desinstalar.
Type: filesandordirs; Name: "{app}"
