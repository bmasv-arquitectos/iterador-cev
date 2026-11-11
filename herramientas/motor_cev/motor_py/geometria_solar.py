# -*- coding: utf-8 -*-
"""
Geometria solar de la ficha 01 en Python: '0.FAV parámetros 1'.

Solo depende de la comuna ('CEV-CEVE'!E9): latitud y radiacion mensual de
'0. Tablas referencia'!U12:AJ357. Traduce, con el orden de operaciones de Excel:
  C4:C15     declinacion del dia medio de cada mes.
  B19:E30    angulo de puesta (ws) y salida del sol, duracion del dia.
  B34:I45    radiacion extraterrestre H0, radiacion del mes H, Kt = H/H0 y Hd/H.
  T35:AQ151  por mes (filas) y hora (columnas T..AQ): dia, declinacion, angulo
             horario, wew y las banderas C1, C2, C3 del azimut.
  T4:AQ15    altura solar.  T20:AQ31  azimut solar (los lee '0.FAV Calculos').
  B51:P66    coeficientes A, C y B (por mes) de cada orientacion (N, NE, E, SE,
             S, SO, O, NO en las columnas B, D, F, H, J, L, N, P).
  A71:D82    a, b, d y a' de cada mes.
  B87:K203   Klein-Theilacker por orientacion (bloques de 15 filas): D, G(wss,wsr),
             G(wss,-ws), G(ws,wsr), |wsr|, wsr, |wss|, wss.
  B207:I218  factor por orientacion (INDIRECT a la columna B de cada bloque segun
             K207:R218) + difusa y albedo. Lo leen el clima y '0.FAV Calculos'.
  B219, B222:I233  promedio y radiacion total (no los usa el motor).

Particularidades que se replican (no se corrigen):
  - B55:P66 (coeficiente B) usan COS(RADIANS(X19..X30)) de su propia columna:
    en N es ws, en NE es D19 (= ws - wr, la duracion del dia en grados) y en las
    demas orientaciones son celdas de la plantilla (vacias: COS(0) = 1).
  - El factor suma Hd/H (I34) completo, sin multiplicar la directa por (1 - Hd/H).
  - D128, D143, D158, D173, D188, D203 (diciembre de E, SE, S, SO, O y NO): en el
    termino SIN(...)*COS(...) el COS lee -1*B45, B60, B75, B90, B105, B120 en vez
    de -1*$B$30 (una referencia relativa arrastrada 15 filas por bloque). Cambia
    el factor de diciembre de esas orientaciones (COS_DICIEMBRE).
  - Las banderas y constantes son numeros (1, -1): se guardan como float.
"""
from __future__ import annotations

import math
import operator as op
from dataclasses import dataclass

from openpyxl.utils import get_column_letter

from .datos import DatosSolar
from .excel import (
    ar, buscarv, copia, es_error, max_args, mayor, mayor_igual, menor, menor_igual, min_args, numero,
    o_, promedio_rango, si, y_,
)

H_SOL = "0.FAV parámetros 1"
H_REF = "0. Tablas referencia"
MESES, HORAS = 12, 24
HC = tuple(get_column_letter(20 + h) for h in range(HORAS))      # T..AQ
OR_COLS = ("B", "D", "F", "H", "J", "L", "N", "P")              # N, NE, E, SE, S, SO, O, NO
FACTOR_COLS = tuple("BCDEFGHI")
AUX_COLS = tuple("KLMNOPQR")
FILA_BLOQUE, PASO_BLOQUE = 87, 15
FILA_FACTOR = 207
# error de la plantilla: celda que lee el COS del termino SIN*COS de D (diciembre), por bloque
COS_DICIEMBRE = {kb: f"B{30 + PASO_BLOQUE * (kb - 1)}" for kb in range(2, 8)}
R, D = math.radians, math.degrees


@dataclass(frozen=True)
class ResultadoSolar:
    celdas: dict           # {hoja: {celda: valor}}
    altura: tuple          # T4:AQ15 -> [mes][hora]
    azimut: tuple          # T20:AQ31 -> [mes][hora]
    factor: dict           # {"B207": v, ...} B207:I218
    meses: tuple           # A207:A218 (claves del factor para el clima)

    def valor(self, celda):
        return self.celdas.get(H_SOL, {}).get(celda)

    def factores(self) -> dict:
        """{mes: [factor N..NO]}: lo que clima.bloques recibe como factores por orientacion."""
        return {mes: [self.factor[f"{c}{FILA_FACTOR + i}"] for c in FACTOR_COLS]
                for i, mes in enumerate(self.meses)}


def _g(b, dd, ap, a, c, bm, j, h, hc=None):
    """G(j, h) de Klein-Theilacker (columnas C, D y E de cada bloque).

    hc: angulo del COS en el termino SIN(h)*COS(h); distinto de h solo por el error
    de la plantilla en diciembre (COS_DICIEMBRE)."""
    if hc is None:
        hc = h
    return ar(lambda b, dd, ap, a, c, bm, j, h, hc: 1 / (2 * dd) * (
        (b * a / 2 - ap * bm) * (j - h) * math.pi / 180
        + (ap * a - b * bm) * (math.sin(R(j)) - math.sin(R(h)))
        - ap * c * (math.cos(R(j)) - math.cos(R(h)))
        + (b * a / 2) * (math.sin(R(j)) * math.cos(R(j)) - math.sin(R(h)) * math.cos(R(hc)))
        + (b * c / 2) * (math.sin(R(j)) ** 2 - math.sin(R(h)) ** 2)), b, dd, ap, a, c, bm, j, h, hc)


def _angulo(signo):
    """DEGREES(ACOS((A*B +/- C*SQRT(A^2-B^2+C^2))/(A^2+C^2)))."""
    return lambda a, bm, c: D(math.acos((a * bm + signo * (c * math.sqrt(a ** 2 - bm ** 2 + c ** 2)))
                                        / (a ** 2 + c ** 2)))


def _decl(n):
    return ar(lambda x: 23.45 * math.sin(R(360 * (284 + x) / 365)), n)


def calcular(d: DatosSolar, comuna) -> ResultadoSolar:
    k = d.celdas
    out: dict = {}

    def put(c, v):
        out[c] = v
        return v

    def v(c):
        return out[c] if c in out else k.get(c)

    f3 = put("F3", copia(comuna))
    f5 = put("F5", buscarv(f3, d.comunas, 16))
    f6, f7, f8 = v("F6"), v("F7"), v("F8")

    # ------------------------------------------------ por mes: declinacion, ws, H0, Kt, Hd/H
    for m in range(MESES):
        n = v(f"B{4 + m}")
        dec = put(f"C{4 + m}", _decl(n))
        ws = put(f"B{19 + m}", ar(lambda la, de: D(math.acos(-math.tan(R(la)) * math.tan(R(de)))), f5, dec))
        wr = put(f"C{19 + m}", ar(lambda la, de: D(-math.acos(-math.tan(R(la)) * math.tan(R(de)))), f5, dec))
        dd = put(f"D{19 + m}", ar(op.sub, ws, wr))
        put(f"E{19 + m}", ar(lambda x: x / 15, dd))
        r = 34 + m
        h0 = put(f"B{r}", ar(lambda gsc, n_, de, la, w: 24 * 3600 * gsc / math.pi
                             * (1 + 0.033 * math.cos(R(360 * n_ / 365)))
                             * (math.cos(R(de)) * math.cos(R(la)) * math.sin(R(w))
                                + (2 * math.pi * w / 360) * math.sin(R(de)) * math.sin(R(la))),
                             f6, n, dec, f5, ws))
        hm = put(f"E{r}", ar(lambda x, j: x * 3.6 * 1000000 / j, buscarv(f3, d.comunas, 3 + m),
                             k.get(f"'{H_REF}'!J{11 + m}")))
        kt = put(f"H{r}", ar(op.truediv, hm, h0))
        p1 = ar(lambda x: 1.391 - 3.56 * x + 4.189 * x ** 2 - 2.137 * x ** 3, kt)
        p2 = ar(lambda x: 1.311 - 3.022 * x + 3.427 * x ** 2 - 1.821 * x ** 3, kt)
        put(f"I{r}", si(y_(menor_igual(ws, 81.4), mayor_igual(kt, 0.3), menor_igual(kt, 0.8)), p1, p2))

    # ------------------------------------------------ por mes y hora: altura y azimut
    altura, azimut = [], []
    for m in range(MESES):
        t35 = put(f"T{35 + m}", copia(v(f"B{4 + m}")))
        fa, fz = [], []
        for j, c in enumerate(HC):
            nd = t35 if j == 0 else put(f"{c}{35 + m}", ar(lambda t, x: t + x / 24, t35, v(f"{c}34")))
            de = put(f"{c}{50 + m}", _decl(nd))
            om = put(f"{c}{65 + m}", ar(lambda x: (x - 12) * 15, v(f"{c}64")))
            c80 = put(f"{c}{80 + m}", ar(lambda d_, la: D(math.acos(math.tan(R(d_)) / math.tan(R(la)))), de, f5))
            ratio = ar(lambda d_, la: math.tan(R(d_)) / math.tan(R(la)), de, f5)
            c95 = put(f"{c}{95 + m}", si(o_(mayor(ratio, 1), menor(ratio, -1)), 1.0,
                                         si(menor(ar(abs, om), c80), 1.0, -1.0)))
            c110 = put(f"{c}{110 + m}", si(mayor_igual(ar(lambda la, d_: la * (la - d_), f5, de), 0), 1.0, -1.0))
            c125 = put(f"{c}{125 + m}", si(mayor_igual(om, 0), 1.0, -1.0))
            alt = put(f"{c}{4 + m}", ar(lambda la, d_, w: 90 - D(math.acos(
                math.sin(R(la)) * math.sin(R(d_)) + math.cos(R(la)) * math.cos(R(d_)) * math.cos(R(w)))),
                f5, de, om))
            c140 = put(f"{c}{140 + m}", ar(lambda w, d_, a: D(math.asin(
                math.sin(R(w)) * math.cos(R(d_)) / math.sin(R(90 - a)))), om, de, alt))
            azi = put(f"{c}{20 + m}", ar(lambda a95, a110, a140, a125:
                                         (a95 * a110 * a140 + a125 * ((1 - a95 * a110) / 2) * 180) * -1,
                                         c95, c110, c140, c125))
            fa.append(alt)
            fz.append(azi)
        altura.append(tuple(fa))
        azimut.append(tuple(fz))

    # ------------------------------------------------ coeficientes por orientacion y por mes
    for x in OR_COLS:
        az = v(f"{x}50")
        put(f"{x}51", ar(lambda b, la, a: math.cos(R(b)) + math.tan(R(la)) * math.cos(R(a)) * math.sin(R(b)),
                         f7, f5, az))
        put(f"{x}52", ar(lambda b, a, la: math.sin(R(b)) * math.sin(R(a)) / math.cos(R(la)), f7, az, f5))
        for m in range(MESES):
            put(f"{x}{55 + m}", ar(lambda w, b, de, a: math.cos(R(w)) * math.cos(R(b))
                                   + math.tan(R(de)) * math.sin(R(b)) * math.cos(R(a)),
                                   v(f"{x}{19 + m}"), f7, v(f"C{4 + m}"), az))
    for m in range(MESES):
        ws = v(f"B{19 + m}")
        a_ = put(f"A{71 + m}", ar(lambda w: 0.409 + 0.5016 * math.sin(R(w - 60)), ws))
        put(f"B{71 + m}", ar(lambda w: 0.6609 - 0.4767 * math.sin(R(w - 60)), ws))
        put(f"C{71 + m}", ar(lambda w: math.sin(R(w)) - math.pi * w / 180 * math.cos(R(w)), ws))
        put(f"D{71 + m}", ar(op.sub, a_, v(f"I{34 + m}")))

    # ------------------------------------------------ Klein-Theilacker por orientacion (filas 87-203)
    for kb, x in enumerate(OR_COLS):
        a, c = v(f"{x}51"), v(f"{x}52")
        for m in range(MESES):
            r = FILA_BLOQUE + PASO_BLOQUE * kb + m
            bm, ws = v(f"{x}{55 + m}"), v(f"B{19 + m}")
            b, dd, ap = v(f"B{71 + m}"), v(f"C{71 + m}"), v(f"D{71 + m}")
            fv = put(f"F{r}", ar(lambda a_, b_, c_: a_ ** 2 - b_ ** 2 + c_ ** 2, a, bm, c))
            put(f"K{r}", fv)
            g = put(f"G{r}", si(mayor(fv, 0), min_args(ws, ar(_angulo(1), a, bm, c)), ws))
            cond = o_(y_(mayor(a, 0), mayor(bm, 0)), mayor_igual(a, bm))
            h = put(f"H{r}", si(cond, ar(lambda y: -1 * y, g), g))
            i_ = put(f"I{r}", si(mayor(fv, 0), min_args(ws, ar(_angulo(-1), a, bm, c)), ws))
            j = put(f"J{r}", si(cond, i_, ar(lambda y: -1 * y, i_)))
            menos_ws = ar(lambda y: -1 * y, ws)
            hc = menos_ws
            if m == MESES - 1 and kb in COS_DICIEMBRE:
                hc = ar(lambda y: -1 * y, v(COS_DICIEMBRE[kb]))
            cv = put(f"C{r}", _g(b, dd, ap, a, c, bm, j, h))
            dv = put(f"D{r}", _g(b, dd, ap, a, c, bm, j, menos_ws, hc))
            ev = put(f"E{r}", _g(b, dd, ap, a, c, bm, ws, h))
            put(f"B{r}", si(mayor_igual(j, h), max_args(0.0, cv), max_args(0.0, ar(op.add, dv, ev))))

    # ------------------------------------------------ factor por orientacion (B207:I218)
    factor = {}
    for m in range(MESES):
        r = FILA_FACTOR + m
        for c, aux in zip(FACTOR_COLS, AUX_COLS):
            fila = numero(v(f"{aux}{r}"))
            base = fila if es_error(fila) else copia(v(f"B{int(fila)}"))
            factor[f"{c}{r}"] = put(f"{c}{r}", ar(
                lambda x, i, b, al: x + i * ((1 + math.cos(R(b))) / 2) + al * ((1 - math.cos(R(b))) / 2),
                base, v(f"I{34 + m}"), f7, f8))
            put(f"{c}{222 + m}", ar(op.mul, v(f"E{34 + m}"), factor[f"{c}{r}"]))
    put("B219", promedio_rango([factor[f"B{FILA_FACTOR + m}"] for m in range(MESES)]))
    meses = tuple(k.get(f"A{FILA_FACTOR + m}") for m in range(MESES))
    return ResultadoSolar({H_SOL: out}, tuple(altura), tuple(azimut), factor, meses)
