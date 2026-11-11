# -*- coding: utf-8 -*-
"""
Geometria del recinto -> muros, ventanas, puentes termicos y FAV.

Reglas (Manual CEV 2025.08.18 entre parentesis; criterio de puentes de Lucas):
  - Azimut del eje ortogonal a la fachada, -180..180, horario (6.2.1).
  - Area de muro por la cara interior, descontados los vanos (6.2, 11.2.1).
  - Sin puentes en muros adiabaticos (6.2.2).
  - Esquinas verticales, contadas una sola vez (6.2.3): entre dos muros
    exteriores P01; entre un muro exterior y uno adiabatico P03, en el muro
    exterior (config: puentes.esquina_con_adiabatico).
  - Bordes horizontales de cada muro exterior: cielo y piso como P03; pasan a
    P01 si el techo o el piso (ventilado) es exterior; contra terreno no
    cuentan (6.2.3, 6.2.4).
  - P04: aleros y aletas, largo total del encuentro con el muro (6.2.5).
  - Perimetro contra terreno por el interior, sin tramos adiabaticos (6.4.1).
  - Ventana que ocupa toda la fachada -> muro de 0,05 m2 (6.7).
  - FAV1 (H, L, D), FAV2 (W, P, S izq/der desde el interior), FAV3 (E, T, b).

Las fachadas se identifican internamente como f1..f4; el nombre que ve el
usuario (Frente, Derecha, Atras, Izquierda) sale de config/recinto.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .modelo import Fachada, Recinto

CONFIG = Path(__file__).parent / "config" / "recinto.yaml"
NOMBRES = ("f1", "f2", "f3", "f4")

# Tipo de puente en el borde superior/inferior de un muro exterior
BORDE_TECHO = {"exterior": "p01", "adiabatico": "p03"}
BORDE_PISO = {"ventilado": "p01", "terreno": None, "adiabatico": "p03"}


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def _cfg_defecto() -> dict:
    return cargar_config()


def etiqueta(nombre: str, cfg: dict | None = None) -> str:
    """Nombre visible de una fachada: 'f1' -> 'Frente'."""
    cfg = cfg or _cfg_defecto()
    return ((cfg.get("fachadas") or {}).get("nombres") or {}).get(nombre, nombre)


def normalizar_azimut(a: float) -> float:
    a = ((float(a) + 180.0) % 360.0) - 180.0
    return 180.0 if a == -180.0 else a + 0.0


def azimutes(az_f1: float) -> tuple:
    return tuple(normalizar_azimut(az_f1 + 90 * i) for i in range(4))


def longitudes(r: Recinto) -> tuple:
    return (r.largo, r.ancho, r.largo, r.ancho)


@dataclass(frozen=True)
class VentanaCalc:
    alto: float
    ancho: float
    area: float
    fachada_completa: bool


@dataclass(frozen=True)
class MuroCalc:
    nombre: str
    azimut: float
    exterior: bool
    largo: float
    area_bruta: float
    area_neta: float
    ventana: VentanaCalc | None = None
    fav: list | None = None          # [D, L, P_izq, S_izq, P_der, S_der, E, T, b]
    p01: float = 0.0
    p02: float = 0.0
    p03: float = 0.0
    p04: float = 0.0
    muro_ficticio: bool = False


@dataclass
class Resultado:
    muros: list
    area_piso: float
    volumen: float
    perimetro_terreno: float
    avisos: list = field(default_factory=list)


def validar(r: Recinto, cfg: dict) -> None:
    lim = cfg["limites"]
    for n in ("largo", "ancho", "altura"):
        lo, hi = lim[n]
        if not lo <= getattr(r, n) <= hi:
            raise ValueError(f"{n}={getattr(r, n)} fuera de [{lo}, {hi}]")
    paso = lim["paso_azimut"]
    if paso and float(r.azimut) % paso != 0:
        raise ValueError(f"azimut debe ser multiplo de {paso}")
    if not any(f.exterior for f in r.fachadas):
        raise ValueError("al menos una fachada debe ser exterior")


def ventana(largo: float, altura: float, pct: float, cfg: dict) -> VentanaCalc | None:
    if pct <= 0:
        return None
    v = cfg["ventana"]
    alto = altura - v["antepecho"] - v["dintel"]
    if alto <= 0:
        raise ValueError("antepecho + dintel >= altura")
    area = pct / 100.0 * largo * altura
    ancho = area / alto
    if ancho > largo + 1e-9:
        raise ValueError(f"{pct}% de vidrio no cabe con alto {alto:.2f} m")
    completa = (largo - ancho) <= v["tolerancia_fachada_completa"]
    return VentanaCalc(alto, ancho, area, completa)


def puentes(r: Recinto, cfg: dict) -> dict:
    """{fachada: {'p01','p02','p03'}} en metros lineales."""
    p = {n: {"p01": 0.0, "p02": 0.0, "p03": 0.0} for n in NOMBRES}
    ext = [f.exterior for f in r.fachadas]
    lon = longitudes(r)
    h = r.altura
    con_ad = cfg["puentes"]["esquina_con_adiabatico"].lower()
    # Esquinas verticales (planta rectangular: todas salientes). Cada esquina
    # se cuenta una vez: entre dos exteriores se asigna a la primera.
    for i in range(4):
        j = (i + 1) % 4
        if ext[i] and ext[j]:
            p[NOMBRES[i]]["p01"] += h
        elif ext[i] or ext[j]:
            k = i if ext[i] else j
            p[NOMBRES[k]][con_ad] += h
    # Bordes horizontales: cielo y piso de cada muro exterior
    for i in range(4):
        if not ext[i]:
            continue
        n = NOMBRES[i]
        p[n][BORDE_TECHO[r.techo]] += lon[i]
        tipo = BORDE_PISO[r.piso]
        if tipo:
            p[n][tipo] += lon[i]
    return p


def fav_ventana(f: Fachada, v: VentanaCalc, largo: float, cfg: dict) -> list:
    pr = f.proteccion
    c = cfg["proteccion"]
    if pr.alero_l > 0:
        d = pr.alero_d if pr.alero_d is not None else c["alero_d"]
        fav1 = [d, pr.alero_l]
    else:
        fav1 = [0.0, 0.0]
    if pr.aleta_s is not None:
        s = pr.aleta_s
    elif c["aletas_en"] == "borde_fachada":
        s = (largo - v.ancho) / 2.0
    else:
        s = 0.0
    s_izq = s if pr.aleta_izq_p > 0 else 0.0
    s_der = s if pr.aleta_der_p > 0 else 0.0
    fav2 = [pr.aleta_izq_p, s_izq, pr.aleta_der_p, s_der]
    fav3 = [pr.celosia_e, pr.celosia_t, pr.celosia_beta]
    return fav1 + fav2 + fav3


def largo_p04(fav: list, v: VentanaCalc, cfg: dict) -> float:
    """Largo del encuentro de aleros y aletas con el muro [m]."""
    c = cfg["puentes"].get("p04") or {}
    D, L, Pi, _, Pd, _ = fav[:6]
    total = 0.0
    if c.get("alero", True) and L > 0:
        total += v.ancho
    if c.get("aletas", True):
        total += sum(v.alto + D for P in (Pi, Pd) if P > 0)
    return total


def calcular(r: Recinto, cfg: dict | None = None) -> Resultado:
    cfg = cfg or cargar_config()
    validar(r, cfg)
    az = azimutes(r.azimut)
    lon = longitudes(r)
    pt = puentes(r, cfg)
    avisos, muros = [], []
    for i, (n, f) in enumerate(zip(NOMBRES, r.fachadas)):
        et = etiqueta(n, cfg)
        v = ventana(lon[i], r.altura, f.vidrio_pct, cfg) if f.exterior else None
        bruta = lon[i] * r.altura
        neta = bruta - (v.area if v else 0.0)
        ficticio = False
        if v and v.fachada_completa:
            neta = cfg["ventana"]["muro_ficticio_area"]
            ficticio = True
            avisos.append(f"{et}: ventana ocupa toda la fachada; muro de {neta} m2 (Manual 6.7)")
        fav = fav_ventana(f, v, lon[i], cfg) if v else None
        p04 = largo_p04(fav, v, cfg) if v else 0.0
        if v and f.proteccion.alero_l > 0 and f.proteccion.alero_l / v.alto < 0.1:
            avisos.append(f"{et}: L/H < 0,1, el FAV1 se podria desestimar (6.7.3.1)")
        muros.append(MuroCalc(n, az[i], f.exterior, lon[i], bruta, neta, v, fav,
                              **pt[n], p04=p04, muro_ficticio=ficticio))
    perim = sum(lon[i] for i in range(4) if r.fachadas[i].exterior) \
        if r.piso == "terreno" else 0.0
    return Resultado(muros, r.largo * r.ancho, r.largo * r.ancho * r.altura,
                     perim, avisos)
