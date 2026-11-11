# Ejecutable e instalador de Windows del Iterador CEV

Una carpeta con `IteradorCEV.exe` y `_internal/`, y un instalador que la copia. Lleva solo el
motor Python (sin Excel ni pywin32) y abre su propia ventana (pywebview sobre WebView2, que ya
viene con Windows 10 y 11). Las descargas abren el «Guardar como» de Windows.

## Entorno (una vez)

Un entorno virtual aparte y limpio (PyInstaller mete en el ejecutable lo que encuentra en el
entorno: con el Python global sale con librerias que no usa y pesa mucho mas). Inno Setup
para el instalador:

```powershell
py -3.12 -m venv .venv-exe          # o la version de Python que tengas (3.12 o 3.13)
.\.venv-exe\Scripts\python.exe -m pip install --upgrade pip
winget install --id JRSoftware.InnoSetup -e
```

## Armar

```powershell
.\.venv-exe\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File distribucion\armar_instalador.ps1          # .exe sin consola + instalador
powershell -ExecutionPolicy Bypass -File distribucion\armar_exe.ps1 -Consola        # solo el .exe, con consola (ver errores)
powershell -ExecutionPolicy Bypass -File distribucion\armar_instalador.ps1 -SinExe  # solo el instalador
```

- Ejecutable: `distribucion\dist\IteradorCEV\IteradorCEV.exe` (unos 300 MB)
- Instalador: `distribucion\instalador\IteradorCEV-<version>-instalador.exe` (unos 100 MB)

Si el ejecutable pesa mucho mas, `armar_exe.ps1` lista las carpetas mas grandes: lo mas
probable es que se haya armado con un entorno que tiene otras librerias.

`build\`, `dist\`, `generado\` e `instalador\` no se versionan.

## Nueva version

1. Cambiar `version` y `version_numero` en `herramientas/comun/distribucion.yaml`.
2. Armar el instalador. Al instalarlo encima, reemplaza la version anterior (mismo AppId) y
   el aviso legal vuelve a aparecer una vez.

## Icono

Tres flechas con colores de la escala CEV: `distribucion.yaml`, seccion `icono:`. Se rehace
al armar (`distribucion\preparar.py`); `distribucion\generado\iterador_cev.svg` sirve para la web.

## Instalacion

- Sin administrador: `%LOCALAPPDATA%\Programs\IteradorCEV`, acceso en el menu Inicio y, si se
  marca, en el escritorio. Se desinstala desde Configuracion > Aplicaciones.
- Windows SmartScreen avisa porque el instalador no esta firmado: "Mas informacion" >
  "Ejecutar de todas formas".

## Donde guarda sus cosas

`%LOCALAPPDATA%\IteradorCEV\` (se borra al desinstalar):

- `estado.json`: si ya se acepto el aviso legal (por version);
- `numba\`: la compilacion del motor (el primer calculo tarda mas; los siguientes no);
- `salidas\`: las carpetas de cada calculo (para el boton Resultados .zip);
- `registro.txt`: lo que el programa escribio en el ultimo arranque (para diagnosticar).

## Probar sin empaquetar

```powershell
$env:ITERADOR_VENTANA = "nativa"; python -m herramientas.app_unidad
```

## Opciones

`herramientas/comun/distribucion.yaml`: `ventana:` (tamano, maximizada, textos; `depurar: true`
para las herramientas de desarrollador), `icono:`, `aviso:` y `creditos:`.
