; Inno Setup script for the WebWays per-user installer. Build: iscc /DAppVersion=0.4.0 packaging\windows\webways.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{CDCD0F89-CD94-415F-95C2-914CEBF53267}
AppName=WebWays
AppVersion={#AppVersion}
AppPublisher=aryank2212
AppPublisherURL=https://github.com/aryank2212/WebWays
AppSupportURL=https://github.com/aryank2212/WebWays/issues
DefaultDirName={autopf}\WebWays
DefaultGroupName=WebWays
; Installs for the current user only: no administrator rights needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist-installer
OutputBaseFilename=WebWays-Setup-{#AppVersion}
SetupIconFile=webways.ico
UninstallDisplayIcon={app}\WebWays.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\WebWays\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Icons]
Name: "{autoprograms}\WebWays"; Filename: "{app}\WebWays.exe"; IconFilename: "{app}\WebWays.exe"
Name: "{autodesktop}\WebWays"; Filename: "{app}\WebWays.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WebWays.exe"; Description: "Start WebWays now"; Flags: nowait postinstall skipifsilent

; Uninstall removes the program only. Your settings, publisher key, resume data and downloads are left alone:
;   %LOCALAPPDATA%\WebWays   and   %USERPROFILE%\Downloads\WebWays
