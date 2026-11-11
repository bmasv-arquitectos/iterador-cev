# -*- coding: utf-8 -*-
"""
Unidad -> ficha 01 oficial (01.-PBTD-Datos-de-Arquitectura v2.2, .xlsm) llenada, sin
Excel: la misma ficha que usa el motor (cev.construir), escrita sobre una copia de la
plantilla oficial (motor_cev/motor_py/ficha_xlsm.py). Boton de la caja Detalles modelo.

La interfaz solo la entrega para descargar: se arma en una carpeta temporal que se borra
al terminar, asi queda unicamente donde el usuario la guarde. Con guardar=True queda ademas en <salida>/fichas01/ (comun/rutas_app.salida).
El nombre lleva al final el sufijo de uso referencial (comun/distribucion.yaml,
aviso.sufijo_archivo: " REFERENCIAL"). Al abrirla, Excel recalcula todo (hay que
habilitar el contenido). Los paquetes de la seccion 1.2 (textos del certificado) quedan
como en la plantilla: se eligen en Excel. Es una ficha de iteracion: la calificacion
oficial la emite un evaluador acreditado.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from herramientas.comun.app_config import sufijo_archivo
from herramientas.comun.rutas_app import salida as ruta_salida

from . import cev
from .modelo import Unidad

SALIDA = "salidas/iterador_unidad"
CARPETA = "fichas01"


@dataclass
class Exportacion:
    ruta: Path | None              # donde quedo guardada (None: solo para descargar)
    nombre: str                    # nombre del archivo (para descargar)
    datos: bytes
    avisos: list = field(default_factory=list)
    virtual: object = None         # ficha_virtual.FichaVirtual escrita (cev, tablas, ficha)


def _limpio(t) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", str(t or "")).strip()


def _sufijo() -> str:
    """" REFERENCIAL" (con un espacio delante) o "" si distribucion.yaml no trae sufijo."""
    s = _limpio(sufijo_archivo())
    return f" {s}" if s else ""


def exportar(u: Unidad, salida=None, unidad: str = "iterador", plantilla=None,
             guardar: bool = False) -> Exportacion:
    """La ficha 01 de la unidad (bytes y nombre para descargar). guardar: tambien queda en
    <salida>/fichas01/. ValueError (mensaje para el usuario) si no cabe en la ficha."""
    from herramientas.motor_cev.motor_py import ficha_virtual, ficha_xlsm

    t = cev.construir(u, unidad=unidad)
    plantilla = Path(plantilla or ficha_virtual.PLANTILLA)
    marca = datetime.now().strftime("%y-%m-%d %H-%M-%S")
    nombre = f"01.-PBTD {_limpio(u.comuna) or 'unidad'} {marca}{_sufijo()}{plantilla.suffix}"
    avisos = list(t.avisos)
    if guardar:
        ruta = ruta_salida(salida or SALIDA) / CARPETA / nombre
        ruta, fv, _ = ficha_xlsm.escribir(t.ficha, t.proyecto, ruta, plantilla)
        return Exportacion(ruta, nombre, ruta.read_bytes(), avisos + list(fv.avisos), fv)
    with tempfile.TemporaryDirectory(prefix="iterador_cev_") as tmp:
        ruta, fv, _ = ficha_xlsm.escribir(t.ficha, t.proyecto, Path(tmp) / nombre, plantilla)
        datos = ruta.read_bytes()
    return Exportacion(None, nombre, datos, avisos + list(fv.avisos), fv)
