# -*- coding: utf-8 -*-
"""
Catalogos de vidrios (datos/vidrios.yaml, agrupados por tipo) y marcos
(datos/normativa/marcos.csv).
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import yaml

DATOS = Path(__file__).parent / "datos"
VIDRIOS = DATOS / "vidrios.yaml"
NORMATIVA = DATOS / "normativa"


@lru_cache(maxsize=1)
def _vidrios() -> dict:
    """{codigo: {grupo, nombre, u, fs, tl, ficha}} en el orden del YAML."""
    with open(VIDRIOS, encoding="utf-8") as fh:
        crudo = yaml.safe_load(fh)
    out = {}
    for grupo, items in crudo["grupos"].items():
        for codigo, d in items.items():
            if codigo in out:
                raise ValueError(f"vidrio repetido en vidrios.yaml: {codigo}")
            u, fs = float(d["u"]), float(d["fs"])
            if u <= 0 or not 0 < fs <= 1:
                raise ValueError(f"vidrio {codigo}: U o FS fuera de rango")
            out[codigo] = {"grupo": grupo, "nombre": str(d["nombre"]), "u": u, "fs": fs,
                           "tl": d.get("tl"), "ficha": d.get("ficha") or None}
    return out


def grupos() -> dict:
    """{grupo: [codigos]} en el orden del YAML."""
    g: dict = {}
    for codigo, d in _vidrios().items():
        g.setdefault(d["grupo"], []).append(codigo)
    return g


def vidrio(codigo: str) -> dict:
    try:
        return _vidrios()[codigo]
    except KeyError:
        raise ValueError(f"vidrio desconocido: {codigo!r}") from None


def vidrios() -> dict:
    """{codigo: (nombre, U)}"""
    return {c: (d["nombre"], d["u"]) for c, d in _vidrios().items()}


def etiqueta_vidrio(codigo: str) -> str:
    d = vidrio(codigo)
    u = f"{d['u']:g}".replace(".", ",")
    fs = f"{d['fs']:.2f}".replace(".", ",")
    return f"{d['nombre']} · U {u} · FS {fs}"


@lru_cache(maxsize=1)
def marcos() -> dict:
    """{codigo: (descripcion, U, fraccion de marco)}"""
    with open(NORMATIVA / "marcos.csv", encoding="utf-8-sig", newline="") as fh:
        return {r["codigo"]: (r["descripcion"], float(r["u"]), float(r["pct_marco_tipico"]))
                for r in csv.DictReader(fh, delimiter=";")}
