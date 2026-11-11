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
"""
from __future__ import annotations

import threading
import traceback


class Cancelado(Exception):
    pass


def revisar(cancelar) -> None:
    """Lanza Cancelado si se pidio cancelar."""
    if cancelar is not None and cancelar.is_set():
        raise Cancelado


class Tarea:
    def __init__(self):
        self._hilo: threading.Thread | None = None
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

    def iniciar(self, fn, *args, **kw) -> None:
        if self.estado == "corriendo":
            raise RuntimeError("ya hay una tarea en curso")
        self._cancelar = threading.Event()
        self.progreso, self.mensaje = 0.0, ""
        self.resultado, self.error = None, None
        cancelar = self._cancelar

        def correr():
            try:
                self.resultado = fn(*args, avanzar=self.avanzar, cancelar=cancelar, **kw)
                self._final = "terminada"
            except Cancelado:
                self.mensaje, self._final = "cancelado", "cancelada"
            except ValueError as ex:
                self.error, self._final = str(ex), "error"
            except Exception as ex:                      # se muestra en la interfaz
                traceback.print_exc()
                self.error, self._final = f"{type(ex).__name__}: {ex}", "error"

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
