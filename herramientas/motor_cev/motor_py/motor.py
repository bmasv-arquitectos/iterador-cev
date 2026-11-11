# -*- coding: utf-8 -*-
r"""
Motor 100 % Python de la ficha 01: Ficha -> lo que lee calculo() -> bloques.

Encadena los modulos validados contra Excel:
  una vez (no dependen del caso): zona y clima horario (clima.py), geometria
    solar de la comuna (geometria_solar.py) y obstrucciones (obstrucciones_far.py);
  por caso: envolvente -> inercia -> radiacion_fav -> clima.bloques -> perfil_uso.
Y arma los cinco rangos que calculo() toma de la ficha (rangos.RANGOS):
  clima    '0. Datos Clima Motor'!E9:Y386
  arq      '0. Datos Arq Motor'!B2:O29
  masa     AH7:AJ18;  sa_libre X9:AF32;  sa_clima X36:AF59
Cada celda sale, en este orden, de: lo que un modulo calcula para esa celda; el
enlace =+'Hoja'!celda de la plantilla, resuelto con lo que calcularon los modulos
(I/J = '0.FAV Calculos'!IC/IQ, E25 = temporada, hora 24 = hora 0...); o la
constante de la plantilla (DatosMotor, motor_py/datos/motor.yaml). Las formulas que nada
resuelve quedan en ResultadoCaso.sin_calcular.

Con esos rangos, calculo_py da los bloques que van a la planilla 03, igual que el
motor hibrido (que lee los mismos rangos desde Excel).

    python -m herramientas.motor_cev.motor_py.motor --ficha RUTA.xlsm
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl.utils import get_column_letter, range_boundaries

from herramientas.motor_cev import calculo_py as cp

from . import clima
from . import envolvente as ev
from . import geometria_solar as gs
from . import inercia as it
from . import obstrucciones_far as of
from . import perfil_uso as pu
from . import radiacion_fav as rf
from .datos import (
    DIR, DatosMotor, FaltanDatos, cargar_clima, cargar_envolvente, cargar_far, cargar_fav,
    cargar_inercia, cargar_motor, cargar_solar, cargar_uso, ubicacion,
)
from .entradas import Ficha, leer_ficha
from .excel import copia
from .rangos import RANGOS

H_DCM = pu.H_DCM
H_ARQ = ev.H_ARQ
CASOS = tuple(range(1, 11))


@dataclass(frozen=True)
class Datos:
    clima: object
    uso: object
    envolvente: object
    inercia: object
    fav: object
    solar: object
    far: object
    motor: DatosMotor


def cargar(carpeta: Path = DIR) -> Datos:
    return Datos(cargar_clima(carpeta), cargar_uso(carpeta), cargar_envolvente(carpeta),
                 cargar_inercia(carpeta), cargar_fav(carpeta), cargar_solar(carpeta),
                 cargar_far(carpeta), cargar_motor(carpeta))


@dataclass(frozen=True)
class Comun:
    """Lo que no cambia entre los 10 casos."""
    zona: object           # '0. Clima'!M2
    horario: object        # clima.Horario
    solar: object          # geometria_solar.calcular
    far: object            # obstrucciones_far.ResultadoFar
    tiempo: float = 0.0


def comun(d: Datos, f: Ficha) -> Comun:
    t0 = time.perf_counter()
    zona = copia(clima.zona_clima(d.clima, f.comuna, copia(f.zona)))
    hor = clima.horario(d.clima, zona)
    rs = gs.calcular(d.solar, f.comuna)
    rfar = of.calcular(d.far, f.far, rs.altura, rs.azimut, hor, d.clima)
    return Comun(zona, hor, rs, rfar, time.perf_counter() - t0)


@dataclass
class ResultadoCaso:
    caso: int
    entradas: dict          # {clave de RANGOS: filas}: lo que lee calculo_py.caso_desde
    valores: dict           # {hoja: {celda: valor}} de esos rangos
    sin_calcular: list      # celdas con formula que nada calculo
    resultados: dict = field(default_factory=dict, repr=False)   # {modulo: resultado}
    tiempo: float = 0.0

    def celdas(self) -> dict:
        return self.valores


# --------------------------------------------------------------------------- celdas de clima
def clima_celdas(b: clima.Bloques, absortividad) -> dict:
    """Columnas de clima de '0. Datos Clima Motor' {celda: valor}."""
    c = {"C8": absortividad}
    for m in range(clima.MESES_ANIO):
        r0 = 10 + 32 * m
        c[f"E{r0}"] = b.meses[m]
        for k in range(clima.FILAS_BLOQUE):
            f = r0 + k
            c[f"F{f}"] = b.horas[m][k]
            c[f"G{f}"] = b.segundos[m][k]
            c[f"H{f}"] = b.t_exterior[m][k]
            c[f"N{f}"] = b.tsol_techo[m][k]
            for j, o in enumerate(clima.ORIENTACIONES):
                if o in b.tsol:
                    c[f"{get_column_letter(15 + j)}{f}"] = b.tsol[o][m][k]
            c[f"W{f}"] = b.modo[m][k]
            c[f"Y{f}"] = b.g_total[m][k]
        for dlt, v in ((3, b.tmax_dia[m]), (5, b.tmin_dia[m]), (7, b.tmax_noche[m]),
                       (9, b.tmin_noche[m]), (11, b.t_suelo[m])):
            c[f"E{r0 + dlt}"] = v
    return c


# --------------------------------------------------------------------------- armar los rangos
def _celdas(rango: str) -> list:
    c1, f1, c2, f2 = range_boundaries(rango)
    return [[f"{get_column_letter(c)}{f}" for c in range(c1, c2 + 1)] for f in range(f1, f2 + 1)]


def valor_en(fuentes, hoja, celda):
    """(True, valor) si algun resultado {hoja: {celda: valor}} tiene la celda."""
    for cs in fuentes:
        d = cs.get(hoja)
        if d is not None and celda in d:
            return True, d[celda]
    return False, None


def armar(dm: DatosMotor, directas: dict, fuentes: list, rangos: dict | None = None):
    """(entradas, valores, sin_calcular). directas: {hoja: {celda: valor}} que los modulos calculan
    para las hojas de los rangos; fuentes: resultados de los modulos para resolver los enlaces."""
    rangos = rangos or RANGOS
    hojas = {h for h, _ in rangos.values()}
    en_rango = {}
    for h, r in rangos.values():
        en_rango.setdefault(h, set()).update(c for fila in _celdas(r) for c in fila)

    def resolver(h, c, visto=frozenset()):
        d = directas.get(h, {})
        if c in d:
            return True, d[c]
        e = dm.enlaces.get(h, {}).get(c)
        if e is not None:
            if (h, c) in visto:
                return False, None
            h2, c2 = e
            ok, v = resolver(h2, c2, visto | {(h, c)}) if h2 in hojas else valor_en(fuentes, h2, c2)
            return ok, (copia(v) if ok else None)
        if c in dm.formulas.get(h, ()):
            return False, None
        if c in dm.constantes.get(h, {}):
            return True, dm.constantes[h][c]
        return (True, None) if c in en_rango.get(h, ()) else (False, None)

    valores, sin, entradas = {}, [], {}
    for clave, (h, r) in rangos.items():
        dv = valores.setdefault(h, {})
        filas = []
        for fila in _celdas(r):
            vals = []
            for c in fila:
                if c not in dv:
                    ok, v = resolver(h, c)
                    if not ok:
                        sin.append(f"{h}!{c}")
                    dv[c] = v
                vals.append(dv[c])
            filas.append(vals)
        entradas[clave] = filas
    return entradas, valores, sin


# --------------------------------------------------------------------------- un caso
def factor_fs(d: Datos, fuentes):
    """base_factor_FS: su celda si un modulo la calcula; si no, el valor de la plantilla."""
    info = d.fav.nombres.get("base_factor_FS") or {}
    u = ubicacion(info)
    if u:
        ok, v = valor_en(fuentes, *u)
        if ok and v is not None:
            return v
    return info.get("valor")


def calcular_caso(d: Datos, f: Ficha, caso: int, c: Comun | None = None) -> ResultadoCaso:
    t0 = time.perf_counter()
    c = c or comun(d, f)
    ee = f.envolvente(caso)
    renv = ev.calcular(d.envolvente, ee)
    ri = it.calcular(d.inercia, d.envolvente, ee, renv, c.zona)
    x = rf.EntradasFav(c.solar.altura, c.solar.azimut, dict(c.solar.factor), c.far.far_fav(),
                       factor_fs(d, [renv.celdas, ri.celdas]))
    rfav = rf.calcular(d.fav, d.envolvente, ee, renv, c.horario, d.clima, x)
    absort = renv.absortividad_techo
    b = clima.bloques(d.clima, c.horario, absort, clima.coincide(renv.valor(H_ARQ, "C32"), "Si"),
                      c.solar.factores())
    ru = pu.calcular(d.uso, d.clima, c.horario, f.uso(caso, renv, c.zona, ri.temporada, rfav.iluminancia))
    directas = {H_DCM: {**clima_celdas(b, absort), **ru.motor.celdas},
                H_ARQ: {**renv.celdas.get(H_ARQ, {}), **ri.celdas.get(H_ARQ, {})}}
    fuentes = [renv.celdas, ri.celdas, rfav.celdas, ru.celdas(), c.far.celdas, c.solar.celdas]
    entradas, valores, sin = armar(d.motor, directas, fuentes)
    res = {"envolvente": renv, "inercia": ri, "fav": rfav, "clima": b, "uso": ru}
    return ResultadoCaso(caso, entradas, valores, sin, res, time.perf_counter() - t0)


def simular(rc: ResultadoCaso):
    """(filas del bloque, dpm, segundos) con calculo_py: lo que el motor deja en la planilla 03."""
    t0 = time.perf_counter()
    M, dpm = cp.simular(cp.caso_desde(rc.entradas))
    return cp.bloque(M, dpm), dpm, time.perf_counter() - t0


@dataclass
class Corrida:
    caso: int
    resultado: ResultadoCaso
    filas: list = field(repr=False)
    dpm: int
    t_modulos: float
    t_calculo: float


def correr(d: Datos, f: Ficha, casos=CASOS) -> list:
    """Los casos pedidos de una ficha: modulos + calculo_py."""
    c = comun(d, f)
    out = []
    for caso in casos:
        rc = calcular_caso(d, f, caso, c)
        filas, dpm, t = simular(rc)
        out.append(Corrida(caso, rc, filas, dpm, rc.tiempo, t))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Motor 100 % Python de la ficha 01")
    p.add_argument("--ficha", type=Path, required=True)
    p.add_argument("--caso", type=int, action="append", help="(repetible; defecto: los 10)")
    a = p.parse_args(argv)
    if not a.ficha.exists():
        print(f"ERROR: no existe la ficha: {a.ficha}")
        return 1
    try:
        d = cargar()
    except FaltanDatos as ex:
        print(f"ERROR: {ex}")
        return 1
    if not cp.HAY_NUMBA:
        print("AVISO: sin numba (pip install numba) calculo() es mucho mas lento.")
    t0 = time.perf_counter()
    f = leer_ficha(a.ficha)
    print(f"Ficha leida en {time.perf_counter() - t0:.1f} s: {f.comuna}, zona {f.zona}")
    c = comun(d, f)
    print(f"Comun a los casos (zona de clima {c.zona}, sol, FAR): {c.tiempo:.2f} s")
    for caso in a.caso or CASOS:
        rc = calcular_caso(d, f, caso, c)
        filas, dpm, t = simular(rc)
        msg = f"caso {caso:>2}: modulos {rc.tiempo:.2f} s, calculo {t:.2f} s, dpm {dpm}"
        if rc.sin_calcular:
            msg += f", sin calcular {len(rc.sin_calcular)} (ej. {', '.join(rc.sin_calcular[:4])})"
        print(msg)
    print(f"Total: {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
