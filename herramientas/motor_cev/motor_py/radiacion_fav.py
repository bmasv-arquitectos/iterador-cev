# -*- coding: utf-8 -*-
"""
Radiacion por puertas y ventanas de la ficha 01 en Python: '0.FAV Calculos'.

La hoja son 23 bloques de 27 filas (bloque k desde la fila 14 + 27*(k-1)): 3 puertas
y 20 ventanas. En cada bloque, por mes (columnas) y hora (24 filas):
  C..N, R..AC   altura y azimut solar (TRANSPOSE de '0.FAV parametros 1').
  AF..AQ, AT..BE  radiacion directa y difusa horizontal ('0. Clima'!Q y P).
  DM, EA, EO, FC  si el sol esta tapado (0) o no (1) por FAV 1 (alero), FAV 2 y 3
                (aleros laterales), FAV 4 (lamas horizontales) y FAV 5 (verticales).
  FQ            obstrucciones remotas ('0. FAR', por orientacion).
  CY            producto (k total); 1 si es horizontal y hay sol.
  BW, CK        radiacion difusa y directa por el area traslucida.
  GE            radiacion maxima (sin protecciones).
  BG16:BR30     parametros del vano (CEV-CEVE: alto, ancho, FAV, FS, area) y
                BH30 = FSM = (difusa + directa) / (maxima * area).
Al final (filas 11-37, columnas HA:JX): factor por orientacion (INDIRECT a
'0.FAV parametros 1'!B207:I218), areas, FLD, radiacion por hora (IC, IQ), la
iluminancia natural JE14:JP37 (la usa el perfil de uso) y el FSM de cada vano
(JT, = 'CEV-CEVE'!AM). Tambien 'CEV-CEVE'!CF (FLD), que lee JW.

Entradas: la envolvente (envolvente.py), el clima horario (clima.horario) y
EntradasFav: altura y azimut solar y factor por orientacion de '0.FAV
parametros 1', las celdas de '0. FAR' que se leen y base_factor_FS. Constantes
de la hoja: DatosFav (motor_py/datos/fav.yaml); incluye las constantes de '0. FAR'!
L148:N155 (clave "'0. FAR'!L148"), que se usan si EntradasFav.far no las trae.

Particularidades que se replican (no se corrigen):
  - Bloque 1 (puerta 1): BH25 sin SI.ERROR (#N/A si la orientacion no esta en
    '0. FAR'!L148:N155, y el FSM de la puerta 1 queda en 0 por el SI.ERROR de BH30).
  - Bloque 4 (ventana 1): BM19 es un angulo y el % visible de FAV 1 esta en BM20;
    BR19 y BM28 tienen resguardo (1 si las medidas son 0).
  - Puertas (bloques 1-3): FS del vidrio de la tabla incluso en el caso base;
    ventanas: base_FS_vidrio * base_factor_FS en el caso base.
  - AT de los bloques 3-23 copia el bloque anterior.
  - HO (area por orientacion) usa la orientacion F del proyecto, no CI (la del caso).
  - Las medidas de los FAV llevan + 1/1000000 (evita dividir por 0).
"""
from __future__ import annotations

import math
import operator as op
from dataclasses import dataclass
from functools import reduce

from openpyxl.utils import column_index_from_string, get_column_letter

from . import envolvente as ev
from .datos import DatosEnvolvente, DatosFav
from .excel import (
    NA, Tabla, ar, buscarv, coincide, concatenar, copia, distinto, es_error, es_numero, iferror,
    igual, indice, mas, mayor, mayor_igual, menor, menor_igual, min_rango, o_, si, suma_rango,
    sumar_si, sumar_si_lista, y_,
)

H_FAV = "0.FAV Calculos"
H_FAR = "0. FAR"
INICIO, ALTO, BLOQUES = 14, 27, 23
HORAS, MESES = 24, 12
VANOS = ev.FILAS_PUERTA + ev.FILAS_VENTANA          # fila de CEV-CEVE de cada bloque
BLOQUE_VENTANA_1 = 3
FAR = (("N", "HG"), ("E", "HT"), ("s", "IG"), ("O", "IT"), ("NE", "JG"), ("SE", "JT"),
       ("SO", "KG"), ("NO", "KT"))                   # FQ: columna de '0. FAR' (fila 65 = hora 0)
ORDEN_IC = (22, 14, 15, 16, 17, 18, 19, 20, 21)     # IC/IQ suman Horiz y luego N..NO
FILAS_OR = tuple(range(14, 23))
MICRO = 1 / 1000000


def _col(letra: str, j: int = 0) -> str:
    return get_column_letter(column_index_from_string(letra) + j)


COLS = {k: tuple(_col(k, j) for j in range(MESES))
        for k in ("C", "R", "AF", "AT", "BW", "CK", "CY", "DM", "EA", "EO", "FC", "FQ", "GE", "HB",
                  "IC", "IQ", "JE")}


@dataclass(frozen=True)
class EntradasFav:
    altura: tuple          # '0.FAV parametros 1'!T4:AQ15 -> [mes][hora]
    azimut: tuple          # '0.FAV parametros 1'!T20:AQ31 -> [mes][hora]
    factor: dict           # '0.FAV parametros 1'!B207:I218 {celda: valor}
    far: dict              # '0. FAR' {celda: valor}: HG65:KT88 (FQ) y L148:N155 (BH25)
    factor_fs: object      # base_factor_FS


@dataclass(frozen=True)
class ResultadoFav:
    celdas: dict           # {hoja: {celda: valor}}
    iluminancia: tuple     # JE14:JP37 -> [mes][hora] (entrada del perfil de uso)
    fsm: tuple             # JT14:JT36 = 'CEV-CEVE'!AM de puertas y ventanas

    def valor(self, hoja, celda):
        return self.celdas.get(hoja, {}).get(celda)


# --------------------------------------------------------------------------- formulas
def _prod(*v):
    return ar(lambda *x: reduce(op.mul, x), *v)


def _t(cond):
    """IF(cond;0;1)."""
    return si(cond, 0.0, 1.0)


def _ang(num, a, delta):
    """DEGREES(ATAN(num/SQRT(a^2+(a*TAN(RADIANS(delta)))^2)))."""
    return ar(lambda n, a_, d: math.degrees(math.atan(
        n / math.sqrt(a_ ** 2 + (a_ * math.tan(math.radians(d))) ** 2))), num, a, delta)


def _gamma(o, bh20, x, inicio: bool):
    """IF(BH17="s";-180+x;BH20+x) (inicio) o IF(BH17="s";180-x;BH20-x)."""
    if inicio:
        return si(igual(o, "s"), ar(lambda v: -180 + v, x), ar(op.add, bh20, x))
    return si(igual(o, "s"), ar(lambda v: 180 - v, x), ar(op.sub, bh20, x))


def _ratio(a, b, h):
    """1-(a*b)/(h*b*2+b*a+h*a): % visible de la radiacion difusa."""
    return ar(lambda a_, b_, h_: 1 - (a_ * b_) / (h_ * b_ * 2 + b_ * a_ + h_ * a_), a, b, h)


def _signo(v):
    return (v > 0) - (v < 0)


def _br(o, bh19, p25, p26, p27, signo):
    """BR25 (signo 1) y BR26 (signo -1): limites de FAV 5."""
    x = ar(lambda e_, a, t: math.degrees(math.atan(
        (e_ * math.sin(math.radians(a)) + signo * t / 2) / (e_ * math.cos(math.radians(a))))), p26, p27, p25)
    return si(igual(o, "s"), ar(lambda v: (-_signo(v)) * 180 + v, x), ar(lambda b, v: b - (90 - v), bh19, x))


def _bm28(k22, k23, k24, k25, k28, k29, k30):
    return ar(lambda a22, a23, a24, a25, a28, a29, a30: 1 - (a24 * a23 + a29 * a28) / (
        a24 * a23 + a29 * a28 + (a24 + a29) / 2 * (a25 + a22 + a30)
        + a23 * math.sqrt((a24 - a29) ** 2 + (a25 + a22 + a30) ** 2)), k22, k23, k24, k25, k28, k29, k30)


def _vis(C, R, o, bh18, bh19):
    """Primer factor de DM, EA, EO y FC: 0 si el sol esta detras del plano del vano."""
    return _t(o_(menor_igual(C, 0),
                 y_(mayor(R, 0), igual(o, "n"), mayor(R, bh19)),
                 y_(mayor(R, 0), igual(o, "s"), menor(R, bh18)),
                 y_(menor(R, 0), igual(o, "s"), mayor(R, bh19)),
                 y_(menor(R, 0), igual(o, "n"), menor(R, bh18)),
                 y_(menor(R, 0), igual(o, "e")),
                 y_(mayor(R, 0), igual(o, "o")),
                 y_(igual(R, 0), distinto(o, "n"))))


def _sol(o, C, R, bh18, bh19):
    """GE: 1 si el sol da en el plano del vano."""
    return si(igual(o, "S"),
              si(o_(y_(mayor(C, 0), mayor(R, bh18)), y_(mayor(C, 0), menor(R, bh19))), 1.0, 0.0),
              si(y_(mayor(bh19, R), menor(bh18, R), mayor(C, 0)), 1.0, 0.0))


def _filas_cev(de: DatosEnvolvente, e: ev.EntradasEnvolvente, renv) -> dict:
    """'CEV-CEVE' filas 96-98 y 103-122: lo que buscan los BUSCARV de la hoja."""
    filas = {}
    for xs, fs in ((e.puertas, ev.FILAS_PUERTA), (e.ventanas, ev.FILAS_VENTANA)):
        for x, f in zip(xs, fs):
            d = {"C": de.cev.get(f"C{f}"), "D": x.tipo, "K": x.alto, "L": x.ancho}
            for c in ("F", "AF", "CH", "CI") + ev.FAV_COPIA:
                d[c] = renv.valor(ev.H_CEV, f"{c}{f}")
            filas[f] = d
    return filas


def _buscar(filas, clave, col, llave="C", desde=96):
    """BUSCARV(clave; 'CEV-CEVE'!llave{desde}:...; col; 0)."""
    if es_error(clave):
        return clave
    for f in sorted(filas):
        if f < desde:
            continue
        k = filas[f].get(llave)
        if k is not None and not es_error(k) and coincide(k, clave):
            return copia(filas[f].get(col))
    return NA


def tabla_far(d: DatosFav, far: dict) -> Tabla:
    """'0. FAR'!L148:N155: de EntradasFav.far si viene; si no, la constante de la plantilla."""
    def celda(c):
        v = far.get(c)
        return d.celdas.get(f"'{H_FAR}'!{c}") if v is None else v

    return Tabla(tuple(tuple(celda(f"{c}{r}") for c in "LMN") for r in range(148, 156)))


# --------------------------------------------------------------------------- todo
def calcular(d: DatosFav, de: DatosEnvolvente, e: ev.EntradasEnvolvente, renv, hor, dc,
             x: EntradasFav) -> ResultadoFav:
    """hor: clima.horario de la zona; dc: DatosClima (meses y horas del horario)."""
    k_ = d.celdas
    out, cev_out = {}, {}
    base = e.caso > 2
    te = ev.tablas(e, ev.Libro(de))
    filas = _filas_cev(de, e, renv)
    b_fs = renv.nombre("base_FS_vidrio")

    def put(c, v):
        out[c] = v
        return v

    # ------------------------------------------------ cabecera: meses del factor y tabla por orientacion
    ge = [copia(k_.get("GE11"))]
    for j in range(1, MESES):
        ge.append(put(f"{COLS['GE'][j]}11", ar(lambda v: v + 1, ge[-1])))
    hb = [copia(k_.get("HB12"))]
    for j in range(1, MESES):
        hb.append(put(f"{COLS['HB'][j]}12", ar(lambda v: v + 1, hb[-1])))
    filas_fac = []
    for r in range(14, 22):
        fila = [k_.get(f"HA{r}")]
        for j in range(MESES):
            dir_ = concatenar(k_.get(f"GZ{r}"), hb[j])
            v = dir_ if es_error(dir_) else copia(x.factor.get(str(dir_).upper()))
            fila.append(put(f"{COLS['HB'][j]}{r}", v))
        filas_fac.append(tuple(fila))
    filas_fac.append((k_.get("HA22"),) + tuple(k_.get(f"{COLS['HB'][j]}22") for j in range(MESES)))
    t_fac = Tabla(tuple(filas_fac))
    t_gz = Tabla(tuple(tuple(k_.get(f"{c}{r}") for c in ("GZ", "HA", "HB", "HC", "HD"))
                       for r in range(25, 34)))
    t_far = tabla_far(d, x.far)
    idx = indice(dc.filas_mes, dc.filas_hora)
    gdir, gdif = hor.g_directa, hor.g_difusa

    # ------------------------------------------------ bloques
    bloques = []
    bg14 = None
    at_prev = None
    for b in range(BLOQUES):
        r0 = INICIO + ALTO * b

        def P(col, fila, b=b):
            return f"{col}{fila + ALTO * b}"

        def pp(col, fila, v):
            out[P(col, fila)] = v
            return v

        if b in (0, BLOQUE_VENTANA_1):
            bg14 = copia(k_.get(P("BG", 14)))
        else:
            bg14 = pp("BG", 14, ar(lambda v: v + 1, bg14))
        bg16 = copia(k_.get(P("BG", 16))) if b < 3 else pp("BG", 16, concatenar("Ventana ", bg14))

        def vc(col, llave="C", desde=96):
            return _buscar(filas, bg16, col, llave, desde)

        v_ci = vc("CI", "CH")
        bh22 = pp("BH", 22, si(igual(v_ci, 0), "N", v_ci))
        o = pp("BH", 17, si(igual(bh22, 0), "N", si(o_(igual(bh22, "NE"), igual(bh22, "NO")), "N",
                                                    si(igual(bh22, "SE"), "E",
                                                       si(igual(bh22, "SO"), "O", bh22)))))
        bh18 = pp("BH", 18, buscarv(o, t_gz, 2))
        bh19 = pp("BH", 19, buscarv(o, t_gz, 3))
        bh20 = pp("BH", 20, buscarv(o, t_gz, 4))
        bh21 = pp("BH", 21, buscarv(o, t_gz, 5))

        def micro(v):
            return ar(lambda y: y + MICRO, v)

        bk17 = pp("BK", 17, micro(vc("L")))
        bk18 = pp("BK", 18, micro(vc("K")))
        bk19 = pp("BK", 19, vc("BU"))
        bk20 = pp("BK", 20, micro(vc("BV")))
        bk22 = pp("BK", 22, copia(bk17))
        bk23 = pp("BK", 23, copia(bk18))
        bk24 = pp("BK", 24, micro(vc("BY")))
        bk25 = pp("BK", 25, vc("BZ"))
        bk27 = pp("BK", 27, copia(bk22))
        bk28 = pp("BK", 28, copia(bk23))
        bk29 = pp("BK", 29, micro(vc("BW")))
        bk30 = pp("BK", 30, vc("BX"))
        cb = vc("CB")
        bp17 = pp("BP", 17, si(igual(cb, 0), bk18, cb))
        bp18 = pp("BP", 18, micro(vc("CA")))
        bp19 = pp("BP", 19, vc("CC"))
        bp20 = pp("BP", 20, copia(bk17))
        bp21 = pp("BP", 21, ar(lambda t, e_, a: t - e_ * math.sin(math.radians(a)), bp17, bp18, bp19))
        bp23 = pp("BP", 23, ar(lambda e_, a: e_ * math.cos(math.radians(a)), bp18, bp19))
        bp25 = pp("BP", 25, copia(bp17))
        bp26 = pp("BP", 26, copia(bp18))
        bp27 = pp("BP", 27, vc("CD"))
        bp28 = pp("BP", 28, copia(bk18))

        def mitad(w, dd):
            return ar(lambda w_, d_: math.degrees(math.atan((w_ / 2) / d_)), w, dd)

        def lateral(w, s_, p_):
            return ar(lambda w_, ss, pq: math.degrees(math.atan((w_ / 2 + ss) / pq)), w, s_, p_)

        x1, x2 = mitad(bk17, bk20), mitad(bp20, bp23)
        bm17 = pp("BM", 17, _gamma(o, bh20, x1, True))
        bm18 = pp("BM", 18, _gamma(o, bh20, x1, False))
        br17 = pp("BR", 17, _gamma(o, bh20, x2, True))
        br18 = pp("BR", 18, _gamma(o, bh20, x2, False))
        bm22 = pp("BM", 22, _gamma(o, bh20, lateral(bk22, bk25, bk24), True))
        bm27 = pp("BM", 27, _gamma(o, bh20, lateral(bk27, bk30, bk29), False))
        br25 = pp("BR", 25, _br(o, bh19, bp25, bp26, bp27, 1))
        br26 = pp("BR", 26, _br(o, bh19, bp25, bp26, bp27, -1))
        br27 = pp("BR", 27, ar(lambda e_, h_, t: 1 - (e_ * h_ * 2) / (e_ * h_ * 2 + t * e_ + t * h_),
                               bp26, bp28, bp25))
        bm28 = _bm28(bk22, bk23, bk24, bk25, bk28, bk29, bk30)
        if b == BLOQUE_VENTANA_1:
            pp("BM", 19, iferror(ar(lambda a, w: math.degrees(math.atan(2 * a / w)), bk20, bk17), 0.0))
            bm_vis = pp("BM", 20, si(mayor(ar(op.mul, bk17, bk18), 0), _ratio(bk17, bk20, bk18), 1.0))
            br19 = pp("BR", 19, si(mayor(ar(op.mul, bp20, bp21), 0), _ratio(bp20, bp23, bp21), 1.0))
            pp("BR", 21, copia(bk18))
            bm28 = pp("BM", 28, si(y_(mayor(bk22, 0), mayor(bk23, 0), o_(mayor(bk24, 0), mayor(bk29, 0))),
                                   bm28, 1.0))
        else:
            bm_vis = pp("BM", 19, _ratio(bk17, bk20, bk18))
            br19 = pp("BR", 19, _ratio(bp20, bp23, bp21))
            bm28 = pp("BM", 28, bm28)
        bh24 = pp("BH", 24, ar(op.mul, min_rango((bm_vis, br19)), min_rango((bm28, br27))))
        v25 = buscarv(bh22, t_far, 3)
        bh25 = pp("BH", 25, v25 if b == 0 else iferror(v25, 1.0))
        bh26 = pp("BH", 26, ar(op.mul, bh25, bh24))
        bh27 = pp("BH", 27, vc("AF"))
        if b < 3:
            bh28 = copia(k_.get(P("BH", 28)))
            bh29 = pp("BH", 29, iferror(buscarv(bh28, te.vidrios, 3), 0.0))
        else:
            bh28 = pp("BH", 28, vc("D", desde=103))
            fs = ar(op.mul, b_fs, x.factor_fs) if base else buscarv(bh28, te.vidrios, 3)
            bh29 = pp("BH", 29, iferror(fs, 0.0))

        # ------------------------------------------ por mes y hora
        num1 = ar(lambda a, c: a / 2 + c, bk18, bk19)
        a1 = ar(lambda a: a / 2, bk17)
        num_a, a_a = ar(lambda a: a / 2, bk28), ar(lambda a, c: a / 2 + c, bk27, bk30)
        num_b, a_b = ar(lambda a: a / 2, bk23), ar(lambda a, c: a / 2 + c, bk22, bk25)
        num4, a4 = ar(lambda a: a / 2, bp21), ar(lambda a: a / 2, bp20)
        c1, c2 = mayor(br26, br25), menor(br26, br25)
        sel = None
        for nombre, colf in FAR:
            t = igual(bh22, nombre)
            if es_error(t) or t:
                sel = t if es_error(t) else colf
                break
        bu = copia(bh22)
        bw = [[None] * HORAS for _ in range(MESES)]
        ck = [[None] * HORAS for _ in range(MESES)]
        gm = [[None] * HORAS for _ in range(MESES)]
        at_b = [[None] * HORAS for _ in range(MESES)]
        for j in range(MESES):
            mes_d = k_.get(f"{COLS['AF'][j]}{r0 - 1}")
            mes_i = k_.get(f"{COLS['AT'][j]}{r0 - 1}")
            v_j = buscarv(bh22, t_fac, ar(lambda g: g + 1, ge[j]))
            for h in range(HORAS):
                r = r0 + h
                C = put(f"{COLS['C'][j]}{r}", copia(x.altura[j][h]))
                R = put(f"{COLS['R'][j]}{r}", copia(x.azimut[j][h]))
                hora = k_.get(f"AE{r}")
                AF = put(f"{COLS['AF'][j]}{r}", sumar_si(idx, gdir, mes_d, float(h) if hora is None else hora))
                if b < 2:
                    hora_i = k_.get(f"AS{r}")
                    AT = sumar_si(idx, gdif, mes_i, float(h) if hora_i is None else hora_i)
                else:
                    AT = copia(at_prev[j][h])
                at_b[j][h] = put(f"{COLS['AT'][j]}{r}", AT)
                if j == 0:
                    put(f"BU{r}", bu)
                bw[j][h] = put(f"{COLS['BW'][j]}{r}",
                               ar(lambda a, c, q, t: a * c * (q * t), bh29, bh27, bh26, AT))
                vis = _vis(C, R, o, bh18, bh19)
                dm = put(f"{COLS['DM'][j]}{r}", _prod(
                    vis,
                    _t(y_(mayor_igual(R, bh18), menor_igual(R, bm18),
                          mayor_igual(C, _ang(num1, a1, ar(op.sub, bh18, R))))),
                    _t(y_(mayor(R, bm18), menor_igual(R, bh20),
                          mayor_igual(C, _ang(num1, bk20, ar(op.sub, R, bh20))))),
                    _t(y_(mayor_igual(R, bh21), menor_igual(R, bm17),
                          mayor_igual(C, _ang(num1, bk20, ar(op.sub, R, bh21))))),
                    _t(y_(mayor_igual(R, bm17), menor_igual(R, bh19),
                          mayor_igual(C, _ang(num1, a1, ar(op.sub, bh19, R)))))))
                ea = put(f"{COLS['EA'][j]}{r}", _prod(
                    vis,
                    _t(y_(mayor_igual(R, bh18), menor_igual(R, bm27),
                          menor_igual(C, _ang(num_a, a_a, ar(op.sub, bh18, R))))),
                    _t(y_(mayor_igual(R, bm22), menor_igual(R, bh19),
                          menor_igual(C, _ang(num_b, a_b, ar(op.sub, bh19, R)))))))
                eo = put(f"{COLS['EO'][j]}{r}", _prod(
                    vis,
                    _t(y_(mayor_igual(R, bh18), menor_igual(R, br18),
                          mayor_igual(C, _ang(num4, a4, ar(op.sub, bh18, R))))),
                    _t(y_(mayor(R, br18), menor_igual(R, bh20),
                          mayor_igual(C, _ang(num4, bp23, ar(op.sub, R, bh20))))),
                    _t(y_(mayor_igual(R, bh21), menor_igual(R, br17),
                          mayor_igual(C, _ang(num4, bp23, ar(op.sub, R, bh21))))),
                    _t(y_(mayor_igual(R, br17), menor_igual(R, bh19),
                          mayor_igual(C, _ang(num4, a4, ar(op.sub, bh19, R)))))))
                fc = put(f"{COLS['FC'][j]}{r}", _prod(vis, _t(o_(
                    y_(c1, menor_igual(R, br26), mayor_igual(R, br25)),
                    y_(c2, menor_igual(R, br26)),
                    y_(c2, mayor_igual(R, br25))))))
                if sel is None:
                    fq = 1.0
                elif es_error(sel):
                    fq = sel
                else:
                    fq = copia(x.far.get(f"{_col(sel, j)}{65 + h}"))
                put(f"{COLS['FQ'][j]}{r}", fq)
                cy = put(f"{COLS['CY'][j]}{r}", si(y_(igual(bh22, "horiz"), mayor(C, 0)), 1.0,
                                                   _prod(dm, ea, eo, fc, fq)))
                ck[j][h] = put(f"{COLS['CK'][j]}{r}",
                               ar(lambda a, c, v, q, f_: a * c * (v * q * f_), bh29, bh27, v_j, cy, AF))
                gm[j][h] = put(f"{COLS['GE'][j]}{r}",
                               ar(lambda s_, f_, v, t: s_ * f_ * v + t, _sol(o, C, R, bh18, bh19), AF, v_j, AT))
        at_prev = at_b
        fila_mes = [(j, h) for h in range(HORAS) for j in range(MESES)]     # SUMA recorre por filas
        bh30 = pp("BH", 30, iferror(ar(lambda s_, g, a: s_ / (g * a),
                                        suma_rango([bw[j][h] for j, h in fila_mes]
                                                   + [ck[j][h] for j, h in fila_mes]),
                                        suma_rango([gm[j][h] for j, h in fila_mes]), bh27), 0.0))
        bh16 = pp("BH", 16, copia(bh30))
        bloques.append({"bg16": bg16, "bh16": bh16, "bu": bu, "bw": bw, "ck": ck,
                        "bv": [k_.get(f"BV{r0 + h}", float(h)) for h in range(HORAS)]})

    # ------------------------------------------------ FSM y FLD de cada vano (JS:JX, CEV-CEVE AM y CF)
    areas = suma_rango([renv.valor(ev.H_CEV, f"D{f}") for f in range(169, 179)]
                       + [renv.valor(ev.H_CEV, f"H{f}") for f in range(169, 178)])
    js, jv, jw, fsm = [], [], [], []
    for i, f in enumerate(VANOS):
        r = 14 + i
        lab = k_.get(f"JR{r}")
        jt = NA
        for bl in bloques:
            if lab is not None and not es_error(bl["bg16"]) and coincide(bl["bg16"], lab):
                jt = copia(bl["bh16"])
                break
        put(f"JT{r}", jt)
        fsm.append(jt)
        af = renv.valor(ev.H_CEV, f"AF{f}")
        am = cev_out[f"AM{f}"] = copia(jt)
        cf = cev_out[f"CF{f}"] = ar(lambda a, c, s_: (0.85 * a * c * 90 / (s_ * (1 - 0.5 ** 2))) / 100,
                                    am, af, areas)
        js.append(put(f"JS{r}", copia(renv.valor(ev.H_CEV, f"F{f}"))))
        ju = put(f"JU{r}", copia(af))
        jw.append(put(f"JW{r}", copia(cf)))
        jv.append(put(f"JV{r}", ar(op.mul, ju, jt)))
        put(f"JX{r}", ar(op.mul, ju, jw[-1]))

    # ------------------------------------------------ por orientacion (HO:HS)
    f_cev = [filas[f].get("F") for f in sorted(filas)]
    af_cev = [filas[f].get("AF") for f in sorted(filas)]
    ho_l, hs_l = [], []
    for r in FILAS_OR:
        ha = k_.get(f"HA{r}")
        ho = put(f"HO{r}", sumar_si_lista(af_cev, f_cev, ha))
        hp = put(f"HP{r}", sumar_si_lista(jv, js, ha))
        put(f"HQ{r}", iferror(ar(op.truediv, hp, ho), 0.0))
        hr = put(f"HR{r}", sumar_si_lista(jw, js, ha))
        ho_l.append(ho)
        hs_l.append(put(f"HS{r}", ar(op.mul, hr, ho)))
    ho12 = put("HO12", float(len([v for v in ho_l if es_numero(v) and v > 0])))
    ho23 = put("HO23", suma_rango(ho_l))
    hs23 = put("HS23", ar(op.truediv, suma_rango(hs_l), suma_rango(ho_l)))

    # ------------------------------------------------ radiacion por hora (IC, IQ) e iluminancia (JE)
    ib = [k_.get(f"IB{14 + h}", float(h)) for h in range(HORAS)]
    jf4 = k_.get("JF4")
    ilum = [[None] * HORAS for _ in range(MESES)]
    for j in range(MESES):
        for h in range(HORAS):
            r = 14 + h
            tot = {}
            for clave, col in (("bw", "IC"), ("ck", "IQ")):
                partes = []
                for ro in ORDEN_IC:
                    ha = k_.get(f"HA{ro}")
                    s_, err = 0.0, None
                    for bl in bloques:
                        bu = bl["bu"]
                        if bu is None or es_error(bu) or not coincide(bu, ha):
                            continue
                        if not coincide(bl["bv"][h], ib[h]):
                            continue
                        v = bl[clave][j][h]
                        if es_error(v):
                            err = v
                            break
                        if es_numero(v):
                            s_ += v
                    partes.append(0.0 if err is not None else s_)
                tot[col] = put(f"{COLS[col][j]}{r}", mas(*partes))
            ilum[j][h] = put(f"{COLS['JE'][j]}{r}", ar(
                lambda jf, a, c, hs, ho, n: jf * ((a + c) * hs * ho) / n,
                jf4, tot["IC"], tot["IQ"], hs23, ho23, ho12))
    return ResultadoFav({H_FAV: out, ev.H_CEV: cev_out}, tuple(tuple(m) for m in ilum), tuple(fsm))
