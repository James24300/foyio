; Script Inno Setup — Foyio v1.0.3
; Généré automatiquement par build_windows.py

#define MyAppName      "Foyio"
#define MyAppVersion   "1.0.3"
#define MyAppPublisher "James-William PULSFORD"
#define MyAppURL       "https://github.com/James24300/foyio"
#define MyAppExeName   "Foyio.exe"

[Setup]
AppId={{F0Y10APP-2026-ABCD-EF12-34567890ABCD}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=FoyioSetup-v{#MyAppVersion}
SetupIconFile=icons\foyio.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
MinVersion=10.0

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Lancer Foyio au démarrage de Windows"; GroupDescription: "Démarrage"; Flags: unchecked

[Files]
Source: "dist\Foyio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                        Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";                 Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";                   Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Supprime uniquement le dossier d'installation (pas les données utilisateur dans %APPDATA%)
Type: filesandordirs; Name: "{app}"