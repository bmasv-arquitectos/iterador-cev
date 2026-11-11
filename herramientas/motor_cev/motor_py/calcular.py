# -*- coding: utf-8 -*-
r"""
Calificacion CEV de una ficha 01, 100 % Python (sin Excel).

    ficha .xlsm (leer_ficha) -> motor.py (10 casos) -> planilla03.py -> letra

Es el clon del flujo oficial (ficha 01 -> motor 02 -> planilla 03): no corrige nada.

    python -m herramientas.motor_cev.motor_py.calcular --ficha RUTA.xlsm
    python -m herramientas.motor_cev.motor_py.calcular --ficha CARPETA          (todas las .xlsm)
    python -m herramientas.motor_cev.motor_py.calcular --ficha RUTA.xlsm --json salida.json

Desde codigo (lo usa la app, backend 'python'):
    from herramientas.motor_cev.motor_py.calcular import calcular
    c = calcular("ficha.xlsm")          # o una Ficha armada en memoria (ficha_virtual)
    c.resumen["letra"], c.resumen["demanda_total"], c.tiempos
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from herramientas.motor_cev import calculo_py as cp

from . import motor as mt
from . import planilla03 as p3
from .datos import FaltanDatos
from .entradas import Ficha, leer_ficha


@lru_cache(maxsize=1)
def datos():
    """(motor.Datos, DatosPlanilla03): se cargan una vez por proceso."""
    return mt.cargar(), p3.cargar_planilla03()


@dataclass
class Calificacion:
    ficha: Ficha
    resumen: dict                  # celdas del Resumen de la 03 (letra, demandas, ahorros, ...)
    corridas: list = field(repr=False)          # motor.Corrida por caso (bloques en .filas)
    planilla: object = field(default=None, repr=False)   # ResultadoPlanilla03
    tiempos: dict = field(default_factory=dict)
    sin_calcular: list = field(default_factory=list)

    def bloques(self) -> dict:
        """{caso: filas} (lo que se pega en 'Resultados' de la 03)."""
        return {c.caso: c.filas for c in self.corridas}


def calcular(ficha, casos=mt.CASOS, antes_de_caso=None) -> Calificacion:
    """ficha: ruta a un .xlsm o una Ficha. Con los 10 casos agrega la planilla 03.
    antes_de_caso(k, total, caso): se llama antes de cada caso (avance; puede lanzar una
    excepcion para cancelar)."""
    t0 = time.perf_counter()
    d, d03 = datos()
    t_datos = time.perf_counter() - t0
    t1 = time.perf_counter()
    f = ficha if isinstance(ficha, Ficha) else leer_ficha(ficha)
    t_ficha = time.perf_counter() - t1
    t2 = time.perf_counter()
    c = mt.comun(d, f)
    casos = list(casos)
    corridas = []
    for k, caso in enumerate(casos):
        if antes_de_caso is not None:
            antes_de_caso(k, len(casos), caso)
        rc = mt.calcular_caso(d, f, caso, c)
        filas, dpm, t = mt.simular(rc)
        corridas.append(mt.Corrida(caso, rc, filas, dpm, rc.tiempo, t))
    t_motor = time.perf_counter() - t2
    resumen, res03, t_03 = {}, None, 0.0
    if set(mt.CASOS) <= set(casos):
        t3 = time.perf_counter()
        res03 = p3.calcular(d03, p3.desde_corridas(f, corridas))
        resumen = dict(res03.resumen)
        t_03 = time.perf_counter() - t3
    sin = sorted({x for k in corridas for x in k.resultado.sin_calcular})
    tiempos = {"datos": t_datos, "ficha": t_ficha, "comun": c.tiempo,
               "modulos": sum(k.t_modulos for k in corridas), "calculo": sum(k.t_calculo for k in corridas),
               "motor": t_motor, "planilla03": t_03, "total": time.perf_counter() - t0}
    return Calificacion(f, resumen, corridas, res03, tiempos, sin)


def fichas_de(ruta: Path) -> list:
    ruta = Path(ruta)
    if ruta.is_dir():
        return sorted(x for x in ruta.rglob("*.xlsm") if not x.name.startswith(("~$", "_armando_")))
    return [ruta]


def _num(v, fmt="{:.4f}"):
    return fmt.format(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def linea(nombre: str, c: Calificacion) -> str:
    r = c.resumen
    return (f"{nombre:<28} letra {r.get('letra')!s:<3} ahorro {_num(r.get('ahorro_total'))}  "
            f"demanda base {_num(r.get('demanda_base_total'), '{:.2f}')} / propuesta "
            f"{_num(r.get('demanda_total'), '{:.2f}')} kWh/m2  ({c.tiempos['total']:.1f} s)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Calificacion CEV 100 % Python de una o varias fichas 01")
    p.add_argument("--ficha", type=Path, required=True, help="una ficha .xlsm o una carpeta")
    p.add_argument("--json", type=Path, default=None, help="guardar los resumenes en un JSON")
    a = p.parse_args(argv)
    fichas = fichas_de(a.ficha)
    if not fichas or not fichas[0].exists():
        print(f"ERROR: no hay fichas en {a.ficha}")
        return 1
    if not cp.HAY_NUMBA:
        print("AVISO: sin numba (pip install numba) el calculo es mucho mas lento.")
    try:
        datos()
    except FaltanDatos as ex:
        print(f"ERROR: {ex}")
        return 1
    salida, errores = {}, 0
    t0 = time.perf_counter()
    for ruta in fichas:
        try:
            c = calcular(ruta)
        except Exception as ex:          # noqa: BLE001 (se informa y se sigue con la siguiente)
            errores += 1
            print(f"{ruta.stem:<28} !! {type(ex).__name__}: {ex}")
            continue
        print(linea(ruta.stem, c))
        if len(fichas) == 1:
            for k, v in c.resumen.items():
                print(f"    {k:<24} {v!r}")
            print("    tiempos: " + ", ".join(f"{k} {v:.2f} s" for k, v in c.tiempos.items()))
        if c.sin_calcular:
            print(f"    !! celdas sin calcular: {len(c.sin_calcular)} (ej. {', '.join(c.sin_calcular[:4])})")
        salida[str(ruta)] = {"resumen": c.resumen, "tiempos": c.tiempos}
    if len(fichas) > 1:
        print(f"\n{len(fichas) - errores} de {len(fichas)} fichas en {time.perf_counter() - t0:.1f} s")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"JSON: {a.json}")
    return 0 if not errores else 1


if __name__ == "__main__":
    raise SystemExit(main())
