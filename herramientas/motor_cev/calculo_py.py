# -*- coding: utf-8 -*-
r"""
Traduccion a Python de la macro calculo() del motor oficial PBTD v2.2.

Fuentes: el VBA de calculo() y las formulas de la hoja que lee en cada paso.

Lo que calculo() lee de la hoja Datos en cada paso (t = Datos!C2):
  G3 mes      = SI(t < 86400*(dpm+1); t // ((dpm+1)*86400) + 1; (t-86400) // (dpm*86400) + 1)
  H3:Y3       = fila 35 del bloque del mes: interpolacion LINEAL entre la hora
                h = (t mod 86400) // 3600 y h+1 de la tabla horaria (filas 10-34,
                tiempo en la columna G); W (modo de clima) sin interpolar. La fila
                del bloque sale de E11 del bloque (numero de mes).
  Z3:AE3      = E13, E15, E17, E19, E21, E23 del bloque (confort, Tsuelo, infiltracion)
  AF3 / SA!B26= E25 del bloque: temporada "v" o "i"
  C8          = (t mod 86400) mod 3600
  Mes 13 (ultimo paso): filas vacias -> todo 0 y temporada "".
SA!D4:N27 elige verano/invierno segun B26 y se lee ANTES de mover C2, o sea con
la temporada del paso anterior.

Se replica tambien lo raro del VBA, porque la meta es diferencia cero:
  - matriz(fila, 1) = t/60 en el dia base y t/3600 despues;
  - qsol y qint se toman de la fila anterior; n se usa antes de asignarse;
  - las Tsol del dia base quedan en 0.

Validado (2026-11-02): 10 casos de una unidad, diferencia exactamente 0
contra el motor oficial; luego tambien en una validacion amplia con mas unidades.

    python -m herramientas.motor_cev.calculo_py --entradas DIR --bloques DIR
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:                                   # numba es opcional: sin el es mucho mas lento
    from numba import njit
    HAY_NUMBA = True
except ImportError:                    # pragma: no cover
    HAY_NUMBA = False

    def njit(*a, **k):
        return a[0] if a and callable(a[0]) else (lambda f: f)

DT = 60
RO, CP = 1.2, 1000.0
HINT = 8.3
PMAX = 100000.0
T_SIN = 13751
RO_HOR, CP_HOR = 2400, 920
BLOQUE, FILAS_MES, HORAS = 32, 26, 25
# filas dentro del bloque de cada mes (fila de Datos - 9)
F_NUM_MES, F_CAT = 11 - 9, 25 - 9


# --------------------------------------------------------------------------- caso
@dataclass
class Caso:
    clima: np.ndarray       # (12, 26, 21): Datos!E9:Y34 de cada mes
    cat: tuple              # E25 de cada mes: "v" / "i"
    tabla_mes: np.ndarray   # E11 de cada mes (1..12): bloque cuya tabla horaria se usa
    arq: list               # Calculo!B2:O29 (28 x 14, numeros y textos)
    masa: np.ndarray        # SA!P34:R45 (12 x 3)
    sa_libre: np.ndarray    # SA!F36:N59 (24 x 9)
    sa_clima: np.ndarray    # SA!F64:N87 (24 x 9)

    def celda(self, ref: str):
        """Valor de Calculo!<ref> (dentro de B2:O29)."""
        return self.arq[int(ref[1:]) - 2][ord(ref[0]) - ord("B")]

    def num(self, ref: str) -> float:
        v = self.celda(ref)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

    def texto(self, ref: str) -> str:
        v = self.celda(ref)
        return "" if v is None else str(v)


def _f(x) -> float:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0.0


def _arr(m) -> np.ndarray:
    return np.array([[_f(x) for x in fila] for fila in m])


def caso_desde(d: dict) -> Caso:
    crudo = d["clima"]                              # filas 9..386 de Datos
    clima = _arr(crudo)
    meses = np.zeros((12, FILAS_MES, clima.shape[1]))
    cat, tabla = [], []
    for m in range(12):
        meses[m] = clima[BLOQUE * m: BLOQUE * m + FILAS_MES]
        c = crudo[BLOQUE * m + F_CAT][0]
        cat.append("" if c is None else str(c).strip())
        nm = meses[m, F_NUM_MES, 0]
        tabla.append(int(nm) if 1 <= nm <= 12 and float(nm).is_integer() else m + 1)
    return Caso(meses, tuple(cat), np.array(tabla), d["arq"], _arr(d["masa"]),
                _arr(d["sa_libre"]), _arr(d["sa_clima"]))


def cargar_caso(ruta: Path) -> Caso:
    return caso_desde(json.loads(Path(ruta).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- hoja Datos
def mes_de(t, dpm: int) -> np.ndarray:
    """Datos!G3."""
    t = np.asarray(t, dtype=np.int64)
    primero = t < 86400 * (dpm + 1)
    return np.where(primero, t // ((dpm + 1) * 86400) + 1, (t - 86400) // (dpm * 86400) + 1)


def mensual(caso: Caso, mes, fila: int) -> np.ndarray:
    """INDIRECTO("E" & fila + 32*(mes-1)): constante del mes (0 en el mes 13)."""
    tabla = np.append(caso.clima[:, fila - 9, 0], 0.0)
    return tabla[np.clip(np.asarray(mes, dtype=np.int64), 1, 13) - 1]


def valores_hora(caso: Caso, t, mes) -> dict:
    """Datos!H3:Y3 (fila 35 del bloque) y temporada (E25) para cada t."""
    t = np.asarray(t, dtype=np.int64)
    mes = np.asarray(mes, dtype=np.int64)
    tday = t % 86400
    h = tday // 3600
    ok = (mes >= 1) & (mes <= 12)
    bloque = np.clip(mes, 1, 12) - 1
    tm = caso.tabla_mes[bloque] - 1
    a = caso.clima[tm, 1 + h]                       # filas 10 + h
    b = caso.clima[tm, 2 + h]
    ga, gb = a[:, 2], b[:, 2]                       # columna G: tiempo [s]
    with np.errstate(divide="ignore", invalid="ignore"):
        v = a + ((b - a) / (gb - ga)[:, None]) * (tday - ga)[:, None]
    v[:, 18] = a[:, 18]                             # W: modo de clima, sin interpolar
    v[~ok] = 0.0
    cat = np.array(list(caso.cat) + [""])[np.where(ok, bloque, 12)]
    c = np.ascontiguousarray
    return {"text": c(v[:, 3]), "rad": c(v[:, 4] + v[:, 5]), "pers": c(v[:, 6]),
            "ilum": c(v[:, 7]), "equip": c(v[:, 8]), "tsol": c(v[:, 9:18]),
            "clima": c(v[:, 18]), "n": c(v[:, 19]),
            "verano": cat == "v", "invierno": cat == "i"}


# --------------------------------------------------------------------------- nucleo
@njit(cache=True)
def _nucleo(n_filas, ib, dt, mes, text, rad, pers, ilum, equip, tsol, clima, nvent,
            tmax1, tmin1, tmax2, tmin2, tsuelo, infilt, verano, invierno, c8,
            sa, ini18, ini31, aplanta, vaire, ut_v, at_v, ut, at,
            a_v, a, fil, u_v, u, apv, upv, filpt, part, area_hor, cap_hor,
            recup, ef_recup):
    M = np.zeros((n_filas + 1, 56))
    paso = int(3600 / dt)
    vrc = vaire * RO * CP
    for f in range(1, ib + 1):
        j = f - 1
        M[f, 1] = j * dt / 60
        M[f, 2] = j * dt
        M[f, 3] = mes[j]
        M[f, 4] = text[j]
        M[f, 18] = ini18[j]
        M[f, 31] = ini31[j]
    n = 0.0
    qv = np.zeros(8)
    qs = np.zeros(8)
    for f in range(ib + 1, n_filas + 1):
        j = f - 1
        s = 1 if verano[j - 1] else 0               # SA con el tiempo de la fila anterior
        M[f, 2] = M[f - 1, 2] + dt
        M[f, 1] = M[f, 2] / 3600
        M[f, 3] = mes[j]
        M[f, 4] = text[j]
        M[f, 5] = rad[j]
        qsol = M[f - 1, 5]
        M[f, 6] = pers[j] * aplanta
        M[f, 7] = ilum[j] * aplanta
        M[f, 8] = equip[j] * aplanta
        qint = M[f - 1, 6] + M[f - 1, 7] + M[f - 1, 8]
        for k in range(9):
            M[f, 9 + k] = tsol[j, k]
        q_techo = 0.0
        for k in range(8):
            qs[k] = 0.0
        q_pv = 0.0
        q_pt = 0.0
        for i in range(1, 25):
            idx = (f - 1) - paso * (i - 1)
            ti = M[idx, 18]
            q_techo = q_techo + ut * at * (M[idx, 9] - ti) * sa[s, i - 1, 0] / 100
            for k in range(8):
                qs[k] = qs[k] + (u[k] * a[k] + fil[k]) * (M[idx, 10 + k] - ti) * sa[s, i - 1, 1 + k] / 100
            q_pv = q_pv + upv * apv * (M[idx, 4] - ti) * sa[s, i - 1, 9] / 100
            q_pt = q_pt + filpt * (tsuelo[j] - ti) * sa[s, i - 1, 10] / 100
        dtv = M[f - 1, 4] - M[f - 1, 18]
        q_techo_v = ut_v * at_v * dtv
        M[f, 36] = q_techo_v
        M[f, 37] = q_techo
        for k in range(8):
            qv[k] = u_v[k] * a_v[k] * dtv
            M[f, 38 + 2 * k] = qv[k]
            M[f, 39 + 2 * k] = qs[k]
        M[f, 54] = q_pv
        M[f, 55] = q_pt
        q_hor = HINT * area_hor * (M[f - 1, 18] + (qsol * 0.85) / (HINT * area_hor) - M[f - 1, 31])
        M[f, 31] = M[f - 1, 31] + (q_hor * dt / cap_hor)
        qmasa = HINT * area_hor * (M[f - 1, 31] - M[f - 1, 18])
        qventanas = qv[0] + qv[1] + qv[2] + qv[3] + qv[4] + qv[5] + qv[6] + qv[7] + q_techo_v
        qtecho = q_techo + qmasa * part[0]
        qmuros = qs[0] + qs[1] + qs[2] + qs[3] + qs[4] + qs[5] + qs[6] + qs[7] + qmasa * part[1]
        qpv = q_pv + qmasa * part[2]
        qpt = q_pt + qmasa * part[3]
        qenv = qventanas + qtecho + qmuros + (qpv + qpt)
        qmasa_ad = qmasa * part[4]
        M[f, 32] = qmasa_ad
        M[f, 19] = qenv
        M[f, 21] = qventanas
        M[f, 22] = qtecho
        M[f, 23] = qmuros
        M[f, 20] = qpv
        M[f, 24] = qpt
        qinfilt = vaire * (infilt[j] / 3600 * dt) * RO * CP * dtv / dt
        M[f, 27] = qinfilt
        qpot = ((vaire * (n / 3600 * dt) * RO * CP * dtv) / dt)
        qrecup = 0.0
        if recup and invierno[j]:
            qrecup = -0.5 * ef_recup * qpot
        n = nvent[j]
        M[f, 25] = qpot
        M[f, 26] = qrecup
        tprev = M[f - 1, 18]
        S = qsol * 0.15 + qint + qenv + qpot + qmasa_ad + qrecup + qinfilt
        qclima = 0.0
        for modo in (1, 2):
            if clima[j] != modo:
                continue
            tmax = tmax1[j] if modo == 1 else tmax2[j]
            tmin = tmin1[j] if modo == 1 else tmin2[j]
            if tprev >= tmax:
                if S > 0:
                    qclima = -S + vrc * (tmax - tprev) / dt
                elif S < 0:
                    qclima = S + vrc * (tmax - tprev) / dt
                if qclima < -PMAX:
                    qclima = -PMAX
            if tprev <= tmin:
                if S < 0:
                    qclima = -S + vrc * (tmin - tprev) / dt
                elif S > 0:
                    qclima = S + vrc * (tmin - tprev) / dt
                if qclima > PMAX:
                    qclima = PMAX
        M[f, 28] = qclima
        q = (qsol * 0.15 + qint + qenv + qpot + qmasa_ad + qclima + qrecup + qinfilt) * dt
        M[f, 18] = tprev + q / vrc
        M[f, 35] = q / dt
        if c8[j] == dt:
            M[f, 33] = 0.0
            M[f, 34] = 0.0
        elif qclima >= 0:
            M[f, 33] = M[f - 1, 33] + qclima * dt / 3600
            M[f, 34] = M[f - 1, 34] + 0
        else:
            M[f, 33] = M[f - 1, 33] + 0
            M[f, 34] = M[f - 1, 34] + qclima * dt / 3600
    return M


# --------------------------------------------------------------------------- caso -> matriz
def _sa(caso: Caso, hay_clima: bool) -> np.ndarray:
    """SA!D4:N27 por temporada [0 invierno, 1 verano] x hora x (H, N..NO, PV, PT)."""
    src = caso.sa_clima if hay_clima else caso.sa_libre      # columnas F..N = 0..8
    out = np.zeros((2, 24, 11))
    for s, (h, m, pv, pt) in enumerate(((3, 1, 5, 7), (2, 0, 4, 6))):
        out[s, :, 0] = src[:, h]
        out[s, :, 1:9] = src[:, [m]]
        out[s, :, 9] = src[:, pv]
        out[s, :, 10] = src[:, pt]
    return out


def simular(caso: Caso):
    """(matriz, dpm) del caso, igual a la matriz VBA (filas y columnas desde 1)."""
    m = caso.masa                                    # SA!P34:R45: filas 34..45, cols P,Q,R
    esp_hor = m[0, 1] if caso.cat[0] == "v" else m[0, 2]   # S34 con t = 0 (mes 1)
    dpm = 5 if esp_hor >= 7 else 3                   # SA!Q47
    ib = 86400 // DT
    n_filas = dpm * 86400 * 12 // DT + ib + 1
    t = np.arange(n_filas, dtype=np.int64) * DT
    mes = mes_de(t, dpm)
    h = valores_hora(caso, t, mes)

    hay = caso.texto("C6")
    aplanta, vaire = caso.num("G26"), caso.num("I26")
    if hay == "Si":
        ini = np.full(ib, (caso.clima[0, 17 - 9, 0] + caso.clima[0, 19 - 9, 0]) / 2)
        ini31 = ini.copy()
    elif hay == "No":
        b1 = caso.clima[0]                           # Datos!H37:H39 del mes 1
        aext = b1[1:25, 3].max() - b1[1:25, 3].min()
        tm = b1[1:25, 3].mean() + b1[1:26, 4].max() / aplanta / m[4, 1]
        amp = aext * m[4, 0] / 2                     # P38 amortiguacion, Q38 CTm, R38 desfase
        ini = np.array([tm + amp * math.sin(j * DT / T_SIN + m[4, 2]) for j in range(ib)])
        ini31 = np.full(ib, tm)
    else:
        ini = np.zeros(ib)
        ini31 = np.zeros(ib)

    filas = range(9, 17)                             # Calculo!H9:N16: N..NO
    vec = lambda col: np.array([caso.num(f"{col}{r}") for r in filas])  # noqa: E731
    M = _nucleo(
        n_filas, ib, DT, mes.astype(np.float64), h["text"], h["rad"], h["pers"], h["ilum"],
        h["equip"], h["tsol"], h["clima"], h["n"],
        mensual(caso, mes, 13), mensual(caso, mes, 15), mensual(caso, mes, 17),
        mensual(caso, mes, 19), mensual(caso, mes, 21), mensual(caso, mes, 23),
        h["verano"], h["invierno"], (t % 86400) % 3600, _sa(caso, hay == "Si"), ini, ini31,
        aplanta, vaire, caso.num("L8"), caso.num("K8"), caso.num("I8"), caso.num("H8"),
        vec("K"), vec("H"), vec("N"), vec("L"), vec("I"),
        caso.num("H17"), caso.num("I17"), caso.num("N17"),
        np.ascontiguousarray(m[7:12, 1]),            # Q41:Q45 participacion de masa
        m[1, 1], RO_HOR * m[1, 1] * esp_hor / 100 * CP_HOR,   # Q35 area, capacidad
        caso.texto("C4") == "Si", caso.num("C5"))
    return M, dpm


def bloque(M: np.ndarray, dpm: int) -> list:
    """Las 312 filas que calculo() deja en Hoja4 (12 x [25 horas + 1 vacia])."""
    inicio = 86400 * dpm // DT + 1
    filas = []
    for mes in range(12):
        for k in range(HORAS):
            filas.append(M[inicio + mes * 86400 * dpm // DT + k * 3600 // DT, 1:56].tolist())
        filas.append(None)
    return filas


def _vacia(fila) -> bool:
    return fila is None or all(x in (None, "") for x in fila)


def comparar(filas: list, ref, tol: float = 1e-9) -> dict:
    """
    Diferencia contra un bloque del motor oficial (ruta a <unidad>_casoNN.json o la
    lista de valores). 'comparadas' cuenta las celdas efectivamente comparadas: si
    es 0, la comparacion no dice nada. 'desalineadas' cuenta filas vacias de un lado
    y con datos del otro (bloques corridos).
    """
    if not isinstance(ref, list):
        ref = json.loads(Path(ref).read_text(encoding="utf-8"))["valores"]
    peor, distintas, comparadas, desalineadas, donde = 0.0, 0, 0, 0, None
    for i, (a, b) in enumerate(zip(filas, ref)):
        va, vb = _vacia(a), _vacia(b)
        if va or vb:
            desalineadas += va != vb
            continue
        for c, (x, y) in enumerate(zip(a, b)):
            y = _f(y)
            d = abs(x - y) / max(1.0, abs(y))
            comparadas += 1
            if d > peor:
                peor, donde = d, (i, c + 1)
            distintas += d > tol
    desalineadas += abs(len(filas) - len(ref))
    return {"filas": len(ref), "filas_py": len(filas), "comparadas": comparadas,
            "desalineadas": desalineadas, "peor_rel": peor,
            "celdas_distintas": distintas, "peor_en": donde}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="calculo() en Python contra los bloques del motor")
    p.add_argument("--entradas", type=Path, required=True, help="carpeta con casoNN.json")
    p.add_argument("--bloques", type=Path, help="carpeta bloques/ del motor oficial")
    p.add_argument("--unidad", default="iterador")
    a = p.parse_args(argv)
    if not HAY_NUMBA:
        print("AVISO: sin numba (pip install numba) cada caso tarda bastante mas.")
    for ruta in sorted(a.entradas.glob("caso*.json")):
        caso_n = int(ruta.stem[4:])
        t0 = time.perf_counter()
        M, dpm = simular(cargar_caso(ruta))
        filas = bloque(M, dpm)
        msg = f"caso {caso_n:>2}: {time.perf_counter() - t0:6.2f} s  dpm {dpm}"
        ref = a.bloques / f"{a.unidad}_caso{caso_n:02d}.json" if a.bloques else None
        if ref and ref.exists():
            r = comparar(filas, ref)
            msg += (f"  peor dif. {r['peor_rel']:.2e} en (fila, col) {r['peor_en']}"
                    f"  celdas > 1e-9: {r['celdas_distintas']}  comparadas: {r['comparadas']}")
            if r["desalineadas"]:
                msg += f"  !! filas desalineadas: {r['desalineadas']}"
            if not r["comparadas"]:
                msg += "  !! no se comparo nada"
        elif ref:
            msg += f"  (no existe {ref.name})"
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
