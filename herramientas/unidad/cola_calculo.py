# -*- coding: utf-8 -*-
"""
El motor Python en procesos aparte, con cupo y fila de espera (modo web).

En la web varias personas calculan a la vez. El motor es calculo puro y, en un hilo del
servidor, retiene el GIL de Python: dejaria lenta la interfaz de todos. Con
calculo.en_procesos (distribucion_ui.preparar lo activa en la web) cada calculo corre en
un proceso de un grupo fijo (calculo.simultaneos, por defecto 2) y los demas esperan en
fila (calculo.cola_max, por defecto 20; con la fila llena se avisa y no se calcula). El
progreso y la cancelacion pasan entre procesos por una cola y un evento. Textos:
calculo.textos_cola (comun/distribucion.yaml, web.textos).

  motor_resumen(ficha, antes_de_caso)         el calculo en el proceso actual (escritorio)
  en_proceso(ficha, avanzar, cancelar, cfg)   lo mismo en el grupo de procesos (web)

Los dos devuelven {"resumen", "tiempos", "base_cal", "base_ref"}: solo datos simples, que
pasan de un proceso a otro.
Cada proceso compila el motor la primera vez que calcula: los primeros calculos de cada
proceso tardan mas.
Lo de multiprocessing se importa dentro de las funciones que lo usan: el modulo se importa
tambien donde no hay procesos (el navegador, con Pyodide).
"""
from __future__ import annotations

import queue as _cola
import threading

from herramientas.comun.tarea import Cancelado, revisar

TEXTOS = {
    "espera": "En espera: {n} cálculo(s) en la fila",
    "lleno": "Hay muchos cálculos en espera. Intenta de nuevo en unos minutos.",
    "caso": "Calculando: caso {k} de {total}{extra}",
    "primera": " (la primera vez carga datos y compila)",
    "caido": "El proceso del motor se detuvo. Vuelve a calcular.",
}
SONDEO_S = 0.25

_lock = threading.Lock()
_estado = {"pool": None, "manager": None, "cupo": None, "esperando": 0}


class CanceladoEnProceso(Exception):
    """El calculo se cancelo dentro del proceso del motor."""


def motor_resumen(ficha, antes_de_caso=None) -> dict:
    """Los 10 casos y la planilla 03 de una Ficha (motor_py.calcular), en datos simples."""
    from herramientas.motor_cev.motor_py.calcular import calcular

    cal = calcular(ficha, antes_de_caso=antes_de_caso)
    out = {"resumen": dict(cal.resumen or {}), "tiempos": dict(cal.tiempos or {}),
           "base_cal": None, "base_ref": None}
    if cal.planilla is not None:
        out["base_cal"] = cal.planilla.valor("Resumen", "E7")
        out["base_ref"] = cal.planilla.valor("Resumen", "F7")
    return out


def _trabajo(ficha, cola, cancelar) -> dict:
    """Corre en el proceso del motor: avisa cada caso por la cola y mira el evento de cancelar."""
    def antes(k, total, caso):
        if cancelar.is_set():
            raise CanceladoEnProceso()
        cola.put((k, total))

    return motor_resumen(ficha, antes)


def _grupo(simultaneos: int):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    with _lock:
        if _estado["cupo"] is None:
            _estado["cupo"] = threading.BoundedSemaphore(simultaneos)
        if _estado["pool"] is None:
            ctx = mp.get_context("spawn")
            _estado["pool"] = ProcessPoolExecutor(max_workers=simultaneos, mp_context=ctx)
            if _estado["manager"] is None:
                _estado["manager"] = ctx.Manager()
        return _estado["pool"], _estado["manager"], _estado["cupo"]


def _reiniciar() -> None:
    """Un proceso del motor murio: el grupo queda roto y se arma otro en el proximo calculo."""
    with _lock:
        pool, _estado["pool"] = _estado["pool"], None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def en_espera() -> int:
    return _estado["esperando"]


def en_proceso(ficha, avanzar, cancelar, cfg: dict | None = None) -> dict:
    """motor_resumen en el grupo de procesos, esperando turno si esta lleno.
    ValueError (mensaje para el usuario) si la fila esta llena; Cancelado si se cancela."""
    cfg = cfg or {}
    tx = {**TEXTOS, **(cfg.get("textos_cola") or {})}
    with _lock:
        if _estado["esperando"] >= int(cfg.get("cola_max", 20)):
            raise ValueError(tx["lleno"])
        _estado["esperando"] += 1
    try:
        from concurrent.futures.process import BrokenProcessPool

        pool, manager, cupo = _grupo(max(1, int(cfg.get("simultaneos", 2))))
        while not cupo.acquire(timeout=0.5):
            revisar(cancelar)
            avanzar(0.05, tx["espera"].format(n=_estado["esperando"]))
    finally:
        with _lock:
            _estado["esperando"] -= 1
    try:
        cola, evento = manager.Queue(), manager.Event()
        try:
            fut = pool.submit(_trabajo, ficha, cola, evento)
        except BrokenProcessPool:
            _reiniciar()
            raise RuntimeError(tx["caido"]) from None
        while not fut.done():
            if cancelar is not None and cancelar.is_set():
                evento.set()
            try:
                k, total = cola.get(timeout=SONDEO_S)
            except _cola.Empty:
                continue
            extra = tx["primera"] if k == 0 else ""
            avanzar(0.08 + 0.84 * k / max(total, 1), tx["caso"].format(k=k + 1, total=total, extra=extra))
        try:
            return fut.result()
        except CanceladoEnProceso:
            raise Cancelado from None
        except BrokenProcessPool:
            _reiniciar()
            raise RuntimeError(tx["caido"]) from None
    finally:
        cupo.release()
