# -*- coding: utf-8 -*-
"""
Tablas fijas de la plantilla 01 que usa el motor Python.

Se extraen automaticamente de la plantilla oficial (no se escriben a mano) y quedan
versionadas en motor_py/datos/. Cada constante guarda la celda de donde salio; los yaml
guardan tambien la huella (sha256) de la plantilla.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .excel import Tabla

DIR = Path(__file__).parent / "datos"
YAML_CLIMA = "clima.yaml"
YAML_USO = "uso.yaml"
YAML_ENV = "envolvente.yaml"
YAML_INER = "inercia.yaml"
YAML_FAV = "fav.yaml"
YAML_SOLAR = "solar.yaml"
YAML_FAR = "far.yaml"
YAML_MOTOR = "motor.yaml"
CSV_CRUDO = "clima_crudo.csv"
CSV_FILAS = "clima_filas.csv"
COLUMNAS_CRUDO = ("mes", "hora", "ciudad", "zona", "t", "g_total", "g_difusa", "g_directa")
COLUMNAS_FILAS = ("fila", "mes", "hora")


class FaltanDatos(FileNotFoundError):
    """Faltan las tablas de la plantilla oficial en motor_py/datos/."""


def a_numero(txt):
    """Texto del CSV -> float; vacio -> None; si no es numero, queda el texto."""
    if txt is None or txt == "":
        return None
    try:
        return float(txt)
    except ValueError:
        return txt


def a_texto(v) -> str:
    """Valor -> texto del CSV sin perder precision (repr de un float es exacto)."""
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v)


def celda_de(texto: str) -> tuple[str, str]:
    """"'0. Datos Arq Motor'!D76" -> ("0. Datos Arq Motor", "D76")."""
    hoja, _, celda = str(texto).rpartition("!")
    hoja = hoja.strip()
    if hoja.startswith("'") and hoja.endswith("'"):
        hoja = hoja[1:-1].replace("''", "'")
    return hoja, celda.replace("$", "").strip().upper()


def ubicacion(info) -> tuple[str, str] | None:
    """(hoja, celda) de un nombre definido de los yaml, o None si no se resolvio.

    Acepta los dos formatos con que se han guardado las tablas:
      nuevo:   {"hoja": "0. Datos Arq Motor", "celda": "D76", ...}
      antiguo: {"celda": "'0. Datos Arq Motor'!D76", ...}
    """
    info = info or {}
    celda = info.get("celda")
    if not celda:
        return None
    hoja = info.get("hoja")
    if hoja:
        return str(hoja), str(celda).replace("$", "").strip().upper()
    if "!" in str(celda):
        return celda_de(celda)
    return None


def escribir_csv(ruta, columnas, filas) -> None:
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(columnas)
        for f in filas:
            w.writerow([a_texto(v) for v in f])


def leer_csv(ruta) -> list:
    with open(ruta, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def _flotante(v):
    return None if v is None else float(v)


def _yaml(carpeta: Path, nombre: str, comando: str = "") -> dict:
    ruta = Path(carpeta) / nombre
    if not ruta.exists():
        raise FaltanDatos(f"falta {nombre} en {carpeta} (tablas de la plantilla oficial)")
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- clima
@dataclass(frozen=True)
class DatosClima:
    # '0. Clima'!C11:J2890: tabla horaria por zona (columna J no se usa: Q = O - P)
    crudo_mes: tuple
    crudo_hora: tuple
    crudo_zona: tuple
    crudo_t: tuple
    crudo_g_total: tuple
    crudo_g_difusa: tuple
    # '0. Clima'!L11:M298: mes y hora de cada fila del horario procesado
    filas_mes: tuple
    filas_hora: tuple
    meses: tuple                  # '0. Clima'!S11:S22
    db_a: float                   # '0. Clima'!T3 (banda de confort, A)
    db_b: float                   # T4 (B)
    db_rango: float               # T5 (Rango)
    comuna_especial: object       # '0. Tablas referencia'!U24 (ver clima.zona_clima)
    zona_especial: str            # "J", dentro de la formula '0. Clima'!M2
    h_sol: float                  # '0. Datos Clima Motor'!C3
    absortividad_muros: float     # '0. Datos Clima Motor'!C7
    radiacion_cielo: float        # 63, dentro de la formula '0. Datos Clima Motor'!N10
    motor_meses: tuple            # '0. Datos Clima Motor'!E10, E42, ... (12)
    motor_horas: tuple            # F de cada bloque (12 x 25)
    motor_segundos: tuple         # G de cada bloque (12 x 25)
    factor_meses: tuple           # '0.FAV parámetros 1'!A207:A218 (claves del factor por orientacion)
    origen: dict = field(default_factory=dict, compare=False)


def cargar_clima(carpeta: Path = DIR) -> DatosClima:
    carpeta = Path(carpeta)
    faltan = [n for n in (YAML_CLIMA, CSV_CRUDO, CSV_FILAS) if not (carpeta / n).exists()]
    if faltan:
        raise FaltanDatos(f"faltan {faltan} en {carpeta} (tablas de la plantilla oficial)")
    cfg = yaml.safe_load((carpeta / YAML_CLIMA).read_text(encoding="utf-8"))
    crudo = leer_csv(carpeta / CSV_CRUDO)
    filas = leer_csv(carpeta / CSV_FILAS)
    c, m = cfg["constantes"], cfg["motor"]

    def num(col, rows):
        return tuple(a_numero(r[col]) for r in rows)

    return DatosClima(
        crudo_mes=tuple(r["mes"] for r in crudo),
        crudo_hora=num("hora", crudo),
        crudo_zona=tuple(r["zona"] for r in crudo),
        crudo_t=num("t", crudo),
        crudo_g_total=num("g_total", crudo),
        crudo_g_difusa=num("g_difusa", crudo),
        filas_mes=tuple(r["mes"] for r in filas),
        filas_hora=num("hora", filas),
        meses=tuple(cfg["meses"]),
        db_a=float(c["dear_brager_a"]["valor"]),
        db_b=float(c["dear_brager_b"]["valor"]),
        db_rango=float(c["dear_brager_rango"]["valor"]),
        comuna_especial=c["comuna_especial"]["valor"],
        zona_especial=str(c["zona_especial"]["valor"]),
        h_sol=float(c["h_sol"]["valor"]),
        absortividad_muros=float(c["absortividad_muros"]["valor"]),
        radiacion_cielo=float(c["radiacion_cielo"]["valor"]),
        motor_meses=tuple(m["meses"]),
        motor_horas=tuple(tuple(_flotante(x) for x in fila) for fila in m["horas"]),
        motor_segundos=tuple(tuple(_flotante(x) for x in fila) for fila in m["segundos"]),
        factor_meses=tuple(cfg.get("factor_orientacion_meses") or ()),
        origen=cfg.get("origen") or {})


# --------------------------------------------------------------------------- perfil de uso
@dataclass(frozen=True)
class DatosUso:
    # '0. Perfil de Uso' (rotulos de la hoja entre parentesis)
    aporte_personas_dia: object        # D4 (C4 'Aporte personas')
    aporte_personas_noche: object      # E4
    ilum_dia: object                   # D6 (C6 'Aporte Iluminacion')
    ilum_noche: object                 # E6
    equipos: object                    # D7 (C7 'Aporte Equipos')
    cargas_variables: object           # D8 (C8 'Cargas internas Variables')
    vent_usuario: object               # K3 (J3 'Vent por usuarios' [l/s])
    vent_superficie: object            # K4 (J4 'Vent por superficie')
    t_apertura: object                 # K6 (J6 'Temperatura minima de apertura de ventanas nocturna')
    vent_extra: object                 # K7 (J7 'Se suma la siguiente tasa de ventilacion' [RAH])
    factor_base: object                # Q3 (P3 'Factor para caso base')
    filas_mes_num: tuple               # B11:B298
    filas_mes: tuple                   # C11:C298
    filas_hora: tuple                  # D11:D298
    # '4. Perfil de Uso'
    p4_horas: tuple                    # B12:B35
    p4_o: tuple                        # O12:O35
    p4_ab: tuple                       # AB12:AB35
    p4_equipos: tuple                  # AC12:AN35 (24 filas x 12 meses)
    p4_chile_horas: tuple              # BS12:BS35
    p4_chile: tuple                    # BT12:BT35 (BT11 'CHILE')
    lux_min: object                    # U7 (P7 'Lux interior min')
    p4_meses_infiltracion: tuple       # AS11:BD11
    p4_noche_usuarios: tuple           # filas de C12:C35 que usan H7 (noche)
    p4_noche_iluminacion: tuple        # filas de P12:P35 que usan U6 (noche)
    # '0. Infiltraciones'
    cat_intermedio: object             # C9
    cat_pesado: object                 # C10
    k4_invierno: object                # C25 (B25 'K4 invierno')
    k50_a_rah: object                  # C27 (B27 'K 50Pa a RAH normal')
    meses_infiltracion: tuple          # C29:C40
    # '0. Ventilacion'
    meses_ventilacion: tuple           # V2:V13
    # '0. Tablas referencia'
    tabla_ventilacion: Tabla           # EQ12:ER17
    tabla_pi_materialidad: Tabla       # CG11:CH17
    tabla_pi_ventanas: Tabla           # CQ11:CR50
    tabla_pi_puertas: Tabla            # CT11:CU13
    tabla_k_zona: Tabla                # CW11:DA20 (K1, K2, K3, K4 verano)
    # nombres definidos del caso base: {nombre: {"hoja", "celda", "valor", "formula"}} (ver
    # ubicacion). El valor es el de la PLANTILLA vacia: algunos dependen del caso.
    nombres: dict
    origen: dict = field(default_factory=dict, compare=False)


def cargar_uso(carpeta: Path = DIR) -> DatosUso:
    cfg = _yaml(carpeta, YAML_USO)
    pc, pf, p4 = cfg["perfil"]["constantes"], cfg["perfil"]["filas"], cfg["perfil4"]
    inf = cfg["infiltraciones"]

    def v(seccion, k):
        return seccion[k]["valor"]

    def tabla(k):
        t = cfg["tablas"][k]
        return Tabla(tuple(tuple(f) for f in t["filas"]), t.get("celda") or "")

    return DatosUso(
        aporte_personas_dia=v(pc, "aporte_personas_dia"),
        aporte_personas_noche=v(pc, "aporte_personas_noche"),
        ilum_dia=v(pc, "ilum_dia"), ilum_noche=v(pc, "ilum_noche"), equipos=v(pc, "equipos"),
        cargas_variables=v(pc, "cargas_variables"), vent_usuario=v(pc, "vent_usuario"),
        vent_superficie=v(pc, "vent_superficie"), t_apertura=v(pc, "t_apertura"),
        vent_extra=v(pc, "vent_extra"), factor_base=v(pc, "factor_base"),
        filas_mes_num=tuple(pf["mes_num"]), filas_mes=tuple(pf["mes"]),
        filas_hora=tuple(pf["hora"]),
        p4_horas=tuple(p4["horas"]), p4_o=tuple(p4["o"]), p4_ab=tuple(p4["ab"]),
        p4_equipos=tuple(tuple(f) for f in p4["equipos"]),
        p4_chile_horas=tuple(p4["chile_horas"]), p4_chile=tuple(p4["chile"]),
        lux_min=p4["lux_min"]["valor"],
        p4_meses_infiltracion=tuple(p4["meses_infiltracion"]),
        p4_noche_usuarios=tuple(bool(x) for x in p4["noche_usuarios"]),
        p4_noche_iluminacion=tuple(bool(x) for x in p4["noche_iluminacion"]),
        cat_intermedio=v(inf["constantes"], "cat_intermedio"),
        cat_pesado=v(inf["constantes"], "cat_pesado"),
        k4_invierno=v(inf["constantes"], "k4_invierno"),
        k50_a_rah=v(inf["constantes"], "k50_a_rah"),
        meses_infiltracion=tuple(inf["meses"]),
        meses_ventilacion=tuple(cfg["ventilacion"]["meses"]),
        tabla_ventilacion=tabla("ventilacion"), tabla_pi_materialidad=tabla("pi_materialidad"),
        tabla_pi_ventanas=tabla("pi_ventanas"), tabla_pi_puertas=tabla("pi_puertas"),
        tabla_k_zona=tabla("k_zona"),
        nombres=dict(cfg.get("nombres") or {}),
        origen=cfg.get("origen") or {})


# --------------------------------------------------------------------------- envolvente
@dataclass(frozen=True)
class DatosEnvolvente:
    tref: dict             # '0. Tablas referencia': celdas sueltas (EO21, M11, M12, EQ17, ...)
    comunas: Tabla         # U12:AP357 reducida a las columnas U, AK..AP (zonas de cada comuna)
    azimut: Tabla          # B23:C39 (rango de azimut -> orientacion)
    pos_aislacion: Tabla   # EN21:EO25
    absortividad: Tabla    # EF11:EG17
    pt_muros: Tabla        # '0. Puentes térmicos'!K12:BB46 (P01, P02, P03)
    pt_p04: Tabla          # K51:BB114
    pt_p05: Tabla          # K118:BB149
    oguc1: Tabla           # Tabla_1_OGUC (U maximos por zona)
    oguc3: Tabla           # Tabla_3_OGUC (% maximo de ventanas)
    orient_base: Tabla     # 'CEV-CEVE'!CH52:CR60 (orientacion de cada caso)
    oguc_hoja: dict        # '0. Envolvente OGUC'!B9:H15 {celda: valor}
    cev: dict              # constantes de 'CEV-CEVE' (AT64:AV64, BW66:BW67, C169:C177, ...)
    piso: dict             # constantes de '0. Transmitancia piso Nch3117' (columna A, D:G, M:P)
    nombres: dict          # {nombre: {hoja, celda, rango, valor, formula}}
    origen: dict = field(default_factory=dict, compare=False)


def cargar_envolvente(carpeta: Path = DIR) -> DatosEnvolvente:
    cfg = _yaml(carpeta, YAML_ENV)

    def tabla(k):
        t = cfg["tablas"][k]
        return Tabla(tuple(tuple(f) for f in t["filas"]), t.get("celda") or "")

    return DatosEnvolvente(
        tref=dict(cfg["tref"]), comunas=tabla("comunas"), azimut=tabla("azimut"),
        pos_aislacion=tabla("pos_aislacion"), absortividad=tabla("absortividad"),
        pt_muros=tabla("pt_muros"), pt_p04=tabla("pt_p04"), pt_p05=tabla("pt_p05"),
        oguc1=tabla("oguc1"), oguc3=tabla("oguc3"), orient_base=tabla("orient_base"),
        oguc_hoja=dict(cfg["oguc_hoja"]), cev=dict(cfg["cev"]), piso=dict(cfg["piso"]),
        nombres=dict(cfg.get("nombres") or {}), origen=cfg.get("origen") or {})


# --------------------------------------------------------------------------- inercia
@dataclass(frozen=True)
class DatosInercia:
    # '0. Inercia Termica': constantes de A1:AX402 y formulas fijas (valor de la plantilla)
    celdas: dict
    fijas: tuple           # celdas con formula tomadas de la plantilla (se comparan igual contra Excel)
    origen: dict = field(default_factory=dict, compare=False)


def cargar_inercia(carpeta: Path = DIR) -> DatosInercia:
    cfg = _yaml(carpeta, YAML_INER)
    fijas = dict(cfg.get("fijas") or {})
    return DatosInercia({**(cfg.get("constantes") or {}), **fijas}, tuple(fijas),
                        cfg.get("origen") or {})


# --------------------------------------------------------------------------- radiacion por vanos
@dataclass(frozen=True)
class DatosFav:
    # '0.FAV Calculos': constantes (horas, meses, rotulos, tabla de orientaciones, JF4, JR)
    celdas: dict
    nombres: dict          # base_factor_FS, base_FS_vidrio, ... {hoja, celda, rango, valor, formula}
    origen: dict = field(default_factory=dict, compare=False)


def cargar_fav(carpeta: Path = DIR) -> DatosFav:
    cfg = _yaml(carpeta, YAML_FAV)
    return DatosFav(dict(cfg.get("constantes") or {}), dict(cfg.get("nombres") or {}),
                    cfg.get("origen") or {})


# --------------------------------------------------------------------------- geometria solar
@dataclass(frozen=True)
class DatosSolar:
    # '0.FAV parámetros 1': constantes de A1:AQ233 (con K207:R218) y "'0. Tablas referencia'!J11..J22"
    celdas: dict
    comunas: Tabla         # '0. Tablas referencia'!U12:AJ357 (comuna, radiacion mensual, latitud)
    origen: dict = field(default_factory=dict, compare=False)


def cargar_solar(carpeta: Path = DIR) -> DatosSolar:
    cfg = _yaml(carpeta, YAML_SOLAR)
    t = cfg["tablas"]["comunas"]
    return DatosSolar(dict(cfg.get("constantes") or {}),
                      Tabla(tuple(tuple(f) for f in t["filas"]), t.get("celda") or ""),
                      cfg.get("origen") or {})


# --------------------------------------------------------------------------- obstrucciones remotas
@dataclass(frozen=True)
class DatosFar:
    # '0. FAR': constantes de A1:LE260 (meses, horas, divisiones, orientaciones, INDIRECT, L148:L155)
    celdas: dict
    origen: dict = field(default_factory=dict, compare=False)


def cargar_far(carpeta: Path = DIR) -> DatosFar:
    cfg = _yaml(carpeta, YAML_FAR)
    return DatosFar(dict(cfg.get("constantes") or {}), cfg.get("origen") or {})


# --------------------------------------------------------------------------- rangos que lee calculo()
@dataclass(frozen=True)
class DatosMotor:
    # rangos.RANGOS en la plantilla: constantes, enlaces =+'Hoja'!celda y demas formulas
    constantes: dict       # {hoja: {celda: valor}}
    enlaces: dict          # {hoja: {celda: (hoja_origen, celda_origen)}}
    formulas: dict         # {hoja: set de celdas} (las calcula un modulo)
    origen: dict = field(default_factory=dict, compare=False)


def cargar_motor(carpeta: Path = DIR) -> DatosMotor:
    cfg = _yaml(carpeta, YAML_MOTOR)
    enlaces = {h: {c: tuple(x) for c, x in cs.items()} for h, cs in (cfg.get("enlaces") or {}).items()}
    formulas = {h: set(cs) for h, cs in (cfg.get("formulas") or {}).items()}
    return DatosMotor(dict(cfg.get("constantes") or {}), enlaces, formulas, cfg.get("origen") or {})
