# -*- coding: utf-8 -*-
"""
Perfil de uso, infiltracion y ventilacion de la ficha 01 en Python.

Traduce, con el orden de operaciones de Excel, las hojas:
  '0. Infiltraciones'  permeabilidad de la envolvente (pisos segun la masa de
                       los muros, ventanas y puertas a 100 Pa llevadas a 50 Pa),
                       ductos y celosias, correccion por zona (K1..K4) y las
                       renovaciones por infiltracion de cada mes (D29:D40) [1/h].
  '0. Ventilacion'     flujo minimo (Fmin = '0. Perfil de Uso'!Q2), RACE, la
                       opcion segun el recuperador y el control (invierno en la
                       columna C, verano en la M) y el valor de cada mes (W2:W13).
  '0. Perfil de Uso'   cabecera (usuarios = dormitorios + 1, Fmin) y, por mes y
                       hora (filas 11-298): ganancias de usuarios, iluminacion y
                       equipos [W/m2] (desde '4. Perfil de Uso') y renovaciones:
                       infiltracion J, ventilacion K, diurna L, nocturna M, total N.
  '4. Perfil de Uso'   perfiles horarios: usuarios (perfil CHILE x aporte de dia
                       o de noche), iluminacion (se apaga si la iluminancia de
                       '0.FAV Calculos'!JE14:JP37 alcanza U7) y equipos (tabla).
  '0. Datos Clima Motor'  K, L, M (= E, F, G), X (= N - J) y E23 (infiltracion del
                       mes = J de la hora 0).

Lo que viene de otros modulos entra en EntradasUso: datos de 'CEV-CEVE', zona
de clima (clima.zona_clima), temporada de cada mes ('0. Inercia Termica'!
X102:X113), iluminancia interior ('0.FAV Calculos'!JE14:JP37, radiacion) y
los valores del caso base (nombres definidos base_*, en '0. Datos Arq
Motor'; los calcula envolvente.py: ResultadoEnvolvente.base_uso()).
base_vidrio_infiltraciones = SI(base_U_vidrio=5,8;"VS";"DVH") se calcula aca.
En la plantilla vacia valen #DIV/0!: no son constantes.

Particularidades que se replican (no se corrigen):
  - '0. Ventilacion'!B34 = MAX(C5;C7), pero L34 = L32: la sexta opcion de
    invierno y de verano se calcula distinto.
  - '0. Datos Clima Motor'!X en enero: N de la fila siguiente menos J
    (X10 = N12 - J11; X33 usa N35, que es febrero hora 0).
  - La fila de la hora 24 repite la hora 0 (K34 = K10, X34 = X10).
"""
from __future__ import annotations

import math
import operator as op
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

from .datos import DatosClima, DatosUso, ubicacion
from .excel import (
    NA, REF, VALOR, Tabla, ar, buscarv, concatenar, copia, distinto, elegir, es_error, iferror,
    igual, large, max_rango, mayor, mayor_igual, menor, menor_igual, o_, posicion, si,
    suma_rango, sumar_si_lista, y_,
)

POT50 = math.pow(50, 0.65)      # POWER(50,0.65)
POT100 = math.pow(100, 0.65)    # POWER(100,0.65)
HORAS = 24
MESES = 12
FILAS = HORAS * MESES
FILA_PDU = 11                   # '0. Perfil de Uso': primera fila del horario
FILA_P4 = 12                    # '4. Perfil de Uso': fila de la hora 0
COL_ILUM_FAV = 265              # '0.FAV Calculos'!JE: iluminancia de enero (JE..JP)
H_INF = "0. Infiltraciones"
H_VEN = "0. Ventilacion"
H_PDU = "0. Perfil de Uso"
H_P4 = "4. Perfil de Uso"
H_DCM = "0. Datos Clima Motor"
# valores del caso base que entran al modulo: clave -> nombre definido de la ficha
NOMBRES_BASE = {"mat_marcos": "base_mat_marcos", "cierre_ventanas": "base_cierre_ventanas",
                "mat_puertas": "base_mat_puertas",
                "infiltracion_variable": "base_infiltracion_variable",
                "u_vidrio": "base_U_vidrio"}
NOMBRE_VIDRIO = "base_vidrio_infiltraciones"
U_VIDRIO_SIMPLE = 5.8           # formula de base_vidrio_infiltraciones


# --------------------------------------------------------------------------- entradas
@dataclass(frozen=True)
class Muro:
    categoria: object      # 'CEV-CEVE'!G66:G81 (masa del muro)
    area: object           # H66:H81 [m2]


@dataclass(frozen=True)
class Ventana:
    marco: object          # 'CEV-CEVE'!M103:M122 (materialidad del marco)
    cierre: object         # H103:H122 (tipo de cierre)
    u_vidrio: object       # AB103:AB122 (U < 5 -> "DVH", si no "VS")
    area: object           # AH103:AH122 [m2]


@dataclass(frozen=True)
class Puerta:
    material: object       # 'CEV-CEVE'!H96:H98
    area: object           # AB96:AB98 [m2]


@dataclass(frozen=True)
class EntradasUso:
    caso: int
    dormitorios: object            # 'CEV-CEVE'!E11
    superficie: object             # D56 [m2]
    volumen: object                # F56 [m3]
    infiltracion_variable: object  # F217
    recuperador: object            # E227
    control_ventilacion: object    # F232
    ventilacion_propuesta: object  # F234 [1/h]
    area_pisos: tuple              # D52:D54 [m2] (piso 1, pisos 2+)
    volumen_pisos: tuple           # F52:F54 [m3]
    categoria_muros: object        # BW65
    muros: tuple                   # 16 Muro (filas 66-81)
    ventanas: tuple                # 20 Ventana (filas 103-122)
    puertas: tuple                 # 3 Puerta (filas 96-98)
    infiltracion_ensayo: object    # F219 [1/h a 50 Pa]
    ductos: object                 # F221 [un]
    celosias: object               # F223 [un]
    zona_clima: object             # '0. Clima'!M2 (clima.zona_clima)
    temporada: tuple               # '0. Inercia Termica'!X102:X113 ("V" verano / "I" invierno)
    iluminancia: tuple             # '0.FAV Calculos'!JE14:JP37, [mes][hora]
    base: dict | None = None       # valores del caso base (claves de NOMBRES_BASE)


# --------------------------------------------------------------------------- resultados
@dataclass(frozen=True)
class Infiltracion:
    rah_mes: tuple             # D29:D40 [1/h]
    permeabilidad: object      # D19 [1/h a 50 Pa]
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Ventilacion:
    por_mes: tuple             # W2:W13 [1/h]
    opcion: object             # C21 (segun el recuperador)
    control: object            # C22 (1 sin control, 2 con control)
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Cabecera:
    usuarios: object           # D2
    superficie: object         # D3
    volumen: object            # K2
    usuarios_dia: object       # D5 [W/m2]
    usuarios_noche: object     # E5 [W/m2]
    infiltracion_variable: object  # K5
    fmin: object               # Q2 [1/h]
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Perfil4:
    tabla: Tabla               # B12:AN35
    infiltracion_mes: tuple    # AS10:BD10
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class PerfilUso:
    usuarios: tuple            # E11:E298 [W/m2]
    iluminacion: tuple         # F
    equipos: tuple             # G
    total: tuple               # H
    infiltracion: tuple        # J [1/h]
    ventilacion: tuple         # K
    diurna: tuple              # L
    nocturna: tuple            # M
    renovaciones: tuple        # N
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Motor:
    usuarios: tuple            # K, [mes][hora 0..24]
    iluminacion: tuple         # L
    equipos: tuple             # M
    renovaciones: tuple        # X
    infiltracion_mes: tuple    # E23 de cada bloque
    celdas: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ResultadoUso:
    infiltracion: Infiltracion
    cabecera: Cabecera
    ventilacion: Ventilacion
    perfil4: Perfil4
    perfil: PerfilUso
    motor: Motor
    base: dict = field(default_factory=dict, compare=False, repr=False)   # {hoja: {celda: valor}}

    def celdas(self) -> dict:
        """{hoja: {celda: valor}} de todo lo calculado (para validar contra Excel)."""
        out = {H_INF: self.infiltracion.celdas, H_VEN: self.ventilacion.celdas,
               H_PDU: {**self.cabecera.celdas, **self.perfil.celdas},
               H_P4: self.perfil4.celdas, H_DCM: self.motor.celdas}
        for hoja, cs in self.base.items():
            out.setdefault(hoja, {}).update(cs)
        return out


# --------------------------------------------------------------------------- caso base
def bases(d: DatosUso, e: EntradasUso) -> tuple[dict, dict]:
    """(valores del caso base, celdas calculadas). Los de e.base mandan sobre la plantilla."""
    v = {k: (d.nombres.get(n) or {}).get("valor") for k, n in NOMBRES_BASE.items()}
    v.update(e.base or {})
    celdas: dict = {}
    if (e.base or {}).get("u_vidrio") is None and ubicacion(d.nombres.get("base_U_vidrio")) is None:
        vidrio = copia((d.nombres.get(NOMBRE_VIDRIO) or {}).get("valor"))
    else:
        vidrio = si(igual(v["u_vidrio"], U_VIDRIO_SIMPLE), "VS", "DVH")
    v["vidrio"] = vidrio
    u = ubicacion(d.nombres.get(NOMBRE_VIDRIO))
    if u:
        celdas.setdefault(u[0], {})[u[1]] = vidrio
    return v, celdas


# --------------------------------------------------------------------------- '0. Infiltraciones'
def infiltracion(d: DatosUso, e: EntradasUso, b: dict) -> Infiltracion:
    base = e.caso > 2
    c: dict = {}
    # pisos: area y volumen del piso 1 y de los demas (C3:E5)
    a1, v1 = copia(e.area_pisos[0]), copia(e.volumen_pisos[0])
    a2 = ar(op.add, e.area_pisos[1], e.area_pisos[2])
    v2 = ar(op.add, e.volumen_pisos[1], e.volumen_pisos[2])
    area, volumen = suma_rango((a1, a2)), suma_rango((v1, v2))
    c.update(C3=a1, E3=v1, C4=a2, E4=v2, C5=area, E5=volumen)

    # masa de los muros: fraccion de area de cada categoria; cuentan las dos mayores (B8:D12)
    cats = (copia(e.categoria_muros), d.cat_intermedio, d.cat_pesado)
    area_cat = tuple(sumar_si_lista(tuple(m.area for m in e.muros),
                                    tuple(m.categoria for m in e.muros), k) for k in cats)
    total_cat = suma_rango(area_cat)
    frac = tuple(ar(op.truediv, a, total_cat) for a in area_cat)
    t_frac = Tabla(tuple(zip(frac, cats)))
    frac1 = large(frac, 1)
    cat1 = buscarv(frac1, t_frac, 2)
    segunda = large(frac, 2)
    frac2 = si(mayor(segunda, 0.2), segunda, 0.0)
    cat2 = si(igual(frac2, 0), 0.0, buscarv(frac2, t_frac, 2))
    for i, f in enumerate((8, 9, 10)):
        c[f"B{f}"], c[f"D{f}"] = frac[i], area_cat[i]
    c.update(C8=cats[0], C11=frac1, D11=cat1, C12=frac2, D12=cat2)

    # permeabilidad de los pisos segun la masa de los muros (L3:R3)
    def pi_masa(cat, fr):
        return iferror(ar(op.mul, buscarv(cat, d.tabla_pi_materialidad, 2), fr), 0.0)

    pi_pisos = ar(op.add, pi_masa(cat1, frac1), pi_masa(cat2, frac2))
    flujo_n = ar(op.mul, area, pi_pisos)
    coef = ar(op.truediv, flujo_n, POT50)
    flujo_pisos = ar(op.mul, coef, POT50)
    c.update(L3=pi_pisos, M3=area, N3=flujo_n, O3=coef, P3=flujo_pisos, R3=flujo_pisos)

    # ventanas (filas 6-25): tipo = marco & cierre & vidrio; permeabilidad a 100 Pa -> 50 Pa
    flujos_v = []
    for i, v in enumerate(e.ventanas):
        f = 6 + i
        if base:
            marco, cierre = copia(b["mat_marcos"]), copia(b["cierre_ventanas"])
            vidrio = copia(b["vidrio"])
        else:
            marco, cierre = copia(v.marco), copia(v.cierre)
            vidrio = si(menor(v.u_vidrio, 5), "DVH", "VS")
        tipo = concatenar(marco, cierre, vidrio)
        pi = iferror(buscarv(tipo, d.tabla_pi_ventanas, 2), 0.0)
        a = copia(v.area)
        f100 = ar(op.mul, pi, a)
        k = ar(op.truediv, f100, POT100)
        f50 = ar(op.mul, k, POT50)
        flujos_v.append(f50)
        c.update({f"H{f}": marco, f"I{f}": cierre, f"J{f}": vidrio, f"K{f}": tipo, f"L{f}": pi,
                  f"M{f}": a, f"N{f}": f100, f"O{f}": k, f"P{f}": f50})

    # puertas (filas 28-30)
    flujos_p = []
    for i, pu in enumerate(e.puertas):
        f = 28 + i
        mat = copia(b["mat_puertas"]) if base else copia(pu.material)
        pi = iferror(buscarv(mat, d.tabla_pi_puertas, 2), 0.0)
        a = copia(pu.area)
        f100 = ar(op.mul, a, pi)
        k = ar(op.truediv, f100, POT100)
        f50 = ar(op.mul, k, POT50)
        flujos_p.append(f50)
        c.update({f"K{f}": mat, f"L{f}": pi, f"M{f}": a, f"N{f}": f100, f"O{f}": k, f"P{f}": f50})

    # permeabilidad total (D15:D19) [1/h a 50 Pa]
    total_v, total_p = suma_rango(flujos_v), suma_rango(flujos_p)
    teorica = ar(op.truediv, suma_rango((flujo_pisos, total_v, total_p)), volumen)
    f219 = copia(e.infiltracion_ensayo)
    ensayo = si(distinto(f219, 0), f219, 0.0)
    ductos, celosias = copia(e.ductos), copia(e.celosias)
    perm = ar(lambda p, nd, nc, vol: p + 250 * math.sqrt(nd) / vol + 250 * math.sqrt(1.5 * nc) / vol,
              si(igual(ensayo, 0), teorica, ensayo), ductos, celosias, volumen)
    c.update(R25=total_v, R30=total_p, D15=teorica, D16=ensayo, D17=ductos, D18=celosias, D19=perm)

    # correccion por zona (C21:C27) y renovaciones de cada mes (D29:D40)
    zona = copia(e.zona_clima)
    k1 = buscarv(zona, d.tabla_k_zona, 2)
    k2 = si(igual(a2, 0), 1.0, buscarv(zona, d.tabla_k_zona, 3))
    k3 = si(igual(perm, 0), 1.0, buscarv(zona, d.tabla_k_zona, 4))
    k4_ver = buscarv(zona, d.tabla_k_zona, 5)
    k4_inv, k50 = copia(d.k4_invierno), copia(d.k50_a_rah)
    c.update(C21=zona, C22=k1, C23=k2, C24=k3, C26=k4_ver)
    rah = []
    for i in range(MESES):
        temp = copia(e.temporada[i])
        k4 = si(igual(temp, "V"), k4_ver, k4_inv)
        rah.append(ar(lambda p, k, x1, x2, x3, x4: p / k * x1 * x2 * x3 * x4,
                      perm, k50, k1, k2, k3, k4))
        c[f"D{29 + i}"], c[f"F{29 + i}"] = rah[-1], temp
    return Infiltracion(tuple(rah), perm, c)


# --------------------------------------------------------------------------- '0. Perfil de Uso' (cabecera)
def cabecera(d: DatosUso, e: EntradasUso, b: dict) -> Cabecera:
    d1 = copia(e.dormitorios)
    usuarios = ar(lambda a: a + 1, d1)
    volumen = copia(e.volumen)
    superficie = copia(e.superficie)
    dia = ar(lambda u, a, s: u * a / s, usuarios, d.aporte_personas_dia, superficie)
    noche = ar(lambda u, a, s: u * a / s, usuarios, d.aporte_personas_noche, superficie)
    k5 = (copia(e.infiltracion_variable) if e.caso in (1, 2)
          else copia(b["infiltracion_variable"]))
    fmin = ar(lambda u, k3, v, s, k4: (u * k3 * 3600 / 1000) / v + (s * k4 * 3600 / 1000) / v,
              usuarios, d.vent_usuario, volumen, superficie, d.vent_superficie)
    c = {"D1": d1, "D2": usuarios, "K2": volumen, "Q2": fmin, "D3": superficie,
         "D5": dia, "E5": noche, "K5": k5}
    return Cabecera(usuarios, superficie, volumen, dia, noche, k5, fmin, c)


# --------------------------------------------------------------------------- '0. Ventilacion'
def _lado(d, inf, fmin, recuperador, control, propuesta, sexta_copia: bool) -> dict:
    """Una columna de '0. Ventilacion' (C invierno / M verano). sexta_copia: L34 = L32."""
    opcion = buscarv(recuperador, d.tabla_ventilacion, 2)
    ctrl = si(igual(control, "No"), 1.0, 2.0)
    f135 = ar(lambda f: 1.35 * f, fmin)
    x = ar(op.truediv, inf, fmin)
    race = ar(lambda a, f: (0.9856 - 0.0014 * a + 0.5785 * a * a) * f, x, fmin)
    op1 = si(mayor(inf, f135), inf, f135)
    op2 = si(menor(inf, ar(lambda f: 0.65 * f, fmin)), ar(lambda a: 0.8 * a, op1), op1)
    op3 = si(menor(race, op1), race, op1)
    op6 = op3 if sexta_copia else max_rango((inf, fmin))
    sin_control = (op1, op2, op3, op3, op3, op6)
    con_control = sin_control              # la columna "con control" copia la "sin control"
    elegidas = tuple(si(igual(ctrl, 1), a, b) for a, b in zip(sin_control, con_control))
    flujo = elegir(opcion, *elegidas)
    propuesta_max = max_rango((propuesta, inf))
    final = si(igual(propuesta, 0), flujo, propuesta_max)
    return {"opcion": opcion, "ctrl": ctrl, "f135": f135, "x": x, "race": race,
            "sin_control": sin_control, "con_control": con_control, "elegidas": elegidas,
            "flujo": flujo, "propuesta_max": propuesta_max, "final": final}


def ventilacion(d: DatosUso, e: EntradasUso, inf: Infiltracion, fmin) -> Ventilacion:
    inv_inf, ver_inf = copia(inf.rah_mes[6]), copia(inf.rah_mes[0])   # D35 julio, D29 enero
    recup, control = copia(e.recuperador), copia(e.control_ventilacion)
    prop, fmin = copia(e.ventilacion_propuesta), copia(fmin)
    inv = _lado(d, inv_inf, fmin, recup, control, prop, False)
    ver = _lado(d, ver_inf, fmin, recup, control, prop, True)
    temp = tuple(copia(t) for t in e.temporada)
    w = tuple(si(igual(t, "V"), ver["final"], inv["final"]) for t in temp)
    c = {"C5": inv_inf, "M5": ver_inf, "C7": fmin, "M7": fmin, "B10": recup, "L10": recup,
         "B13": control, "L13": control, "H17": prop, "R17": prop}
    for lado, (cv, cs, cd, ce) in ((inv, ("C", "B", "D", "E")), (ver, ("M", "L", "N", "O"))):
        c.update({f"{cv}21": lado["opcion"], f"{cv}22": lado["ctrl"], f"{cv}24": lado["f135"],
                  f"{cv}25": lado["x"], f"{cv}26": lado["race"], f"{ce}29": lado["flujo"],
                  f"{cv}42": lado["flujo"], f"{cv}43": lado["propuesta_max"],
                  f"{cv}44": lado["final"]})
        for i in range(6):
            f = 29 + i
            c[f"{cs}{f}"] = lado["sin_control"][i]
            c[f"{cv}{f}"] = lado["con_control"][i]
            c[f"{cd}{f}"] = lado["elegidas"][i]
    for i in range(MESES):
        c[f"W{2 + i}"], c[f"X{2 + i}"] = w[i], temp[i]
    return Ventilacion(w, inv["opcion"], inv["ctrl"], c)


# --------------------------------------------------------------------------- '4. Perfil de Uso'
def _luz(lux, d: DatosUso, encendida, noche: bool):
    """P12:AA35: se apaga si la iluminancia alcanza el minimo; error -> 0 de noche, U5 de dia."""
    return iferror(si(mayor_igual(lux, d.lux_min), 0.0, encendida), 0.0 if noche else encendida)


def perfil4(d: DatosUso, e: EntradasUso, cab: Cabecera, inf: Infiltracion) -> Perfil4:
    h6, h7 = cab.usuarios_dia, cab.usuarios_noche
    u5, u6 = copia(d.ilum_dia), copia(d.ilum_noche)
    usuarios = tuple(ar(op.mul, h7 if d.p4_noche_usuarios[r] else h6, d.p4_chile[r])
                     for r in range(HORAS))
    luz = tuple(tuple(_luz(e.iluminancia[j][r], d, u6 if d.p4_noche_iluminacion[r] else u5,
                           d.p4_noche_iluminacion[r]) for r in range(HORAS)) for j in range(MESES))
    inf_mes = tuple(copia(x) for x in inf.rah_mes)
    filas = tuple((d.p4_horas[r],) + (usuarios[r],) * MESES + (d.p4_o[r],)
                  + tuple(luz[j][r] for j in range(MESES)) + (d.p4_ab[r],)
                  + tuple(d.p4_equipos[r]) for r in range(HORAS))
    c = {"U5": u5, "H6": h6, "U6": u6, "H7": h7}
    for j in range(MESES):
        c[f"{get_column_letter(45 + j)}10"] = inf_mes[j]                  # AS10:BD10
    for r in range(HORAS):
        f = FILA_P4 + r
        for j in range(MESES):
            c[f"{get_column_letter(3 + j)}{f}"] = usuarios[r]              # C..N
            c[f"{get_column_letter(16 + j)}{f}"] = luz[j][r]               # P..AA
            c[f"{get_column_letter(45 + j)}{f}"] = inf_mes[j]              # AS..BD
    return Perfil4(Tabla(filas, "'4. Perfil de Uso'!B12:AN35"), inf_mes, c)


# --------------------------------------------------------------------------- '0. Perfil de Uso' (horario)
def _infiltracion_hora(d: DatosUso, p4: Perfil4, mes, hora):
    """BUSCARH(mes; '4. Perfil de Uso'!AS11:BD35; hora+2; 0): las filas 12-35 repiten AS10."""
    if es_error(mes):
        return mes
    i = posicion(d.p4_meses_infiltracion, mes)
    if i is None:
        return NA
    fila = ar(lambda h: h + 2, hora)
    if es_error(fila):
        return fila
    fila = int(fila)
    if fila < 1:
        return VALOR
    if fila > 1 + HORAS:
        return REF
    return copia(d.p4_meses_infiltracion[i]) if fila == 1 else p4.infiltracion_mes[i]


def perfil(d: DatosUso, e: EntradasUso, cab: Cabecera, inf: Infiltracion, ven: Ventilacion,
           p4: Perfil4, hor) -> PerfilUso:
    no_variables = igual(d.cargas_variables, "No")
    t_inf = Tabla(tuple(zip(d.meses_infiltracion, inf.rah_mes)))         # C29:D40
    t_chile = Tabla(tuple(zip(d.p4_chile_horas, d.p4_chile)))           # BS12:BT35
    t_ven = Tabla(tuple(zip(d.meses_ventilacion, ven.por_mes)))         # V2:W13
    t_conf = Tabla(tuple(zip(hor.meses, hor.t_media, hor.tn_min, hor.tn_max)))  # S11:V22
    propuesto = menor_igual(e.caso, 2)
    k6, k7 = copia(d.t_apertura), copia(d.vent_extra)
    cols = {k: [] for k in "EFGHJKLMN"}
    for r in range(FILAS):
        mes_n, mes, hora, t = d.filas_mes_num[r], d.filas_mes[r], d.filas_hora[r], hor.t[r]
        usu = si(no_variables,
                 ar(lambda a, b, c_: a * b / c_, d.aporte_personas_dia, cab.usuarios, cab.superficie),
                 buscarv(hora, p4.tabla, ar(lambda b: 1 + b, mes_n), exacto=False))
        luz = si(no_variables, copia(d.ilum_dia),
                 buscarv(hora, p4.tabla, ar(lambda b: 14 + b, mes_n), exacto=False))
        equ = si(no_variables, copia(d.equipos),
                 buscarv(hora, p4.tabla, ar(lambda b: 27 + b, mes_n), exacto=False))
        tot = suma_rango((usu, luz, equ))
        infil = si(mayor(ven.opcion, 2), 0.0,
                   si(igual(cab.infiltracion_variable, "No"), buscarv(mes, t_inf, 2),
                      _infiltracion_hora(d, p4, mes, hora)))
        co2 = ar(lambda v, u, k3, vol, s, k4: (v * u * k3 * 3600 / 1000) / vol
                 + (s * k4 * 3600 / 1000) / vol,
                 buscarv(hora, t_chile, 2), cab.usuarios, d.vent_usuario, cab.volumen,
                 cab.superficie, d.vent_superficie)
        otra = si(propuesto, ar(op.sub, buscarv(mes, t_ven, 2), infil),
                  ar(lambda q, f_, j: q * f_ - j, cab.fmin, d.factor_base, infil))
        vent = si(y_(propuesto, mayor(ven.opcion, 2), igual(ven.control, 2)), co2, otra)
        nocturna = si(y_(mayor(t, k6), o_(menor(hora, 7), mayor(hora, 21))), k7, 0.0)
        diurna = si(y_(igual(nocturna, 0), mayor_igual(t, buscarv(mes, t_conf, 3)),
                       menor_igual(t, buscarv(mes, t_conf, 4))), k7, 0.0)
        total_ren = ar(lambda a, b, c_, d_: a + b + c_ + d_, nocturna, vent, infil, diurna)
        for k, v in zip("EFGHJKLMN", (usu, luz, equ, tot, infil, vent, diurna, nocturna, total_ren)):
            cols[k].append(v)
    c = {f"{k}{FILA_PDU + r}": cols[k][r] for k in cols for r in range(FILAS)}
    return PerfilUso(*(tuple(cols[k]) for k in "EFGHJKLMN"), celdas=c)


# --------------------------------------------------------------------------- '0. Datos Clima Motor'
def columnas_motor(dc: DatosClima, d: DatosUso, p: PerfilUso) -> Motor:
    t_pdu = Tabla(tuple(zip(d.filas_mes, d.filas_hora, p.usuarios, p.iluminacion, p.equipos,
                            p.total, (None,) * FILAS, p.infiltracion)))   # C11:J298
    K, L, M, X, E23 = [], [], [], [], []
    c: dict = {}
    for m in range(MESES):
        b = HORAS * m
        k_ = [p.usuarios[b + h] for h in range(HORAS)]
        l_ = [p.iluminacion[b + h] for h in range(HORAS)]
        m_ = [p.equipos[b + h] for h in range(HORAS)]
        sig = 1 if m == 0 else 0        # enero: N de la fila siguiente (X10 = N12 - J11)
        x_ = [ar(op.sub, p.renovaciones[b + h + sig], p.infiltracion[b + h]) for h in range(HORAS)]
        for col in (k_, l_, m_, x_):
            col.append(col[0])          # hora 24 = hora 0
        e23 = buscarv(dc.motor_meses[m], t_pdu, 8)
        r0 = 10 + 32 * m
        for h in range(HORAS + 1):
            for letra, col in (("K", k_), ("L", l_), ("M", m_), ("X", x_)):
                c[f"{letra}{r0 + h}"] = col[h]
        c[f"E{r0 + 13}"] = e23
        K.append(tuple(k_))
        L.append(tuple(l_))
        M.append(tuple(m_))
        X.append(tuple(x_))
        E23.append(e23)
    return Motor(tuple(K), tuple(L), tuple(M), tuple(X), tuple(E23), c)


# --------------------------------------------------------------------------- todo
def calcular(d: DatosUso, dc: DatosClima, hor, e: EntradasUso) -> ResultadoUso:
    """hor: clima.horario de la zona del caso."""
    b, celdas_base = bases(d, e)
    inf = infiltracion(d, e, b)
    cab = cabecera(d, e, b)
    ven = ventilacion(d, e, inf, cab.fmin)
    p4 = perfil4(d, e, cab, inf)
    per = perfil(d, e, cab, inf, ven, p4, hor)
    mot = columnas_motor(dc, d, per)
    return ResultadoUso(inf, cab, ven, p4, per, mot, celdas_base)
