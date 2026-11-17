# -*- coding: utf-8 -*-
"""
NiceGUI para el navegador: la interfaz web es la misma del instalable (app_unidad), con
NiceGUI corriendo en Pyodide y sin servidor (herramientas/web/nicegui_web.py). Este script toma
NiceGUI y sus dependencias TAL COMO ESTAN INSTALADOS en el entorno activo (.venv), asi la
version del navegador es la misma que se probo en escritorio, y arma:

  public/py/nicegui.zip    lo que importa Python: NiceGUI y sus dependencias de Python puro.
                           De NiceGUI van todos sus archivos salvo static/ y elements/lib/, que
                           van vacios (Python solo necesita que existan; el navegador los
                           descarga de public/ng/).
  public/py/nicegui.json   version de NiceGUI, paquetes puros incluidos, paquetes con codigo
                           compilado (se piden a Pyodide con micropip), modulos de la
                           biblioteca estandar que Pyodide trae aparte (STDLIB: se cargan con
                           loadPackage) y los que se omiten.
  public/ng/_nicegui/<version>/
                           lo que NiceGUI sirve al navegador, con su misma ruta: static/ (Vue,
                           Quasar, nicegui.js) y nicegui/... (todos los archivos del paquete que
                           no son Python: componentes de elements/, functions/refreshable.js,
                           librerias de elements/lib sin las pesadas que el editor no usa,
                           OMITIR_LIB). nicegui_web reescribe las URL con claves hacia nicegui/.

Los paquetes con codigo compilado (.pyd/.so) no sirven en el navegador: se usan los de Pyodide
(pydantic va siempre desde Pyodide, para que calce con su pydantic_core). Los de SIN_NAVEGADOR
(servidor, recarga, ventana propia) no se piden.

    python web/scripts/empaquetar_nicegui.py        (o, desde web/: npm run nicegui)
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO_PY = RAIZ / "web" / "public" / "py"
DESTINO_NG = RAIZ / "web" / "public" / "ng"
ANTIGUO = RAIZ / "web" / "public" / "nc"        # ubicacion anterior (se borra)
FECHA = (1980, 1, 1, 0, 0, 0)
BINARIO = (".pyd", ".so", ".dll", ".dylib")
# siempre desde Pyodide (version emparejada con su parte compilada)
DESDE_PYODIDE = {"pydantic", "pydantic-core"}
# biblioteca estandar que Pyodide no carga sola (engineio y uvicorn importan ssl)
STDLIB = ["ssl"]
# servidor, recarga y ventana propia: no hacen falta en el navegador
SIN_NAVEGADOR = {"uvloop", "httptools", "watchfiles", "websockets", "pywebview", "pywin32", "pythonnet",
                 "clr-loader", "proxy-tools", "bottle", "pyobjc", "pyqt5", "pyqt6", "pyside6", "cffi"}
# librerias de NiceGUI (elements/lib/<carpeta>) que el editor no usa
OMITIR_LIB = ("plotly", "echarts", "mermaid", "aggrid", "codemirror", "leaflet", "nipplejs", "vanilla-jsoneditor",
              "highcharts", "mathjax", "anywidget", "altair", "vega", "xterm", "pyecharts")
# del paquete nicegui no van al navegador: Python, plantillas, pruebas y documentacion
NO_NAVEGADOR = (".py", ".pyc", ".pyi", ".md", ".typed")
CARPETAS_FUERA = ("static", "templates", "testing", "__pycache__")


def norma(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def requisitos(dist) -> list:
    """Nombres de los requisitos que aplican aqui (sin extras)."""
    try:
        from packaging.requirements import Requirement
    except ImportError:
        Requirement = None
    out = []
    for r in dist.requires or ():
        if Requirement is not None:
            try:
                req = Requirement(r)
                if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                    continue
                out.append(norma(req.name))
                continue
            except Exception:
                pass
        if "extra ==" in r:
            continue
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", r)
        if m:
            out.append(norma(m.group(1)))
    return out


def distribuciones(raiz: str = "nicegui") -> dict:
    """{nombre: Distribution} de raiz y todo lo que necesita (instalado)."""
    vistas, pendientes, faltan = {}, [norma(raiz)], []
    while pendientes:
        n = pendientes.pop()
        if n in vistas or n in SIN_NAVEGADOR:
            continue
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            faltan.append(n)
            continue
        vistas[n] = d
        pendientes += requisitos(d)
    if faltan:
        print("No instalados (se omiten):", ", ".join(sorted(set(faltan))))
    return vistas


def archivos(d) -> list:
    """[(ruta en site-packages, Path)] de una distribucion, sin pyc ni ejecutables."""
    out = []
    for f in d.files or ():
        s = str(f).replace("\\", "/")
        if s.startswith("..") or "__pycache__" in s or s.endswith(".pyc"):
            continue
        p = Path(d.locate_file(f))
        if p.is_file():
            out.append((s, p))
    return out


def binaria(d) -> bool:
    return any(s.endswith(BINARIO) for s, _ in archivos(d))


def escribir(z, nombre: str, datos: bytes) -> None:
    info = zipfile.ZipInfo(nombre, date_time=FECHA)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    z.writestr(info, datos)


def es_estatico(s: str) -> bool:
    """Archivo de NiceGUI que va al navegador (public/ng) y en el zip queda vacio."""
    return s.startswith(("nicegui/static/", "nicegui/elements/lib/"))


def omitido(rel: str) -> bool:
    partes = rel.split("/")
    return len(partes) > 2 and partes[0] == "elements" and partes[1] == "lib" and \
        any(partes[2].startswith(o) for o in OMITIR_LIB)


def para_navegador(rel: str) -> bool:
    """rel (relativa al paquete nicegui) es un archivo que el navegador puede pedir."""
    partes = rel.split("/")
    return (partes[0] not in CARPETAS_FUERA and "__pycache__" not in partes
            and not rel.endswith(NO_NAVEGADOR) and not omitido(rel))


def copiar_navegador(raiz_nc: Path, version: str) -> tuple:
    """static/ en public/ng/_nicegui/<version>/static/ y el resto de los archivos del paquete que
    no son Python en public/ng/_nicegui/<version>/nicegui/ (misma ruta que dentro del paquete)."""
    for vieja in (DESTINO_NG, ANTIGUO):
        if vieja.exists():
            shutil.rmtree(vieja)
    base = DESTINO_NG / "_nicegui" / version
    total, copiados = 0, 0
    for p in sorted(raiz_nc.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(raiz_nc).as_posix()
        if rel.startswith("static/"):
            if "__pycache__" in rel:
                continue
            dst = base / rel
        elif para_navegador(rel):
            dst = base / "nicegui" / rel
        else:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        total += p.stat().st_size
        copiados += 1
    return total, copiados


def main() -> int:
    try:
        import nicegui
    except ImportError:
        print("ERROR: NiceGUI no esta instalado en este entorno (activa el .venv)")
        return 1
    dists = distribuciones()
    puros, compilados, de_pyodide = [], [], []
    DESTINO_PY.mkdir(parents=True, exist_ok=True)
    zip_ = DESTINO_PY / "nicegui.zip"
    n_archivos = 0
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, d in sorted(dists.items()):
            ver = d.version
            if n in DESDE_PYODIDE:
                de_pyodide.append(n)
                continue
            if binaria(d):
                compilados.append(f"{n}=={ver}")
                continue
            puros.append(f"{n}=={ver}")
            for s, p in archivos(d):
                escribir(z, s, b"" if es_estatico(s) else p.read_bytes())
                n_archivos += 1
    datos = zip_.read_bytes()
    total, copiados = copiar_navegador(Path(nicegui.__file__).parent, nicegui.__version__)

    info = {"nicegui": nicegui.__version__, "python_escritorio": sys.version.split()[0],
            "puros": puros, "compilados": compilados,
            "pyodide": sorted(de_pyodide + [c.split("==")[0] for c in compilados]),
            "stdlib": list(STDLIB), "omitidos": sorted(SIN_NAVEGADOR), "zip_bytes": len(datos),
            "zip_sha256": hashlib.sha256(datos).hexdigest(), "nc_bytes": total, "nc_archivos": copiados}
    (DESTINO_PY / "nicegui.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(f"NiceGUI {nicegui.__version__}")
    print(f"{zip_}: {len(puros)} paquetes puros, {n_archivos} archivos, {len(datos) / 1e6:.1f} MB")
    print(f"Desde Pyodide: {', '.join(info['pyodide']) or '-'}")
    print(f"Biblioteca estandar aparte: {', '.join(STDLIB)}")
    print(f"{DESTINO_NG}: {copiados} archivos, {total / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
