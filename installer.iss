; Inno Setup script for MartinWorks Converter
; Packages the PyInstaller one-folder build into a single shareable Setup.exe.

#define MyAppName "MartinWorks Converter"
; Single source of truth for the version: the VERSION file at the repo root.
#define MyAppVersion Trim(FileRead(FileOpen("VERSION")))
#define MyAppPublisher "Martin de Lange"
#define MyAppURL "https://martinworks.org"
#define MyAppExeName "Image Converter.exe"
; Where PyInstaller leaves the one-folder build (see converter.spec).
#define MyBuildDir "dist\Image Converter"

[Setup]
; All paths below are relative to this script.
SourceDir=.
AppId={{8F3A1C2E-5B7D-4E9A-A1F6-2C9D4B8E7A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppCopyright=Copyright (C) 2026 Martin de Lange (MartinWorks). Licensed under the GNU AGPL v3 or later.
LicenseFile=LICENSE
VersionInfoVersion=1.0.0.0
VersionInfoCompany=Martin de Lange (MartinWorks)
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (C) 2026 Martin de Lange
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install: no admin/UAC prompt, friendlier to share.
PrivilegesRequired=lowest
; Keep the output off the Desktop: Windows Defender locks new .exe files written
; there while Inno stamps the version resource (EndUpdateResource then fails).
OutputDir=build\installer
OutputBaseFilename=MartinWorks Converter Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#MyBuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyBuildDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; DestName: "License.txt"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\MartinWorks Converter"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function PriorInstallDir(): String;
var s: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\MartinWorks Converter', 'InstallDir', s) then
    Result := s;
end;

// If the Converter is already installed, offer to repair/reinstall or uninstall.
function InitializeSetup(): Boolean;
var dir, unins: String; res: Integer;
begin
  Result := True;
  dir := PriorInstallDir();
  // Only prompt for an interactive install; a silent reinstall just repairs.
  if (dir <> '') and DirExists(dir) and (not WizardSilent()) then begin
    unins := AddBackslash(dir) + 'unins000.exe';
    res := MsgBox('MartinWorks Converter is already installed on this computer.' #13#10 #13#10
      + 'YES  -  repair / reinstall it (recommended after an update)' #13#10
      + 'NO   -  uninstall it' #13#10
      + 'CANCEL  -  do nothing',
      mbConfirmation, MB_YESNOCANCEL);
    if res = IDNO then begin
      if FileExists(unins) then
        Exec(unins, '/SILENT', '', SW_SHOW, ewWaitUntilTerminated, res);
      Result := False;
    end else if res = IDCANCEL then
      Result := False;
  end;
end;
