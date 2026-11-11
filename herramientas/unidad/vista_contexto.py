# -*- coding: utf-8 -*-
"""
Vista Contexto del editor en SVG (Python puro): la planta donde se dibujan los
volumenes del entorno (FAR dibujado) referidos a la unidad.

  - La unidad, solo como referencia (aca no se edita): el contorno EXTERIOR de cada
    nivel (la cara interior corrida el espesor de muro), relleno y continuo el nivel 1
    y segmentado los de arriba, mas el contorno interior fino; y el rotulo de las caras
    del nivel 1 paralelas a los ejes ("L1 N"), que son las que usan las cotas.
  - Los volumenes de contexto (Unidad.contexto), semitransparentes, con nombre y altura.
  - Cotas (contexto.cotas): del cursor mientras se dibuja, del rectangulo que se esta
    dibujando y del volumen elegido. Una por eje, desde la cara mas cercana; si se mide
    a la prolongacion de la cara, esa prolongacion va segmentada.
  - FAR de una orientacion (far = (PuntoFar, ResultadoPunto o None, segmentos de sus
    muros)): los muros que definen el punto, el punto de referencia, el semicirculo con
    sus 5 divisiones (1 a 5 de izquierda a derecha mirando hacia afuera) y cada
    obstruccion como el obstaculo equivalente de la ficha: la cuerda de ancho D a la
    distancia B, perpendicular a B, y el sector que tapa. Las omitidas (descarte o
    mas de 8), en gris segmentado.
  - Asas del volumen elegido (con Mover): esquinas y puntos medios de los lados.
La estetica sale de config/editor.yaml: planta: (grilla, texto, borrador, seleccion,
vertice, norte) y vista_contexto: (unidad, volumen, cota, asa, far, textos).
"""
from __future__ import annotations

import math

from . import contexto as cx
from . import edicion_contexto as ec
from .contexto_far import orientacion
from .modelo import Unidad
from .vista_planta import Vista, _circulo, _grilla, _linea, _norte, _poligono, _texto, _trazo, encuadrar, num

DEFECTO = {
    "unidad": {"relleno": "#f6f4ef", "color": "#6b7280", "grosor": 2, "interior": "#c4c9cf",
               "trazo_otro_nivel": "6 4", "rotulos": True},
    "volumen": {"relleno": "#94a3b8", "opacidad": 0.3, "color": "#64748b", "grosor": 1.5},
    "cota": {"color": "#2563eb", "grosor": 1, "extension": "#93c5fd", "trazo": "4 3", "marca_px": 5,
             "decimales": 2},
    "asa": {"lado_px": 8, "relleno": "#ffffff"},
    "far": {"color": "#0d9488", "relleno": "#14b8a6", "opacidad": 0.18, "grosor": 1.5, "trazo": "5 4",
            "muro_grosor": 6, "omitida": "#9ca3af", "radio_min_m": 12, "margen": 1.1, "segmentos": 64},
}
TEXTOS = {
    "etiqueta": "{nombre} · {h} m",
    "cota_separacion": "{d} m · {cara} {rumbo}",
    "cota_desfase": "{d} m · plano {cara} {rumbo}",
    "rectangulo": "{ancho} × {fondo} m",
    "tramo": "{largo} m",
    "cara": "{lado} {rumbo}",
    "far_rotulo": "FAR {o} · z = {z} m",
    "far_division": "{k}",
    "far_tramo": "{volumen} · A {a} · B {b} · D {d}",
}


def estilo(planta: dict, vc: dict | None = None, textos: dict | None = None) -> dict:
    """planta: (config/editor.yaml) con las secciones de vista_contexto: y los textos."""
    vc = vc or {}
    e = dict(planta)
    for k, d in DEFECTO.items():
        e[k] = {**d, **(vc.get(k) or {})}
    e["textos"] = {**TEXTOS, **(vc.get("textos") or {}), **(textos or {})}
    return e


def encuadre(u: Unidad, lienzo: dict, extra=()) -> Vista:
    """Vista que abarca la unidad y todos los volumenes de contexto."""
    pts = [p for n in u.niveles for p in n.vertices] + [p for c in u.contexto for p in c.vertices] + list(extra)
    return encuadrar(pts, lienzo["ancho_px"], lienzo["alto_px"], lienzo["margen_px"], lienzo["extension_min_m"])


def contorno_exterior(vs, espesor: float) -> tuple:
    """El perimetro corrido espesor hacia afuera (esquinas en inglete)."""
    if espesor <= 0:
        return tuple(vs)
    from shapely.geometry import Polygon

    p = Polygon(vs).buffer(espesor, join_style=2)
    if p.is_empty or p.geom_type != "Polygon":
        return tuple(vs)
    return tuple(p.exterior.coords)[:-1]


def _centro(vs) -> tuple:
    from shapely.geometry import Polygon

    q = Polygon(vs).representative_point()
    return (q.x, q.y)


def _dir(az: float) -> tuple:
    """Direccion en planta de un azimut relativo al eje +y (horario)."""
    a = math.radians(az)
    return (math.sin(a), math.cos(a))


# --------------------------------------------------------------------------- piezas
def _unidad(u: Unidad, v: Vista, est: dict, espesor: float) -> list:
    e = est["unidad"]
    out = []
    for k in reversed(range(len(u.niveles))):          # el nivel 1 queda encima
        n = u.niveles[k]
        ext = contorno_exterior(n.vertices, espesor)
        if k == 0:
            out.append(_poligono(v, ext, e["relleno"], e["color"], e["grosor"], clase="unidad"))
            if espesor > 0:
                out.append(_poligono(v, n.vertices, "none", e["interior"], 1, clase="unidad"))
        else:
            out.append(_poligono(v, ext, "none", e["color"], e["grosor"], e.get("trazo_otro_nivel"), "unidad"))
    return out


def _rotulos(u: Unidad, v: Vista, est: dict, espesor: float) -> list:
    if not est["unidad"].get("rotulos") or not u.niveles:
        return []
    T, tx = est["textos"], est["texto"]
    d = tx["separacion_px"]
    out = []
    for c in cx.caras(u, espesor):
        if not c.id.startswith("N1-"):
            continue
        m = (c.desde + c.hasta) / 2
        x, y = v.px((m, c.pos) if c.eje == "y" else (c.pos, m))
        if c.eje == "y":
            y -= c.signo * d                            # pantalla: y hacia abajo
        else:
            x += c.signo * d
        texto = T["cara"].format(lado=c.id.split("-", 1)[1], rumbo=orientacion(c.azimut))
        out.append(_texto(x, y, texto, tx, est["unidad"]["color"]))
    return out


def _volumenes(u: Unidad, v: Vista, est: dict, sel) -> tuple:
    e, T, tx = est["volumen"], est["textos"], est["texto"]
    color_sel = est["seleccion"]["color"]
    out, etiquetas = [], []
    for i, c in enumerate(u.contexto):
        elegido = i == sel
        out.append(_poligono(v, c.vertices, e["relleno"], color_sel if elegido else e["color"],
                             e["grosor"] * (2 if elegido else 1), clase="contexto", opacidad=e["opacidad"]))
        x, y = v.px(_centro(c.vertices))
        etiquetas.append(_texto(x, y, T["etiqueta"].format(nombre=c.nombre, h=num(c.h, 1)), tx,
                                color_sel if elegido else None))
    return out, etiquetas


def _cota(v: Vista, est: dict, c) -> list:
    e, T, tx = est["cota"], est["textos"], est["texto"]
    out = []
    a, b, cara = c.desde, c.hasta, c.cara
    otro = a[0] if cara.eje == "y" else a[1]
    if otro < cara.desde - 1e-9 or otro > cara.hasta + 1e-9:          # se mide a la prolongacion
        fin = cara.desde if otro < cara.desde else cara.hasta
        q = (fin, cara.pos) if cara.eje == "y" else (cara.pos, fin)
        out.append(_linea(v, q, a, e["extension"], 1, e.get("trazo"), "cota"))
    if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-9:
        out.append(_linea(v, a, b, e["color"], e["grosor"], None, "cota"))
    m = e["marca_px"]
    for p in (a, b):
        x, y = v.px(p)
        x1, y1, x2, y2 = (x - m, y, x + m, y) if cara.eje == "y" else (x, y - m, x, y + m)
        out.append(f'<line class="cota" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                   f'stroke="{e["color"]}" stroke-width="{e["grosor"]}"/>')
    xm, ym = v.px(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    t = T[f"cota_{c.tipo}"].format(d=num(c.distancia, int(e.get("decimales", 2))), cara=cara.id,
                                   rumbo=orientacion(cara.azimut))
    if cara.eje == "y":
        out.append(_texto(xm + 8, ym, t, tx, e["color"], "start"))
    else:
        out.append(_texto(xm, ym - 10, t, tx, e["color"]))
    return out


def _borrador(v: Vista, est: dict, pts, cursor, modo) -> list:
    b, tx, T = est["borrador"], est["texto"], est["textos"]
    out = []
    if modo == "rect" and pts and cursor is not None:
        a = pts[0]
        x0, x1 = sorted((a[0], cursor[0]))
        y0, y1 = sorted((a[1], cursor[1]))
        out.append(_poligono(v, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), "none", b["color"], b["grosor"],
                             b.get("trazo"), "borrador"))
        x, y = v.px(cursor)
        out.append(_texto(x + 12, y - 14, T["rectangulo"].format(ancho=num(x1 - x0), fondo=num(y1 - y0)), tx,
                          b["color"], "start"))
    elif modo == "poli":
        seq = list(pts) + ([cursor] if cursor is not None and pts else [])
        if len(seq) >= 2:
            ps = " ".join(f"{x:.1f},{y:.1f}" for x, y in (v.px(p) for p in seq))
            out.append(f'<polyline class="borrador" points="{ps}" fill="none" stroke="{b["color"]}" '
                       f'stroke-width="{b["grosor"]}"{_trazo(b.get("trazo"))}/>')
        radio = est["vertice"]["radio"]
        for i, p in enumerate(pts):
            primero = i == 0 and len(pts) >= 3
            out.append(_circulo(v, p, radio * b["factor_primero"] if primero else radio,
                                est["fondo"] if primero else b["color"], b["color"], "borrador"))
        if pts and cursor is not None:
            largo = math.hypot(cursor[0] - pts[-1][0], cursor[1] - pts[-1][1])
            if largo > 1e-9:
                x, y = v.px(cursor)
                out.append(_texto(x + 12, y - 14, T["tramo"].format(largo=num(largo)), tx, b["color"], "start"))
    if cursor is not None:
        out.append(_circulo(v, cursor, 3, b["color"], b["color"], "cursor"))
    return out


def _asas(v: Vista, est: dict, vs) -> list:
    e = est["asa"]
    color = est["seleccion"]["color"]
    lado = e["lado_px"]
    out = []
    for _, _, p in ec.asas(vs):
        x, y = v.px(p)
        out.append(f'<rect class="asa" x="{x - lado / 2:.1f}" y="{y - lado / 2:.1f}" width="{lado}" '
                   f'height="{lado}" fill="{e["relleno"]}" stroke="{color}" stroke-width="1.5"/>')
    return out


# --------------------------------------------------------------------------- FAR de una orientacion
def _tramo(v: Vista, est: dict, p, rel: float, o, activa: bool) -> list:
    """Obstaculo equivalente de la ficha: cuerda perpendicular a B por el punto medio M, cortada
    por los rayos extremos (ancho D), y el sector que tapa desde el punto."""
    e, T, tx = est["far"], est["textos"], est["texto"]
    mx, my = o.punto_medio
    tm = math.degrees(math.atan2(mx - p[0], my - p[1])) - rel
    tm = (tm + 180.0) % 360.0 - 180.0

    def borde(theta):
        c = math.cos(math.radians(theta - tm))
        r = o.b / c if c > 1e-6 else o.b
        dx, dy = _dir(rel + theta)
        return (p[0] + dx * r, p[1] + dy * r)

    a, b = borde(o.theta_i), borde(o.theta_f)
    color = e["color"] if activa else e["omitida"]
    clase = "far-tramo" if activa else "far-omitida"
    trazo = None if activa else e.get("trazo")
    out = [_poligono(v, (p, a, b), e["relleno"] if activa else e["omitida"], "none", 0, clase=clase,
                     opacidad=e["opacidad"]),
           _linea(v, a, b, color, e["grosor"] * 2, trazo, clase)]
    x, y = v.px((mx, my))
    t = T["far_tramo"].format(volumen=o.volumen, k=o.division, a=num(o.a, 1), b=num(o.b, 1), d=num(o.d, 1))
    out.append(_texto(x, y - 12, t, tx, color))
    return out


def _far(u: Unidad, v: Vista, est: dict, pf, res, segmentos) -> list:
    e, T, tx = est["far"], est["textos"], est["texto"]
    p = (pf.punto.x, pf.punto.y)
    rel = pf.punto.azimut
    lejos = [math.hypot(x - p[0], y - p[1]) for c in u.contexto for x, y in c.vertices]
    R = max(float(e["radio_min_m"]), float(e["margen"]) * max(lejos, default=0.0))

    def en(theta, r):
        dx, dy = _dir(rel + theta)
        return (p[0] + dx * r, p[1] + dy * r)

    out = [_linea(v, a, b, e["color"], e["muro_grosor"], None, "far") for a, b in segmentos]
    n = max(8, int(e["segmentos"]))
    arco = " ".join(f"{x:.1f},{y:.1f}" for x, y in (v.px(en(-90 + 180 * k / n, R)) for k in range(n + 1)))
    out.append(f'<polyline class="far" points="{arco}" fill="none" stroke="{e["color"]}" '
               f'stroke-width="{e["grosor"]}"/>')
    for k in range(6):
        out.append(_linea(v, p, en(-90 + 36 * k, R), e["color"], 1, e.get("trazo"), "far"))
    if res is not None:
        for o in res.obstrucciones:
            out += _tramo(v, est, p, rel, o, True)
        for m in res.omitidas:
            if m.motivo != "angosto":
                out += _tramo(v, est, p, rel, m.obstruccion, False)
    for k in range(5):
        x, y = v.px(en(-72 + 36 * k, R * 1.05))
        out.append(_texto(x, y, T["far_division"].format(k=k + 1), tx, e["color"]))
    out.append(_circulo(v, p, 5, e["color"], "#ffffff", "far"))
    x, y = v.px(p)
    out.append(_texto(x + 10, y + 14, T["far_rotulo"].format(o=pf.orientacion, z=num(pf.punto.z, 1)), tx,
                      e["color"], "start"))
    return out


# --------------------------------------------------------------------------- salida
def contenido(u: Unidad, v: Vista, est: dict, espesor: float = 0.0, sel=None, borrador=(), cursor=None,
              modo=None, asas: bool = False, far=None) -> str:
    """Elementos SVG de la vista Contexto. est: estilo(); espesor: cara desde la que se mide
    (0 = interior); sel: indice del volumen elegido; borrador, cursor y modo (rect | poli):
    lo que se esta dibujando; asas: las del volumen elegido; far: (PuntoFar, ResultadoPunto o
    None, [(a, b)] muros del punto) de la orientacion que se muestra."""
    valido = sel is not None and 0 <= sel < len(u.contexto)
    out = _grilla(v, est["grilla"])
    out += _unidad(u, v, est, espesor)
    vols, etiquetas = _volumenes(u, v, est, sel if valido else None)
    out += vols
    if far is not None and far[0] is not None:
        out += _far(u, v, est, *far)
    medidas = []
    if valido:
        medidas.append(cx.cotas(u, u.contexto[sel].vertices, espesor))
    if modo == "rect" and borrador and cursor is not None:
        medidas.append(cx.cotas(u, [borrador[0], cursor], espesor))
    elif modo is not None and cursor is not None:
        medidas.append(cx.cotas_punto(u, cursor, espesor))
    for cs in medidas:
        for c in cs.values():
            if c is not None:
                out += _cota(v, est, c)
    out += _borrador(v, est, list(borrador), cursor, modo)
    out += etiquetas + _rotulos(u, v, est, espesor)
    if asas and valido:
        out += _asas(v, est, u.contexto[sel].vertices)
    out += _norte(v, est, u.azimut_y)
    return "".join(out)
