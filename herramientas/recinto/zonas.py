# -*- coding: utf-8 -*-
"""
Comuna -> region y zona termica, con los textos exactos de la ficha 01.

Fuente unica: datos/comunas.yaml. Lo que devuelve este modulo se escribe tal
cual en la ficha: no hay traduccion de nombres.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DATOS = Path(__file__).parent / "datos" / "comunas.yaml"


@dataclass(frozen=True)
class OpcionZona:
    zona: str
    meridiano: str | None = None
    altitud: str | None = None

    def etiqueta(self) -> str:
        cond = [c for c in (self.meridiano, self.altitud) if c]
        return self.zona + (f" ({', '.join(cond)})" if cond else "")


def _norm(t: str) -> str:
    """Solo para BUSCAR: sin tildes, sin mayusculas, espacios (incl. duros) simples."""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split()).casefold()


def _limpiar(x):
    return None if x in (None, "-", "") else str(x)


@lru_cache(maxsize=1)
def cargar(ruta: Path = DATOS) -> dict:
    """{comuna: (region, [OpcionZona])}, textos exactos de la ficha 01."""
    with open(ruta, encoding="utf-8") as fh:
        crudo = yaml.safe_load(fh)
    salida = {}
    for region, comunas in crudo["regiones"].items():
        for comuna, v in comunas.items():
            if comuna in salida:
                raise ValueError(f"comuna repetida: {comuna!r}")
            if isinstance(v, str):
                ops = [OpcionZona(v)]
            else:
                ops = [OpcionZona(str(z), _limpiar(m), _limpiar(a)) for z, m, a in v]
            salida[comuna] = (region, ops)
    return salida


def region(comuna: str) -> str:
    return cargar()[comuna][0]


def opciones(comuna: str) -> list:
    return cargar()[comuna][1]


def buscar(texto: str, limite: int = 20) -> list:
    """Comunas que contienen el texto, sin importar tildes, mayusculas ni espacios."""
    t = _norm(texto)
    return [c for c in cargar() if t in _norm(c)][:limite]


def zona_de(comuna: str, zona: str | None = None) -> str:
    ops = opciones(comuna)
    zonas = [o.zona for o in ops]
    if zona is None:
        if len(set(zonas)) != 1:
            raise ValueError(f"{comuna} tiene varias zonas: elegir entre {zonas}")
        return zonas[0]
    if zona not in zonas:
        raise ValueError(f"{zona} no es zona de {comuna}: {zonas}")
    return zona
