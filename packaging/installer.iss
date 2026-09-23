; DroidDesk installer. See Section 10.2.
;
; - Config goes to {userappdata}\DroidDesk, database to {localappdata}\DroidDesk
;   - never Program Files, which is not user-writable.
; - Bundles gitleaks.exe (the only external tool shipped; everything else is
;   discovered on the host via the ToolLocator chain, Section 3.1).
; - Registers a .apk file association so double-clicking opens the analyzer.
; - Enables long path support (Section 8.1 - deep Flutter/Gradle build trees).

#define MyAppName "DroidDesk"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DroidDesk"
#define MyAppExeName "droiddesk.exe"

[Setup]
AppId={{6C2B6C1E-6B2A-4A1E-9C1D-DROIDDESK0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=DroidDesk-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Files]
Source: "..\dist\__main__.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\droiddesk\resources\bin\gitleaks.exe"; DestDir: "{app}\resources\bin"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Registry]
Root: HKCU; Subkey: "Software\Classes\.apk"; ValueType: string; ValueName: ""; ValueData: "DroidDesk.ApkFile"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\DroidDesk.ApkFile"; ValueType: string; ValueName: ""; ValueData: "Android Package"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\DroidDesk.ApkFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function CheckAndroidSdk(): Boolean;
var
  AndroidHome: String;
  SdkRoot: String;
  LocalApp: String;
  Found: Boolean;
begin
  Found := False;
  AndroidHome := GetEnv('ANDROID_HOME');
  SdkRoot := GetEnv('ANDROID_SDK_ROOT');
  LocalApp := GetEnv('LOCALAPPDATA');

  if (AndroidHome <> '') and DirExists(AndroidHome) then
    Found := True
  else if (SdkRoot <> '') and DirExists(SdkRoot) then
    Found := True
  else if (LocalApp <> '') and DirExists(LocalApp + '\Android\Sdk') then
    Found := True;

  if not Found then
  begin
    SuppressibleMsgBox(
      'Notice: No Android SDK installation was automatically detected.' + #13#10 + #13#10 +
      'DroidDesk requires Android SDK command-line tools (adb, aapt2, apksigner) ' +
      'for device control and APK analysis. You can configure SDK locations ' +
      'in DroidDesk Settings or install Android Studio.',
      mbInformation, MB_OK, IDOK
    );
  end;

  Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := CheckAndroidSdk();
end;
