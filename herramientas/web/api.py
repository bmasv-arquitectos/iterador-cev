# -*- coding: utf-8 -*-
"""
Funciones del Iterador CEV para el cliente web (se llaman con puente.llamar).

F0, diagnostico:
  info()               versiones de Python y de la herramienta, y que librerias y modulos
                       cargan (en el navegador no hay numba: el motor usa Python puro y el
                       bucle de la simulacion en JavaScript, motor_web.usar_nucleo_js)
  probar_traduccion()  unidad de prueba -> ficha 01 -> ficha 01 virtual (sin simular), con
                       el tiempo de cada paso
  eco(valor)           devuelve lo que recibe (prueba del puente)
El calculo completo (F2) esta en motor_web.py.
"""
from __future__ import annotations

import importlib
import sys
import time

LIBRERIAS = ("numpy", "yaml", "openpyxl", "shapely", "pymupdf", "numba")
MODULOS = (
    "herramientas.comun.app_config",
    "herramientas.unidad.modelo",
    "herramientas.unidad.geometria",
    "herramientas.unidad.editor",
    "herramientas.unidad.vista_planta",
    "herramientas.unidad.cev",
    "herramientas.unidad.ficha01",
    "herramientas.motor_cev.calculo_py",
    "herramientas.motor_cev.motor_py.motor",
    "herramientas.motor_cev.motor_py.ficha_virtual",
    "herramientas.motor_cev.motor_py.ficha_xlsm",
    "herramientas.motor_cev.motor_py.calcular",
    "herramientas.unidad.calculo_cev",
    "herramientas.web.motor_web",
)


def _probar(nombre: str) -> dict:
    t0 = time.perf_counter()
    try:
        m = importlib.import_module(nombre)
    except Exception as ex:
        return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
    return {"ok": True, "version": str(getattr(m, "__version__", "") or ""),
            "s": round(time.perf_counter() - t0, 3)}


def info() -> dict:
    from herramientas.comun import app_config

    return {
        "python": sys.version.split()[0],
        "plataforma": sys.platform,
        "navegador": sys.platform == "emscripten",
        "herramienta": f"{app_config.nombre()} {app_config.version()}",
        "librerias": {n: _probar(n) for n in LIBRERIAS},
        "modulos": {n: _probar(n) for n in MODULOS},
    }


def unidad_prueba():
    """Un nivel, un muro exterior con ventana y un volumen de contexto (FAR)."""
    from herramientas.unidad import editor as ed
    from herramientas.unidad import modelo as m

    h = 2.4
    bloque = m.Contexto("Bloque", ((-6.0, 16.0), (14.0, 16.0), (14.0, 26.0), (-6.0, 26.0)), 12.0)
    n = m.Nivel(m.rectangulo(8, 6), tuple(m.Lado((m.Tramo(c),)) for c in
                                          ("exterior", "adiabatico", "adiabatico", "adiabatico")))
    u = m.Unidad("Santiago", (n,), h, contexto=(bloque,))
    w = ed.vano_desde_esquinas("ventana", (1.0, 0.9), (4.0, 2.1), 8.0, h, "DVH_AIRE_12")
    return ed.agregar_vano(u, 0, 0, 0, "ventana", w)


def probar_traduccion(avanzar=None) -> dict:
    avanzar = avanzar or (lambda f, m="": None)
    t, t0 = {}, time.perf_counter()

    def marca(clave):
        nonlocal t0
        t[clave] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()

    avanzar(0.05, "Importando la herramienta")
    from herramientas.motor_cev.motor_py import ficha_virtual
    from herramientas.unidad import cev
    marca("importar")
    avanzar(0.2, "Unidad de prueba")
    u = unidad_prueba()
    marca("unidad")
    avanzar(0.35, "Traduccion a la ficha 01")
    tr = cev.construir(u)
    marca("traduccion")
    avanzar(0.5, "Ficha 01 virtual (lee la plantilla oficial)")
    fv = ficha_virtual.construir(tr.ficha, tr.proyecto)
    marca("ficha_virtual")
    avanzar(1.0, "Listo")
    return {"tiempos": t, "comuna": fv.ficha.comuna, "zona": fv.ficha.zona,
            "celdas_escritas": fv.escritas, "avisos": list(tr.avisos) + list(fv.avisos)}


def eco(valor, avanzar=None):
    if avanzar is not None:
        avanzar(1.0, "eco")
    return valor
