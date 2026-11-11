# -*- coding: utf-8 -*-
"""
Edicion de un tabique (modelo.Tabique) con la herramienta Mover, sin interfaz (se
prueba sin NiceGUI).

Con un tabique elegido, sus extremos muestran asas (svg_asas):
  - arrastrar un extremo lo mueve; el otro queda fijo. Salvo libre (Shift), queda a un
    angulo multiplo de snap.angulo y un largo multiplo de snap.largo_m desde el otro
    extremo y, si pasa cerca de un muro (radio), se lleva hasta el (como al dibujarlo);
  - arrastrar el cuerpo mueve el tabique entero, en pasos de snap.largo_m.
extremo: 0 = a, 1 = b, cualquier otro valor (-1) = el cuerpo.
"""
from __future__ import annotations

from . import editor
from .edicion_obstaculos import svg_puntos


def tocar_extremo(tb, p, tol: float):
    """0 (a) o 1 (b) si p esta a menos de tol de un extremo del tabique (el mas cercano); None
    si no."""
    da, db = editor.distancia(p, tb.a), editor.distancia(p, tb.b)
    if min(da, db) > tol:
        return None
    return 0 if da <= db else 1


def arrastrar(u, k: int, t: int, extremo: int, p0, p, libre: bool = False, paso: float | None = None,
              radio: float = 0.0):
    """La unidad con el extremo (0 o 1) o el cuerpo (otro valor) del tabique t del nivel k
    arrastrado de p0 a p."""
    n = u.niveles[k]
    tb = n.tabiques[t]
    if extremo in (0, 1):
        otro = tb.b if extremo == 0 else tb.a
        if libre:
            q = editor.ajustar(p)
        else:
            q = editor.ajustar_desde(otro, p)
            if radio > 0:
                q = editor.extender_a_muro(n, otro, q, radio)
        return editor.mover_tabique(u, k, t, **{"a" if extremo == 0 else "b": q})
    dx, dy = p[0] - p0[0], p[1] - p0[1]
    if not libre:
        dx, dy = editor.redondear(dx, paso), editor.redondear(dy, paso)
    return editor.mover_tabique(u, k, t, a=(tb.a[0] + dx, tb.a[1] + dy), b=(tb.b[0] + dx, tb.b[1] + dy))


def svg_asas(tb, v, est: dict) -> str:
    """Asas de los extremos del tabique (v: vista_planta.Vista; est: config planta:)."""
    return svg_puntos([tb.a, tb.b], v, est)
