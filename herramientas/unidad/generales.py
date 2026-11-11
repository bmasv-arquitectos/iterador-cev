# -*- coding: utf-8 -*-
"""
Soluciones generales de una unidad, sin interfaz. Cada elemento (muro, ventana,
puerta, techo, piso) usa por defecto la solucion GENERAL de su tipo; si se le da
una propia (modelo.py), cambiar la general ya no lo toca. sobrescribir() vuelve
todos los de un grupo a la general.

Categorias (Unidad.generales):
  muro, techo, piso_terreno, piso_ventilado   None = cumple norma | dict = personalizado
  vidrio                                      codigo de recinto/datos/vidrios.yaml | dict
  puerta                                      tipo de la ficha (cev.yaml puertas.tipos) | dict
Sin clave: la de config/cev.yaml (generales: vidrio y puerta; los opacos, la norma).
Los personalizados nuevos se llaman como generales.nombres de cev.yaml ("Muro
general"...), para no chocar con los propios en la ficha.

Grupos de la interfaz (GRUPOS): muro, ventana (vidrio), puerta, techo y piso
(piso_terreno y piso_ventilado; cada piso usa la de su condicion).

resolver(u, g) entrega la unidad (y su geometria) con lo general ya reemplazado,
como la entiende cev.py: muros GENERAL -> DEFECTO, o la clave GENERAL con los
datos en muros_personalizados[GENERAL]; ventanas y puertas con el vidrio o tipo
general. Techos y pisos los resuelve modelo.personalizado_horizontal.
Todas las funciones devuelven una Unidad nueva.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import yaml

from herramientas.recinto import catalogo, personalizado

from .modelo import DEFECTO, GENERAL, Unidad, estado_horizontal

CONFIG = Path(__file__).parent / "config" / "cev.yaml"
OPACOS = ("muro", "techo", "piso_terreno", "piso_ventilado")
CATEGORIAS = OPACOS + ("vidrio", "puerta")
GRUPOS = {"muro": ("muro",), "ventana": ("vidrio",), "puerta": ("puerta",), "techo": ("techo",),
          "piso": ("piso_terreno", "piso_ventilado")}


@lru_cache(maxsize=1)
def _cev() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def config() -> dict:
    """{vidrio, puerta, nombres}: valores de partida de las generales (cev.yaml)."""
    c = _cev()
    g = c.get("generales") or {}
    return {"vidrio": g.get("vidrio") or "DVH_AIRE_12", "puerta": g.get("puerta") or c["puertas"]["defecto"],
            "nombres": g.get("nombres") or {}}


def _revisar(cat: str) -> None:
    if cat not in CATEGORIAS:
        raise ValueError(f"categoria debe ser una de {CATEGORIAS}")


def valor(u: Unidad, cat: str):
    """La solucion general efectiva de la categoria."""
    _revisar(cat)
    v = u.generales.get(cat)
    if v is None and cat in ("vidrio", "puerta"):
        return config()[cat]
    return v


def modo(u: Unidad, cat: str) -> str:
    """norma | listado | personalizado."""
    if isinstance(valor(u, cat), dict):
        return "personalizado"
    return "norma" if cat in OPACOS else "listado"


def nombre(cat: str) -> str:
    return config()["nombres"].get(cat) or f"{cat.replace('_', ' ').capitalize()} general"


def poner(u: Unidad, cat: str, modo_: str, sols: dict | None = None, codigo: str | None = None) -> Unidad:
    """Opacos: norma | personalizado (parte de la solucion de la zona, sols).
    Vidrio y puerta: listado (codigo; None conserva el actual) | personalizado."""
    _revisar(cat)
    gen = dict(u.generales)
    actual = valor(u, cat)
    if cat in OPACOS:
        if modo_ == "norma":
            gen.pop(cat, None)
        elif modo_ == "personalizado":
            if isinstance(actual, dict):
                return u
            d = personalizado.inicial("piso" if cat.startswith("piso") else cat, sols)
            d["nombre"] = nombre(cat)
            gen[cat] = d
        else:
            raise ValueError("modo debe ser norma o personalizado")
    elif modo_ == "listado":
        cod = codigo or (actual if isinstance(actual, str) else config()[cat])
        if cat == "vidrio" and cod not in catalogo.vidrios():
            raise ValueError(f"vidrio desconocido: {cod!r}")
        if cat == "puerta" and cod not in _cev()["puertas"]["tipos"]:
            raise ValueError(f"tipo de puerta desconocido: {cod!r}")
        gen[cat] = cod
    elif modo_ == "personalizado":
        if isinstance(actual, dict):
            return u
        if cat == "vidrio":
            base = catalogo.vidrio(actual) if actual in catalogo.vidrios() else None
            d = personalizado.inicial("vidrio", vidrio=base)
        else:
            d = personalizado.defectos("puerta")
        d["nombre"] = nombre(cat)
        gen[cat] = d
    else:
        raise ValueError("modo debe ser listado o personalizado")
    return replace(u, generales=gen)


def editar(u: Unidad, cat: str, campo: str, v) -> Unidad:
    _revisar(cat)
    d = u.generales.get(cat)
    if not isinstance(d, dict):
        raise ValueError(f"La solución general ({cat}) no está personalizada")
    gen = dict(u.generales)
    gen[cat] = dict(d, **{campo: v})
    return replace(u, generales=gen)


# --------------------------------------------------------------------------- todos los elementos
def _mapear(u: Unidad, f) -> Unidad:
    """La unidad con f aplicada a cada tramo."""
    return replace(u, niveles=tuple(
        replace(n, lados=tuple(replace(l, tramos=tuple(f(t) for t in l.tramos)) for l in n.lados))
        for n in u.niveles))


def _propia_ventana(w) -> bool:
    return bool(w.vidrio_personalizado) or w.vidrio != GENERAL


def _propia_puerta(p) -> bool:
    return bool(p.personalizada) or p.tipo != GENERAL


def _tramos(u: Unidad):
    return (t for n in u.niveles for l in n.lados for t in l.tramos)


def particulares(u: Unidad, grupo: str, g=None) -> int:
    """Cuantos elementos del grupo tienen solucion propia (techos y pisos: necesita g)."""
    if grupo == "muro":
        return sum(1 for t in _tramos(u) if t.exterior and t.solucion != GENERAL)
    if grupo == "ventana":
        return sum(1 for t in _tramos(u) for w in t.ventanas if _propia_ventana(w))
    if grupo == "puerta":
        return sum(1 for t in _tramos(u) for p in t.puertas if _propia_puerta(p))
    if grupo not in ("techo", "piso"):
        raise ValueError(f"grupo debe ser uno de {tuple(GRUPOS)}")
    hs = [h for h in (g.horizontales if g is not None else ()) if h.destino == grupo and h.condicion != "adiabatico"]
    return sum(1 for h in hs if estado_horizontal(u, grupo, h.nivel) != "general")


def sobrescribir(u: Unidad, grupo: str) -> Unidad:
    """Todos los elementos del grupo vuelven a la solucion general (los muros
    personalizados quedan definidos, por si se quieren volver a asignar)."""
    if grupo == "muro":
        return _mapear(u, lambda t: replace(t, solucion=GENERAL))
    if grupo == "ventana":
        return _mapear(u, lambda t: replace(t, ventanas=tuple(
            replace(w, vidrio=GENERAL, vidrio_personalizado=None) for w in t.ventanas)))
    if grupo == "puerta":
        return _mapear(u, lambda t: replace(t, puertas=tuple(
            replace(p, tipo=GENERAL, personalizada=None) for p in t.puertas)))
    if grupo in ("techo", "piso"):
        resto = {k: v for k, v in u.superficies_personalizadas.items() if not k.startswith(f"{grupo}|")}
        return replace(u, superficies_personalizadas=resto, **{f"{grupo}_personalizado": None})
    raise ValueError(f"grupo debe ser uno de {tuple(GRUPOS)}")


# --------------------------------------------------------------------------- para calcular
def resolver(u: Unidad, g=None) -> tuple:
    """(unidad, geometria) con las soluciones generales reemplazadas (ver arriba).
    g: la geometria de u (geometria.calcular) o None."""
    gm, gv, gp = valor(u, "muro"), valor(u, "vidrio"), valor(u, "puerta")
    usa_muro = []

    def ventana(w):
        if _propia_ventana(w):
            return w
        if isinstance(gv, dict):
            return replace(w, vidrio="", vidrio_personalizado=dict(gv))
        return replace(w, vidrio=gv)

    def puerta(p):
        if _propia_puerta(p):
            return p
        if isinstance(gp, dict):
            return replace(p, tipo="", personalizada=dict(gp))
        return replace(p, tipo=gp)

    def tramo(t):
        sol = t.solucion
        if sol == GENERAL:
            if isinstance(gm, dict) and t.exterior:
                usa_muro.append(True)
            else:
                sol = DEFECTO
        return replace(t, solucion=sol, ventanas=tuple(map(ventana, t.ventanas)),
                       puertas=tuple(map(puerta, t.puertas)))

    ru = _mapear(u, tramo)
    if usa_muro:
        ru = replace(ru, muros_personalizados={**ru.muros_personalizados, GENERAL: dict(gm)})
    if g is None:
        return ru, None
    panos = []
    for x in g.panos:
        t = ru.niveles[x.nivel].lados[x.lado].tramos[x.tramo]
        panos.append(replace(x, solucion=t.solucion, puertas=tuple(t.puertas),
                             ventanas=tuple(replace(v, datos=t.ventanas[v.indice]) for v in x.ventanas)))
    return ru, replace(g, panos=panos)
