# -*- coding: utf-8 -*-
"""
Datos de entrada y salida del motor FAR, y su forma JSON.

Entrada (JSON):
    {"version": 1,
     "puntos": [{"id": "N", "x": 0, "y": 0, "z": 1.5, "azimut": 0}],
     "volumenes": [{"id": "Edificio B", "poligono": [[x, y], ...], "h": 15}],
     "parametros": {"paso_grados": 0.1, ...}}

z y h se miden desde el terreno natural (plano). Los volúmenes parten siempre
del terreno: no hay volúmenes flotantes.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

VERSION = 1
DESCARTES = ("ninguno", "logico", "literal")
DECIMALES = 4


@dataclass(frozen=True)
class Punto:
    """Punto de referencia de una orientación (centro de la fachada)."""
    id: str
    x: float
    y: float
    z: float            # altura sobre el terreno natural
    azimut: float       # centro del semicírculo (normal hacia afuera)


@dataclass(frozen=True)
class Volumen:
    """Volumen del contexto: planta poligonal extruida desde el terreno hasta h."""
    id: str
    poligono: tuple     # ((x, y), ...)
    h: float


@dataclass(frozen=True)
class Parametros:
    paso_grados: float = 0.1          # resolución del barrido
    ancho_min_grados: float = 0.5     # tramos más angostos se omiten ("angosto")
    descarte: str = "ninguno"         # ninguno | logico (D/B, A/B) | literal (B/D, B/A)
    umbral_descarte: float = 0.1
    maximo: int | None = 8            # obstrucciones por punto; None = sin tope

    def validar(self) -> None:
        if not 0 < self.paso_grados <= 36:
            raise ValueError(f"paso_grados fuera de (0, 36]: {self.paso_grados}")
        if self.ancho_min_grados < 0:
            raise ValueError(f"ancho_min_grados negativo: {self.ancho_min_grados}")
        if self.descarte not in DESCARTES:
            raise ValueError(f"descarte debe ser uno de {DESCARTES}: {self.descarte!r}")
        if self.maximo is not None and self.maximo < 0:
            raise ValueError(f"maximo negativo: {self.maximo}")


@dataclass(frozen=True)
class Obstruccion:
    division: int       # 1..5, de izquierda a derecha mirando desde adentro
    volumen: str
    a: float            # altura sobre el punto: h - z
    b: float            # distancia al punto medio de la cuerda visible
    d: float            # ancho perpendicular a B cortado por los rayos extremos
    theta_i: float      # rayo izquierdo, grados respecto de la normal
    theta_f: float      # rayo derecho
    elevacion: float    # atan(A/B), grados
    relevancia: float   # fracción de cielo difuso que le asigna la ficha
    punto_medio: tuple  # (x, y) del punto medio de la cuerda

    def a_dict(self) -> dict:
        r = lambda v: round(v, DECIMALES)
        return {"division": self.division, "volumen": self.volumen, "a": r(self.a), "b": r(self.b),
                "d": r(self.d), "theta_i": r(self.theta_i), "theta_f": r(self.theta_f),
                "elevacion": r(self.elevacion), "relevancia": round(self.relevancia, 6),
                "punto_medio": [r(self.punto_medio[0]), r(self.punto_medio[1])]}


@dataclass(frozen=True)
class Omitida:
    obstruccion: Obstruccion
    motivo: str         # angosto | descarte | maximo

    def a_dict(self) -> dict:
        return {**self.obstruccion.a_dict(), "motivo": self.motivo}


@dataclass(frozen=True)
class ResultadoPunto:
    punto: str
    obstrucciones: tuple
    omitidas: tuple = ()
    avisos: tuple = ()

    def a_dict(self) -> dict:
        return {"punto": self.punto,
                "obstrucciones": [o.a_dict() for o in self.obstrucciones],
                "omitidas": [o.a_dict() for o in self.omitidas],
                "avisos": list(self.avisos)}


_CAMPOS = {f.name for f in fields(Parametros)}


def desde_dict(datos: dict) -> tuple[tuple, tuple, Parametros]:
    """JSON de entrada -> (puntos, volumenes, parametros)."""
    puntos = tuple(Punto(str(p["id"]), float(p["x"]), float(p["y"]), float(p["z"]), float(p["azimut"]))
                   for p in datos.get("puntos", ()))
    vols = tuple(Volumen(str(v["id"]), tuple((float(x), float(y)) for x, y in v["poligono"]), float(v["h"]))
                 for v in datos.get("volumenes", ()))
    crudo = dict(datos.get("parametros") or {})
    otros = set(crudo) - _CAMPOS
    if otros:
        raise ValueError(f"parámetros desconocidos: {sorted(otros)}")
    par = Parametros(**crudo)
    par.validar()
    return puntos, vols, par


def a_dict(resultados) -> dict:
    """Resultados -> JSON de salida."""
    return {"version": VERSION, "resultados": [r.a_dict() for r in resultados]}


def entrada_dict(puntos, volumenes, parametros: Parametros | None = None) -> dict:
    """(puntos, volumenes, parametros) -> JSON de entrada."""
    par = parametros or Parametros()
    return {"version": VERSION,
            "puntos": [{"id": p.id, "x": p.x, "y": p.y, "z": p.z, "azimut": p.azimut} for p in puntos],
            "volumenes": [{"id": v.id, "poligono": [list(q) for q in v.poligono], "h": v.h} for v in volumenes],
            "parametros": {f: getattr(par, f) for f in sorted(_CAMPOS)}}
