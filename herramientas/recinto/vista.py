# -*- coding: utf-8 -*-
"""
Planta y axonometria del recinto en SVG (Python puro, sin dependencias).

Coordenadas mundo: x = Este, y = Norte, z = arriba, origen al centro del recinto.
Cada fachada se recorre de izquierda a derecha vista desde el interior, igual
que la convencion de aletas izquierda/derecha del Manual CEV 6.7.3.2.
La estetica sale de config/estilo.yaml.
"""
from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from .geometria import Resultado, cargar_config, etiqueta
from .modelo import Recinto

ESTILO = Path(__file__).parent / "config" / "estilo.yaml"
ROSA = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
EPS = 1e-9


def cargar_estilo(ruta: Path = ESTILO) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rumbo(az: float) -> str:
    return ROSA[int(((az % 360) + 22.5) // 45) % 8]


def _rot(x: float, y: float, az: float) -> tuple:
    """Gira (x, y) en sentido horario az grados."""
    a = math.radians(az)
    c, s = math.cos(a), math.sin(a)
    return (x * c + y * s, -x * s + y * c)


def bordes(r: Recinto) -> list:
    """[(izquierda, derecha, normal exterior)] por fachada, en mundo."""
    L, W = r.largo / 2, r.ancho / 2
    local = [((-L, W), (L, W), (0, 1)), ((L, W), (L, -W), (1, 0)),
             ((L, -W), (-L, -W), (0, -1)), ((-L, -W), (-L, W), (-1, 0))]
    return [(_rot(*a, r.azimut), _rot(*b, r.azimut), _rot(*n, r.azimut))
            for a, b, n in local]


def _fachadas(r: Recinto, res: Resultado, cfg: dict) -> list:
    out = []
    for (a, b, n), m in zip(bordes(r), res.muros):
        u = ((b[0] - a[0]) / m.largo, (b[1] - a[1]) / m.largo)
        f = {"m": m, "a": a, "b": b, "u": u, "n": n, "vent": None}
        if m.ventana:
            s0 = (m.largo - m.ventana.ancho) / 2
            z0 = cfg["ventana"]["antepecho"]
            f["vent"] = (s0, s0 + m.ventana.ancho, z0, z0 + m.ventana.alto)
        out.append(f)
    return out


def _p(f: dict, s: float, d: float = 0.0) -> tuple:
    """Punto a s metros desde la izquierda del muro y d metros hacia afuera."""
    a, u, n = f["a"], f["u"], f["n"]
    return (a[0] + u[0] * s + n[0] * d, a[1] + u[1] * s + n[1] * d)


def _fav(f: dict) -> tuple:
    return tuple(f["m"].fav) if f["m"].fav else (0.0,) * 9


def _encuadre(pts: list, ancho_px: float, margen: float) -> tuple:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = (ancho_px - 2 * margen) / max(x1 - x0, y1 - y0, EPS)
    w, h = (x1 - x0) * k + 2 * margen, (y1 - y0) * k + 2 * margen
    return k, x0, y1, w, h


def _svg(w: float, h: float, cuerpo: list) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.1f} {h:.1f}">' + "".join(cuerpo) + "</svg>")


def _pts(ps) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in ps)


def _texto(x, y, t, est, color=None, ancla="middle") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{ancla}" dominant-baseline="middle" '
            f'font-family="{est["fuente"]}" font-size="{est["tamano_texto"]}" '
            f'fill="{color or est["color_texto"]}">{escape(t)}</text>')


# --------------------------------------------------------------------------- planta
def planta_svg(r: Recinto, res: Resultado, estilo: dict | None = None,
               cfg: dict | None = None) -> str:
    est = (estilo or cargar_estilo())["planta"]
    cfg = cfg or cargar_config()
    fs = _fachadas(r, res, cfg)
    lineas, etiquetas = [], []
    for f in fs:
        m = f["m"]
        lineas.append(([f["a"], f["b"]], "muro_exterior" if m.exterior else "muro_adiabatico"))
        salida = 0.0
        if f["vent"]:
            s0, s1, _, _ = f["vent"]
            _, L, Pi, Si, Pd, Sd, _, _, _ = _fav(f)
            lineas.append(([_p(f, s0), _p(f, s1)], "ventana"))
            if L > 0:
                lineas.append(([_p(f, s0), _p(f, s0, L), _p(f, s1, L), _p(f, s1)], "alero"))
            if Pi > 0:
                lineas.append(([_p(f, s0 - Si), _p(f, s0 - Si, Pi)], "aleta"))
            if Pd > 0:
                lineas.append(([_p(f, s1 + Sd), _p(f, s1 + Sd, Pd)], "aleta"))
            salida = max(L, Pi, Pd)
        etiquetas.append((_p(f, m.largo / 2, salida + est["separacion_etiqueta_m"]),
                          f"{etiqueta(m.nombre, cfg)} · {rumbo(m.azimut)}", m.exterior))

    pts = [p for pl, _ in lineas for p in pl] + [e[0] for e in etiquetas]
    k, x0, y1, w, h = _encuadre(pts, est["ancho_px"], est["margen_px"])
    mg = est["margen_px"]

    def T(p):
        return ((p[0] - x0) * k + mg, (y1 - p[1]) * k + mg)

    c = [f'<polygon class="piso" points="{_pts(T(f["a"]) for f in fs)}" '
         f'fill="{est["piso"]["relleno"]}" stroke="none"/>']
    for pl, clase in lineas:
        e = est["clases"][clase]
        trazo = f' stroke-dasharray="{e["trazo"]}"' if e.get("trazo") else ""
        c.append(f'<polyline class="{clase}" points="{_pts(T(p) for p in pl)}" fill="none" '
                 f'stroke="{e["color"]}" stroke-width="{e["grosor"]}"{trazo}/>')
    for p, t, ext in etiquetas:
        x, y = T(p)
        c.append(_texto(x, y, t, est, None if ext else est["color_texto_adiabatico"]))
    if est.get("mostrar_area"):
        x, y = T((0.0, 0.0))
        c.append(_texto(x, y, f"{res.area_piso:.1f} m²".replace(".", ","), est))
    no = est["norte"]
    xn, yb, yt = mg / 2, 14 + no["largo_px"], 14
    c.append(f'<g class="norte"><line x1="{xn}" y1="{yb}" x2="{xn}" y2="{yt}" '
             f'stroke="{no["color"]}" stroke-width="2"/>'
             f'<polygon points="{xn - 5},{yt + 8} {xn},{yt} {xn + 5},{yt + 8}" fill="{no["color"]}"/>'
             + _texto(xn, yb + 10, "N", est, no["color"]) + "</g>")
    return _svg(w, h, c)


# --------------------------------------------------------------------------- axonometria
def _protecciones_3d(f: dict) -> list:
    if not f["vent"]:
        return []
    s0, s1, z0, z1 = f["vent"]
    D, L, Pi, Si, Pd, Sd, _, _, _ = _fav(f)
    out = []
    if L > 0:
        z = z1 + D
        out.append([(_p(f, s0), z), (_p(f, s1), z), (_p(f, s1, L), z), (_p(f, s0, L), z)])
    for s, P in ((s0 - Si, Pi), (s1 + Sd, Pd)):
        if P > 0:
            out.append([(_p(f, s), z0), (_p(f, s, P), z0), (_p(f, s, P), z1), (_p(f, s), z1)])
    return out


def axonometria_svg(r: Recinto, res: Resultado, estilo: dict | None = None,
                    cfg: dict | None = None) -> str:
    est = (estilo or cargar_estilo())["axonometria"]
    cfg = cfg or cargar_config()
    fs = _fachadas(r, res, cfg)
    H = r.altura
    phi, el = math.radians(est["vista_desde"]), math.radians(est["elevacion"])
    dv = (math.sin(phi), math.cos(phi))           # hacia el observador
    rv = (-math.cos(phi), math.sin(phi))          # derecha en pantalla

    def P(q):
        (x, y), z = q
        return (x * rv[0] + y * rv[1],
                -(z * math.cos(el) - (x * dv[0] + y * dv[1]) * math.sin(el)))

    def visible(f):
        return f["n"][0] * dv[0] + f["n"][1] * dv[1] > EPS

    caras = []        # (puntos 3D, clase)
    lineas = []       # (2 puntos 3D, clase)
    textos = []       # (punto 3D, texto)
    for f in fs:
        if not visible(f):
            caras += [(q, "proteccion") for q in _protecciones_3d(f)]
    for f in fs:
        if not visible(f):
            continue
        m = f["m"]
        caras.append(([(f["a"], 0), (f["b"], 0), (f["b"], H), (f["a"], H)],
                      "cara_exterior" if m.exterior else "cara_adiabatica"))
        if f["vent"]:
            s0, s1, z0, z1 = f["vent"]
            caras.append(([(_p(f, s0), z0), (_p(f, s1), z0), (_p(f, s1), z1), (_p(f, s0), z1)],
                          "vidrio"))
            _, _, _, _, _, _, E, Tl, _ = _fav(f)
            if E > 0 and Tl > 0:
                for i in range(1, min(int((z1 - z0) / Tl), 60) + 1):
                    z = z0 + i * Tl
                    lineas.append(([(_p(f, s0), z), (_p(f, s1), z)], "celosia"))
        if est.get("mostrar_etiquetas"):
            textos.append(((_p(f, m.largo / 2, est["separacion_etiqueta_m"]), 0),
                           f"{etiqueta(m.nombre, cfg)} · {rumbo(m.azimut)}"))
    caras.append(([(f["a"], H) for f in fs],
                  "cubierta_exterior" if r.techo == "exterior" else "cubierta_adiabatica"))
    for f in fs:
        if visible(f):
            caras += [(q, "proteccion") for q in _protecciones_3d(f)]

    pts = [P(q) for qs, _ in caras for q in qs] + [P(q) for q, _ in textos]
    # _encuadre espera y hacia arriba: se invierte el signo
    k, x0, y1, w, h = _encuadre([(x, -y) for x, y in pts], est["ancho_px"], est["margen_px"])
    mg = est["margen_px"]

    def S(q):
        x, y = P(q)
        return ((x - x0) * k + mg, (y1 + y) * k + mg)

    c = []
    for qs, clase in caras:
        e = est["clases"][clase]
        c.append(f'<polygon class="{clase}" points="{_pts(S(q) for q in qs)}" fill="{e["relleno"]}" '
                 f'fill-opacity="{e["opacidad"]}" stroke="{e["borde"]}" '
                 f'stroke-width="{e["grosor"]}" stroke-linejoin="round"/>')
    for qs, clase in lineas:
        e = est["clases"][clase]
        c.append(f'<polyline class="{clase}" points="{_pts(S(q) for q in qs)}" fill="none" '
                 f'stroke="{e["borde"]}" stroke-width="{e["grosor"]}"/>')
    for q, t in textos:
        x, y = S(q)
        c.append(_texto(x, y, t, est))
    return _svg(w, h, c)
