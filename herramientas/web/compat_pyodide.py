# -*- coding: utf-8 -*-
"""
Compatibilidad de Pyodide (Python en el navegador) para importar NiceGUI y sus dependencias.

El navegador no tiene procesos ni memoria compartida, y Pyodide no trae los modulos en C que
los manejan. NiceGUI y su servidor los importan al cargarse aunque en el navegador no se usen
(nicegui.run importa multiprocessing.forkserver, que importa _multiprocessing y _posixshmem;
nicegui.native.native_mode importa multiprocessing.synchronize, que exige
_multiprocessing.SemLock). preparar() pone versiones minimas de esos modulos, antes de
importar NiceGUI:

  _multiprocessing   sem_unlink (no hace nada), flags vacio y SemLock: un semaforo de un solo
                     hilo (en el navegador Python corre en un solo hilo: nunca hay que esperar
                     a otro). Alcanza para que multiprocessing.synchronize importe y para usar
                     Lock, RLock, Semaphore o Event sin bloquear; esperar un semaforo en cero
                     con block=True da error en vez de colgarse.
  _posixshmem        shm_unlink (no hace nada) y shm_open (error: no hay memoria compartida)

Fuera del navegador no hace nada. Devuelve la lista de lo que agrego.
"""
from __future__ import annotations

import sys
import types

RECURSIVE_MUTEX, SEMAPHORE = 0, 1          # los mismos que multiprocessing.synchronize
SEM_VALUE_MAX = 2 ** 31 - 1


def _falta(nombre: str) -> bool:
    if nombre in sys.modules:
        return False
    try:
        __import__(nombre)
        return False
    except ImportError:
        return True


class SemLock:
    """Semaforo de un solo hilo con la interfaz de _multiprocessing.SemLock."""

    SEM_VALUE_MAX = SEM_VALUE_MAX

    def __init__(self, kind, value, maxvalue, name=None, unlink=True):
        self.kind, self.maxvalue, self.name = int(kind), int(maxvalue), name
        self.handle = id(self)
        self._valor = int(value)
        self._mio = 0                            # veces tomado (mutex recursivo)

    @classmethod
    def _rebuild(cls, handle, kind, maxvalue, name):
        return cls(kind, 1 if kind == RECURSIVE_MUTEX else 0, maxvalue, name)

    def acquire(self, block=True, timeout=None):
        if self.kind == RECURSIVE_MUTEX and self._mio:
            self._mio += 1
            return True
        if self._valor > 0:
            self._valor -= 1
            self._mio += 1
            return True
        if block and timeout is None:
            raise RuntimeError("en el navegador no hay otro hilo que libere este semaforo")
        return False

    def release(self):
        if self.kind == RECURSIVE_MUTEX:
            if not self._mio:
                raise AssertionError("attempt to release recursive lock not owned by thread")
            self._mio -= 1
            if self._mio:
                return
        elif self._valor >= self.maxvalue:
            raise ValueError("semaphore or lock released too many times")
        self._valor += 1

    __enter__ = acquire

    def __exit__(self, *args):
        self.release()

    def _count(self):
        return self._mio

    def _is_mine(self):
        return self._mio > 0

    def _get_value(self):
        return self._valor

    def _is_zero(self):
        return self._valor == 0

    def _after_fork(self):
        self._mio = 0


def _multiprocessing() -> types.ModuleType:
    m = types.ModuleType("_multiprocessing")
    m.__doc__ = "Version minima para Pyodide (herramientas.web.compat_pyodide)"
    m.flags = {}
    m.SemLock = SemLock

    def sem_unlink(nombre):
        return None

    m.sem_unlink = sem_unlink
    return m


def _posixshmem() -> types.ModuleType:
    m = types.ModuleType("_posixshmem")
    m.__doc__ = "Version vacia para Pyodide (herramientas.web.compat_pyodide)"

    def shm_open(path, flags, mode=0o777):
        raise OSError("no hay memoria compartida en el navegador")

    def shm_unlink(path):
        return None

    m.shm_open, m.shm_unlink = shm_open, shm_unlink
    return m


VACIOS = {"_multiprocessing": _multiprocessing, "_posixshmem": _posixshmem}


def preparar() -> list:
    if sys.platform != "emscripten":
        return []
    hechos = []
    for nombre, crear in VACIOS.items():
        if _falta(nombre):
            sys.modules[nombre] = crear()
            hechos.append(nombre)
    return hechos
