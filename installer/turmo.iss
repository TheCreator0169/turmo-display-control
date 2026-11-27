; TURMO Display Control installer (Inno Setup 6). DRAFT for v0.3.0 M4: not compiled into a release yet.
; Build: ISCC.exe /DAppVersion=v0.2.9.9 installer\turmo.iss   (build_release.py will pass the version later)
; The two exes are one-file PyInstaller builds: themes, previews and assets are INSIDE the GUI exe, so they are not copied.
; Open decisions are marked TODO(user).

#ifndef AppVersion
  #define AppVersion "v0.0.0"
#endif

[Setup]
AppId={{B6E1D9C4-6C0F-4B7A-9E54-2F7A1D3C8B05}
AppName=TURMO Display Control
AppVersion={#AppVersion}
AppPublisher=TURMO
DefaultDirName={autopf}\TURMO Display Control
DefaultGroupName=TURMO Display Control
UninstallDisplayIcon={app}\TURMO-Display-Control.exe
SetupIconFile=turmo.ico
LicenseFile=..\LICENSE
InfoBeforeFile=info_before.txt
WizardImageFile=wizard_side.bmp
WizardSmallImageFile=wizard_small.bmp
OutputDir=..\dist
OutputBaseFilename=TURMO-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
; Per-machine (the CPU helper task needs admin). TODO(user): confirm per-machine only.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
CloseApplicationsFilter=TURMO-*.exe
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start TURMO with Windows"; Flags: unchecked

[Files]
Source: "..\dist\TURMO-Display-Control.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\TURMO-Monitor.exe"; DestDir: "{app}"; Flags: ignoreversion
; The CPU temperature helper is a separate onedir build (turmo_cpumonitor_helper.spec), unchanged between releases.
Source: "..\dist\TURMO-CpuTempHelper\*"; DestDir: "{app}\TURMO-CpuTempHelper"; Flags: ignoreversion recursesubdirs
Source: "helper_task.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\TURMO Display Control"; Filename: "{app}\TURMO-Display-Control.exe"
Name: "{autodesktop}\TURMO Display Control"; Filename: "{app}\TURMO-Display-Control.exe"; Tasks: desktopicon

[Registry]
; Same entry as the Settings switch: TURMO starts with Windows, hidden in the tray (the GUI starts the Monitor). Removed again on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TURMO";   ValueData: """{app}\TURMO-Display-Control.exe"" --startup"; Tasks: startup; Flags: uninsdeletevalue

[Run]
; The installer already runs as admin: the CPU temperature task is registered here, so the app never shows a UAC prompt for it.
; No driver (PawnIO) is installed by this script. Failure is not fatal: the Settings button stays as the repair.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\helper_task.ps1"" -Action install -Dir ""{app}\TURMO-CpuTempHelper""";   Flags: runhidden waituntilterminated; StatusMsg: "Enabling CPU temperature..."
Filename: "{app}\TURMO-Display-Control.exe"; Description: "Start TURMO Display Control"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\helper_task.ps1"" -Action remove -Dir ""{app}\TURMO-CpuTempHelper""";   Flags: runhidden waituntilterminated; RunOnceId: "RemoveTurmoHelperTask"

[Code]
// Upgrade over a running install: the elevated CPU helper holds its files open (setup would abort, exit 5, seen in
// Windows Sandbox). Remove its task and stop it by its exact path first; the [Run] step registers it again.
// The GUI and the Monitor are closed by Windows' Restart Manager (CloseApplications), which works by file lock, not by name.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  Script: String;
begin
  Result := '';
  Script := ExpandConstant('{app}\installer\helper_task.ps1');
  if FileExists(Script) then
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + Script + '" -Action remove -Dir "' +
      ExpandConstant('{app}\TURMO-CpuTempHelper') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// Uninstall asks whether to keep settings and custom themes (default: keep).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    if MsgBox('Also delete your settings and custom themes (%APPDATA%\TURMO)?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\TURMO'), True, True, True);
end;
