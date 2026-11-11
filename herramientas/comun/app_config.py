# -*- coding: utf-8 -*-
"""
Configuracion de la distribucion: modo (escritorio | web), version, motores, aviso
legal, creditos y ventana propia. Lo editable esta en comun/distribucion.yaml;
ITERADOR_MODO reemplaza el modo del archivo (util en el servidor web) e
ITERADOR_VENTANA (nativa | navegador) si se abre en ventana propia.

Aviso al abrir: en escritorio, una vez (y otra vez con cada version nueva si
repetir_por_version); queda anotado en <carpeta del usuario>/estado.json. En la web,
cada vez, y el servidor no guarda nada de los visitantes.
No usa NiceGUI (se prueba sola).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .rutas_app import carpeta_usuario, empaquetado

CONFIG = Path(__file__).with_name("distribucion.yaml")
ENV_MODO = "ITERADOR_MODO"
ENV_VENTANA = "ITERADOR_VENTANA"
MODOS = ("escritorio", "web")
FRECUENCIAS = ("una_vez", "cada_vez", "nunca")
ESTADO = "estado.json"
SI = ("si", "sí", "true", "1", "nativa")
VENTANA = {"nativa": "auto", "ancho": 1440, "alto": 900, "maximizada": True, "depurar": False,
           "textos": {"guardado": "Guardado en {ruta}", "error_dialogo": "No se pudo abrir «Guardar como»: {error}",
                      "error_guardar": "No se pudo guardar: {error}", "todos": "Todos los archivos (*.*)"}}


@lru_cache(maxsize=1)
def config() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["app"]


# --------------------------------------------------------------------------- modo y version
def modo() -> str:
    m = str(os.environ.get(ENV_MODO) or config().get("modo") or "escritorio").strip().lower()
    if m not in MODOS:
        raise ValueError(f"modo desconocido: {m!r} (usa {' o '.join(MODOS)})")
    return m


def es_web() -> bool:
    return modo() == "web"


def nombre() -> str:
    return str(config()["nombre"])


def version() -> str:
    return str(config()["version"])


def version_numero() -> str:
    """La version solo con numeros ("0.1.0"): version_numero del archivo o los numeros de version."""
    v = config().get("version_numero")
    if v:
        return str(v)
    nums = re.findall(r"\d+", version())[:3]
    return ".".join((nums + ["0", "0", "0"])[:3])


def titulo_barra() -> str:
    return str(config().get("titulo_barra") or "{nombre}").format(nombre=nombre(), version=version())


def motores() -> list:
    return list((config().get("motores") or {}).get(modo()) or ["python"])


# --------------------------------------------------------------------------- ventana propia
def ventana() -> dict:
    """Opciones de la ventana; v["nativa"] queda en True o False: nunca en la web; auto = solo
    en el programa empaquetado; ITERADOR_VENTANA (nativa | navegador) manda sobre el archivo."""
    archivo = config().get("ventana") or {}
    v = {**VENTANA, **archivo, "textos": {**VENTANA["textos"], **(archivo.get("textos") or {})}}
    pedido = str(os.environ.get(ENV_VENTANA) or v["nativa"]).strip().lower()
    if es_web():
        v["nativa"] = False
    elif pedido == "auto":
        v["nativa"] = empaquetado()
    else:
        v["nativa"] = pedido in SI
    return v


# --------------------------------------------------------------------------- aviso y creditos
def aviso() -> dict:
    return config()["aviso"]


def texto_aviso() -> str:
    return " ".join(str(aviso()["texto"]).split())


def sufijo_archivo() -> str:
    return str(aviso().get("sufijo_archivo") or "")


def pie_reporte() -> str:
    return str(aviso().get("pie_reporte") or "").format(nombre=nombre(), version=version())


def creditos() -> dict:
    return config()["creditos"]


def opciones_web() -> dict:
    return config().get("web") or {}


# --------------------------------------------------------------------------- estado del usuario (escritorio)
def _ruta_estado(carpeta=None) -> Path:
    return Path(carpeta or carpeta_usuario()) / ESTADO


def _leer_estado(carpeta=None) -> dict:
    try:
        return json.loads(_ruta_estado(carpeta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _clave_aviso() -> str:
    return version() if aviso().get("repetir_por_version", True) else "*"


def debe_mostrar_aviso(carpeta=None) -> bool:
    frec = (aviso().get("al_abrir") or {}).get(modo(), "una_vez")
    if frec not in FRECUENCIAS:
        raise ValueError(f"aviso.al_abrir desconocido: {frec!r} (usa {', '.join(FRECUENCIAS)})")
    if frec == "nunca":
        return False
    if frec == "cada_vez":
        return True
    return _leer_estado(carpeta).get("aviso_aceptado") != _clave_aviso()


def marcar_aviso_aceptado(carpeta=None) -> None:
    if es_web():
        return                                   # el servidor no guarda estado de los visitantes
    ruta = _ruta_estado(carpeta)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        estado = _leer_estado(carpeta)
        estado["aviso_aceptado"] = _clave_aviso()
        ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass                                     # sin permiso de escritura: se vuelve a mostrar
