# -*- coding: utf-8 -*-
"""
Protecciones solares de las ventanas (Manual CEV 6.7.3): activar o quitar cada
una, cambiar sus datos y su geometria para el 3D y el alzado.

Tipos (en el orden de la ficha 01, columnas P..Y):
  alero      FAV1: L saliente y D distancia del borde superior del vano al alero.
  aleta_izq  FAV2 izquierda (vista desde el interior): P saliente y S separacion del vano.
  aleta_der  FAV2 derecha.
  celosia    FAV3: E, T y el angulo de las lamas; horizontal -> columna b (X), vertical -> a (Y).
Una proteccion esta activa si sus medidas son positivas (alero_l > 0, aleta_*_p > 0,
celosia_e y celosia_t > 0). Al activarla se usan los valores de config/editor.yaml
(protecciones.defecto); al quitarla, sus medidas vuelven a 0.
"""
from __future__ import annotations

from dataclasses import replace

from . import editor
from .modelo import Proteccion, Unidad

TIPOS = ("alero", "aleta_izq", "aleta_der", "celosia")
APAGADA = {
    "alero": {"alero_l": 0.0, "alero_d": None},
    "aleta_izq": {"aleta_izq_p": 0.0, "aleta_izq_s": None},
    "aleta_der": {"aleta_der_p": 0.0, "aleta_der_s": None},
    "celosia": {"celosia_e": 0.0, "celosia_t": 0.0, "celosia_beta": 0.0, "celosia_orientacion": "horizontal"},
}


def activas(pr: Proteccion) -> list:
    out = []
    if pr.alero_l > 0:
        out.append("alero")
    if pr.aleta_izq_p > 0:
        out.append("aleta_izq")
    if pr.aleta_der_p > 0:
        out.append("aleta_der")
    if pr.celosia_e > 0 and pr.celosia_t > 0:
        out.append("celosia")
    return out


def separacion(pr: Proteccion, lado: str) -> float:
    """S de la aleta 'izq' o 'der': la propia, si no aleta_s, si no 0."""
    s = pr.aleta_izq_s if lado == "izq" else pr.aleta_der_s
    if s is None:
        s = pr.aleta_s
    return 0.0 if s is None else float(s)


def con_tipos_proteccion(pr: Proteccion, tipos, defecto: dict) -> Proteccion:
    """Deja activas exactamente las protecciones de `tipos` (las nuevas con sus valores por defecto)."""
    tipos = set(tipos)
    raros = tipos - set(TIPOS)
    if raros:
        raise ValueError(f"Protección desconocida: {sorted(raros)}")
    act = set(activas(pr))
    cambios = {}
    for t in TIPOS:
        if t in tipos and t not in act:
            cambios.update(defecto[t])
        elif t not in tipos and t in act:
            cambios.update(APAGADA[t])
    return replace(pr, **cambios)


# --------------------------------------------------------------------------- sobre la unidad
def _ventana(u: Unidad, k: int, i: int, j: int, m: int):
    t = u.niveles[k].lados[i].tramos[j]
    if not 0 <= m < len(t.ventanas):
        raise ValueError("No existe esa ventana")
    return t, t.ventanas[m]


def _con_proteccion(u: Unidad, k: int, i: int, j: int, m: int, pr: Proteccion) -> Unidad:
    t, w = _ventana(u, k, i, j, m)
    lista = list(t.ventanas)
    lista[m] = replace(w, proteccion=pr)
    return editor._con_tramo(u, k, i, j, replace(t, ventanas=tuple(lista)))


def cambiar(u: Unidad, k: int, i: int, j: int, m: int, **campos) -> Unidad:
    """Cambia datos de la proteccion de la ventana m (Proteccion revisa los valores)."""
    _, w = _ventana(u, k, i, j, m)
    return _con_proteccion(u, k, i, j, m, replace(w.proteccion, **campos))


def con_tipos(u: Unidad, k: int, i: int, j: int, m: int, tipos, defecto: dict) -> Unidad:
    _, w = _ventana(u, k, i, j, m)
    return _con_proteccion(u, k, i, j, m, con_tipos_proteccion(w.proteccion, tipos, defecto))


# --------------------------------------------------------------------------- geometria
def piezas(w, em: float, espesor: float = 0.03, max_lamas: int = 60) -> list:
    """Cajas (tipo, s0, s1, d0, d1, z0, z1) de las protecciones de la ventana w.

    Coordenadas del muro: s a lo largo del tramo desde su inicio (a la izquierda vista
    desde el interior), d hacia afuera desde la cara interior (la exterior esta en em)
    y z desde el piso del nivel. Las lamas de la celosia se dibujan sin inclinar."""
    pr = w.proteccion
    x0, x1 = w.x, w.x + w.ancho
    z0, z1 = w.antepecho, w.antepecho + w.alto
    D = pr.alero_d or 0.0
    out = []
    if pr.alero_l > 0:
        out.append(("alero", x0, x1, em, em + pr.alero_l, z1 + D, z1 + D + espesor))
    for lado, P in (("izq", pr.aleta_izq_p), ("der", pr.aleta_der_p)):
        if P > 0:
            S = separacion(pr, lado)
            sa, sb = (x0 - S - espesor, x0 - S) if lado == "izq" else (x1 + S, x1 + S + espesor)
            out.append((f"aleta_{lado}", sa, sb, em, em + P, z0, z1 + D))
    E, T = pr.celosia_e, pr.celosia_t
    if E > 0 and T > 0:
        if pr.celosia_orientacion == "horizontal":
            for q in range(1, min(int(w.alto / T + 1e-9), max_lamas) + 1):
                z = z0 + q * T
                out.append(("celosia", x0, x1, em, em + E, z - espesor, z))
        else:
            for q in range(1, min(int(w.ancho / T + 1e-9), max_lamas) + 1):
                s = x0 + q * T
                out.append(("celosia", s - espesor, s, em, em + E, z0, z1))
    return out
