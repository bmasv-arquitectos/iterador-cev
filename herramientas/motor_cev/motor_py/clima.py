# -*- coding: utf-8 -*-
"""
Clima de la ficha 01 en Python: hoja '0. Clima' y las columnas de clima de
'0. Datos Clima Motor' (lo que el motor recibe por mes y hora).

Traduccion de las formulas de la plantilla v2.2, con el mismo orden de
operaciones que Excel para dar el mismo numero. Validado contra Excel:
54.600 celdas en los 10 casos, todas exactas (2026-11-02). Celdas de origen:

  zona_clima  '0. Clima'!M2 = SI('CEV-CEVE'!E9 = '0. Tablas referencia'!U24; "J"; E10)
  horario     '0. Clima'!N11:Q298  T, G total, G difusa (SUMAR.SI.CONJUNTO sobre la
              tabla horaria por zona, mes y hora) y G directa = total - difusa;
              S11:V22  T media mensual (PROMEDIO.SI.CONJUNTO) y banda de confort
              Tn = A + B*Tm -/+ Rango.
  bloques     '0. Datos Clima Motor': 12 bloques de 25 filas (horas 0 a 24) que
              empiezan en la fila 10 + 32*mes:
                H  T exterior (= '0. Clima'!N, por posicion)
                N  T sol-aire del techo = H + C8/C3*Y - 1/C3*63
                O..V  T sol-aire de muros N, NE, E, SE, S, SO, O, NO
                      = H + C7/C3*factor(mes, orientacion)*Y
                W  modo: con climatizacion 2 de noche (horas 0-6 y 22-23) y
                   1 de dia; sin climatizacion 0
                Y  G total (SUMAR.SI.CONJUNTO sobre '0. Clima'!O por mes y hora)
                E  Tmax dia = Tn max, Tmin dia = Tn min, Tmax noche = Tmax dia,
                   Tmin noche = MAX(Tmin dia - 2; 17), T suelo = PROMEDIO(H horas 0-23)
              La fila de la hora 24 repite la de la hora 0 (H34 = H10, Y386 = Y362).
              En enero la T sol-aire de la hora 24 es la T exterior (N34 = H34,
              O34 = N34 ... V34 = U34); en los demas meses repite la hora 0.

Lo que viene de otros modulos entra como argumento: absortividad del techo
(C8 = 'CEV-CEVE'!AR150, cambia con el caso), climatizacion del caso
('0. Datos Arq Motor'!C32) y el factor de radiacion por orientacion y mes
('0.FAV parámetros 1'!B207:I218, se traduce con la radiacion).
Quedan para otros modulos: I/J (radiacion por ventanas), K/L/M y X (perfil
de uso, perfil_uso.py), E23 (infiltracion) y E25 (temporada, inercia).
"""
from __future__ import annotations

from dataclasses import dataclass

from .datos import DatosClima
from .excel import (  # noqa: F401  (se re-exportan)
    buscar, clave, coincide, es_numero, indice, suma_secuencial, sumar_si,
)

ORIENTACIONES = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")   # columnas O..V
HORAS = 24
FILAS_BLOQUE = HORAS + 1                 # horas 0..24
NOCHE = frozenset(range(0, 7)) | frozenset((22, 23))   # W10:W16 y W32:W33
MESES_ANIO = 12


# --------------------------------------------------------------------------- '0. Clima'
def zona_clima(datos: DatosClima, comuna, zona) -> str:
    """'0. Clima'!M2: la comuna especial usa su propia zona de clima; si no, la de la ficha."""
    return datos.zona_especial if coincide(comuna, datos.comuna_especial) else zona


@dataclass(frozen=True)
class Horario:
    """'0. Clima'!L11:Q298 (288 filas: 12 meses x 24 horas) y S11:V22."""
    zona: str
    mes: tuple
    hora: tuple
    t: tuple            # N
    g_total: tuple      # O
    g_difusa: tuple     # P
    g_directa: tuple    # Q
    meses: tuple        # S
    t_media: tuple      # T
    tn_min: tuple       # U
    tn_max: tuple       # V


def horario(datos: DatosClima, zona) -> Horario:
    idx = indice(datos.crudo_zona, datos.crudo_mes, datos.crudo_hora)
    filas = list(zip(datos.filas_mes, datos.filas_hora))
    t = tuple(sumar_si(idx, datos.crudo_t, zona, m, h) for m, h in filas)
    gt = tuple(sumar_si(idx, datos.crudo_g_total, zona, m, h) for m, h in filas)
    gd = tuple(sumar_si(idx, datos.crudo_g_difusa, zona, m, h) for m, h in filas)
    gdir = tuple(a - b for a, b in zip(gt, gd))
    tm = []
    for mes in datos.meses:
        vals = [v for v, m in zip(t, datos.filas_mes) if coincide(m, mes)]
        if not vals:
            raise ZeroDivisionError(f"#DIV/0!: el horario no tiene filas de {mes!r}")
        tm.append(suma_secuencial(vals) / len(vals))
    a, b, r = datos.db_a, datos.db_b, datos.db_rango
    return Horario(
        zona=zona, mes=tuple(datos.filas_mes), hora=tuple(datos.filas_hora),
        t=t, g_total=gt, g_difusa=gd, g_directa=gdir, meses=tuple(datos.meses),
        t_media=tuple(tm),
        tn_min=tuple(a + b * x - r for x in tm),
        tn_max=tuple(a + b * x + r for x in tm))


# --------------------------------------------------------------------------- '0. Datos Clima Motor'
@dataclass(frozen=True)
class Bloques:
    """Columnas de clima de '0. Datos Clima Motor': listas [mes][hora 0..24]."""
    meses: tuple        # E de la primera fila de cada bloque
    horas: tuple        # F
    segundos: tuple     # G
    t_exterior: tuple   # H
    tsol_techo: tuple   # N
    tsol: dict          # orientacion -> [mes][hora] (O..V); vacio si no hay factores
    modo: tuple         # W
    g_total: tuple      # Y
    tmax_dia: tuple     # E fila +3
    tmin_dia: tuple     # E fila +5
    tmax_noche: tuple   # E fila +7
    tmin_noche: tuple   # E fila +9
    t_suelo: tuple      # E fila +11


def _factor(factores: dict, mes) -> list:
    """BUSCARV(mes; '0.FAV parámetros 1'!A207:I218; 2..9; 0)."""
    for k, v in factores.items():
        if coincide(k, mes):
            if len(v) != len(ORIENTACIONES):
                raise ValueError(f"el factor de {mes!r} tiene {len(v)} orientaciones")
            return list(v)
    raise KeyError(f"#N/A: sin factor por orientacion para {mes!r}")


def bloques(datos: DatosClima, hor: Horario, absortividad_techo: float, climatizado: bool,
            factores: dict | None = None) -> Bloques:
    if len(hor.t) != MESES_ANIO * HORAS:
        raise ValueError(f"el horario tiene {len(hor.t)} filas (se esperan {MESES_ANIO * HORAS})")
    c3, c7, cielo = datos.h_sol, datos.absortividad_muros, datos.radiacion_cielo
    c8 = float(absortividad_techo)
    idx = indice(hor.mes, hor.hora)
    H, N, W, Y = [], [], [], []
    T = {o: [] for o in ORIENTACIONES} if factores is not None else {}
    tmax_d, tmin_d, tmax_n, tmin_n, tsuelo = [], [], [], [], []
    for m in range(MESES_ANIO):
        mes = datos.motor_meses[m]
        horas = datos.motor_horas[m]
        h = [hor.t[HORAS * m + k] for k in range(HORAS)]
        y = [sumar_si(idx, hor.g_total, mes, horas[k]) for k in range(HORAS)]
        n = [h[k] + c8 / c3 * y[k] - 1 / c3 * cielo for k in range(HORAS)]
        w = [(2 if k in NOCHE else 1) if climatizado else 0 for k in range(HORAS)]
        h.append(h[0])
        y.append(y[0])
        w.append(w[0])
        n.append(h[HORAS] if m == 0 else n[0])
        H.append(tuple(h))
        N.append(tuple(n))
        W.append(tuple(w))
        Y.append(tuple(y))
        if factores is not None:
            f = _factor(factores, mes)
            for j, o in enumerate(ORIENTACIONES):
                s = [h[k] + c7 / c3 * f[j] * y[k] for k in range(HORAS)]
                s.append(n[HORAS] if m == 0 else s[0])
                T[o].append(tuple(s))
        i = buscar(hor.meses, mes)
        tmax_d.append(hor.tn_max[i])
        tmin_d.append(hor.tn_min[i])
        tmax_n.append(hor.tn_max[i])
        tmin_n.append(max(hor.tn_min[i] - 2, 17))
        tsuelo.append(suma_secuencial(h[:HORAS]) / HORAS)
    return Bloques(
        meses=tuple(datos.motor_meses), horas=tuple(datos.motor_horas),
        segundos=tuple(datos.motor_segundos), t_exterior=tuple(H), tsol_techo=tuple(N),
        tsol={o: tuple(v) for o, v in T.items()}, modo=tuple(W), g_total=tuple(Y),
        tmax_dia=tuple(tmax_d), tmin_dia=tuple(tmin_d), tmax_noche=tuple(tmax_n),
        tmin_noche=tuple(tmin_n), t_suelo=tuple(tsuelo))
