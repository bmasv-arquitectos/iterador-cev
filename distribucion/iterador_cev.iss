; Instalador de Windows del Iterador CEV (Inno Setup 6.3 o mas nuevo).
; Se compila con distribucion\armar_instalador.ps1, que pasa los datos de
; herramientas\comun\distribucion.yaml (version, editor, icono, aviso) con /D.
;
; - Sin administrador: se instala para el usuario en %LOCALAPPDATA%\Programs\IteradorCEV
;   (el dialogo deja elegir "para todos" si se tiene permiso).
; - Antes de instalar muestra el aviso legal (distribucion\generado\aviso_instalador.txt).
; - Acceso en el menu Inicio y, si se marca, en el escritorio.
; - Al actualizar borra las librerias de la version anterior (_internal) antes de copiar.
; - Al desinstalar borra %LOCALAPPDATA%\IteradorCEV (cache del motor, carpetas de
;   calculo, estado del aviso y registro). Lo que el usuario guardo con "Guardar como" no se toca.
;
; Compresion: el compilador de Inno Setup es de 32 bits (maximo unos 2 GB de memoria).
; lzma2/ultra64 con varios hilos la agota con ~300 MB de archivos ("Out of memory"); por eso
; lzma2/max, un solo hilo y el compresor en un proceso aparte (LZMAUseSeparateProcess, con
; su propia memoria). Para otra: armar_instalador.ps1 -Compresion "lzma2/normal" (mas rapido,
; algo mas grande) o "lzma2/ultra" (mas chico, mas memoria).

#ifndef Nombre
  #define Nombre "Iterador CEV"
#endif
#ifndef Version
  #define Version "0.1 beta"
#endif
#ifndef VersionNum
  #define VersionNum "0.1.0"
#endif
#ifndef Editor
  #define Editor "B+V Arquitectos"
#endif
#ifndef Url
  #define Url ""
#endif
#ifndef Origen
  #define Origen "dist\IteradorCEV"
#endif
#ifndef Salida
  #define Salida "instalador"
#endif
#ifndef Archivo
  #define Archivo "IteradorCEV-instalador"
#endif
#ifndef Icono
  #define Icono "generado\iterador_cev.ico"
#endif
#ifndef Aviso
  #define Aviso "generado\aviso_instalador.txt"
#endif
#ifndef Compresion
  #define Compresion "lzma2/max"
#endif
#define Exe "IteradorCEV.exe"

[Setup]
; AppId identifica al programa entre versiones: no cambiarlo nunca
AppId={{8F3C2A51-6B7D-4E2A-9C41-3D5E7F9A1B20}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher={#Editor}
#if Url != ""
AppPublisherURL={#Url}
AppSupportURL={#Url}
#endif
VersionInfoVersion={#VersionNum}
VersionInfoProductName={#Nombre}
VersionInfoCompany={#Editor}
DefaultDirName={autopf}\IteradorCEV
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Salida}
OutputBaseFilename={#Archivo}
SetupIconFile={#Icono}
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nombre} {#Version}
Compression={#Compresion}
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
InfoBeforeFile={#Aviso}
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#Exe}"; Description: "{cm:LaunchProgram,{#Nombre}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\IteradorCEV"
