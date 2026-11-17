# -*- coding: utf-8 -*-
"""
Arma web/public/py/herramientas.zip: el paquete herramientas que carga el navegador (Pyodide,
web/src/python/worker.ts), y web/public/py/paquete.json (archivos, tamano y huella). Copia
ademas los iconos de la interfaz (herramientas/app_unidad/iconos) a web/public/iconos/, que
en el instalable sirve app.add_static_files("/iconos", ...) (en la web, nicegui_web.ESTATICOS).

Solo archivos versionados (git ls-files) de CARPETAS, sin EXCLUIR: en el repositorio publico
son solo los publicados, asi que el sitio armado alli no lleva nada mas. El zip es
reproducible (orden y fechas fijas): misma huella si nada cambio.
Incluye la interfaz del instalable (app_unidad), que en la web corre con NiceGUI en el
navegador (herramientas/web/nicegui_web.py; NiceGUI lo empaqueta empaquetar_nicegui.py).

    python web/scripts/empaquetar_python.py        (o, desde web/: npm run python)
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "web" / "public" / "py"
ICONOS = RAIZ / "herramientas" / "app_unidad" / "iconos"
DESTINO_ICONOS = RAIZ / "web" / "public" / "iconos"
CARPETAS = ("herramientas/__init__.py", "herramientas/web/", "herramientas/comun/", "herramientas/unidad/",
            "herramientas/recinto/", "herramientas/far/", "herramientas/fichas_cev/", "herramientas/motor_cev/",
            "herramientas/app_cev/", "herramientas/app_unidad/")
EXCLUIR = re.compile(r"(__pycache__/|/analisis/|\.md$|/bases/0[23]\.|/bases/.*\.pdf$|app_cev/motores_)")
FECHA = (1980, 1, 1, 0, 0, 0)


def archivos() -> list:
    r = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "herramientas"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return sorted(f for f in r.stdout.splitlines()
                  if f.startswith(CARPETAS) and not EXCLUIR.search(f) and (RAIZ / f).is_file())


def copiar_iconos() -> int:
    if DESTINO_ICONOS.exists():
        shutil.rmtree(DESTINO_ICONOS)
    DESTINO_ICONOS.mkdir(parents=True)
    n = 0
    for p in sorted(ICONOS.glob("*")):
        if p.is_file() and p.suffix.lower() in (".svg", ".png"):
            shutil.copyfile(p, DESTINO_ICONOS / p.name)
            n += 1
    return n


def main() -> int:
    lista = archivos()
    if not lista:
        print("ERROR: no hay archivos (se corre dentro del repositorio)")
        return 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    zip_ = DESTINO / "herramientas.zip"
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in lista:
            info = zipfile.ZipInfo(f, date_time=FECHA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (RAIZ / f).read_bytes())
    datos = zip_.read_bytes()
    resumen = {"archivos": len(lista), "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest(),
               "creado": datetime.now().isoformat(timespec="seconds")}
    (DESTINO / "paquete.json").write_text(json.dumps(resumen, indent=1), encoding="utf-8")
    n = copiar_iconos()
    print(f"{zip_} ({len(lista)} archivos, {len(datos) / 1e6:.1f} MB)")
    print(f"{DESTINO_ICONOS} ({n} iconos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
