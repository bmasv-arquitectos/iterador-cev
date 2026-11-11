# -*- coding: utf-8 -*-
"""
Soluciones constructivas por zona: base fija + EPS al espesor minimo.

  U = 1 / (Rsi + sum(e/lambda) + Rse)  <=  U_max(zona, elemento)
  e_EPS >= lambda_EPS * (1/U_max - Rsi - Rse - R_base), redondeado hacia
  arriba al paso de config/envolvente.yaml.

Datos: datos/normativa (NCh853, OGUC y Manual de Procedimientos CEV).
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .datos.normativa.nch853_tablas import RES_SUPERFICIAL
from .datos.normativa.tabla1_u_max import U_MAX_POR_USO

NORMATIVA = Path(__file__).parent / "datos" / "normativa"
CONFIG = Path(__file__).parent / "config" / "envolvente.yaml"


@lru_cache(maxsize=1)
def lambdas() -> dict:
    with open(NORMATIVA / "materiales_nch853.csv", encoding="utf-8-sig", newline="") as fh:
        return {r["nombre"]: float(r["valor_termico"])
                for r in csv.DictReader(fh) if r["tipo_termico"] == "lambda"}


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Capa:
    material: str
    espesor: float      # m
    lam: float          # W/mK

    @property
    def r(self) -> float:
        return self.espesor / self.lam


@dataclass(frozen=True)
class Solucion:
    elemento: str
    capas: tuple
    rsi: float
    rse: float
    u_max: float | None
    espesor_aislante_mm: int

    @property
    def r_total(self) -> float:
        return self.rsi + sum(c.r for c in self.capas) + self.rse

    @property
    def u(self) -> float:
        return 1.0 / self.r_total

    @property
    def cumple(self) -> bool:
        return self.u_max is None or self.u <= self.u_max + 1e-12


def _lam(nombre: str) -> float:
    try:
        return lambdas()[nombre]
    except KeyError:
        raise KeyError(f"material no esta en materiales_nch853.csv: {nombre!r}") from None


def u_max(zona: str, exigencia: str, cfg: dict) -> float:
    tabla = U_MAX_POR_USO[cfg["uso"]]
    if zona not in tabla:
        raise ValueError(f"zona {zona!r} sin U maximo en la Tabla 1")
    return tabla[zona][exigencia]


def espesor_minimo_mm(umax: float, r_fijo: float, lam: float,
                      paso: int, minimo: int = 0) -> int:
    e_mm = max(lam * (1.0 / umax - r_fijo) * 1000.0, 0.0)
    n = math.ceil(e_mm / paso - 1e-9)
    return max(int(n * paso), int(minimo))


def solucion(elemento: str, zona: str, cfg: dict | None = None) -> Solucion:
    cfg = cfg or cargar_config()
    el = cfg["elementos"][elemento]
    ais = cfg["aislante"]
    rs = RES_SUPERFICIAL[el["flujo"]]
    base = tuple(Capa(c["material"], float(c["espesor"]), _lam(c["material"]))
                 for c in el["base"])
    lam_ais = _lam(ais["material"])
    if el.get("exigencia"):
        umax = u_max(zona, el["exigencia"], cfg)
        r_fijo = rs["Rsi"] + rs["Rse"] + sum(c.r for c in base)
        mm = espesor_minimo_mm(umax, r_fijo, lam_ais, ais["paso_mm"], ais["minimo_mm"])
    else:
        umax = None
        mm = solucion(el["copiar_espesor_de"], zona, cfg).espesor_aislante_mm
    capas = base + ((Capa(ais["material"], mm / 1000.0, lam_ais),) if mm > 0 else ())
    return Solucion(elemento, capas, rs["Rsi"], rs["Rse"], umax, mm)


def soluciones(zona: str, cfg: dict | None = None) -> dict:
    cfg = cfg or cargar_config()
    return {e: solucion(e, zona, cfg) for e in cfg["elementos"]}
