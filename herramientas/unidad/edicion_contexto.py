# -*- coding: utf-8 -*-
"""
Edicion con el raton de los volumenes de contexto (vista Contexto del editor), sin
interfaz: ajuste del cursor, asas y arrastres. La usa app_unidad/contexto_ui.py.

Ajuste (Shift lo apaga):
  - primer punto (rectangulo o polilinea): a cotas redondas desde las caras de la
    unidad (contexto.ajustar_a_cotas), asi queda referido a la unidad;
  - segunda esquina del rectangulo: ancho y fondo multiplos de paso;
  - siguientes puntos de la polilinea: en horizontal o vertical desde el anterior
    (sin diagonales) y con largo multiplo de paso.
Asas del volumen elegido (Mover): esquinas (mueven el vertice y sus dos lados), lados
(en paralelo) y el cuerpo (todo el volumen). Los desplazamientos se redondean a paso.
"""
from __future__ import annotations

import math

from . import contexto as cx


def _r(x: float, paso) -> float:
    return x if not paso else round(x / paso) * paso


def ajustar(u, p, ancla, modo: str, libre: bool, paso, espesor: float = 0.0) -> tuple:
    """Punto ajustado. ancla: el punto anterior (None si es el primero); modo: rect | poli."""
    p = (float(p[0]), float(p[1]))
    if ancla is None:
        return p if libre else cx.ajustar_a_cotas(u, p, paso, espesor)
    ax, ay = float(ancla[0]), float(ancla[1])
    if modo == "poli":
        if abs(p[0] - ax) >= abs(p[1] - ay):
            return (p[0] if libre else ax + _r(p[0] - ax, paso), ay)
        return (ax, p[1] if libre else ay + _r(p[1] - ay, paso))
    if libre:
        return p
    return (ax + _r(p[0] - ax, paso), ay + _r(p[1] - ay, paso))


def asas(vs) -> list:
    """[(tipo, j, punto)]: esquinas y puntos medios de los lados."""
    n = len(vs)
    out = [("esquina", j, tuple(vs[j])) for j in range(n)]
    out += [("lado", j, ((vs[j][0] + vs[(j + 1) % n][0]) / 2, (vs[j][1] + vs[(j + 1) % n][1]) / 2))
            for j in range(n)]
    return out


def tocar_asa(vs, p, radio: float):
    """("esquina", j) o ("lado", j) bajo el cursor (las esquinas mandan), o None."""
    n = len(vs)
    dist, j = min((math.hypot(p[0] - x, p[1] - y), j) for j, (x, y) in enumerate(vs))
    if dist <= radio:
        return ("esquina", j)
    dist, j = min((cx.distancia_segmento(p, vs[j], vs[(j + 1) % n]), j) for j in range(n))
    if dist <= radio:
        return ("lado", j)
    return None


def arrastrar(u, i: int, asa, p0, p, libre: bool, paso):
    """Unidad con el volumen i arrastrado de p0 a p por el asa (None o ("cuerpo", 0): todo)."""
    dx, dy = p[0] - p0[0], p[1] - p0[1]
    tipo = asa[0] if asa else "cuerpo"
    if tipo == "lado":
        nx, ny = cx.normal_lado(u.contexto[i].vertices, asa[1])
        d = dx * nx + dy * ny
        return cx.mover_lado(u, i, asa[1], d if libre else _r(d, paso))
    if not libre:
        dx, dy = _r(dx, paso), _r(dy, paso)
    if tipo == "esquina":
        x, y = u.contexto[i].vertices[asa[1]]
        return cx.mover_esquina(u, i, asa[1], (x + dx, y + dy))
    return cx.mover(u, i, dx, dy)


def cursor(asa, vs) -> str | None:
    """Cursor CSS sobre un asa."""
    if asa is None:
        return None
    tipo, j = asa
    if tipo == "esquina":
        return "nwse-resize"
    if tipo == "cuerpo":
        return "move"
    a, b = vs[j], vs[(j + 1) % len(vs)]
    return "ns-resize" if abs(a[1] - b[1]) <= 1e-9 else "ew-resize"
