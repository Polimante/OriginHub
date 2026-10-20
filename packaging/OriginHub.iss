; Inno Setup script: wraps dist\OriginHub\ into dist\OriginHub-Setup-<version>.exe
; Run through packaging\build.ps1, or: ISCC /DAppVersion=0.2.0 packaging\OriginHub.iss
;
; Installs per user (no administrator rights) into %LOCALAPPDATA%\Programs\OriginHub, so
; updates can be installed without a Windows permission prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; never change AppId: Windows uses it to recognize upgrades of the same app
AppId={{632EE1B2-7DB5-42A9-8E71-B8E198C9175E}
AppName=OriginHub
AppVersion={#AppVersion}
AppVerName=OriginHub {#AppVersion}
AppPublisher=Lucas Polimante (UFABC)
AppPublisherURL=https://github.com/Polimante/OriginHub
AppSupportURL=https://github.com/Polimante/OriginHub/issues
AppUpdatesURL=https://github.com/Polimante/OriginHub/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\OriginHub
DefaultGroupName=OriginHub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=OriginHub-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\OriginHub.exe
UninstallDisplayName=OriginHub
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; an upgrade starts from a clean folder: files removed from a new version must not linger
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\OriginHub\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\OriginHub"; Filename: "{app}\OriginHub.exe"
Name: "{autodesktop}\OriginHub"; Filename: "{app}\OriginHub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OriginHub.exe"; Description: "{cm:LaunchProgram,OriginHub}"; Flags: nowait postinstall skipifsilent
