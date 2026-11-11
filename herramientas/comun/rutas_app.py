# -*- coding: utf-8 -*-
"""
Donde estan las cosas, con el codigo en el repositorio o empaquetado (PyInstaller).

  recurso(...)      archivos que vienen con el programa (plantilla PBTD, mapa.yaml, datos,
                    iconos, config): relativos a la raiz del repositorio, o a la carpeta
                    del programa empaquetado (sys._MEIPASS). No dependen de la carpeta de
                    trabajo.
  carpeta_usuario() datos propios del usuario: %LOCALAPPDATA%\\IteradorCEV en Windows,
                    ~/Library/Application Support/IteradorCEV en Mac, ~/.local/share/
                    iterador-cev en Linux. Variable de entorno ITERADOR_CEV_DATOS para
                    cambiarla.
  salida(ruta)      donde se escriben los resultados. Una ruta absoluta queda igual; una
                    relativa ("salidas/iterador_unidad", como en config/editor.yaml) va a
                    carpeta_salidas(): <repositorio>/salidas al desarrollar (igual que
                    antes, ejecutando desde la raiz) y <carpeta del usuario>/salidas
                    empaquetado. Variable ITERADOR_CEV_SALIDAS para cambiarla.
  preparar_entorno() al arrancar la app, antes de importar numba: empaquetado, deja la
                    cache de numba en la carpeta del usuario (NUMBA_CACHE_DIR; asi no
                    recompila en cada arranque) y la carpeta de trabajo en la del programa
                    (red de seguridad para alguna ruta relativa que quede).

No importa nada del resto del proyecto (se puede usar desde cualquier modulo).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

NOMBRE = "IteradorCEV"
NOMBRE_LINUX = "iterador-cev"
ENV_DATOS = "ITERADOR_CEV_DATOS"
ENV_SALIDAS = "ITERADOR_CEV_SALIDAS"
PREFIJO_SALIDAS = "salidas"


def empaquetado() -> bool:
    """El programa corre empaquetado (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def raiz() -> Path:
    """Raiz de los recursos: el repositorio, o la carpeta del programa empaquetado."""
    base = getattr(sys, "_MEIPASS", None)
    if empaquetado() and base:
        return Path(base)
    return Path(__file__).resolve().parents[2]


def recurso(*partes) -> Path:
    """Archivo que viene con el programa, p. ej. recurso("herramientas/fichas_cev/mapa.yaml")."""
    return raiz().joinpath(*partes)


def carpeta_usuario() -> Path:
    """Carpeta de los datos del usuario (no se crea aca)."""
    if os.environ.get(ENV_DATOS):
        return Path(os.environ[ENV_DATOS])
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / NOMBRE
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOMBRE
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / NOMBRE_LINUX


def carpeta_salidas() -> Path:
    if os.environ.get(ENV_SALIDAS):
        return Path(os.environ[ENV_SALIDAS])
    return (carpeta_usuario() if empaquetado() else raiz()) / PREFIJO_SALIDAS


def salida(ruta=None) -> Path:
    """Ruta de resultados: absoluta, igual; relativa, dentro de carpeta_salidas() (sin repetir
    el "salidas/" inicial). None: carpeta_salidas()."""
    if ruta is None or str(ruta).strip() == "":
        return carpeta_salidas()
    p = Path(ruta)
    if p.is_absolute():
        return p
    partes = p.parts
    if partes and partes[0] == PREFIJO_SALIDAS:
        partes = partes[1:]
    return carpeta_salidas().joinpath(*partes)


def preparar_entorno() -> None:
    """Llamar al arrancar la app, antes de importar numba. Fuera del empaquetado no cambia nada."""
    if not empaquetado():
        return
    usuario = carpeta_usuario()
    usuario.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("NUMBA_CACHE_DIR"):
        cache = usuario / "numba"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["NUMBA_CACHE_DIR"] = str(cache)
    try:
        os.chdir(raiz())
    except OSError:
        pass
