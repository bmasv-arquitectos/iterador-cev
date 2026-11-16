# -*- coding: utf-8 -*-
"""
Una tarea larga en un hilo, con progreso y cancelacion. Sin interfaz: la
interfaz solo lee estado, progreso y mensaje (por ejemplo con un ui.timer).

La funcion que corre recibe dos argumentos con nombre:
    avanzar(fraccion, mensaje)   informa el progreso (0..1)
    cancelar                     threading.Event; si esta puesto, la funcion
                                 debe lanzar Cancelado lo antes posible
y devuelve el resultado (cualquier objeto).

    t = Tarea()
    t.iniciar(fn, unidad, cfg=...)      # fn(unidad, avanzar=..., cancelar=..., cfg=...)
    t.estado                            # inactiva | corriendo | terminada | cancelada | error
    t.progreso, t.mensaje, t.resultado, t.error

Un ValueError se muestra como mensaje para el usuario (sin el tipo); cualquier
otro error, con su tipo y el detalle en la consola.

En el navegador (Pyodide) no hay hilos: la funcion corre en el bucle de eventos, un momento
despues de iniciar (asi la interfaz alcanza a mostrar que empezo). Si es async (devuelve algo
que se espera), se espera sin bloquear: la interfaz sigue viva y el progreso se ve. Una funcion
normal, en cambio, deja la pagina quieta mientras corre.
Fuera del navegador una funcion async corre con asyncio.run dentro del hilo.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import traceback

EN_NAVEGADOR = sys.platform == "emscripten"
ESPERA_NAVEGADOR_S = 0.15


class Cancelado(Exception):
    pass


def revisar(cancelar) -> None:
    """Lanza Cancelado si se pidio cancelar."""
    if cancelar is not None and cancelar.is_set():
        raise Cancelado


class _HiloNavegador:
    """Lo que Tarea usa de threading.Thread, sin hilos: corre fn en el bucle de eventos; si fn
    devuelve algo que se espera, sigue "vivo" hasta que termine."""

    def __init__(self, fn, espera: float = ESPERA_NAVEGADOR_S):
        self._fn, self._espera, self._vivo = fn, espera, False
        self._tarea = None

    def start(self) -> None:
        self._vivo = True
        asyncio.get_event_loop().call_later(self._espera, self._correr)

    def _terminar(self, *_):
        self._vivo = False

    def _correr(self) -> None:
        try:
            r = self._fn()
        except BaseException:
            self._vivo = False
            raise
        if inspect.isawaitable(r):
            self._tarea = asyncio.ensure_future(r)
            self._tarea.add_done_callback(self._terminar)
        else:
            self._vivo = False

    def is_alive(self) -> bool:
        return self._vivo

    def join(self, timeout=None) -> None:
        pass


class Tarea:
    def __init__(self):
        self._hilo = None
        self._cancelar = threading.Event()
        self._final = "inactiva"
        self.progreso = 0.0
        self.mensaje = ""
        self.resultado = None
        self.error: str | None = None

    @property
    def estado(self) -> str:
        if self._hilo is None:
            return "inactiva"
        if self._hilo.is_alive():
            return "corriendo"
        return self._final

    def _fallo(self, ex: Exception) -> None:
        if isinstance(ex, Cancelado):
            self.mensaje, self._final = "cancelado", "cancelada"
        elif isinstance(ex, ValueError):
            self.error, self._final = str(ex), "error"
        else:                                            # se muestra en la interfaz
            traceback.print_exception(ex)
            self.error, self._final = f"{type(ex).__name__}: {ex}", "error"

    async def _esperar(self, aw) -> None:
        try:
            self.resultado = await aw
            self._final = "terminada"
        except Exception as ex:
            self._fallo(ex)

    def iniciar(self, fn, *args, **kw) -> None:
        if self.estado == "corriendo":
            raise RuntimeError("ya hay una tarea en curso")
        self._cancelar = threading.Event()
        self.progreso, self.mensaje = 0.0, ""
        self.resultado, self.error = None, None
        cancelar = self._cancelar

        def correr():
            try:
                r = fn(*args, avanzar=self.avanzar, cancelar=cancelar, **kw)
            except Exception as ex:
                self._fallo(ex)
                return None
            if inspect.isawaitable(r):
                if EN_NAVEGADOR:
                    return self._esperar(r)          # _HiloNavegador la espera
                asyncio.run(self._esperar(r))
                return None
            self.resultado, self._final = r, "terminada"
            return None

        if EN_NAVEGADOR:
            self._hilo = _HiloNavegador(correr)
        else:
            self._hilo = threading.Thread(target=correr, daemon=True)
        self._hilo.start()

    def avanzar(self, fraccion: float, mensaje: str = "") -> None:
        self.progreso = max(0.0, min(1.0, float(fraccion)))
        self.mensaje = mensaje

    def cancelar(self) -> None:
        self._cancelar.set()

    def esperar(self, timeout: float | None = None) -> None:
        if self._hilo is not None:
            self._hilo.join(timeout)
