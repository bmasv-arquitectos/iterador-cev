# -*- coding: utf-8 -*-
"""
Planta de un nivel de la Unidad en SVG, para el editor (app_unidad) y para
exportar. Python puro.

Mundo: metros, x a la derecha, y hacia arriba (modelo.py). Pantalla: px, y hacia
abajo. Vista guarda la escala (px/m) y la esquina superior izquierda en mundo;
px() y mundo() convierten ida y vuelta, asi un clic en la imagen vuelve a metros.
zoom() acerca respecto del centro, zoom_en() respecto de un punto (el cursor),
que queda fijo en la pantalla, desplazar() mueve el dibujo junto con el raton y
redimensionar() cambia el tamano del lienzo (la ventana) sin mover el centro.
contenido() entrega solo los elementos (lo que va dentro del <svg> que pone
ui.interactive_image); svg_completo() los envuelve para guardar o probar.
Ventanas en celeste y puertas en verde, sobre la linea del muro.
Obstrucciones dibujadas del nivel (planta.obstaculo): la horizontal como un
rectangulo semitransparente con una diagonal; la vertical como una linea gruesa.
Balcones (planta.balcon, verde): su poligono con borde segmentado (no hacen sombra).
Un perimetro abierto (borrador) se dibuja segmentado; su primer punto, mas
grande, es donde se cierra. Mientras se dibuja una obstruccion (obstaculo = (tipo,
primer punto), o ("balcon", puntos, snap)) se ve su previa; en el balcon, una marca
(planta.snap) dice a que se pego el cursor: un anillo en un vertice o en el punto de
cierre, un cuadrado en un muro. La estetica sale de config/editor.yaml (planta:).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import quote
from xml.sax.saxutils import escape

from . import editor
from .modelo import Nivel, Unidad

OBSTACULO = {"color": "#57534e", "relleno": "#d6d3d1", "opacidad": 0.55, "grosor": 1.5, "grosor_vertical": 5}
BALCON = {"color": "#15803d", "relleno": "#bbf7d0", "opacidad": 0.6, "grosor": 1.5, "trazo": "5 3"}
SNAP = {"color": "#16a34a", "radio": 9, "grosor": 2}


def num(v: float, d: int = 2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


@dataclass(frozen=True)
class Vista:
    ancho_px: float
    alto_px: float
    escala: float                  # px por metro
    x0: float                      # x de mundo en el borde izquierdo
    y1: float                      # y de mundo en el borde superior

    def px(self, p) -> tuple:
        return ((p[0] - self.x0) * self.escala, (self.y1 - p[1]) * self.escala)

    def mundo(self, x: float, y: float) -> tuple:
        return (self.x0 + x / self.escala, self.y1 - y / self.escala)

    def metros(self, px: float) -> float:
        return px / self.escala

    def centro(self) -> tuple:
        return self.mundo(self.ancho_px / 2, self.alto_px / 2)

    def zoom(self, factor: float) -> "Vista":
        return self.zoom_en(factor, self.centro())

    def zoom_en(self, factor: float, p, escala_min: float = 0.0, escala_max: float = math.inf) -> "Vista":
        """Escala por factor dejando el punto de mundo p en el mismo lugar de la pantalla."""
        e = min(max(self.escala * factor, escala_min), escala_max)
        sx, sy = self.px(p)
        return Vista(self.ancho_px, self.alto_px, e, p[0] - sx / e, p[1] + sy / e)

    def desplazar(self, dx_px: float, dy_px: float) -> "Vista":
        """El dibujo se mueve dx, dy pixeles (lo que estaba bajo el raton lo sigue)."""
        return Vista(self.ancho_px, self.alto_px, self.escala, self.x0 - dx_px / self.escala,
                     self.y1 + dy_px / self.escala)

    def redimensionar(self, ancho_px: float, alto_px: float) -> "Vista":
        """Otro tamano de lienzo con la misma escala y el mismo centro."""
        cx, cy = self.centro()
        e = self.escala
        return Vista(ancho_px, alto_px, e, cx - ancho_px / 2 / e, cy + alto_px / 2 / e)


def encuadrar(puntos, ancho_px: float, alto_px: float, margen_px: float, extension_min_m: float) -> Vista:
    pts = list(puntos) or [(0.0, 0.0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w = max(max(xs) - min(xs), extension_min_m)
    h = max(max(ys) - min(ys), extension_min_m)
    e = min((ancho_px - 2 * margen_px) / w, (alto_px - 2 * margen_px) / h)
    return Vista(ancho_px, alto_px, e, cx - ancho_px / 2 / e, cy + alto_px / 2 / e)


def encuadrar_unidad(u: Unidad, lienzo: dict, extra=()) -> Vista:
    return encuadrar([p for n in u.niveles for p in n.vertices] + list(extra), lienzo["ancho_px"],
                     lienzo["alto_px"], lienzo["margen_px"], lienzo["extension_min_m"])


def fuente_vacia(ancho: float, alto: float, fondo: str) -> str:
    """Imagen de fondo para ui.interactive_image (fija el tamano en px)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho:.0f}" height="{alto:.0f}">'
           f'<rect width="100%" height="100%" fill="{fondo}"/></svg>')
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


# --------------------------------------------------------------------------- piezas
def _trazo(trazo) -> str:
    return f' stroke-dasharray="{trazo}"' if trazo else ""


def _linea(v: Vista, a, b, color, grosor, trazo=None, clase="") -> str:
    x1, y1 = v.px(a)
    x2, y2 = v.px(b)
    return (f'<line class="{clase}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{grosor}"{_trazo(trazo)}/>')


def _poligono(v: Vista, pts, relleno, borde="none", grosor=0, trazo=None, clase="", opacidad=None) -> str:
    ps = " ".join(f"{x:.1f},{y:.1f}" for x, y in (v.px(p) for p in pts))
    op = f' fill-opacity="{opacidad}"' if opacidad is not None else ""
    return (f'<polygon class="{clase}" points="{ps}" fill="{relleno}"{op} stroke="{borde}" '
            f'stroke-width="{grosor}"{_trazo(trazo)}/>')


def _circulo(v: Vista, p, r, relleno, borde, clase="", grosor=1.5) -> str:
    x, y = v.px(p)
    return (f'<circle class="{clase}" cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{relleno}" '
            f'stroke="{borde}" stroke-width="{grosor}"/>')


def _texto(x, y, t, tx: dict, color=None, ancla="middle") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{ancla}" dominant-baseline="middle" '
            f'font-family="{tx["fuente"]}" font-size="{tx["tamano"]}" fill="{color or tx["color"]}" '
            f'stroke="{tx["halo"]}" stroke-width="3" paint-order="stroke">{escape(t)}</text>')


def _grilla(v: Vista, g: dict) -> list:
    paso = g["paso_m"]
    xa, yt = v.mundo(0, 0)
    xb, yb = v.mundo(v.ancho_px, v.alto_px)
    while (xb - xa) / paso > g["max_lineas"]:
        paso *= g["mayor_cada"]
    out = []
    for i in range(math.ceil(xa / paso), math.floor(xb / paso) + 1):
        x = (i * paso - v.x0) * v.escala
        color = g["color_mayor"] if i % g["mayor_cada"] == 0 else g["color"]
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{v.alto_px:.0f}" stroke="{color}" '
                   f'stroke-width="{g["grosor"]}"/>')
    for j in range(math.ceil(yb / paso), math.floor(yt / paso) + 1):
        y = (v.y1 - j * paso) * v.escala
        color = g["color_mayor"] if j % g["mayor_cada"] == 0 else g["color"]
        out.append(f'<line x1="0" y1="{y:.1f}" x2="{v.ancho_px:.0f}" y2="{y:.1f}" stroke="{color}" '
                   f'stroke-width="{g["grosor"]}"/>')
    return out


def _es(sel, tipo, **kw) -> bool:
    return sel is not None and sel.tipo == tipo and all(getattr(sel, c) == x for c, x in kw.items())


def _rect_obstaculo(a, b) -> tuple:
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _obstaculos(n: Nivel, v: Vista, est: dict, sel) -> list:
    e = {**OBSTACULO, **(est.get("obstaculo") or {})}
    eb = {**BALCON, **(est.get("balcon") or {})}
    color_sel = est["seleccion"]["color"]
    out = []
    for t, o in enumerate(n.obstaculos):
        elegido = _es(sel, "obstaculo", indice=t)
        if o.tipo == "balcon":
            color = color_sel if elegido else eb["color"]
            out.append(_poligono(v, o.vertices, eb["relleno"], color, eb["grosor"] * (2 if elegido else 1),
                                 eb.get("trazo"), "balcon", eb["opacidad"]))
            continue
        color = color_sel if elegido else e["color"]
        if o.tipo == "horizontal":
            pts = _rect_obstaculo(o.a, o.b)
            out.append(_poligono(v, pts, e["relleno"], color, e["grosor"] * (2 if elegido else 1),
                                 clase="obstaculo", opacidad=e["opacidad"]))
            out.append(_linea(v, pts[0], pts[2], color, 0.8, None, "obstaculo"))
        else:
            out.append(_linea(v, o.a, o.b, color, e["grosor_vertical"], None, "obstaculo"))
    return out


def _nivel(n: Nivel, v: Vista, est: dict, sel) -> list:
    out = [_poligono(v, n.vertices, est["piso"]["relleno"], clase="piso")]
    m, tx = est["muro"], est["texto"]
    color_sel = est["seleccion"]["color"]
    etiquetas = []
    for i, lado in enumerate(n.lados):
        a, b = editor.extremos(n, i)
        ux, uy, _ = editor.direccion(a, b)
        nx, ny = -uy, ux
        lim = editor.limites(n, i)
        varios = len(lado.tramos) > 1
        for j, t in enumerate(lado.tramos):
            pa = (a[0] + ux * lim[j], a[1] + uy * lim[j])
            pb = (a[0] + ux * lim[j + 1], a[1] + uy * lim[j + 1])
            e = m["exterior" if t.exterior else "adiabatico"]
            color = color_sel if _es(sel, "tramo", lado=i, tramo=j) else e["color"]
            out.append(_linea(v, pa, pb, color, e["grosor"], e.get("trazo"), "muro"))
            for tipo, _, w in editor.vanos(t):
                wa = (pa[0] + ux * w.x, pa[1] + uy * w.x)
                wb = (pa[0] + ux * (w.x + w.ancho), pa[1] + uy * (w.x + w.ancho))
                out.append(_linea(v, wa, wb, est[tipo]["color"], est[tipo]["grosor"], clase=tipo))
            sm = (lim[j] + lim[j + 1]) / 2
            x, y = v.px((a[0] + ux * sm, a[1] + uy * sm))
            d = tx["separacion_px"]
            nombre = f"L{i + 1}" + (f"-T{j + 1}" if varios else "")
            etiquetas.append(_texto(x + nx * d, y - ny * d, f"{nombre} · {num(lim[j + 1] - lim[j])}", tx,
                                    None if t.exterior else m["adiabatico"]["color"]))
    tb_e = est["tabique"]
    for t_i, tb in enumerate(n.tabiques):
        color = color_sel if _es(sel, "tabique", indice=t_i) else tb_e["color"]
        out.append(_linea(v, tb.a, tb.b, color, tb_e["grosor"], clase="tabique"))
    out += _obstaculos(n, v, est, sel)
    vt, ct = est["vertice"], est["corte"]
    for i, lado in enumerate(n.lados):
        for c_i, c in enumerate(lado.cortes):
            color = color_sel if _es(sel, "corte", lado=i, indice=c_i) else ct["relleno"]
            out.append(_circulo(v, editor.punto_en(n, i, c), ct["radio"], color, vt["borde"], "corte"))
    for i, p in enumerate(n.vertices):
        color = color_sel if _es(sel, "vertice", indice=i) else vt["relleno"]
        out.append(_circulo(v, p, vt["radio"], color, vt["borde"], "vertice"))
        if vt.get("etiquetas"):
            x, y = v.px(p)
            etiquetas.append(_texto(x + vt["dx"], y - vt["dy"], f"V{i + 1}", tx, vt["color_etiqueta"], "start"))
    return out + etiquetas


def _marca_snap(v: Vista, est: dict, cursor, snap) -> list:
    """Anillo (vertice o cierre) o cuadrado (muro) donde se pego el cursor."""
    if not snap or cursor is None:
        return []
    s = {**SNAP, **(est.get("snap") or {})}
    if snap in ("vertice", "cierre"):
        return [_circulo(v, cursor, s["radio"], "none", s["color"], "snap", s["grosor"])]
    x, y = v.px(cursor)
    r = float(s["radio"]) * 0.75
    return [f'<rect class="snap" x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" '
            f'fill="none" stroke="{s["color"]}" stroke-width="{s["grosor"]}"/>']


def _borrador_balcon(v: Vista, est: dict, puntos, cursor, snap=None) -> list:
    """Balcon que se esta dibujando: la polilinea hasta el cursor, sus puntos (el primero, mas
    grande, cierra), la marca del snap y el largo y angulo del tramo actual."""
    b, tx = est["borrador"], est["texto"]
    pts = list(puntos)
    out = []
    linea = pts + ([cursor] if cursor is not None and pts else [])
    if len(linea) >= 2:
        ps = " ".join(f"{x:.1f},{y:.1f}" for x, y in (v.px(p) for p in linea))
        out.append(f'<polyline class="borrador" points="{ps}" fill="none" stroke="{b["color"]}" '
                   f'stroke-width="{b["grosor"]}"{_trazo(b.get("trazo"))}/>')
    radio = est["vertice"]["radio"]
    for i, p in enumerate(pts):
        primero = i == 0 and len(pts) >= 3
        out.append(_circulo(v, p, radio * b["factor_primero"] if primero else radio,
                            b["color"] if not primero else est["fondo"], b["color"], "borrador"))
    out += _marca_snap(v, est, cursor, snap)
    if cursor is not None:
        out.append(_circulo(v, cursor, 3, b["color"], b["color"], "cursor"))
        if pts and editor.distancia(pts[-1], cursor) > 1e-9:
            x, y = v.px(cursor)
            out.append(_texto(x + 12, y - 14, f"{num(editor.distancia(pts[-1], cursor))} m · "
                                              f"{editor.angulo(pts[-1], cursor):.0f}°", tx, b["color"], "start"))
    return out


def _borrador(v: Vista, est: dict, borrador, cursor, tabique, dibujando: bool, obstaculo=None) -> list:
    if obstaculo is not None and obstaculo[0] == "balcon":
        return _borrador_balcon(v, est, obstaculo[1] or (), cursor, obstaculo[2] if len(obstaculo) > 2 else None)
    b, tx = est["borrador"], est["texto"]
    out = []
    pts = list(borrador) + ([cursor] if dibujando and cursor is not None and borrador else [])
    if len(pts) >= 2:
        ps = " ".join(f"{x:.1f},{y:.1f}" for x, y in (v.px(p) for p in pts))
        out.append(f'<polyline class="borrador" points="{ps}" fill="none" stroke="{b["color"]}" '
                   f'stroke-width="{b["grosor"]}"{_trazo(b.get("trazo"))}/>')
    radio = est["vertice"]["radio"]
    for i, p in enumerate(borrador):
        primero = i == 0 and len(borrador) >= 3
        out.append(_circulo(v, p, radio * b["factor_primero"] if primero else radio,
                            b["color"] if not primero else est["fondo"], b["color"], "borrador"))
    if tabique is not None and cursor is not None:
        out.append(_linea(v, tabique, cursor, b["color"], b["grosor"], b.get("trazo"), "borrador"))
    ancla = obstaculo[1] if obstaculo is not None and obstaculo[1] is not None else None
    if ancla is not None and cursor is not None:
        if obstaculo[0] == "vertical":
            out.append(_linea(v, ancla, cursor, b["color"], b["grosor"], b.get("trazo"), "borrador"))
        else:
            out.append(_poligono(v, _rect_obstaculo(ancla, cursor), "none", b["color"], b["grosor"],
                                 b.get("trazo"), "borrador"))
    if cursor is not None:
        out.append(_circulo(v, cursor, 3, b["color"], b["color"], "cursor"))
        x, y = v.px(cursor)
        if ancla is not None and obstaculo[0] == "horizontal":
            out.append(_texto(x + 12, y - 14, f"{num(abs(cursor[0] - ancla[0]))} × {num(abs(cursor[1] - ancla[1]))} m",
                              tx, b["color"], "start"))
            return out
        ultimo = tabique if tabique is not None else (
            ancla if ancla is not None else (borrador[-1] if dibujando and borrador else None))
        if ultimo is not None and editor.distancia(ultimo, cursor) > 1e-9:
            ang = editor.angulo(ultimo, cursor)
            out.append(_texto(x + 12, y - 14, f"{num(editor.distancia(ultimo, cursor))} m · {ang:.0f}°", tx,
                              b["color"], "start"))
    return out


def _norte(v: Vista, est: dict, azimut_y: float) -> list:
    no = est["norte"]
    a = math.radians(azimut_y)
    dx, dy = -math.sin(a), -math.cos(a)          # norte en pantalla (y hacia abajo)
    cx = no["x_px"] if no["x_px"] >= 0 else v.ancho_px + no["x_px"]
    cy = no["y_px"] if no["y_px"] >= 0 else v.alto_px + no["y_px"]
    L = no["largo_px"]
    x0, y0 = cx - dx * L / 2, cy - dy * L / 2
    x1, y1 = cx + dx * L / 2, cy + dy * L / 2
    px, py = -dy, dx
    punta = (f"{x1:.1f},{y1:.1f} {x1 - dx * 9 + px * 5:.1f},{y1 - dy * 9 + py * 5:.1f} "
             f"{x1 - dx * 9 - px * 5:.1f},{y1 - dy * 9 - py * 5:.1f}")
    return [f'<g class="norte"><line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            f'stroke="{no["color"]}" stroke-width="2"/><polygon points="{punta}" fill="{no["color"]}"/>'
            + _texto(x1 + dx * 10, y1 + dy * 10, "N", est["texto"], no["color"]) + "</g>"]


# --------------------------------------------------------------------------- salida
def contenido(u: Unidad, k: int, v: Vista, est: dict, seleccion=None, borrador=(), cursor=None,
              tabique=None, dibujando: bool = False, obstaculo=None) -> str:
    """Elementos SVG del nivel k (los demas niveles, en gris segmentado).
    obstaculo: (tipo, primer punto o None) de la obstruccion que se esta dibujando, o
    ("balcon", puntos, snap) del balcon que se esta dibujando."""
    out = _grilla(v, est["grilla"])
    o = est["otro_nivel"]
    for kk, n in enumerate(u.niveles):
        if kk != k:
            out.append(_poligono(v, n.vertices, "none", o["color"], o["grosor"], o.get("trazo"), "otro_nivel"))
    if 0 <= k < len(u.niveles):
        out += _nivel(u.niveles[k], v, est, seleccion)
    out += _borrador(v, est, borrador, cursor, tabique, dibujando, obstaculo)
    out += _norte(v, est, u.azimut_y)
    return "".join(out)


def svg_completo(u: Unidad, k: int, v: Vista, est: dict, **kw) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{v.ancho_px:.0f}" height="{v.alto_px:.0f}" '
            f'viewBox="0 0 {v.ancho_px:.0f} {v.alto_px:.0f}"><rect width="100%" height="100%" '
            f'fill="{est["fondo"]}"/>' + contenido(u, k, v, est, **kw) + "</svg>")
