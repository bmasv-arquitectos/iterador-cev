# -*- coding: utf-8 -*-
"""
Inercia termica de la ficha 01 en Python: '0. Inercia Termica'.

Traduce, con el orden de operaciones de Excel:
  K10:N13   superficies por densidad (muros, techos, pisos, marcos) y O11
            (tabiques = 2 x superficie de muros y vanos por orientacion).
  F16:J18   capacidad (densidad x Cp x superficie) por densidad; fila 16:
            tabiques y marcos como elemento interior liviano (P16, U16, AH16).
  C45:D46   U del caso base de techos y pisos ventilados, acotado al limite.
  27-42     muros, 46-50 techos, 54-57 pisos ventilados, 60-63 pisos contra
            terreno: U truncado a 2 decimales (L), U para SA (M), posicion de
            la aislacion (N, O), clave (H) y, desde la tabla AL10:AX402,
            superficie activa y espesor de verano (Q, R, S) e invierno (V, W, X),
            amortiguamiento, CTm y fi (AA:AC); masas e*A*rho*Cp (AG:AJ).
  74-97     SA de cada hora por elemento (I:P) y su copia "con clima" (Q:X).
  75-81     masa: participacion por elemento (AF), espesor equivalente de H.A.
            (AG81, AH81 -> AA75, AB75), area equivalente (AA76), y Z79:AB79.
  100-113   temporada de cada mes segun la zona (X102:X113: "i"/"v").
  'CEV-CEVE'!BC96:BC98, BC103:BC122 (densidad de puertas y ventanas).
  '0. Datos Arq Motor'!X9:AE32, X36:AE59 (SA horarias) y AH7:AJ18 (masa).

Entradas: EntradasEnvolvente y ResultadoEnvolvente (envolvente.py), la zona
de clima ('0. Clima'!M2) y DatosInercia (constantes y formulas fijas de la
hoja, motor_py/datos/inercia.yaml). Los rangos que suma Excel (SUM(P16:P63)...) se
leen de la hoja completa: lo calculado mas las constantes de la plantilla.

Particularidades que se replican (no se corrigen):
  - L27:L42 (muros) usan en el caso base $C$45, que es el U de TECHO.
  - L60:L63 usan siempre D18/M18 de la NCh3117 (piso 1) para los 4 pisos.
  - J54 tiene IF(G54;...) pero J55:J57 copian 'CEV-CEVE'!F sin condicion.
  - AH/AJ (muros adiabaticos) usan AI9 si es liviano y AI11 en otro caso.
  - Temporada en minuscula ("i", "v"); quienes la usan comparan sin
    distinguir mayusculas.
"""
from __future__ import annotations

import operator as op
from dataclasses import dataclass

from openpyxl.utils import get_column_letter, range_boundaries

from . import envolvente as ev
from .datos import DatosEnvolvente, DatosInercia
from .excel import (
    Tabla, ar, buscarv, concatenar, copia, distinto, iferror, igual, mas, mayor, mayor_igual,
    menor, menor_igual, o_, si, suma_rango, sumar_si_lista, truncar, y_,
)

H_INER = "0. Inercia Termica"
MAPA_MURO = tuple(zip(range(27, 43), ev.FILAS_MURO))
MAPA_TECHO = tuple(zip(range(46, 51), ev.FILAS_TECHO))
MAPA_PV = tuple(zip(range(54, 58), ev.FILAS_PISO))
MAPA_PT = tuple(zip(range(60, 64), ev.FILAS_PISO))
COLS_SA = ("Q", "R", "S", "V", "W", "X")
COLS_DIN = (("AA", "AD"), ("AB", "AE"), ("AC", "AF"))
COLS_HORA = ("I", "J", "K", "L", "M", "N", "O", "P")
COLS_HORA_CLIMA = ("Q", "R", "S", "T", "U", "V", "W", "X")
GRUPOS_HORA = (("I", "J", range(27, 43)), ("K", "L", range(46, 51)),
               ("M", "N", range(54, 58)), ("O", "P", range(60, 64)))
# '0. Datos Arq Motor' AH7:AJ18 <- '0. Inercia Termica'
MASA_ARQ = (("AI7", "AA75"), ("AJ7", "AB75"), ("AI8", "AA76"), ("AH11", "Z79"), ("AI11", "AA79"),
            ("AJ11", "AB79"), ("AI14", "AF75"), ("AI15", "AF76"), ("AI16", "AF77"), ("AI17", "AF78"),
            ("AI18", "AF79"))


class Hoja:
    """Celdas de una hoja: constantes de la plantilla + lo calculado (calc)."""

    def __init__(self, base: dict):
        self.v = dict(base)
        self.calc: dict = {}

    def __call__(self, celda):
        return self.v.get(celda)

    def put(self, celda, valor):
        self.v[celda] = valor
        self.calc[celda] = valor
        return valor

    def rango(self, rango: str) -> list:
        """Valores del rango por filas (como los recorre SUMA)."""
        c1, f1, c2, f2 = range_boundaries(rango)
        return [self.v.get(f"{get_column_letter(c)}{f}")
                for f in range(f1, f2 + 1) for c in range(c1, c2 + 1)]

    def tabla(self, rango: str) -> Tabla:
        c1, f1, c2, f2 = range_boundaries(rango)
        return Tabla(tuple(tuple(self.v.get(f"{get_column_letter(c)}{f}") for c in range(c1, c2 + 1))
                           for f in range(f1, f2 + 1)), rango)


@dataclass(frozen=True)
class ResultadoInercia:
    celdas: dict           # {hoja: {celda: valor}}
    temporada: tuple       # '0. Inercia Termica'!X102:X113 ("i" invierno / "v" verano)

    def valor(self, hoja, celda):
        return self.celdas.get(hoja, {}).get(celda)


def calcular(di: DatosInercia, de: DatosEnvolvente, e: ev.EntradasEnvolvente,
             renv: ev.ResultadoEnvolvente, zona) -> ResultadoInercia:
    h = Hoja(di.celdas)
    base = e.caso > 2
    rv = renv.valor
    cev, arq = {}, {}

    # --------------------------------------------------------------- densidad de los vanos (CEV-CEVE BC)
    for k, f in enumerate(ev.FILAS_PUERTA):
        cev[f"BC{f}"] = copia(h(f"I{10 + k}"))
    for x, f in zip(e.ventanas, ev.FILAS_VENTANA):
        cev[f"BC{f}"] = copia(si(igual(x.categoria, "Madera"), h("I10"), h("I11")))

    # --------------------------------------------------------------- superficies por densidad (K10:O13)
    def col(letra, filas):
        return [rv(ev.H_CEV, f"{letra}{f}") for f in filas]

    vanos = ev.FILAS_PUERTA + ev.FILAS_VENTANA
    grupos = (("K", col("BD", ev.FILAS_MURO), col("BC", ev.FILAS_MURO)),
              ("L", col("BD", ev.FILAS_TECHO), col("BC", ev.FILAS_TECHO)),
              ("M", col("BD", ev.FILAS_PISO), col("BC", ev.FILAS_PISO)),
              ("N", col("BD", vanos), [cev[f"BC{f}"] for f in vanos]))
    for r in range(10, 14):
        for letra, bd, bc in grupos:
            h.put(f"{letra}{r}", sumar_si_lista(bd, bc, h(f"I{r}")))
    filas_or = range(170, 178)
    h.put("O11", ar(lambda s: s * 2, suma_rango(col("D", filas_or) + col("H", filas_or))))

    # --------------------------------------------------------------- capacidad por densidad (F16:J18)
    h.put("J16", suma_rango(h.rango("K10:O11")))
    h.put("J17", suma_rango(h.rango("K12:N12")))
    h.put("J18", suma_rango(h.rango("K13:N13")))
    for r in (16, 17, 18):
        h.put(f"F{r}", ar(lambda g, c, j: g * c * j, h(f"G{r}"), h(f"H{r}"), h(f"J{r}")))
    t_dens = h.tabla("E16:H18")
    t_sa = h.tabla("AL10:AR402")
    t_din = h.tabla("AL10:AX402")

    def rho_cp(k):
        return buscarv(k, t_dens, 3), buscarv(k, t_dens, 4)

    # fila 16: tabiques y marcos como elemento interior
    h.put("P16", mas(h("O11"), h("N10"), h("N11")))
    h.put("R16", copia(h("AI9")))
    h.put("U16", ar(lambda r_, p: r_ * p / 100, h("R16"), h("P16")))
    g3, g4 = rho_cp(h("K16"))
    h.put("AH16", ar(lambda u, a, c: u * a * c, h("U16"), g3, g4))
    h.put("AJ16", copia(h("AH16")))

    # --------------------------------------------------------------- U del caso base (C45:D46)
    b23, c23, d23 = h("B23"), h("C23"), h("D23")
    for r, nombre in ((45, "base_U_techo"), (46, "base_U_PV")):
        d = h.put(f"D{r}", copia(renv.nombre(nombre)))
        h.put(f"C{r}", copia(si(y_(mayor_igual(d, d23), menor_igual(d, b23)), d23, d)))
    c45, c46 = h("C45"), h("C46")

    # --------------------------------------------------------------- un elemento (filas 27-63)
    b16, b17, b18, b19, b20 = (h(f"B{r}") for r in range(16, 21))
    b32, b37, b38 = h("B32"), h("B37"), h("B38")
    ah9, ai9, ai11 = h("AH9"), h("AI9"), h("AI11")

    def elemento(r, I, J, L, N, P):
        def put(c, v):
            return h.put(f"{c}{r}", v)

        put("I", I)
        put("J", J)
        K = put("K", copia(si(o_(igual(J, b37), igual(J, b38)), b32, J)))
        put("L", L)
        M = put("M", si(igual(L, 0), 0.0, si(mayor_igual(L, b23), L, si(menor(L, c23), copia(c23),
                                                                       si(mayor(L, d23), copia(d23), L)))))
        put("N", N)
        O = put("O", copia(si(mayor_igual(M, b23), b16, si(igual(K, b32), b17, si(igual(N, b16), N, si(
            o_(igual(N, b17), igual(N, b20)), b17, si(o_(igual(N, b18), igual(N, b19)), b18, 0.0)))))))
        H = put("H", si(igual(O, b16), concatenar(K, O), concatenar(K, O, M)))
        put("P", P)
        m0 = igual(M, 0)
        v = {c: put(c, si(m0, 0.0, buscarv(H, t_sa, h(f"{c}24")))) for c in COLS_SA}
        put("T", ar(op.mul, v["Q"], P))
        U = put("U", ar(lambda x, p: x * p / 100, v["R"], P))
        put("Y", ar(op.mul, v["V"], P))
        Z = put("Z", ar(lambda x, p: x * p / 100, v["W"], P))
        for c_din, c_sup in COLS_DIN:
            x = put(c_din, si(m0, 0.0, buscarv(H, t_din, h(f"{c_din}24"))))
            put(c_sup, ar(op.mul, x, P))
        r3, r4 = rho_cp(K)
        put("AG", iferror(si(mayor(L, 0), ar(lambda u, a, c: u * a * c, U, r3, r4), 0.0), 0.0))
        esp = si(igual(K, ah9), ar(lambda a: a / 100, ai9), ar(lambda a: a / 100, ai11))
        adiab = iferror(si(igual(L, 0), ar(lambda p, s_, a, c: p * s_ * a * c, P, esp, r3, r4), 0.0), 0.0)
        put("AH", adiab)
        put("AI", iferror(si(mayor(L, 0), ar(lambda z, a, c: z * a * c, Z, r3, r4), 0.0), 0.0))
        put("AJ", adiab)

    te = e.tablas
    te_muros = ev._rango(te, 61, 75, "C", "H")
    te_techos = ev._rango(te, 79, 82, "C", "H")
    te_pisos = ev._rango(te, 87, 91, "C", "M")

    def u_tabla(tabla, I, col_u):
        return copia(c45) if base else buscarv(I, tabla, col_u)

    for (r, f), m in zip(MAPA_MURO, e.muros):
        I = copia(m.nombre)
        L = si(igual(I, 0), 0.0, iferror(truncar(u_tabla(te_muros, I, 3), 2), 0.0))
        elemento(r, I, copia(rv(ev.H_CEV, f"G{f}")), L, iferror(buscarv(I, te_muros, 6), 0.0), copia(m.area))
    for (r, f), t in zip(MAPA_TECHO, e.techos):
        I = copia(t.tipo)
        L = si(igual(I, 0), 0.0, iferror(truncar(u_tabla(te_techos, I, 2), 2), 0.0))
        elemento(r, I, copia(t.categoria), L, iferror(buscarv(I, te_techos, 6), 0.0), copia(t.area))
    m11, m12 = de.tref.get("M11"), de.tref.get("M12")
    for (r, f), p in zip(MAPA_PV, e.pisos_env):
        G = h.put(f"G{r}", si(igual(p.condicion, m11), True, False))
        I = si(G, copia(p.tipo), 0.0)
        J = si(G, copia(p.categoria), 0.0) if r == 54 else copia(p.categoria)
        L = si(G, iferror(truncar(copia(c46) if base else buscarv(I, te_pisos, 2), 2), 0.0), 0.0)
        elemento(r, I, J, L, iferror(buscarv(I, te_pisos, 11), 0.0),
                 si(igual(p.perimetro, 0), copia(p.area), 0.0))
    d18, m18 = rv(ev.H_PISO, "D18"), rv(ev.H_PISO, "M18")
    for (r, f), p in zip(MAPA_PT, e.pisos_env):
        G = h.put(f"G{r}", si(igual(p.condicion, m12), True, False))
        I = si(G, copia(p.tipo), 0.0)
        J = si(G, copia(p.categoria), 0.0)
        L = si(G, iferror(truncar(copia(m18) if base else copia(d18), 2), 0.0), 0.0)
        elemento(r, I, J, L, iferror(buscarv(I, te_pisos, 11), 0.0),
                 si(distinto(p.perimetro, 0), copia(p.area), 0.0))

    # --------------------------------------------------------------- SA de cada hora (filas 74-97)
    listas = {}
    for c_v, c_i, filas in GRUPOS_HORA:
        listas[c_v] = ([h(f"T{x}") for x in filas], [h(f"S{x}") for x in filas],
                       [h(f"Y{x}") for x in filas], [h(f"X{x}") for x in filas],
                       suma_rango([h(f"P{x}") for x in filas]))
    for k in range(24):
        r = 74 + k
        hr = h("H74") if k == 0 else h.put(f"H{r}", ar(lambda x: x + 1, h(f"H{r - 1}")))
        for c_v, c_i, _ in GRUPOS_HORA:
            T, S, Y, X, sp = listas[c_v]
            h.put(f"{c_v}{r}", iferror(ar(op.truediv, sumar_si_lista(T, S, hr), sp), 0.0))
            h.put(f"{c_i}{r}", iferror(ar(op.truediv, sumar_si_lista(Y, X, hr), sp), 0.0))
        for src, dst in zip(COLS_HORA, COLS_HORA_CLIMA):
            h.put(f"{dst}{r}", copia(h(f"{src}{r}")))

    # --------------------------------------------------------------- masa (filas 64, 75-81)
    def s(rango):
        return suma_rango(h.rango(rango))

    h.put("AH64", s("AH16:AH63"))
    h.put("AJ64", s("AJ16:AJ63"))
    for r, filas in ((75, "46:50"), (76, "27:42"), (77, "54:57"), (78, "60:63")):
        f1, f2 = filas.split(":")
        h.put(f"AG{r}", s(f"AG{f1}:AG{f2}"))
        h.put(f"AH{r}", s(f"AI{f1}:AI{f2}"))
    h.put("AG79", copia(h("AH64")))
    h.put("AH79", copia(h("AJ64")))
    h.put("AG80", s("AG75:AG79"))
    h.put("AH80", s("AH75:AH79"))
    for r in range(75, 81):
        h.put(f"AI{r}", ar(op.add, h(f"AH{r}"), h(f"AG{r}")))
    for r in range(75, 80):
        h.put(f"AF{r}", ar(op.truediv, h(f"AI{r}"), h("AI80")))
    h.put("AA76", s("K10:M13"))
    for c, src in (("AG81", "AG80"), ("AH81", "AH80")):
        h.put(c, ar(lambda a, area, g, c_: 100 * a / (area * g * c_), h(src), h("AA76"), h("G18"), h("H18")))
    h.put("AA75", copia(h("AG81")))
    h.put("AB75", copia(h("AH81")))
    sp = s("P16:P63")
    for c, src in (("Z79", "AD"), ("AA79", "AE"), ("AB79", "AF")):
        h.put(c, ar(op.truediv, s(f"{src}16:{src}63"), sp))

    # --------------------------------------------------------------- temporada (filas 100-113)
    w = h.put("W101", copia(zona))
    i112 = h.put("I112", copia(w))
    t_zona = h.tabla("I102:U111")
    for j in range(12):
        c = get_column_letter(10 + j)                       # J..U
        x = buscarv(i112, t_zona, h(f"{c}100"))
        h.put(f"{c}112", si(mayor_igual(x, h("I101")), "i", "v"))
    temporada = tuple(h.put(f"X{102 + j}", copia(h(f"{get_column_letter(10 + j)}112"))) for j in range(12))

    # --------------------------------------------------------------- '0. Datos Arq Motor'
    for k in range(24):
        for j in range(8):
            c = get_column_letter(24 + j)                   # X..AE
            arq[f"{c}{9 + k}"] = copia(h(f"{COLS_HORA[j]}{74 + k}"))
            arq[f"{c}{36 + k}"] = copia(h(f"{COLS_HORA_CLIMA[j]}{74 + k}"))
    for c_arq, c_in in MASA_ARQ:
        arq[c_arq] = copia(h(c_in))

    iner = {c: h.v.get(c) for c in di.fijas}
    iner.update(h.calc)
    return ResultadoInercia({H_INER: iner, ev.H_CEV: cev, ev.H_ARQ: arq}, temporada)
