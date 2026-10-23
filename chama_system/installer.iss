; ─────────────────────────────────────────────────────────────────────────────
; Finance Wise TBM — Inno Setup Installer Script
;
; Produces:  Output\FinanceWiseTBM_Setup_v1.0.0.exe
; Requires:  Inno Setup 6  (https://jrsoftware.org/isinfo.php)
; Build:     ISCC.exe installer.iss
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "Finance Wise TBM"
#define AppPublisher "Finance Wise"
#define AppVersion   "1.0.0"
#define AppExeName   "FinanceWiseTBM.exe"
#define AppId        "{{A3F8D2C1-7E4B-4A9F-B2D3-8C5E1F6A0B7D}"
#define SourceDir    "dist\FinanceWiseTBM"
#define OutputDir    "installer_output"

[Setup]
; Basic identity
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://financewise.local
AppSupportURL=https://financewise.local
AppUpdatesURL=https://financewise.local

; Versioning — allows in-place upgrades without uninstalling first
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Installer

; Install location
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir={#OutputDir}
OutputBaseFilename=FinanceWiseTBM_Setup_v{#AppVersion}

; Compression — LZMA2 gives best ratio for Python bundles
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Require admin for install (writes to Program Files + registry)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Visual — modern wizard style
WizardStyle=modern
WizardSizePercent=120
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Misc
ShowLanguageDialog=auto
DisableDirPage=no
DisableProgramGroupPage=no
ChangesAssociations=no


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "Create a &desktop shortcut";      GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupicon";   Description: "Start automatically at &login";   GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; ── Main application bundle ──────────────────────────────────────
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── Installer icon ───────────────────────────────────────────────
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion

; ── Visual C++ Redistributable (needed by some Python extensions) ─
; Uncomment if you bundle the VCRT installer alongside the .iss file:
; Source: "vcredist_x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
; Start Menu
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\app.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop (optional task)
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

; Startup (optional task) — run at Windows login (per-machine, avoids per-user warning)
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Registry]
; Register in Add/Remove Programs with metadata
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1"; \
    ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1"; \
    ValueType: string; ValueName: "Publisher"; ValueData: "{#AppPublisher}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1"; \
    ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue

[Run]
; Offer to launch app after install (runasoriginaluser prevents launching as elevated admin)
Filename: "{app}\{#AppExeName}"; \
    Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
; Gracefully kill the app before uninstalling
Filename: "taskkill.exe"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillApp"

[Code]
// ── Pre-install: kill running instance gracefully ────────────────
function InitializeSetup(): Boolean;
var
  DummyCode: Integer;
begin
  Result := True;
  if CheckForMutexes('FinanceWiseTBMRunning') then begin
    if MsgBox(
      '{#AppName} is currently running.' + #13#10 +
      'Click OK to close it automatically, or Cancel to abort.',
      mbConfirmation, MB_OKCANCEL) = IDOK then
    begin
      Exec('taskkill.exe', '/F /IM {#AppExeName}', '', SW_HIDE,
           ewWaitUntilTerminated, DummyCode);
      Sleep(1500);
    end else begin
      Result := False;
    end;
  end;
end;

// ── Post-uninstall: offer to keep user data ───────────────────────
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  CommonDir: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    DataDir := ExpandConstant('{userappdata}\FinanceWiseTBM');
    CommonDir := ExpandConstant('{commonappdata}\FinanceWiseTBM');
    if DirExists(DataDir) or DirExists(CommonDir) then begin
      if MsgBox(
        'Keep your database and settings?' + #13#10 +
        '(' + DataDir + ')' + #13#10#13#10 +
        'Click Yes to keep your data, No to delete it permanently.',
        mbConfirmation, MB_YESNO) = IDNO then
      begin
        if DirExists(DataDir) then
          DelTree(DataDir, True, True, True);
        if DirExists(CommonDir) then
          DelTree(CommonDir, True, True, True);
      end;
    end;
  end;
end;
