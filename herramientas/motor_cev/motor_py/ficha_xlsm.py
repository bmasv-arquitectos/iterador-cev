# -*- coding: utf-8 -*-
"""
La ficha 01 oficial (.xlsm) llenada, SIN Excel: lo que hace fichas_cev.escritor.generar
(copiar la plantilla y escribir celdas por COM), pero editando el XML del archivo.

1. ficha_virtual.construir llena la ficha en memoria con las MISMAS funciones del escritor
   (escribir_catalogo y llenar), validando celdas bloqueadas igual que Excel.
2. Se compara con las constantes de la plantilla (ficha_virtual.base): lo que cambio se
   escribe y lo que el escritor vacio se vacia ('CEV-CEVE' y '3. Tablas Envolvente').
3. xlsm.escribir_libro copia la plantilla tocando solo esas dos hojas y
   workbook.xml: macros, formulas, formatos, listas, imagenes y protecciones quedan tal
   cual; workbook.xml queda con fullCalcOnLoad="1" (Excel recalcula todo al abrirla) y se
   borra calcChain.xml (Excel lo rehace).

Diferencias con escritor.generar:
  - no elige los paquetes de la seccion 1.2 ('CEV-CEVE' E33:O40, seleccionar_paquetes):
    son textos compuestos por formula que solo existen despues de recalcular, y no
    entran al calculo (describen la vivienda en el certificado). Quedan como en la
    plantilla y se eligen en Excel;
  - un texto con forma de numero queda como texto (Excel lo convertiria en numero;
    ficha_virtual lo avisa);
  - hasta abrirla en Excel, las formulas guardan el valor de la plantilla.
Leerla de vuelta (entradas.leer_ficha) da la misma Ficha que la ficha virtual: el motor
Python la calcula igual.
"""
from __future__ import annotations

from pathlib import Path

from . import ficha_virtual as fvm
from .xlsm import Cambios, escribir_libro


def _distinto(a, b) -> bool:
    return a != b or type(a) is not type(b)


def cambios(fv, b) -> dict:
    """{hoja: Cambios} que llevan la plantilla (b: ficha_virtual.base) a la ficha virtual fv."""
    out = {}
    for h, despues in ((fvm.H_CEV, fv.cev), (fvm.H_TE, fv.tablas)):
        antes = b.valores.get(h, {})
        valores = {c: v for c, v in despues.items() if c not in antes or _distinto(antes[c], v)}
        limpiar = tuple(sorted(c for c in antes if c not in despues))
        out[h] = Cambios(valores=valores, limpiar=limpiar)
    return out


def escribir(ficha_cev, proyecto: dict, destino, plantilla=fvm.PLANTILLA, mapa: dict | None = None) -> tuple:
    """(ruta, FichaVirtual, estadisticas por hoja) de la ficha 01 escrita en destino.
    ficha_cev, proyecto: los de recinto.a_ficha.construir o unidad.cev.construir."""
    plantilla, destino = Path(plantilla), Path(destino)
    fv = fvm.construir(ficha_cev, proyecto, mapa, plantilla)
    stats = escribir_libro(plantilla, destino, cambios(fv, fvm.base(str(plantilla))))
    return destino, fv, stats
