; Instalador de Lycan Face Control (modelo: el de su programa hermano, Lycan M. Control).
;
; En la nube: .github\workflows\windows.yml
; A mano:     iscc /DMyAppVersion=1.1.0 empaquetado\lycan-face-control.iss
;             (sin /DMyAppVersion compila igual como version 0.0.0)
;
; El AppId es FIJO: no cambiarlo nunca, o Windows toma cada version como otro programa.

#define MyAppName "Lycan Face Control"
#define MyAppPublisher "Lycan Developments"
#define MyAppExeName "LycanFaceControl.exe"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
; VersionInfoVersion solo acepta numeros (a.b.c.d). El workflow pasa /DMyAppVersionNum con la
; parte numerica cuando la version trae algo como "1.1.0-beta".
#ifndef MyAppVersionNum
  #define MyAppVersionNum MyAppVersion
#endif

[Setup]
AppId={{B4BABCB7-C4E4-4A96-88FE-6619BB585A56}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersionNum}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Lycan Face Control - maneje el computador con la cabeza y la cara
VersionInfoProductName={#MyAppName}

; Instalacion para el usuario actual, SIN pedir permiso de administrador
; (va a C:\Users\<usuario>\AppData\Local\Programs\Lycan Face Control).
; Si en el dialogo elige "para todos los usuarios", va a Program Files y pide administrador.
DefaultDirName={autopf}\Lycan Face Control
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes

OutputDir=..\dist
OutputBaseFilename=Lycan-Face-Control-{#MyAppVersion}-Windows-64-bits

WizardStyle=modern
ShowLanguageDialog=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; LZMA2 solido: la carpeta de ~200 MB queda en un instalador de ~55-60 MB.
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Cierra el programa si esta abierto al actualizar o desinstalar
; (si no, Windows no deja reemplazar los archivos en uso).
CloseApplications=force
RestartApplications=no
#if FileExists(AddBackslash(SourcePath) + "..\recursos\lycan-face.ico")
SetupIconFile=..\recursos\lycan-face.ico
#endif

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.Inicio=Abrir Lycan Face Control al encender el computador
spanish.Opciones=Opciones:
spanish.BorrarConfig=¿Desea borrar también su configuración (calibración, gestos, frases rápidas, palabras aprendidas y atajos) y los registros de errores?%n%nSi va a volver a instalar Lycan Face Control, elija No para conservarlos.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "inicio"; Description: "{cm:Inicio}"; GroupDescription: "{cm:Opciones}"; Flags: unchecked

[InstallDelete]
; Al actualizar, borrar la carpeta interna anterior para no mezclar DLL viejas.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\LycanFaceControl\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Arranque con Windows (solo si marca la casilla). Arranca activo si ya hay calibracion y en PAUSA si no
; (segun "arranque.estado" de la configuracion).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "LycanFaceControl"; \
    ValueData: """{app}\{#MyAppExeName}"" --minimizado"; \
    Tasks: inicio; Flags: uninsdeletevalue

; La configuracion y los registros viven en %APPDATA%\Lycan Face Control ({userappdata}).
; NO se borran sin preguntar: ver [Code] (por defecto se conservan).

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
// Al desinstalar: borrar SIEMPRE el arranque con Windows (tambien si lo activo el programa
// desde Opciones, que Inno no conoce) y preguntar si se borra la configuracion
// (por defecto se conserva).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Carpeta: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegValueExists(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'LycanFaceControl') then
      RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'LycanFaceControl');
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    Carpeta := ExpandConstant('{userappdata}\Lycan Face Control');
    if DirExists(Carpeta) and (not UninstallSilent) then
    begin
      if MsgBox(CustomMessage('BorrarConfig'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Carpeta, True, True, True);
    end;
  end;
end;
