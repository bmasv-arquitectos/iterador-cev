# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller: Iterador CEV para Windows, en UNA CARPETA (dist/IteradorCEV/IteradorCEV.exe y
_internal/). Se arma con distribucion/armar_exe.ps1 (ver distribucion/LEEME.md), que antes
corre distribucion/preparar.py (el icono queda en distribucion/generado/).

Incluye:
  - el paquete herramientas (sus modulos, aunque se importen con importlib) y sus archivos
    que no son .py (config/*.yaml, datos, plantilla PBTD, mapas, iconos, estilo.css,
    modelos), en la misma ruta relativa: comun/rutas_app.recurso y los
    Path(__file__).parent / ... los encuentran dentro de _internal/;
  - NiceGUI (sus archivos estaticos), pywebview y pythonnet (ventana propia sobre
    WebView2), numba y llvmlite, shapely y PyMuPDF.
Deja fuera: pywin32 (si el entorno lo tiene, se sacan sus DLL igual), los .md, las pruebas de
las librerias y las librerias pesadas que la app no usa (PESADAS): NiceGUI tiene elementos
opcionales que las importan (graficos, tablas de pandas) y, si el entorno las tiene,
PyInstaller las meteria enteras (torch, scipy, pandas, matplotlib...: cientos de MB).
Nunca se excluye una dependencia declarada (obligatoria, sin extras) de los paquetes que se
incluyen: se lee de los metadatos instalados (dependencias()). Asi, si NiceGUI pasa a
necesitar algo de la lista, entra igual (pygments, que usa ui.markdown, fallo asi una vez).
Variable ITERADOR_CONSOLA=1 (armar_exe.ps1 -Consola): con consola, para ver errores.
"""
import os
import re
import sys
from importlib import metadata
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(RAIZ))

NOMBRE = "IteradorCEV"
CONSOLA = os.environ.get("ITERADOR_CONSOLA") == "1"
ICONO = RAIZ / "distribucion" / "generado" / "iterador_cev.ico"
PAQUETES = ("nicegui", "webview", "pythonnet", "clr_loader", "numba", "llvmlite", "shapely", "pymupdf")
# distribuciones (nombre en pip) cuyas dependencias obligatorias nunca se excluyen
DISTRIBUCIONES = ("nicegui", "pywebview", "pythonnet", "clr-loader", "numba", "llvmlite", "shapely", "pymupdf",
                  "pyyaml", "openpyxl", "reportlab", "pypdf")
OMITIR_CARPETAS = {"__pycache__"}
OMITIR_EXT = {".py", ".pyc", ".pyo", ".md"}
PESADAS = ["torch", "torchvision", "torchaudio", "tensorflow", "keras", "jax", "jaxlib", "onnxruntime", "onnx",
           "transformers", "diffusers", "accelerate", "safetensors", "huggingface_hub", "tokenizers",
           "cv2", "skimage", "sklearn", "scipy", "pandas", "polars", "pyarrow", "matplotlib", "plotly",
           "kaleido", "bokeh", "altair", "seaborn", "sympy", "networkx", "numexpr", "tables", "h5py",
           "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "notebook", "jupyter", "jupyterlab", "ipykernel",
           "zmq", "sphinx"]


def _norm(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def dependencias(raices) -> set:
    """Distribuciones (normalizadas) que necesitan las raices, sin las de extras opcionales."""
    vistas, pendientes = set(), [_norm(r) for r in raices]
    while pendientes:
        d = pendientes.pop()
        if d in vistas:
            continue
        vistas.add(d)
        try:
            req = metadata.requires(d) or []
        except metadata.PackageNotFoundError:
            continue
        for r in req:
            if "extra ==" in r.replace('"', "'"):
                continue
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", r)
            if m:
                pendientes.append(_norm(m.group(1)))
    return vistas


def modulos_de(distribuciones: set) -> set:
    """Modulos de primer nivel que instalan esas distribuciones."""
    out = set()
    for modulo, dists in metadata.packages_distributions().items():
        if any(_norm(x) in distribuciones for x in dists):
            out.add(modulo)
    return out


NECESARIOS = modulos_de(dependencias(DISTRIBUCIONES))
protegidas = sorted(p for p in PESADAS if p in NECESARIOS)
if protegidas:
    print("[iterador] se incluyen porque las necesita una dependencia:", ", ".join(protegidas))
PESADAS = [p for p in PESADAS if p not in NECESARIOS]

EXCLUIR = ["win32com", "pythoncom", "pywintypes", "win32api", "win32con", "win32comext", "pythonwin",
           "xlwings", "tkinter", "pytest", "IPython"] + PESADAS
# pruebas de las librerias (no hacen falta para correr)
PRUEBAS = re.compile(r"([\\/.]tests?([\\/.]|$))", re.I)
# pywin32 (por si el entorno lo tiene: sus DLL entran por los hooks aunque no se importe)
PYWIN32 = re.compile(r"(^|[\\/])(pywintypes\d*\.dll|pythoncom\d*\.dll|win32com|win32comext|pywin32_system32|"
                     r"pythonwin|win32|win32\w*\.pyd)([\\/]|$)", re.I)
# archivos de las librerias pesadas que igual entren por un hook (sus carpetas .libs, DLL)
RASTRO_PESADAS = re.compile(r"(^|[\\/])(" + "|".join(re.escape(p) for p in PESADAS) + r")([\\/.]|$)", re.I)


def pesada(nombre: str) -> bool:
    return nombre.split(".")[0] in PESADAS


datas, binaries, hidden = [], [], []
for paquete in PAQUETES:
    try:
        d, b, h = collect_all(paquete)
    except Exception as ex:                                # p. ej. sin pythonnet fuera de Windows
        print(f"[iterador] no se incluye {paquete}: {ex}")
        continue
    datas += [x for x in d if not PRUEBAS.search(x[1])]
    binaries += b
    hidden += [m for m in h if not PRUEBAS.search(m) and not pesada(m)]

base = RAIZ / "herramientas"
for f in sorted(base.rglob("*")):
    if not f.is_file() or f.suffix.lower() in OMITIR_EXT:
        continue
    if OMITIR_CARPETAS & set(f.relative_to(base).parts):
        continue
    datas.append((str(f), f.parent.relative_to(RAIZ).as_posix()))

hidden += collect_submodules("herramientas")

a = Analysis(
    [str(RAIZ / "distribucion" / "iterador_cev.py")],
    pathex=[str(RAIZ)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=EXCLUIR,
    noarchive=False,
)
fuera = re.compile(PYWIN32.pattern + "|" + RASTRO_PESADAS.pattern, re.I)
sacados = sorted({e[0] for e in list(a.binaries) + list(a.datas) if fuera.search(e[0])})
if sacados:
    print(f"[iterador] fuera del ejecutable ({len(sacados)}):", ", ".join(sacados[:12]))
a.binaries = [e for e in a.binaries if not fuera.search(e[0])]
a.datas = [e for e in a.datas if not fuera.search(e[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE,
    console=CONSOLA,
    icon=str(ICONO) if ICONO.is_file() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NOMBRE, upx=False)
