# -*- coding: utf-8 -*-
"""
Ejecucion de un calculo en un hilo, con progreso y cancelacion, y registro de motores.

Un motor (backend) es fn(objeto, avanzar, cancelar, **opciones) -> dict, donde
avanzar(fraccion, mensaje) informa progreso y cancelar es un threading.Event.
El dict de salida usa: letra, ahorro_pct, ahorro_cal_pct, ahorro_ref_pct,
demanda, demanda_cal, demanda_ref, demanda_base, valido_entrega, nota, aviso,
archivo, minutos.

BACKENDS registra los motores por nombre; aca solo esta demo (prueba la interfaz sin
calcular). El editor de unidad calcula con el motor Python por su cuenta
(unidad/calculo_cev.py) y usa de aca resultado_python y carpeta_nueva. Otros motores se
agregan como modulos de esta carpeta cuyo nombre empieza con "motores_": al importar este
modulo se importan solos (cargar_extensiones) y registran los suyos en BACKENDS. Sin
ninguno, el unico motor que calcula es el Python.
"""
from __future__ import annotations

import importlib
import pkgutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

NOTA_PYTHON = ("Motor Python – solo para iteración, no válido para entrega. La calificación "
               "oficial se calcula con las planillas oficiales y la emite un evaluador acreditado.")
PREFIJO_EXTENSION = "motores_"


class Cancelado(Exception):
    pass


@dataclass(frozen=True)
class Backend:
    descripcion: str
    fn: Callable
    disponible: bool
    valido_entrega: bool


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pct(v):
    """Los ahorros de la 03 (G8, H8, C92) vienen como fraccion: 0,288 = 28,8 %."""
    v = _num(v)
    return None if v is None else 100.0 * v


def resultado_desde_resumen(r: dict, minutos: float | None = None) -> dict:
    """Resumen de la planilla 03 -> resultado para la interfaz."""
    out = {"letra": r.get("letra"),
           "ahorro_pct": _pct(r.get("ahorro_total")),
           "ahorro_cal_pct": _pct(r.get("ahorro_calefaccion")),
           "ahorro_ref_pct": _pct(r.get("ahorro_refrigeracion")),
           "demanda": _num(r.get("demanda_total")),
           "demanda_cal": _num(r.get("demanda_calefaccion")),
           "demanda_ref": _num(r.get("demanda_refrigeracion")),
           "demanda_base": _num(r.get("demanda_base_total")),
           "valido_entrega": True,
           "archivo": r.get("archivo"), "carpeta": r.get("carpeta"),
           "minutos": minutos if minutos is not None else r.get("minutos")}
    caso_base = str(r.get("caso_base") or "")
    if "NO OFICIAL" in caso_base.upper():
        out["aviso"] = f"{caso_base} (la calefacción de los casos base suma cero)"
    return out


def resultado_python(r: dict, minutos: float | None = None) -> dict:
    out = resultado_desde_resumen(r, minutos)
    out["valido_entrega"] = False
    out["nota"] = NOTA_PYTHON
    return out


def carpeta_nueva(base: Path) -> Path:
    """base/NNN (siguiente numero)."""
    from herramientas.motor_cev import rutas

    carpeta = Path(base) / rutas.siguiente_numero(Path(base))
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _demo(objeto, avanzar, cancelar, pasos: int = 20, pausa: float = 0.1, **_):
    for i in range(pasos):
        if cancelar.is_set():
            raise Cancelado
        time.sleep(pausa)
        avanzar((i + 1) / pasos, f"demo {i + 1}/{pasos}")
    return {"letra": None, "valido_entrega": False,
            "nota": "Demo: no calcula nada, solo prueba la interfaz."}


BACKENDS = {
    "demo": Backend("Demo de interfaz (no calcula)", _demo, True, False),
}


def disponible(nombre: str) -> bool:
    return nombre in BACKENDS and BACKENDS[nombre].disponible


class Ejecucion:
    def __init__(self):
        self._hilo: threading.Thread | None = None
        self._cancelar = threading.Event()
        self._final = "inactiva"
        self.progreso = 0.0
        self.mensaje = ""
        self.resultado: dict | None = None
        self.error: str | None = None

    @property
    def estado(self) -> str:
        if self._hilo is None:
            return "inactiva"
        if self._hilo.is_alive():
            return "corriendo"
        return self._final

    def iniciar(self, nombre: str, objeto, **opciones) -> None:
        if self.estado == "corriendo":
            raise RuntimeError("ya hay un cálculo en curso")
        if not disponible(nombre):
            raise ValueError(f"backend no disponible: {nombre}")
        b = BACKENDS[nombre]
        self._cancelar = threading.Event()
        self.progreso, self.mensaje = 0.0, "iniciando"
        self.resultado, self.error = None, None

        def correr():
            try:
                res = b.fn(objeto, self._avanzar, self._cancelar, **opciones)
                res.setdefault("backend", nombre)
                res.setdefault("valido_entrega", b.valido_entrega)
                self.resultado, self._final = res, "terminada"
            except Cancelado:
                self.mensaje, self._final = "cancelado", "cancelada"
            except Exception as ex:  # se muestra en la interfaz
                self.error, self._final = f"{type(ex).__name__}: {ex}", "error"

        self._hilo = threading.Thread(target=correr, daemon=True)
        self._hilo.start()

    def _avanzar(self, fraccion: float, mensaje: str = "") -> None:
        self.progreso = max(0.0, min(1.0, float(fraccion)))
        self.mensaje = mensaje

    def cancelar(self) -> None:
        self._cancelar.set()

    def esperar(self, timeout: float | None = None) -> None:
        if self._hilo:
            self._hilo.join(timeout)


def cargar_extensiones() -> list:
    """Importa los modulos de esta carpeta que empiezan con PREFIJO_EXTENSION (registran sus
    motores en BACKENDS). Un modulo que falla al importar se avisa y se salta."""
    paquete = __name__.rpartition(".")[0]
    cargadas = []
    for info in sorted(pkgutil.iter_modules([str(Path(__file__).parent)]), key=lambda m: m.name):
        if not info.name.startswith(PREFIJO_EXTENSION):
            continue
        try:
            importlib.import_module(f"{paquete}.{info.name}")
        except Exception as ex:
            print(f"No se pudo cargar {info.name}: {type(ex).__name__}: {ex}", flush=True)
            continue
        cargadas.append(info.name)
    return cargadas


EXTENSIONES = cargar_extensiones()
