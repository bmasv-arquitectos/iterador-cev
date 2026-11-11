# -*- coding: utf-8 -*-
"""
Edicion de una obstruccion dibujada (modelo.Obstaculo) con asas en la planta,
sin interfaz (la usa la herramienta Mover del editor; se prueba sin NiceGUI).

Asas (clave, punto):
  - horizontal: las cuatro esquinas (x0, y0) ... y el medio de cada borde (x0,),
    (x1,), (y0,), (y1,). x0/x1 = lado izquierdo/derecho, y0/y1 = abajo/arriba.
    Un borde no pasa al otro lado: el rectangulo no baja de tramo_min.
  - vertical: sus extremos (a,) (el que nace en el muro) y (b,).
  - balcon: cada vertice (v, i).
Ajuste (salvo libre = Shift): el rectangulo a la grilla de paso y a los muros
cercanos (radio); el vertice de un balcon a un vertice de la unidad, si no a la grilla
y al muro; el extremo de una vertical a 10 grados y 10 cm desde el otro, y su base se
pega al muro. Arrastrar el cuerpo (mover entero) es editor.mover_obstaculo.
svg_asas() dibuja las asas (planta.asa en config/editor.yaml, opcional); svg_puntos()
las de cualquier lista de puntos (tambien los tabiques).

snap_balcon(): el punto de un balcon que se esta dibujando y a que se pego, para que la
planta lo marque. Prioridad: el primer punto (cierre, con 3 o mas puntos), un vertice
de la unidad, el muro (siguiendo la direccion desde el punto anterior, o el muro que
queda bajo el cursor) y si no, el ajuste de 10 grados y 10 cm.
"""
from __future__ import annotations

from . import editor

ASA = {"lado_px": 7, "relleno": "#ffffff", "grosor": 1.5}
ESQUINAS = (("x0", "y0"), ("x1", "y0"), ("x1", "y1"), ("x0", "y1"))


def _rect(o) -> dict:
    x0, x1 = sorted((o.a[0], o.b[0]))
    y0, y1 = sorted((o.a[1], o.b[1]))
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def asas(o) -> list:
    """[(clave, (x, y))] de las asas de la obstruccion."""
    if o.tipo == "vertical":
        return [(("a",), tuple(o.a)), (("b",), tuple(o.b))]
    if o.tipo == "balcon":
        return [(("v", i), tuple(q)) for i, q in enumerate(o.vertices)]
    r = _rect(o)
    xm, ym = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
    out = [(c, (r[c[0]], r[c[1]])) for c in ESQUINAS]
    out += [(("x0",), (r["x0"], ym)), (("x1",), (r["x1"], ym)), (("y0",), (xm, r["y0"])), (("y1",), (xm, r["y1"]))]
    return out


def tocar_asa(o, p, tol: float):
    """Clave del asa mas cercana a p (a menos de tol), o None."""
    mejor = None
    for clave, q in asas(o):
        d = editor.distancia(p, q)
        if d <= tol and (mejor is None or d < mejor[0]):
            mejor = (d, clave)
    return None if mejor is None else mejor[1]


def cursor(clave, tipo: str):
    """Cursor CSS sobre un asa (None si no hay asa). En pantalla y crece hacia arriba."""
    if clave is None:
        return None
    if tipo != "horizontal":
        return "crosshair"
    if len(clave) == 2:
        return "nesw-resize" if (clave[0] == "x0") == (clave[1] == "y0") else "nwse-resize"
    return "ew-resize" if clave[0][0] == "x" else "ns-resize"


def snap_balcon(n, p, previos, libre: bool = False, radio: float = 0.0, paso: float | None = None,
                cierre: float | None = None) -> tuple:
    """(punto, tipo) de un balcon que se dibuja; tipo: cierre (el primer punto), vertice (de la
    unidad), muro o None. n: el nivel (None: sin unidad); previos: los puntos ya puestos;
    cierre: distancia para cerrar en el primer punto (None: radio)."""
    previos = [tuple(q) for q in previos]
    if libre:
        return editor.ajustar(p), None
    if len(previos) >= 3 and editor.distancia(p, previos[0]) <= (radio if cierre is None else cierre):
        return previos[0], "cierre"
    verts = list(n.vertices) if n is not None else []
    v = editor.atraer(p, verts, radio)
    if v is not None:
        return v, "vertice"
    if previos:
        q = editor.ajustar_desde(previos[-1], p, alinear=previos + verts, radio=radio)
    else:
        q = editor.ajustar(p, paso)
    if n is not None:
        if previos:
            e = editor.extender_a_muro(n, previos[-1], q, radio)     # sigue la direccion hasta el muro
            if e is not q:
                return e, "muro"
        m = editor.proyectar_a_muro(n, q, radio)
        if m is not q:
            return m, "muro"
        m = editor.proyectar_a_muro(n, p, radio)                       # el muro bajo el cursor
        if m is not p:
            return m, "muro"
    return q, None


def redimensionar(u, k: int, t: int, clave, p, libre: bool = False, paso: float | None = None,
                  radio: float = 0.0):
    """La unidad con el asa `clave` de la obstruccion t del nivel k llevada a p."""
    n = u.niveles[k]
    o = n.obstaculos[t]
    mn = editor._dib()["tramo_min"]
    if o.tipo == "balcon":
        if libre:
            q = editor.ajustar(p)
        else:
            q = editor.atraer(p, list(n.vertices), radio) or editor.ajustar(p, paso)
            if radio > 0:
                q = editor.proyectar_a_muro(n, q, radio)
        vs = list(o.vertices)
        vs[int(clave[1])] = editor._rp(q)
        return editor.cambiar_obstaculo(u, k, t, **editor.con_vertices(vs))
    if o.tipo == "vertical":
        mueve = clave[0]
        otro = o.b if mueve == "a" else o.a
        if libre:
            q = editor.ajustar(p)
        else:
            q = editor.ajustar_desde(otro, p)
            if mueve == "a" and radio > 0:
                q = editor.proyectar_a_muro(n, q, radio)
        if editor.distancia(q, otro) < mn:
            raise ValueError("La obstrucción es demasiado pequeña")
        return editor.cambiar_obstaculo(u, k, t, **{mueve: editor._rp(q)})
    q = editor.ajustar(p) if libre else editor.ajustar(p, paso)
    if not libre and radio > 0:
        q = editor.proyectar_a_muro(n, q, radio)
    r = _rect(o)
    for b in clave:
        v = q[0] if b[0] == "x" else q[1]
        if b == "x0":
            r["x0"] = min(v, r["x1"] - mn)
        elif b == "x1":
            r["x1"] = max(v, r["x0"] + mn)
        elif b == "y0":
            r["y0"] = min(v, r["y1"] - mn)
        else:
            r["y1"] = max(v, r["y0"] + mn)
    return editor.cambiar_obstaculo(u, k, t, a=editor._rp((r["x0"], r["y0"])), b=editor._rp((r["x1"], r["y1"])))


def svg_puntos(puntos, v, est: dict) -> str:
    """Asas cuadradas en esos puntos (v: vista_planta.Vista; est: config planta:)."""
    e = {**ASA, **(est.get("asa") or {})}
    color = e.get("borde") or est["seleccion"]["color"]
    lado = float(e["lado_px"])
    out = []
    for q in puntos:
        x, y = v.px(q)
        out.append(f'<rect class="asa" x="{x - lado / 2:.1f}" y="{y - lado / 2:.1f}" width="{lado:.1f}" '
                   f'height="{lado:.1f}" fill="{e["relleno"]}" stroke="{color}" stroke-width="{e["grosor"]}"/>')
    return "".join(out)


def svg_asas(o, v, est: dict) -> str:
    """Asas de la obstruccion en SVG (v: vista_planta.Vista; est: config planta:)."""
    return svg_puntos([q for _, q in asas(o)], v, est)
