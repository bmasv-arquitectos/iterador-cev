# -*- coding: utf-8 -*-
"""
"Calculadora" del editor (como unidad/calculo_cev.py, ver calculo.modulo de config/editor.yaml)
para la interfaz del instalable corriendo en el navegador (nicegui_web.py).

El proceso de la interfaz no calcula: le pide a la pagina (canal_js, canal "calculo") que corra el
motor repartido en los procesos de calculo (web/src/cev/motor.ts, calcularRepartido, con el
nucleo en JavaScript), y espera sin bloquear: mientras tanto la interfaz sigue viva y la barra de
progreso avanza. La pagina avisa con avance(), listo() y fallo() (web/src/apps/iterador-nicegui).
Con el resumen de la planilla 03 arma el mismo resultado que calculo_cev (etiqueta, detalle,
CSV, carpeta con unidad.json, resumen.json, resultado.csv y la etiqueta en SVG).

calcular() es async: comun/tarea.Tarea la espera en el navegador. Cancelar se nota en el
siguiente aviso de avance (el calculo de los otros procesos termina, pero se descarta).
vista, detalle, paquete, imagen y motores son los de calculo_cev.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import time

from herramientas.comun.tarea import Cancelado
from herramientas.unidad import calculo_cev as cc
from herramientas.unidad.calculo_cev import detalle, imagen, motores, paquete, vista  # noqa: F401

CANAL = "calculo"
INICIO, TRAMO = 0.03, 0.90          # el avance de la pagina (0..1) va de INICIO a INICIO + TRAMO
_pendientes: dict = {}
_ids = itertools.count(1)


async def _remoto(unidad: str, avanzar, cancelar) -> dict:
    """Pide el calculo a la pagina y espera {planilla, segundos}."""
    import canal_js

    n = next(_ids)
    fut = asyncio.get_event_loop().create_future()
    _pendientes[n] = {"fut": fut, "avanzar": avanzar, "cancelar": cancelar}
    canal_js.enviar(CANAL, json.dumps({"id": n, "unidad": unidad}))
    try:
        return await fut
    finally:
        _pendientes.pop(n, None)


def _activo(n):
    p = _pendientes.get(int(n))
    if p is None or p["fut"].done():
        return None
    c = p["cancelar"]
    if c is not None and c.is_set():
        p["fut"].set_exception(Cancelado())
        return None
    return p


def avance(n, fraccion, mensaje: str = "") -> bool:
    """La pagina avisa el progreso; False si el calculo ya no interesa (cancelado o terminado)."""
    p = _activo(n)
    if p is None:
        return False
    p["avanzar"](INICIO + TRAMO * max(0.0, min(1.0, float(fraccion))), str(mensaje))
    return True


def listo(n, resultado) -> bool:
    p = _activo(n)
    if p is not None:
        p["fut"].set_result(resultado)
    return p is not None


def fallo(n, mensaje) -> bool:
    p = _activo(n)
    if p is not None:
        p["fut"].set_exception(RuntimeError(str(mensaje)))
    return p is not None


async def calcular(u, avanzar=None, cancelar=None, cfg: dict | None = None, motor: str = "python") -> dict:
    """Unidad -> motor repartido en los procesos de calculo -> resultado (y su carpeta)."""
    from herramientas.app_cev.ejecucion import carpeta_nueva, resultado_python
    from herramientas.unidad import cev, modelo

    from . import motor_web

    cfg = cfg or {}
    avanzar = avanzar or (lambda f, m="": None)
    inicio = time.perf_counter()
    avanzar(0.01, "Traduciendo la unidad a la ficha 01")
    t = cev.construir(u)                                   # ValueError: mensaje para el usuario
    out = await _remoto(motor_web.a_texto(u), avanzar, cancelar)
    pl = out.get("planilla") or {}
    if not pl.get("resumen"):
        raise RuntimeError("el motor no entrego el resumen de la planilla 03")
    carpeta = carpeta_nueva(cc._salida(cfg))
    r = dict(pl["resumen"])
    r["carpeta"] = str(carpeta)
    res = resultado_python(r)
    res["tiempos"] = dict(out.get("segundos") or {})
    res["demanda_base_cal"] = cc._numero(pl.get("base_cal"))
    res["demanda_base_ref"] = cc._numero(pl.get("base_ref"))
    cc.completar_bases(res)
    res.update(carpeta=str(carpeta), backend=motor, avisos=list(t.avisos), zona=t.zona,
               area=sum(t.geometria.areas), volumen=t.geometria.volumen, far=cc.resumen_far(t),
               minutos=(time.perf_counter() - inicio) / 60, huella=pl.get("huella"))
    avanzar(0.96, "Guardando la etiqueta y el resumen")
    modelo.guardar(u, carpeta / "unidad.json")
    (carpeta / "resumen.json").write_text(
        json.dumps({"nota": res.get("nota"), "resultado": res}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    cc.escribir_csv(res, carpeta / "resultado.csv")
    ec, ecfg = cc._etiqueta(cfg)
    (carpeta / f"{ecfg['png']['nombre']}.svg").write_text(ec.svg(res, ecfg), encoding="utf-8")
    avanzar(1.0, "Listo")
    return res
