# -*- coding: utf-8 -*-
"""
Obstrucciones remotas de la ficha 01 en Python: '0. FAR'.

La hoja son 8 bloques de 26 columnas (bloque b desde la columna A + 26*b), uno por
orientacion: N, E, S, O, NE, SE, SO, NO. En cada bloque (coordenadas del bloque 1):
  C4:Z15, C20:Z31   altura y azimut solar por mes (filas) y hora (columnas C..Z),
                    de '0.FAV parametros 1' (los bloques 2-8 copian el bloque 1).
  C34:Z45, C48:Z59  radiacion directa y difusa horizontal ('0. Clima'!Q y P).
  D68:D73           orientacion del calculo (D68, desde la orientacion real D73 =
                    'CEV-CEVE'!E125...) y sus limites de la tabla B145:F149.
  G68:O75           8 obstaculos ('CEV-CEVE'!E127:H134...): division (G), alto (H),
                    distancia (I), ancho (J); centro K, azimut inicial L y final M,
                    altura N y % de cielo difuso que tapa O.
  C107:Z118         directa que llega al plano del vano; C121:Z132 cuantos obstaculos
                    tapan el sol; C79:Z90 = 1 si llega y nadie lo tapa; C93:Z104 directa
                    que entra.
  T68 / T69         FAR directo (SUM(C93:Z104)/SUM(C107:Z118)) y difuso (1 - SUM(O)).
  Bloques 5-8 (NE, SE, SO, NO): un segundo juego en las filas 136-200 con la
  orientacion cardinal de D136 (E, S, S, O) y los mismos obstaculos.
Fuera de los bloques:
  HG65:LE88         INDIRECT a C79:Z90 de cada bloque (hora en filas, mes en columnas):
                    lo lee '0.FAV Calculos'!FQ.
  L148:N155         FAR directo (M) y difuso (N) por orientacion: lo lee '0.FAV Calculos'!BH25.
                    NE, SE, SO y NO promedian los dos juegos.
  B159:AA254        C79:Z90 de los 8 bloques uno bajo otro (B = orientacion & mes).
  A106, A120        repiten C107 y C121 (hora 0 de enero).

Entradas: EntradasFar (orientacion real y obstaculos de 'CEV-CEVE'), altura y
azimut solar (geometria_solar.py) y el clima horario (clima.horario).
Constantes de la hoja: DatosFar (motor_py/datos/far.yaml).

Particularidades que se replican (no se corrigen):
  - M68:M75: el IF(AND(G="Division 3";D="S")) lee la columna D de SU fila (D68 solo
    en M68; D69:D72 son numeros, D73 es la orientacion real, D74:D75 vacias). En el
    segundo juego (filas 136-143) lee DD$136 fijo.
  - HG65:KT88 (lo que usa la radiacion directa por hora) solo lee el primer juego:
    para NE, SE, SO y NO la directa por hora usa la orientacion N, E, O, N, y la
    tabla L148:N155 (difusa) promedia los dos juegos.
  - B207:B254 (NE, SE, SO, NO) concatenan $D$68, $AD$68, $BD$68, $CD$68: la
    orientacion de N, E, S, O, no la suya.
  - T68 = #DIV/0! si al vano no le llega directa en ninguna hora del anio.
  - ATAN(x)*180/PI() y las sumas en el orden de Excel.
"""
from __future__ import annotations

import math
import operator as op
from dataclasses import dataclass, field

from openpyxl.utils import column_index_from_string, get_column_letter

from .datos import DatosFar
from .excel import (
    Tabla, ar, buscarv, concatenar, copia, distinto, es_error, iferror, igual, indice, mas, max_args,
    mayor, mayor_igual, menor_igual, o_, promedio_rango, si, suma_rango, sumar_si, y_,
)

H_FAR = "0. FAR"
BLOQUES, ANCHO = 8, 26
HORAS, MESES = 24, 12
OBSTACULOS = 8
ORIENTACIONES = ("N", "E", "S", "O", "NE", "SE", "SO", "NO")
COL_FQ = ("HG", "HT", "IG", "IT", "JG", "JT", "KG", "KT")      # INDIRECT por orientacion
# 'CEV-CEVE': (columna, fila de la orientacion real, primera fila de obstaculos) por bloque
CEV_FAR = (("E", 125, 127), ("J", 125, 127), ("O", 125, 127), ("T", 125, 127),
           ("E", 137, 139), ("J", 137, 139), ("O", 137, 139), ("T", 137, 139))
# (obstaculos, libre, bloqueado, directa al vano, cuantos tapan): filas del juego
FILAS_SUP = (68, 79, 93, 107, 121)
FILAS_INF = (136, 147, 161, 175, 189)
DIAGONALES = range(4, 8)
FILA_TABLA = 159                    # B159:AA254, 12 filas por bloque
DIV3 = "División 3"


def celda(b: int, col: str, fila: int) -> str:
    """Celda del bloque b (0..7) dada la columna en coordenadas del bloque 1."""
    return f"{get_column_letter(column_index_from_string(col) + ANCHO * b)}{fila}"


def hcol(h: int) -> str:
    """Columna de la hora h (C = hora 0) en el bloque 1."""
    return get_column_letter(3 + h)


def _grados(x):
    return math.atan(x) * 180 / math.pi


@dataclass(frozen=True)
class Obstaculo:
    division: object       # G ('Cadrante': Division 1..5)
    alto: object           # H (A)
    distancia: object      # I (B)
    ancho: object          # J (D)


@dataclass(frozen=True)
class EntradasFar:
    orientacion: tuple     # 8: 'CEV-CEVE'!E125, J125, O125, T125, E137, J137, O137, T137
    obstaculos: tuple      # 8 x 8 Obstaculo ('CEV-CEVE'!E127:H134, J127:M134, ...)


def entradas_desde_cev(cev) -> EntradasFar:
    """cev: funcion celda -> valor de 'CEV-CEVE'."""
    ori, obs = [], []
    for col, f_or, f_obs in CEV_FAR:
        c0 = column_index_from_string(col)
        ori.append(cev(f"{col}{f_or}"))
        obs.append(tuple(Obstaculo(*(cev(f"{get_column_letter(c0 + j)}{f_obs + i}") for j in range(4)))
                         for i in range(OBSTACULOS)))
    return EntradasFar(tuple(ori), tuple(obs))


@dataclass(frozen=True)
class ResultadoFar:
    celdas: dict           # {hoja: {celda: valor}}
    far: dict = field(default_factory=dict, compare=False, repr=False)

    def valor(self, c):
        return self.celdas.get(H_FAR, {}).get(c)

    def far_fav(self) -> dict:
        """Lo que lee '0.FAV Calculos': HG65:LE88 y L148:N155 (EntradasFav.far)."""
        return dict(self.far)


def calcular(d: DatosFar, e: EntradasFar, altura, azimut, hor, dc) -> ResultadoFar:
    """altura, azimut: [mes][hora] (geometria_solar); hor: clima.horario; dc: DatosClima."""
    k = d.celdas
    out: dict = {}

    def put(c, v):
        out[c] = v
        return v

    def val(c):
        return out[c] if c in out else k.get(c)

    # ------------------------------------------------ divisiones (C135:E139) y orientaciones (B145:F149)
    g135 = k.get("G135")
    put("D135", copia(g135))
    put("E135", copia(g135))
    for r in (136, 137):
        for c in "DE":
            put(f"{c}{r}", ar(lambda a, x: a + x * 2, val(f"{c}{r - 1}"), g135))
    for r in (138, 139):
        put(f"D{r}", ar(lambda a, x: a + x * 2, val(f"D{r - 1}"), g135))
    put("E138", ar(lambda x: -180 - x * 3, g135))
    put("E139", ar(lambda x: -180 - x, g135))
    t_div = Tabla(tuple((k.get(f"C{r}"), val(f"D{r}"), val(f"E{r}")) for r in range(135, 140)))
    t_or = Tabla(tuple(tuple(k.get(f"{c}{r}") for c in "BCDEF") for r in range(145, 150)))

    # ------------------------------------------------ sol y radiacion (bloque 1; los demas copian)
    idx = indice(dc.filas_mes, dc.filas_hora)
    for m in range(MESES):
        for h in range(HORAS):
            c = hcol(h)
            hora = k.get(f"{c}33")
            vals = ((4, copia(altura[m][h])), (20, copia(azimut[m][h])),
                    (34, sumar_si(idx, hor.g_directa, k.get(f"B{34 + m}"), hora)),
                    (48, sumar_si(idx, hor.g_difusa, k.get(f"B{48 + m}"), hora)))
            for f0, v in vals:
                for b in range(BLOQUES):
                    put(celda(b, c, f0 + m), v)

    # ------------------------------------------------ un juego de 8 obstaculos
    def juego(b, filas, d_or, inferior):
        fo, f_libre, f_bloq, f_dir, f_cnt = filas
        dv = [put(celda(b, "D", fo + 1 + i), buscarv(d_or, t_or, 2 + i)) for i in range(4)]
        d_i, d71, d72 = dv[0], dv[2], dv[3]
        obs = []
        for i in range(OBSTACULOS):
            r = fo + i
            g_, a_, b_, w_ = (val(celda(b, c, r)) for c in "GHIJ")
            kk = put(celda(b, "K", r), iferror(ar(op.add, d_i, si(igual(d_or, "s"), buscarv(g_, t_div, 3),
                                                                   buscarv(g_, t_div, 2))), 0.0))
            atn = ar(lambda w, bb: _grados(w / (2 * bb)), w_, b_)
            ll = put(celda(b, "L", r), iferror(ar(op.sub, kk, atn), 0.0))
            d_m = d_or if inferior else val(celda(b, "D", r))
            mm = put(celda(b, "M", r), iferror(si(y_(igual(g_, DIV3), igual(d_m, "S")),
                                                  ar(lambda x, y: -x + y, kk, atn), ar(op.add, kk, atn)), 0.0))
            nn = put(celda(b, "N", r), iferror(ar(lambda a, bb: _grados(a / bb), a_, b_), 0.0))
            oo = put(celda(b, "O", r), si(y_(igual(d_or, "S"), distinto(g_, DIV3)),
                                          ar(lambda n, mq, lq: (n / 90) * (mq - lq) / 180, nn, mm, ll),
                                          ar(lambda n, a, lq, bq, mq: (n / 90) * ((a - lq) - (bq - mq)) / 180,
                                             nn, d71, ll, d72, mm)))
            obs.append((ll, mm, nn, oo))
        lim_i, lim_f = ar(lambda x: x - 90, d71), ar(lambda x: x + 90, d72)
        sur = igual(d_or, "S")
        for m in range(MESES):
            for h in range(HORAS):
                c = hcol(h)
                a = val(celda(b, c, 4 + m))
                z = val(celda(b, c, 20 + m))
                s = val(celda(b, c, 34 + m))
                sol = mayor(a, 0)
                directa = put(celda(b, c, f_dir + m), si(
                    sur,
                    si(o_(y_(sol, mayor_igual(z, lim_i)), y_(sol, menor_igual(z, lim_f))), s, 0.0),
                    si(y_(sol, mayor_igual(z, lim_i), menor_igual(z, lim_f)), s, 0.0)))
                cnt = put(celda(b, c, f_cnt + m), mas(*(
                    si(y_(sol, menor_igual(a, o[2]), mayor(z, o[0]), menor_igual(z, o[1])), 1.0, 0.0)
                    for o in obs)))
                libre = put(celda(b, c, f_libre + m), si(y_(mayor(directa, 0), igual(cnt, 0)), 1.0, 0.0))
                put(celda(b, c, f_bloq + m), ar(op.mul, libre, directa))

        def rect(f0):
            return [val(celda(b, hcol(h), f0 + m)) for m in range(MESES) for h in range(HORAS)]

        put(celda(b, "T", fo), ar(op.truediv, suma_rango(rect(f_bloq)), suma_rango(rect(f_dir))))
        put(celda(b, "T", fo + 1), max_args(0.0, ar(lambda x: 1 - x, suma_rango([o[3] for o in obs]))))

    # ------------------------------------------------ bloques
    for b in range(BLOQUES):
        d73 = put(celda(b, "D", 73), copia(e.orientacion[b]))
        d68 = put(celda(b, "D", 68), si(igual(d73, 0), "N", si(o_(igual(d73, "NE"), igual(d73, "NO")), "N",
                                                                 si(igual(d73, "SE"), "E",
                                                                    si(igual(d73, "SO"), "O", d73)))))
        for i, ob in enumerate(e.obstaculos[b]):
            for c, v in zip("GHIJ", (ob.division, ob.alto, ob.distancia, ob.ancho)):
                put(celda(b, c, 68 + i), copia(v))
        juego(b, FILAS_SUP, d68, False)
        if b in DIAGONALES:
            put(celda(b, "D", 141), copia(d73))
            for i in range(OBSTACULOS):
                for c in "GHIJ":
                    put(celda(b, c, 136 + i), copia(val(celda(b, c, 68 + i))))
            juego(b, FILAS_INF, copia(k.get(celda(b, "D", 136))), True)
    put("A106", val("C107"))
    put("A120", val("C121"))

    # ------------------------------------------------ INDIRECT por orientacion (HG65:LE88)
    far: dict = {}
    for colq in COL_FQ:
        c0 = column_index_from_string(colq)
        letras = get_column_letter(c0 - 1)
        filas = [copia(k.get(f"{colq}62"))]
        for j in range(1, MESES):
            filas.append(put(f"{get_column_letter(c0 + j)}62", ar(lambda x: x + 1, filas[-1])))
        for h in range(HORAS):
            letra = k.get(f"{letras}{65 + h}")
            for j in range(MESES):
                dirc = concatenar(letra, filas[j])
                v = dirc if es_error(dirc) else copia(val(str(dirc).upper()))
                c = f"{get_column_letter(c0 + j)}{65 + h}"
                far[c] = put(c, v)

    # ------------------------------------------------ FAR directo y difuso por orientacion (L148:N155)
    for i, r in enumerate(range(148, 156)):
        if i < 4:
            md, nd = copia(val(celda(i, "T", 68))), copia(val(celda(i, "T", 69)))
        else:
            md = promedio_rango([val(celda(i, "T", 68)), val(celda(i, "T", 136))])
            nd = promedio_rango([val(celda(i, "T", 69)), val(celda(i, "T", 137))])
        far[f"L{r}"] = k.get(f"L{r}")
        far[f"M{r}"] = put(f"M{r}", md)
        far[f"N{r}"] = put(f"N{r}", nd)
    for i, r in enumerate(range(152, 156)):
        put(f"B{r}", copia(val(celda(i, "D", 73))))

    # ------------------------------------------------ C79:Z90 de los 8 bloques uno bajo otro (B159:AA254)
    for s in range(BLOQUES):
        d68 = val(celda(s % 4, "D", 68))
        for m in range(MESES):
            r = FILA_TABLA + 12 * s + m
            mes = put(f"C{r}", copia(val(f"B{79 + m}") if s == 0 else val(f"C{FILA_TABLA + m}")))
            put(f"B{r}", concatenar(d68, mes))
            for h in range(HORAS):
                put(f"{get_column_letter(4 + h)}{r}", copia(val(celda(s, hcol(h), 79 + m))))
    return ResultadoFar({H_FAR: out}, far)
