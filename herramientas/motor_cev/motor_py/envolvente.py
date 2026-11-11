# -*- coding: utf-8 -*-
"""
Envolvente de la ficha 01 en Python: lo que 'CEV-CEVE' y sus hojas auxiliares
calculan con los muros, puertas, ventanas, techos y pisos, hasta el resumen
por orientacion que lee el motor ('0. Datos Arq Motor'!G8:N17).

Hojas que traduce (plantilla v2.2, mismo orden de operaciones que Excel):
  'CEV-CEVE'            zona OGUC 2007 de la comuna (L9:O10), dimensiones (52-56),
                        muros 66-81 (U, area efectiva, puentes P01-P03), P04 87-91,
                        puertas 96-98, ventanas 103-122 (U ponderado, vidrio y
                        marco, P05), techos 150-154 (absortividad AR150), pisos
                        158-161 y el resumen por orientacion (filas 169-178).
  '3. Tablas Envolvente' U de puertas (I12:K23) y FS de vidrios de fabrica (E27:E31).
  '0. Envolvente OGUC'  1/U de la Tabla 1 (D9:H15), % de ventanas OGUC 2007
                        (C17:C21) y U de ventana en techo (Q18).
  '0. Transmitancia piso Nch3117'  Ls de los pisos contra terreno, propuesto (D:G)
                        y caso base (M:P), y el que usa el caso (C40:C43).
  '0. Datos Arq Motor'  envolvente del caso base (D59:D94: los nombres base_*) y
                        lo que lee el motor (C4:C6, C32, G8:N17, G22:I24, G26, I26).
  '0. Infiltraciones'   H44, H50, H55 (materialidades del caso base).

Entradas: EntradasEnvolvente (lo que se escribe en 'CEV-CEVE' y en '3. Tablas
Envolvente'). Tablas fijas: DatosEnvolvente (motor_py/datos/envolvente.yaml). Los nombres
definidos (Zona_2007, base_U_muro...) se resuelven por su celda: si es una
celda que calcula este modulo se usa ese valor; si no, el de la plantilla.

Quedan para otros modulos: AM y CF (radiacion por ventanas) y BC de puertas
y ventanas (inercia).

Particularidades que se replican (no se corrigen):
  - P05 del caso base (AZ): la ventana 1 usa base_marco_P05, base_pos_P05 y
    base_retorno_P05; las ventanas 2 a 20 traen "Metalico", "Centrada" y "Sin"
    escritos en la formula.
  - La orientacion de los casos base (CH52:CR60) se usa tal cual; en la
    plantilla v2.2, CP56 dice "MO" (no es una orientacion).
  - P04: AR87 es la posicion de la aislacion en texto (columna H de la tabla
    de muros); en los muros AR66 es el codigo de '0. Tablas referencia'!EN21:EO25.
"""
from __future__ import annotations

import math
import operator as op
from dataclasses import dataclass, field

from openpyxl.utils import column_index_from_string, get_column_letter

from .datos import DatosEnvolvente
from .excel import (
    NA, Tabla, ar, buscarv, concatenar, copia, es_error, iferror, igual, mas, max_args,
    max_rango, mayor, mayor_igual, menor, menor_igual, min_args, min_rango, o_, posicion,
    promedio_rango, si, suma_rango, sumar_si_lista, trunc,
)

H_CEV = "CEV-CEVE"
H_TE = "3. Tablas Envolvente"
H_OGUC = "0. Envolvente OGUC"
H_ARQ = "0. Datos Arq Motor"
H_PISO = "0. Transmitancia piso Nch3117"
H_INF = "0. Infiltraciones"
FILAS_MURO = tuple(range(66, 82))
FILAS_P04 = tuple(range(87, 92))
FILAS_PUERTA = (96, 97, 98)
FILAS_VENTANA = tuple(range(103, 123))
FILAS_TECHO = tuple(range(150, 155))
FILAS_PISO = tuple(range(158, 162))
FILAS_ORIENTACION = tuple(range(169, 178))          # techo (Horiz) y 8 orientaciones
FILAS_DIM = (52, 53, 54)
FAV = tuple(get_column_letter(c) for c in range(16, 26))        # P..Y (FAV 1, 2 y 3)
FAV_COPIA = tuple(get_column_letter(c) for c in range(73, 83))  # BU..CD
COL_COMUNA = 15        # BUSCARV(E9; U12:AP357; k) -> columna k - 15 de la tabla reducida (U, AK..AP)
COLS_PROPUESTO = ("D", "E", "F", "G")              # NCh3117: pisos 1, 2, 3 y 4+
COLS_BASE = ("M", "N", "O", "P")
FILAS_TABLA_PISO = (12, 13, 20, 21, 22, 26, 27, 28)


# --------------------------------------------------------------------------- entradas
@dataclass(frozen=True)
class Muro:
    nombre: object         # 'CEV-CEVE'!D66:D81 (abreviatura de '3. Tablas Envolvente'!C61:C75)
    azimut: object         # E (rango de azimut)
    area: object           # H [m2]
    p01: object            # K [m]
    p02: object            # L [m]
    p03: object            # M [m]


@dataclass(frozen=True)
class P04:
    muro: object           # 'CEV-CEVE'!D87:D91 (muro donde esta)
    azimut: object         # E
    elemento: object       # G (elemento perpendicular)
    aislacion: object      # H
    longitud: object       # I [m]


@dataclass(frozen=True)
class Puerta:
    tipo: object           # 'CEV-CEVE'!D96:D98 (abreviatura de C12:C23)
    azimut: object         # E
    alto: object           # K [m]
    ancho: object          # L [m]
    fav: tuple             # P..Y


@dataclass(frozen=True)
class Ventana:
    tipo: object           # 'CEV-CEVE'!D103:D122 (vidrio, C27:C42)
    azimut: object         # E
    elemento: object       # G (muro o techo donde esta)
    cierre: object         # H
    posicion: object       # I
    retorno: object        # J
    alto: object           # K [m]
    ancho: object          # L [m]
    categoria: object      # M (categoria para PT e infiltraciones)
    marco: object          # N (marco, C46:C57)
    fav: tuple             # P..Y


@dataclass(frozen=True)
class Techo:
    tipo: object           # 'CEV-CEVE'!D150:D154 (C79:C82)
    categoria: object      # F
    area: object           # G [m2]
    color_k: object        # K (absortividad)
    color_l: object        # L


@dataclass(frozen=True)
class Piso:
    tipo: object           # 'CEV-CEVE'!D158:D161 (C87:C91)
    categoria: object      # F
    area: object           # G [m2]
    perimetro: object      # K [m]
    condicion: object      # L (ventilado / contra terreno)


@dataclass(frozen=True)
class EntradasEnvolvente:
    caso: int
    comuna: object                 # 'CEV-CEVE'!E9
    zona: object                   # E10
    pisos: tuple                   # ((area, altura) x 3): D52:E54
    muros: tuple                   # 16 Muro
    p04: tuple                     # 5 P04
    puertas: tuple                 # 3 Puerta
    ventanas: tuple                # 20 Ventana
    techos: tuple                  # 5 Techo
    pisos_env: tuple               # 4 Piso
    recuperador: object            # E227
    eficiencia_recuperador: object  # F229 [%]
    tablas: dict                   # '3. Tablas Envolvente' {celda: valor}


# --------------------------------------------------------------------------- celdas
class Libro:
    """Celdas calculadas {hoja: {celda: valor}} y nombres definidos de la ficha."""

    def __init__(self, d: DatosEnvolvente):
        self.d = d
        self.celdas: dict = {}
        self.avisos: list = []

    def put(self, hoja, celda, valor):
        self.celdas.setdefault(hoja, {})[celda] = valor
        return valor

    def get(self, hoja, celda):
        return self.celdas.get(hoja, {}).get(celda)

    def columna(self, letra, filas, hoja=H_CEV) -> list:
        return [self.get(hoja, f"{letra}{f}") for f in filas]

    def nombre(self, n):
        info = self.d.nombres.get(n) or {}
        hoja, celda = info.get("hoja"), info.get("celda")
        if hoja is None:
            self.avisos.append(f"!! nombre {n} sin resolver en las tablas de la plantilla")
            return NA
        if celda in self.celdas.get(hoja, {}):
            return self.celdas[hoja][celda]
        if info.get("formula"):
            self.avisos.append(f"{n} ({hoja}!{celda}) no se calcula aca: valor de la plantilla")
        return info.get("valor")


@dataclass(frozen=True)
class ResultadoEnvolvente:
    celdas: dict                   # {hoja: {celda: valor}}
    avisos: tuple
    nombres: dict = field(default_factory=dict, compare=False, repr=False)

    def valor(self, hoja, celda):
        return self.celdas.get(hoja, {}).get(celda)

    def nombre(self, n):
        info = self.nombres.get(n) or {}
        hoja, celda = info.get("hoja"), info.get("celda")
        if celda in self.celdas.get(hoja, {}):
            return self.celdas[hoja][celda]
        return info.get("valor")

    @property
    def absortividad_techo(self):
        """'CEV-CEVE'!AR150 (= '0. Datos Clima Motor'!C8, entrada de clima.bloques)."""
        return self.valor(H_CEV, "AR150")

    @property
    def categoria_muros(self):
        """'CEV-CEVE'!BW65 (= '0. Infiltraciones'!C8, entrada de perfil_uso)."""
        return self.valor(H_CEV, "BW65")

    def base_uso(self) -> dict:
        """Valores del caso base que usa perfil_uso (EntradasUso.base)."""
        return {"mat_marcos": self.nombre("base_mat_marcos"),
                "cierre_ventanas": self.nombre("base_cierre_ventanas"),
                "mat_puertas": self.nombre("base_mat_puertas"),
                "infiltracion_variable": self.nombre("base_infiltracion_variable"),
                "u_vidrio": self.nombre("base_U_vidrio")}


# --------------------------------------------------------------------------- utilidades
def _fila(L: Libro, f, hoja=H_CEV):
    return lambda col, v: L.put(hoja, f"{col}{f}", v)


def _rango(t: dict, f1, f2, c1, c2) -> Tabla:
    cols = [get_column_letter(c) for c in range(column_index_from_string(c1),
                                                 column_index_from_string(c2) + 1)]
    return Tabla(tuple(tuple(t.get(f"{c}{f}") for c in cols) for f in range(f1, f2 + 1)))


def _orientacion(d, azimut):
    """F: BUSCARV(azimut; '0. Tablas referencia'!B23:C39; 2; 0); 0 si no esta."""
    return iferror(buscarv(azimut, d.azimut, 2), 0.0)


def _orientacion_caso(d, F, caso: int):
    """CI: orientacion del caso (CH52:CR60 gira la vivienda en los casos base)."""
    return iferror(buscarv(F, d.orient_base, caso + 1), F)


def _muro_10_20(espesor):
    """AP: muro de 10 o 20 cm segun el espesor del muro solido."""
    return iferror(si(menor_igual(espesor, 15), 10.0, 20.0), 0.0)


def _espesor_pt(base: bool, b_esp, espesor):
    """SI(caso>2; base_espesor_aislante_PT; SI(TRUNCAR(e)>=20; 20; TRUNCAR(e)))."""
    tr = trunc(espesor)
    return si(base, copia(b_esp), si(mayor_igual(tr, 20), 20.0, tr))


def _marco_p05(categoria):
    return si(igual(categoria, "PVC"), "Madera", si(igual(categoria, "Fierro"), "Metalico", categoria))


def _fav(L, f, fav, base: bool):
    """BU..CD = SI(caso>2; 0; P..Y): las protecciones solares no existen en el caso base."""
    for col, v in zip(FAV_COPIA, fav):
        L.put(H_CEV, f"{col}{f}", 0.0 if base else copia(v))


# --------------------------------------------------------------------------- tablas y portada
@dataclass(frozen=True)
class Tablas:
    """'3. Tablas Envolvente' con lo calculado, y los rangos que se buscan."""
    celdas: dict
    puertas: Tabla          # C12:K23
    vidrios: Tabla          # C27:E42
    marcos: Tabla           # C46:E57
    muros: Tabla            # C61:H75
    muros_techos: Tabla     # C61:H82
    techos: Tabla           # C79:D82
    pisos: Tabla            # C87:M91
    pisos_aislacion: Tabla  # C88:L91


def tablas(e: EntradasEnvolvente, L: Libro) -> Tablas:
    t = dict(e.tablas)
    t["E27"] = L.put(H_TE, "E27", 0.87)
    for f in range(28, 32):
        t[f"E{f}"] = L.put(H_TE, f"E{f}", 0.89 * 0.87)
    vidrios = _rango(t, 27, 42, "C", "E")
    for f in range(12, 24):
        d_, f_, g_, h_ = (t.get(f"{c}{f}") for c in "DFGH")
        k = t[f"K{f}"] = L.put(H_TE, f"K{f}", iferror(buscarv(t.get(f"E{f}"), vidrios, 2), 0.0))
        t[f"I{f}"] = L.put(H_TE, f"I{f}", ar(lambda a, b, c, kk, g: a * (1 - b - c) + kk * b + g * c,
                                             d_, f_, h_, k, g_))
        t[f"J{f}"] = L.put(H_TE, f"J{f}", ar(lambda a, b, c, g: (a * (1 - b - c) + g * c) / (1 - b),
                                             d_, f_, h_, g_))
    return Tablas(t, _rango(t, 12, 23, "C", "K"), vidrios, _rango(t, 46, 57, "C", "E"),
                  _rango(t, 61, 75, "C", "H"), _rango(t, 61, 82, "C", "H"), _rango(t, 79, 82, "C", "D"),
                  _rango(t, 87, 91, "C", "M"), _rango(t, 88, 91, "C", "L"))


def portada(d: DatosEnvolvente, e: EntradasEnvolvente, L: Libro) -> None:
    """L9:N10 zonas de la comuna, O10 zona OGUC 2007 de la zona elegida, CH49 = caso."""
    v = {}
    for celda, k in (("L9", 17), ("M9", 18), ("N9", 19), ("L10", 20), ("M10", 21), ("N10", 22)):
        v[celda] = L.put(H_CEV, celda, buscarv(e.comuna, d.comunas, k - COL_COMUNA))
    i = None if es_error(e.zona) else posicion((v["L9"], v["M9"], v["N9"]), e.zona)
    o10 = NA if i is None else copia((v["L10"], v["M10"], v["N10"])[i])
    L.put(H_CEV, "O10", o10)
    L.put(H_OGUC, "C17", copia(o10))
    L.put(H_CEV, "CH49", float(e.caso))


def dimensiones(e: EntradasEnvolvente, L: Libro) -> None:
    for (area, alto), f in zip(e.pisos, FILAS_DIM):
        L.put(H_CEV, f"F{f}", ar(op.mul, area, alto))
    L.put(H_CEV, "D56", suma_rango([a for a, _ in e.pisos]))
    L.put(H_CEV, "F56", suma_rango(L.columna("F", FILAS_DIM)))


# --------------------------------------------------------------------------- caso base
def base_inicial(d: DatosEnvolvente, te: Tablas, L: Libro) -> None:
    """'0. Datos Arq Motor'!D59:D94 que no dependen de las ventanas."""
    def a(celda, v):
        return L.put(H_ARQ, celda, v)

    z = L.nombre("Zona_2007")
    a("D59", buscarv(z, d.oguc1, 4))
    a("D60", buscarv(z, d.oguc1, 2))
    a("D61", buscarv(z, d.oguc1, 6))
    a("D62", copia(te.celdas.get("D48")))
    a("D63", copia(te.celdas.get("E48")))
    a("D67", copia(te.celdas.get("I15")))
    for inf, ref in (("H44", "AX12"), ("H50", "AZ13"), ("H55", "BB12")):
        L.put(H_INF, inf, copia(d.tref.get(ref)))
    a("D73", copia(L.get(H_INF, "H50")))
    a("D74", copia(L.get(H_INF, "H55")))
    a("D75", copia(L.get(H_INF, "H44")))
    a("D81", trunc(max_args(ar(lambda u: 0.04 * (1 / u - 0.26) * 100, L.nombre("base_U_muro")), 0.0)))
    for celda, ref in (("D82", "EN12"), ("D84", "BJ12"), ("D85", "BL12"), ("D94", "EG12")):
        a(celda, copia(d.tref.get(ref)))


def base_vidrios(d: DatosEnvolvente, L: Libro) -> None:
    """D64:D66 y D76: U y FS del vidrio del caso base segun el % de ventanas OGUC 2007."""
    pv, z = L.nombre("porcentaje_ventanas_2007"), L.nombre("Zona_2007")
    d64 = L.put(H_ARQ, "D64", si(mayor(pv, buscarv(z, d.oguc3, 2)),
                                  si(mayor(pv, buscarv(z, d.oguc3, 3)), 2.4, 3.6), 5.8))
    L.put(H_ARQ, "D65", si(igual(d64, 5.8), 0.87, 0.77))
    L.put(H_ARQ, "D66", copia(L.get(H_OGUC, "Q18")))
    L.put(H_ARQ, "D76", si(igual(L.nombre("base_U_vidrio"), 5.8), "VS", "DVH"))


# --------------------------------------------------------------------------- muros y P04
def muros(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    b_u, b_esp = L.nombre("base_U_muro"), L.nombre("base_espesor_aislante_PT")
    eo21 = d.tref.get("EO21")
    prefijos = tuple(d.cev.get(f"{c}64") for c in ("AT", "AU", "AV"))
    for m, f in zip(e.muros, FILAS_MURO):
        p, n = _fila(L, f), m.nombre
        F = p("F", _orientacion(d, m.azimut))
        G = p("G", iferror(buscarv(n, te.muros, 2), ""))
        I = p("I", iferror(buscarv(n, te.muros, 3), ""))
        O = p("O", iferror(buscarv(n, te.muros, 6), ""))
        AD = p("AD", si(igual(I, 0), 0.0, 1.0))
        AE = p("AE", ar(op.mul, AD, m.area))
        p("AF", iferror(si(mayor(m.area, 0), ar(op.add, buscarv(n, te.muros, 4), buscarv(n, te.muros, 5)),
                           ""), 0.0))
        AG = p("AG", 0.0 if n is None else copia(b_u if base else I))
        p("AB", iferror(ar(op.mul, AG, AE), 0.0))
        AP = p("AP", _muro_10_20(buscarv(n, te.muros, 4)))
        AR = p("AR", iferror(buscarv(O, d.pos_aislacion, 2), 0.0))
        AQ = p("AQ", iferror(si(igual(AR, eo21), 0.0, _espesor_pt(base, b_esp, buscarv(n, te.muros, 5))), 0.0))
        AS = p("AS", si(igual(AP, 10), 2.0, 24.0))
        mat, col = buscarv(n, te.muros, 2), ar(op.add, AQ, AS)
        for pref, ct, cw, largo in zip(prefijos, ("AT", "AU", "AV"), ("AW", "AX", "AY"),
                                       (m.p01, m.p02, m.p03)):
            clave = p(ct, concatenar(pref, mat, AR))
            p(cw, ar(op.mul, iferror(buscarv(clave, d.pt_muros, col), 0.0), largo))
        p("BC", copia(G))
        p("BD", copia(m.area))
        p("CI", _orientacion_caso(d, F, e.caso))
    # material de los muros para infiltraciones (BV65:BW67) y espesor promedio (AF82)
    areas, mats = [m.area for m in e.muros], L.columna("G", FILAS_MURO)
    bv = [L.put(H_CEV, f"BV{f}", iferror(sumar_si_lista(areas, mats, d.cev.get(f"BW{f}")), ""))
          for f in (66, 67)]
    mx = max_rango(bv)
    bv65 = L.put(H_CEV, "BV65", si(igual(mx, 0), "", mx))
    t = Tabla(((bv[0], d.cev.get("BW66")), (bv[1], d.cev.get("BW67"))))
    L.put(H_CEV, "BW65", iferror(buscarv(bv65, t, 2), ""))
    L.put(H_CEV, "AF82", iferror(promedio_rango(L.columna("AF", FILAS_MURO)), 0.0))


def p04(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    b_esp, b_pos = L.nombre("base_espesor_aislante_PT"), L.nombre("base_pos_aislante_P04")
    eo21 = d.tref.get("EO21")
    for x, f in zip(e.p04, FILAS_P04):
        p = _fila(L, f)
        F = p("F", _orientacion(d, x.azimut))
        AP = p("AP", _muro_10_20(buscarv(x.muro, te.muros, 4)))
        AR = p("AR", iferror(buscarv(x.muro, te.muros, 6), ""))
        AQ = p("AQ", iferror(si(igual(AR, eo21), 0.0, _espesor_pt(base, b_esp, buscarv(x.muro, te.muros, 5))),
                             0.0))
        AS = p("AS", si(igual(AP, 10), 2.0, 24.0))
        pref, mat = d.cev.get(f"C{f}"), buscarv(x.muro, te.muros, 2)
        AT = p("AT", concatenar(pref, mat, x.elemento, b_pos if base else x.aislacion))
        p("AU", ar(op.mul, iferror(buscarv(AT, d.pt_p04, ar(op.add, AQ, AS)), 0.0), x.longitud))
        p("CI", _orientacion_caso(d, F, e.caso))


# --------------------------------------------------------------------------- puertas y ventanas
def puertas(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    b_a, b_u = L.nombre("base_A_puerta_traslucida"), L.nombre("base_U_puerta")
    for x, f in zip(e.puertas, FILAS_PUERTA):
        p = _fila(L, f)
        F = p("F", _orientacion(d, x.azimut))
        AB = p("AB", ar(op.mul, x.alto, x.ancho))
        AI = p("AI", iferror(buscarv(x.tipo, te.puertas, 4), 0.0))
        N = p("N", iferror(ar(op.mul, AB, AI), ""))
        AE = p("AE", iferror(buscarv(buscarv(x.tipo, te.puertas, 3), te.vidrios, 2), 0.0))
        AF = p("AF", copia(b_a) if base else copia(N))
        p("AG", iferror(ar(op.mul, AE, AF), 0.0))
        AH = p("AH", 0.0 if x.tipo is None else
               (copia(b_u) if base else iferror(buscarv(x.tipo, te.puertas, 7), 0.0)))
        p("AC", ar(op.mul, AB, AH))
        AJ = p("AJ", ar(op.sub, AB, AF))
        AK = p("AK", iferror(buscarv(x.tipo, te.puertas, 8), 0.0))
        p("AL", ar(op.mul, AK, AJ))
        BD = p("BD", ar(lambda k, l, n: k * l - n, x.alto, x.ancho, N))
        p("BE", ar(lambda v: v * 0.05, BD))
        _fav(L, f, x.fav, base)
        p("CH", copia(d.cev.get(f"C{f}")))
        p("CI", _orientacion_caso(d, F, e.caso))


def ventanas_areas(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    """Marco y areas de vidrio y marco (las necesita el % de ventanas OGUC 2007)."""
    b_um, b_fm = L.nombre("base_U_marco"), L.nombre("base_FM_ventana")
    for x, f in zip(e.ventanas, FILAS_VENTANA):
        p, vacia = _fila(L, f), x.tipo is None
        F = p("F", _orientacion(d, x.azimut))
        p("CI", _orientacion_caso(d, F, e.caso))
        p("AD", 0.0 if vacia else (copia(b_um) if base else iferror(buscarv(x.marco, te.marcos, 2), 0.0)))
        AE = p("AE", 0.0 if vacia else (copia(b_fm) if base else iferror(buscarv(x.marco, te.marcos, 3), 0.0)))
        AF = p("AF", iferror(ar(lambda k, l, fm: k * l * fm, x.alto, x.ancho, AE), 0.0))
        AG = p("AG", iferror(ar(lambda k, l, fm: k * l * (1 - fm), x.alto, x.ancho, AE), 0.0))
        p("AH", ar(op.add, AG, AF))


def ventanas(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    b_uv, b_uvt = L.nombre("base_U_vidrio"), L.nombre("base_U_vidrio_techo")
    b_fs, b_esp = L.nombre("base_FS_vidrio"), L.nombre("base_espesor_aislante_PT")
    b_marco, b_pos, b_ret = (L.nombre(n) for n in ("base_marco_P05", "base_pos_P05", "base_retorno_P05"))
    for x, f in zip(e.ventanas, FILAS_VENTANA):
        p, vacia = _fila(L, f), x.tipo is None
        g = lambda col, f=f: L.get(H_CEV, f"{col}{f}")
        AB = p("AB", 0.0 if vacia else
               (si(igual(x.azimut, "Horiz"), copia(b_uvt), copia(b_uv)) if base
                else iferror(buscarv(x.tipo, te.vidrios, 2), 0.0)))
        p("AC", 0.0 if vacia else (copia(b_fs) if base else iferror(buscarv(x.tipo, te.vidrios, 3), 0.0)))
        AF, AG, AH, AD = g("AF"), g("AG"), g("AH"), g("AD")
        p("AI", iferror(ar(lambda af, ab, ag, ad, ah: (af * ab + ag * ad) / ah, AF, AB, AG, AD, AH), 0.0))
        p("AJ", ar(op.mul, AF, AB))
        p("AK", ar(lambda k, l: 2 * (k + l), x.alto, x.ancho))
        p("AL", ar(op.mul, AD, AG))
        AX = p("AX", copia(x.elemento))
        horiz, marco = igual(g("CI"), "Horiz"), _marco_p05(x.categoria)
        mat = buscarv(AX, te.muros, 2)
        techo = concatenar("P05Tabique", marco, x.posicion, x.retorno)
        propio = si(horiz, techo, concatenar("P05", mat, marco, x.posicion, x.retorno))
        if f == FILAS_VENTANA[0]:
            del_base = si(horiz, techo, concatenar("P05", mat, b_marco, b_pos, b_ret))
        else:
            del_base = si(horiz, techo, concatenar("P05", mat, "Metalico", "Centrada", "Sin"))
        AZ = p("AZ", iferror(del_base, 0.0))
        AP = p("AP", iferror(AZ if base else propio, 0.0))
        AQ = p("AQ", iferror(si(horiz, 10.0, si(menor_igual(buscarv(AX, te.muros, 4), 15), 10.0, 20.0)), 0.0))
        AR = p("AR", iferror(_espesor_pt(base, b_esp, buscarv(AX, te.muros_techos, 5)), 0.0))
        AS = p("AS", si(igual(AQ, 10), 2.0, 24.0))
        AT = p("AT", iferror(buscarv(AP, d.pt_p05, ar(op.add, AR, AS)), 0.0))
        AU = p("AU", ar(lambda k, l: 2 * k + 2 * l, x.alto, x.ancho))
        p("AV", ar(op.mul, AU, AT))
        BD = p("BD", copia(AG))
        p("BE", ar(lambda v: v * 0.05, BD))
        _fav(L, f, x.fav, base)
        p("CH", copia(d.cev.get(f"C{f}")))


# --------------------------------------------------------------------------- OGUC 2007
def oguc(d: DatosEnvolvente, e: EntradasEnvolvente, L: Libro) -> None:
    for r in range(9, 16):
        for c_u, c_r in (("C", "D"), ("E", "F"), ("G", "H")):
            L.put(H_OGUC, f"{c_r}{r}", ar(lambda u: 1 / u, d.oguc_hoja.get(f"{c_u}{r}")))
    col = L.columna
    c18 = L.put(H_OGUC, "C18", suma_rango(col("AF", FILAS_VENTANA) + col("AF", FILAS_PUERTA)))
    L.put(H_OGUC, "Q18", si(mayor(L.nombre("Zona_2007"), 2), 3.6, 5.8))
    c19 = L.put(H_OGUC, "C19", suma_rango(col("AG", FILAS_VENTANA)))
    c20 = L.put(H_OGUC, "C20", ar(op.sub, suma_rango([m.area for m in e.muros] + col("AB", FILAS_PUERTA)),
                                  suma_rango(col("N", FILAS_PUERTA))))
    L.put(H_OGUC, "C21", ar(lambda a, b, s: (a + b) / s, c19, c18, suma_rango((c18, c19, c20))))


# --------------------------------------------------------------------------- techos y pisos
def techos(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool) -> None:
    b_u, b_abs = L.nombre("base_U_techo"), L.nombre("base_absortividad_techo")
    c79 = te.celdas.get("C79")
    aq = []
    for x, f in zip(e.techos, FILAS_TECHO):
        p = _fila(L, f)
        H = p("H", iferror(buscarv(x.tipo, te.techos, 2), ""))
        AC = p("AC", 0.0 if x.tipo is None else (si(igual(x.tipo, c79), 0.0, copia(b_u)) if base else H))
        AD = p("AD", si(igual(H, 0), 0.0, 1.0))
        AE = p("AE", ar(op.mul, AD, x.area))
        p("AB", iferror(ar(op.mul, AE, AC), 0.0))
        AP = p("AP", copia(b_abs) if base else
               iferror(min_args(buscarv(x.color_k, d.absortividad, 2), buscarv(x.color_l, d.absortividad, 2)), 0.0))
        aq.append(p("AQ", ar(op.mul, AP, x.area)))
        p("BC", copia(x.categoria))
        p("BD", copia(x.area))
    L.put(H_CEV, "AR150", iferror(ar(op.truediv, suma_rango(aq), suma_rango([x.area for x in e.techos])), 0.0))


def _ls(v: dict, put):
    """Ls [W/K] de un piso contra terreno (NCh3117, filas 8-36). v: valores de las filas de entrada."""
    terreno, area, perim, w, lam = v[5], v[6], v[7], v[9], v[16]
    b = put(8, si(terreno, ar(lambda a, p: a / (0.5 * p), area, perim), 0.0))
    rf = put(14, si(igual(v[12], 0), 0.0, ar(op.truediv, v[13], v[12])))
    dt = put(15, ar(lambda s, l, w_: s * l + w_, suma_rango((v[10], v[11], rf)), lam, w))
    pi = put(17, math.pi)
    uo = put(18, si(terreno, si(menor(dt, b),
                                ar(lambda l, p, b_, d_: (2 * l / (p * b_ + d_)) * math.log(p * b_ / d_ + 1),
                                   lam, pi, b, dt),
                                ar(lambda l, b_, d_: l / (0.457 * b_ + d_), lam, b, dt)), 0.0))
    dv = put(23, si(igual(v[22], 0), 0.4, v[22]))
    sin_vertical = o_(igual(v[20], 0), igual(v[21], 0))
    lv = put(24, si(sin_vertical, 1.63, v[20]))
    ev = put(25, si(sin_vertical, w, v[21]))
    rh = put(29, si(igual(v[27], 0), 0.0, ar(lambda e_, l2, l: e_ / l2 - e_ / l, v[27], v[26], lam)))
    rv = put(30, ar(lambda e_, l2, l: e_ / l2 - e_ / l, ev, lv, lam))
    d_h = put(31, ar(op.mul, rh, lam))
    d_v = put(32, ar(op.mul, rv, lam))
    dy_h = put(33, si(igual(v[27], 0), 0.0, ar(
        lambda l, p, D, d_, x: -(l / p) * (math.log(D / d_ + 1) - math.log(D / (x + d_) + 1)),
        lam, pi, v[28], dt, d_h)))
    dy_v = put(34, ar(
        lambda l, p, D, d_, x: -(l / p) * (math.log((2 * D / d_) + 1) - math.log((2 * D / (x + d_)) + 1)),
        lam, pi, dv, dt, d_v))
    dy = put(35, min_rango((dy_h, dy_v)))
    return put(36, ar(lambda a, u, p, y: a * u + p * y, area, uo, perim, dy))


def nch3117(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro) -> list:
    w = ar(lambda x: x / 100, L.get(H_CEV, "AF82"))
    m12 = d.tref.get("M12")
    col_a = {r: d.piso.get(f"A{r}") for r in FILAS_TABLA_PISO}
    ls = []
    for x, cp, cb in zip(e.pisos_env, COLS_PROPUESTO, COLS_BASE):
        def pp(r, v, c=cp):
            return L.put(H_PISO, f"{c}{r}", v)

        def pb(r, v, c=cb):
            return L.put(H_PISO, f"{c}{r}", v)

        tipo = pp(3, copia(x.tipo))
        terreno = pp(5, si(igual(x.condicion, m12), True, False))
        v = {5: terreno, 6: pp(6, si(terreno, copia(x.area), 0.0)),
             7: pp(7, si(terreno, copia(x.perimetro), 0.0)), 9: pp(9, w)}
        for r in (10, 11, 16):
            v[r] = d.piso.get(f"{cp}{r}")
        for r in (12, 20, 26):
            v[r] = pp(r, iferror(buscarv(tipo, te.pisos_aislacion, col_a[r]), 0.0))
        for r in (13, 21, 27):
            v[r] = pp(r, iferror(ar(lambda y: y / 100, buscarv(tipo, te.pisos_aislacion, col_a[r])), 0.0))
        for r in (22, 28):
            v[r] = pp(r, ar(lambda y: y / 100, iferror(buscarv(tipo, te.pisos_aislacion, col_a[r]), 0.0)))
        propuesto = _ls(v, pp)
        vb = {5: pb(5, v[5]), 6: pb(6, copia(v[6])), 7: pb(7, copia(v[7])), 9: pb(9, copia(v[9]))}
        for r in (10, 11, 12, 13, 16, 20, 21, 22, 26, 27, 28):
            vb[r] = d.piso.get(f"{cb}{r}")
        ls.append((propuesto, _ls(vb, pb)))
    return [L.put(H_PISO, f"C{f}", lb if e.caso > 2 else lp) for (lp, lb), f in zip(ls, range(40, 44))]


def pisos(d: DatosEnvolvente, e: EntradasEnvolvente, te: Tablas, L: Libro, base: bool, ls: list) -> None:
    b_u, c87, m11 = L.nombre("base_U_PV"), te.celdas.get("C87"), d.tref.get("M11")
    for x, f, ls_f in zip(e.pisos_env, FILAS_PISO, ls):
        p = _fila(L, f)
        H = p("H", iferror(buscarv(x.tipo, te.pisos, 2), ""))
        p("R", si(o_(igual(x.tipo, c87), igual(x.perimetro, 0)), 0.0, copia(ls_f)))
        AC = p("AC", 0.0 if x.tipo is None else (si(igual(x.tipo, c87), 0.0, copia(b_u)) if base else H))
        AD = p("AD", si(igual(H, 0), 0.0, 1.0))
        ventilado = igual(x.condicion, m11)
        AE = p("AE", si(ventilado, ar(op.mul, AD, x.area), 0.0))
        p("AB", si(ventilado, ar(op.mul, AE, AC), 0.0))
        p("BC", copia(x.categoria))
        p("BD", copia(x.area))


# --------------------------------------------------------------------------- resumen
def resumen(d: DatosEnvolvente, e: EntradasEnvolvente, L: Libro) -> None:
    """'CEV-CEVE' filas 169-178: areas, U y puentes por orientacion."""
    c, s = L.columna, sumar_si_lista
    m_ci, m_h = c("CI", FILAS_MURO), [m.area for m in e.muros]
    m_ae, m_ab = c("AE", FILAS_MURO), c("AB", FILAS_MURO)
    m_pt = [c(x, FILAS_MURO) for x in ("AW", "AX", "AY")]
    p4_ci, p4_au = c("CI", FILAS_P04), c("AU", FILAS_P04)
    pu_ci, pu_aj, pu_af, pu_ag, pu_al = (c(x, FILAS_PUERTA) for x in ("CI", "AJ", "AF", "AG", "AL"))
    v_ci, v_ag, v_af, v_aj, v_al, v_av = (c(x, FILAS_VENTANA) for x in ("CI", "AG", "AF", "AJ", "AL", "AV"))
    for f in FILAS_ORIENTACION:
        p, k = _fila(L, f), d.cev.get(f"C{f}")
        D = mas(s(m_h, m_ci, k), s(pu_aj, pu_ci, k), s(v_ag, v_ci, k))
        E = mas(s(m_ae, m_ci, k), s(pu_aj, pu_ci, k), s(v_ag, v_ci, k))
        if f == FILAS_ORIENTACION[0]:          # techo: suma los techos y su U*A
            D = mas(D, suma_rango([t.area for t in e.techos]))
            E = mas(E, suma_rango(c("AE", FILAS_TECHO)))
            F = iferror(ar(op.truediv, suma_rango(c("AB", FILAS_TECHO)), E), 0.0)
        else:
            F = iferror(ar(op.truediv, mas(s(m_ab, m_ci, k), s(pu_al, pu_ci, k), s(v_al, v_ci, k)), E), 0.0)
            pts = [p(col, s(lista, m_ci, k)) for col, lista in zip("KLM", m_pt)]
            pts.append(p("N", s(p4_au, p4_ci, k)))
            pts.append(p("O", s(v_av, v_ci, k)))
            p("P", suma_rango(pts))
        p("D", D)
        p("E", E)
        p("F", F)
        H = p("H", mas(s(pu_af, pu_ci, k), s(v_af, v_ci, k)))
        p("I", iferror(ar(op.truediv, mas(s(pu_ag, pu_ci, k), s(v_aj, v_ci, k)), H), 0.0))
    L.put(H_CEV, "D178", suma_rango([x.area for x in e.pisos_env]))
    e178 = L.put(H_CEV, "E178", suma_rango(c("AE", FILAS_PISO)))
    L.put(H_CEV, "F178", iferror(ar(op.truediv, suma_rango(c("AB", FILAS_PISO)), e178), 0.0))
    L.put(H_CEV, "P178", suma_rango(c("R", FILAS_PISO)))


def resumen_motor(d: DatosEnvolvente, e: EntradasEnvolvente, L: Libro) -> None:
    """'0. Datos Arq Motor': lo que lee el motor (Calculo!B2:O29)."""
    def a(celda, v):
        return L.put(H_ARQ, celda, v)

    a("C4", si(igual(e.recuperador, d.tref.get("EQ17")), "Si", "No"))
    a("C5", ar(lambda x: x / 100, e.eficiencia_recuperador))
    c32 = a("C32", si(igual(ar(lambda c: (-1.0) ** c, float(e.caso)), 1), "No", "Si"))
    a("C6", copia(c32))
    for i, f in enumerate(range(169, 179)):
        r = 8 + i
        for c_m, c_c in (("G", "D"), ("H", "E"), ("I", "F")):
            a(f"{c_m}{r}", copia(L.get(H_CEV, f"{c_c}{f}")))
        if f <= 177:
            a(f"K{r}", copia(L.get(H_CEV, f"H{f}")))
            a(f"L{r}", copia(L.get(H_CEV, f"I{f}")))
        if f >= 170:
            a(f"N{r}", copia(L.get(H_CEV, f"P{f}")))
    for i, ((area, alto), f) in enumerate(zip(e.pisos, FILAS_DIM)):
        a(f"G{22 + i}", copia(area))
        a(f"H{22 + i}", copia(alto))
        a(f"I{22 + i}", copia(L.get(H_CEV, f"F{f}")))
    a("G26", copia(L.get(H_CEV, "D56")))
    a("I26", copia(L.get(H_CEV, "F56")))


# --------------------------------------------------------------------------- todo
def calcular(d: DatosEnvolvente, e: EntradasEnvolvente) -> ResultadoEnvolvente:
    L = Libro(d)
    base = e.caso > 2
    portada(d, e, L)
    te = tablas(e, L)
    dimensiones(e, L)
    base_inicial(d, te, L)
    muros(d, e, te, L, base)
    p04(d, e, te, L, base)
    puertas(d, e, te, L, base)
    ventanas_areas(d, e, te, L, base)
    oguc(d, e, L)
    base_vidrios(d, L)
    ventanas(d, e, te, L, base)
    techos(d, e, te, L, base)
    ls = nch3117(d, e, te, L)
    pisos(d, e, te, L, base, ls)
    resumen(d, e, L)
    resumen_motor(d, e, L)
    return ResultadoEnvolvente(L.celdas, tuple(dict.fromkeys(L.avisos)), dict(d.nombres))
