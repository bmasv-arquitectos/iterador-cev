# -*- coding: utf-8 -*-
"""
Componentes personalizados (muro, techo, piso, vidrio, puerta).

El motor es generico: los campos, sus columnas en la ficha, rangos y listas
viven en config/personalizado.yaml. Un componente personalizado es un dict
{clave: valor} que se valida aqui y que a_ficha (o unidad/cev.py) escribe en su
fila del catalogo ('3. Tablas Envolvente'). Python puro, sin interfaz.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .modelo import PERSONALIZABLES

CONFIG = Path(__file__).parent / "config" / "personalizado.yaml"
ELEMENTOS = PERSONALIZABLES + ("vidrio", "puerta")


@lru_cache(maxsize=1)
def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def spec(elemento: str) -> dict:
    try:
        return cargar_config()["elementos"][elemento]
    except KeyError:
        raise ValueError(f"componente no personalizable: {elemento!r}") from None


def opciones(campo: dict) -> list:
    return cargar_config()["listas"][campo["lista"]]


def aplica(campo: dict, piso: str | None = None) -> bool:
    """Los campos marcados 'solo' dependen del tipo de piso (ventilado/terreno)."""
    solo = campo.get("solo")
    return not solo or solo == piso


def campos(elemento: str, piso: str | None = None) -> list:
    return [c for c in spec(elemento)["campos"] if aplica(c, piso)]


def defectos(elemento: str) -> dict:
    return {c["clave"]: c.get("defecto") for c in spec(elemento)["campos"]}


def inicial(elemento: str, sols: dict | None = None, vidrio: dict | None = None) -> dict:
    """Valores de partida: los del componente que se esta reemplazando."""
    d = defectos(elemento)
    sols = sols or {}
    if elemento in ("muro", "techo") and elemento in sols:
        s = sols[elemento]
        ais = s.espesor_aislante_mm / 10
        total = sum(c.espesor for c in s.capas) * 100
        d.update(u=round(s.u, 3), solido_cm=round(total - ais, 1), aislante_cm=round(ais, 1))
    elif elemento == "piso":
        if "piso_ventilado" in sols:
            d["u"] = round(sols["piso_ventilado"].u, 3)
        t = sols.get("piso_terreno")
        if t is not None and t.espesor_aislante_mm:
            d.update(lambda_aislante=t.capas[-1].lam, e_aislante_cm=t.espesor_aislante_mm / 10)
    elif elemento == "vidrio" and vidrio:
        d.update(u=vidrio["u"], fs=vidrio["fs"])
    return d


def validar(elemento: str, datos: dict, piso: str | None = None) -> dict:
    """Devuelve una copia limpia o lanza ValueError con un mensaje para el estudiante."""
    sp = spec(elemento)
    out = {}
    for c in sp["campos"]:
        k, v = c["clave"], datos.get(c["clave"])
        if not aplica(c, piso):
            out[k] = v
            continue
        et = f"{sp['titulo']}: {c['etiqueta']}"
        if c["tipo"] == "texto":
            v = " ".join(str(v or "").split())
            if not 3 <= len(v) <= 60:
                raise ValueError(f"{et} debe tener entre 3 y 60 caracteres")
            for r in sp.get("reservados") or []:
                if v in r:
                    raise ValueError(f"{et}: '{v}' se confunde con una opción de la ficha; usa otro nombre")
        elif c["tipo"] == "lista":
            if v not in opciones(c):
                raise ValueError(f"{et}: elige una opción de la lista")
        else:
            if v in (None, "") or (c.get("opcional") and not v):
                if c.get("opcional"):
                    out[k] = None
                    continue
                raise ValueError(f"falta {et}")
            v = float(v)
            if not c["min"] <= v <= c["max"]:
                raise ValueError(f"{et} fuera de rango [{c['min']}, {c['max']}]")
        out[k] = v
    return out


def valores_ficha(elemento: str, datos: dict, piso: str | None = None) -> dict:
    """{letra de columna: valor} de la fila del catalogo. C (abreviatura) = nombre."""
    out = {"C": datos["nombre"]}
    for c in spec(elemento)["campos"]:
        col, v = c.get("col"), datos.get(c["clave"])
        if not col or v is None or not aplica(c, piso):
            continue
        out[col] = round(v, 4) if isinstance(v, float) else v
    return out


def u(elemento: str, datos: dict, piso: str | None = None) -> float | None:
    """U que se puede mostrar. El piso contra terreno lo calcula la ficha (NCh3117)."""
    if elemento == "piso" and piso != "ventilado":
        return None
    return datos.get("u")


def ajustar_espesores(esp: dict, personalizados: dict | None) -> dict:
    """Espesores de dibujo [m] con los muros y techos personalizados."""
    esp = dict(esp)
    for el, clave in (("muro", "muro_exterior"), ("techo", "techo")):
        d = (personalizados or {}).get(el)
        if d:
            total = ((d.get("solido_cm") or 0) + (d.get("aislante_cm") or 0)) / 100
            if total > 0:
                esp[clave] = total
    return esp
