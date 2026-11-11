# -*- coding: utf-8 -*-
"""
Geometría plana del FAR. Solo math.

x hacia el este, y hacia el norte; azimut en grados desde el norte, horario.
"""
from __future__ import annotations

import math

EPS = 1e-9


def direccion(azimut: float) -> tuple[float, float]:
    """Vector unitario del azimut (0 = norte = (0, 1), 90 = este = (1, 0))."""
    a = math.radians(azimut)
    return math.sin(a), math.cos(a)


def azimut(dx: float, dy: float) -> float:
    """Azimut en grados del vector (dx, dy)."""
    return math.degrees(math.atan2(dx, dy))


def relativo(angulo: float) -> float:
    """Ángulo llevado a (-180, 180]."""
    a = (angulo + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def _cruz(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def impacto(ox: float, oy: float, ux: float, uy: float, poligono) -> tuple[float, float, float] | None:
    """Primer cruce del rayo o + t·u (t > 0) con el contorno del polígono.

    Devuelve (t, x, y) o None. Con u unitario, t es la distancia horizontal.
    """
    mejor = None
    n = len(poligono)
    for i in range(n):
        px, py = poligono[i]
        qx, qy = poligono[(i + 1) % n]
        ex, ey = qx - px, qy - py
        den = _cruz(ux, uy, ex, ey)
        if abs(den) < 1e-12:
            continue
        wx, wy = px - ox, py - oy
        t = _cruz(wx, wy, ex, ey) / den
        s = _cruz(wx, wy, ux, uy) / den
        if t > EPS and -EPS <= s <= 1 + EPS and (mejor is None or t < mejor):
            mejor = t
    if mejor is None:
        return None
    return mejor, ox + mejor * ux, oy + mejor * uy


def contiene(x: float, y: float, poligono) -> bool:
    """True si (x, y) está dentro del polígono (regla par-impar)."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                dentro = not dentro
    return dentro
