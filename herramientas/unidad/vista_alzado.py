# -*- coding: utf-8 -*-
"""
Alzado de un tramo de muro en SVG, para dibujar, mover y cambiar el tamano de
ventanas y puertas.

Mundo del alzado: metros, w a la derecha y z hacia arriba, con el muro entre
w = 0 y w = largo y entre z = 0 (piso) y z = altura. Por defecto se ve desde el
EXTERIOR (config/editor.yaml, alzado.desde): como Ventana.x se mide desde el
extremo izquierdo visto desde el interior, el dibujo queda en espejo
(w = largo - s). a_mundo y desde_mundo convierten entre (s, z) del modelo y (w, z).
Usa la misma Vista que la planta (zoom, desplazar). Ventanas en celeste y
puertas en verde; la previa (al dibujar) va segmentada. Las protecciones
solares (alero, aletas y lamas) se dibujan de frente (alzado.proteccion), y las
obstrucciones dibujadas del nivel que se apoyan en el plano del muro, tambien de
frente (alzado.obstaculo; obstrucciones.proyecciones).

Rotulo (alzado.rotulo): texto con {muro} y {desde} en la posicion x_px, y_px
(negativos: desde la derecha o desde abajo). texto "" o null: sin rotulo.

Edicion (herramienta Mover): el vano elegido muestra asas en sus esquinas y en
el medio de sus bordes (alzado.asa; la puerta no tiene asa en el medio del borde
inferior porque siempre parte del piso). tocar_borde dice que bordes hay bajo el
cursor (izq, der, inf, sup en el sentido del modelo: izq = inicio del tramo) y
cursor_borde el cursor del navegador que corresponde, ya con el espejo.
"""
from __future__ import annotations

from . import editor, obstrucciones, protecciones
from .modelo import Nivel, Unidad
from .vista_planta import Vista, _grilla, _texto, _trazo, encuadrar, num

ROTULO = {"texto": "Alzado {muro} · visto desde el {desde}", "x_px": 12, "y_px": 18}
OBSTACULO = {"relleno": "#d6d3d1", "opacidad": 0.8, "borde": "#57534e", "grosor": 1, "espesor_m": 0.15,
             "ancho_m": 0.15}


def espejo(alz: dict) -> bool:
    return alz.get("desde", "exterior") == "exterior"


def a_mundo(s: float, z: float, largo: float, esp: bool) -> tuple:
    return (largo - s if esp else s, z)


def desde_mundo(p, largo: float, esp: bool) -> tuple:
    return (largo - p[0] if esp else p[0], p[1])


def encuadrar_alzado(largo: float, altura: float, lienzo: dict, alz: dict) -> Vista:
    return encuadrar([(0.0, 0.0), (largo, altura)], lienzo["ancho_px"], lienzo["alto_px"], alz["margen_px"],
                     alz["extension_min_m"])


def nombre_muro(n: Nivel, k: int, i: int, j: int) -> str:
    return f"N{k + 1}-L{i + 1}" + (f"-T{j + 1}" if len(n.lados[i].tramos) > 1 else "")


def nombres_extremos(n: Nivel, i: int, j: int) -> tuple:
    """(inicio, fin) del tramo: el vertice si es extremo del lado, si no el corte."""
    ultimo = len(n.lados[i].tramos) - 1
    ini = f"V{i + 1}" if j == 0 else f"corte {j}"
    fin = f"V{(i + 1) % len(n.vertices) + 1}" if j == ultimo else f"corte {j + 1}"
    return ini, fin


def _rect(v: Vista, largo: float, esp: bool, x, z, a, al, e: dict, clase: str, borde=None, trazo=None) -> str:
    w0 = largo - (x + a) if esp else x
    x0, y0 = v.px((w0, z + al))
    x1, y1 = v.px((w0 + a, z))
    return (f'<rect class="{clase}" x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" '
            f'fill="{e["relleno"]}" fill-opacity="{e.get("opacidad", 1)}" stroke="{borde or e["borde"]}" '
            f'stroke-width="{e["grosor"]}"{_trazo(trazo)}/>')


def tocar_vano(t, s: float, z: float, tol: float):
    """(tipo, indice) del vano bajo (s, z), o None."""
    hit = None
    for tipo, m, w in editor.vanos(t):
        x, z0, a, al = editor.rect(tipo, w)
        if x - tol <= s <= x + a + tol and z0 - tol <= z <= z0 + al + tol:
            hit = (tipo, m)
    return hit


def tocar_borde(t, s: float, z: float, tol: float, preferir=None):
    """(tipo, indice, bordes) si (s, z) esta a menos de tol del borde de un vano, o None.
    bordes: frozenset de izq, der, inf, sup (dos en una esquina). La puerta no tiene
    borde inferior. preferir: (tipo, indice) que se revisa primero (el vano elegido)."""
    vs = editor.vanos(t)
    if preferir is not None:
        vs = sorted(vs, key=lambda x: (x[0], x[1]) != tuple(preferir))
    for tipo, m, w in vs:
        x, z0, a, al = editor.rect(tipo, w)
        if not (x - tol <= s <= x + a + tol and z0 - tol <= z <= z0 + al + tol):
            continue
        b = set()
        if abs(s - x) <= tol:
            b.add("izq")
        elif abs(s - (x + a)) <= tol:
            b.add("der")
        if abs(z - (z0 + al)) <= tol:
            b.add("sup")
        elif tipo == "ventana" and abs(z - z0) <= tol:
            b.add("inf")
        if b:
            return (tipo, m, frozenset(b))
    return None


def cursor_borde(bordes, esp: bool) -> str | None:
    """Cursor CSS para arrastrar esos bordes (None si no hay ninguno)."""
    if not bordes:
        return None
    hz, vt = {"izq", "der"} & set(bordes), {"inf", "sup"} & set(bordes)
    if hz and vt:
        izquierda = ("der" in hz) if esp else ("izq" in hz)     # izquierda en la pantalla
        return "nwse-resize" if izquierda == ("sup" in vt) else "nesw-resize"
    return "ew-resize" if hz else "ns-resize"


def _asas(v: Vista, largo: float, esp: bool, tipo: str, r, e: dict, color: str) -> list:
    x, z, a, al = r
    pts = [(x, z + al), (x + a / 2, z + al), (x + a, z + al), (x, z + al / 2), (x + a, z + al / 2), (x, z), (x + a, z)]
    if tipo == "ventana":
        pts.append((x + a / 2, z))
    lado = float(e.get("lado_px", 7))
    out = []
    for s, zz in pts:
        cx, cy = v.px(a_mundo(s, zz, largo, esp))
        out.append(f'<rect class="asa" x="{cx - lado / 2:.1f}" y="{cy - lado / 2:.1f}" width="{lado:.1f}" '
                   f'height="{lado:.1f}" fill="{e.get("relleno", "#ffffff")}" stroke="{e.get("borde") or color}" '
                   f'stroke-width="{e.get("grosor", 1.5)}"/>')
    return out


def _rotulo(v: Vista, alz: dict, muro: str, tx: dict) -> list:
    r = alz.get("rotulo", ROTULO)
    if isinstance(r, str) or r is None:
        r = {"texto": r}
    texto = r.get("texto", ROTULO["texto"]) if "texto" in r else ROTULO["texto"]
    if not texto:
        return []
    x, y = float(r.get("x_px", ROTULO["x_px"])), float(r.get("y_px", ROTULO["y_px"]))
    x = x if x >= 0 else v.ancho_px + x
    y = y if y >= 0 else v.alto_px + y
    ancla = "end" if float(r.get("x_px", 0)) < 0 else "start"
    return [_texto(x, y, texto.format(muro=muro, desde=alz.get("desde", "exterior")), tx, None, ancla)]


def _obstaculos(u: Unidad, k: int, i: int, j: int, v: Vista, largo: float, esp: bool, alz: dict) -> list:
    """Obstrucciones dibujadas del nivel que se apoyan en el plano del tramo."""
    oe = {**OBSTACULO, **(alz.get("obstaculo") or {})}
    try:
        proy = obstrucciones.proyecciones(u, k, i, j, espesor_h=float(oe["espesor_m"]),
                                          espesor_v=float(oe["ancho_m"]))
    except Exception:                    # el alzado se dibuja igual
        return []
    sx = alz.get("suelo_extra_m", 0.6)
    out = []
    for _, _, s0, s1, z0, z1 in proy:
        s0, s1 = max(s0, -sx), min(s1, largo + sx)
        if s1 > s0 and z1 > z0:
            out.append(_rect(v, largo, esp, s0, z0, s1 - s0, z1 - z0, oe, "obstaculo"))
    return out


def contenido(u: Unidad, k: int, i: int, j: int, v: Vista, est: dict, alz: dict, seleccion=None,
              previa=None, cursor=None, asas: bool = False) -> str:
    """Elementos SVG del alzado del tramo j del lado i del nivel k.

    seleccion: (tipo, indice); previa: (tipo, (x, z, ancho, alto)); cursor: (s, z);
    asas: dibuja las asas del vano elegido (herramienta Mover)."""
    n = u.niveles[k]
    t = n.lados[i].tramos[j]
    largo, h, esp = editor.largo_tramo(n, i, j), u.altura, espejo(alz)
    tx = est["texto"]
    out = _grilla(v, est["grilla"])
    out.append(_rect(v, largo, esp, 0.0, 0.0, largo, h, alz["muro"]["exterior" if t.exterior else "adiabatico"],
                     "muro"))
    sx = alz["suelo_extra_m"]
    (xa, ya), (xb, _) = v.px((-sx, 0.0)), v.px((largo + sx, 0.0))
    out.append(f'<line class="suelo" x1="{xa:.1f}" y1="{ya:.1f}" x2="{xb:.1f}" y2="{ya:.1f}" '
               f'stroke="{alz["suelo"]["color"]}" stroke-width="{alz["suelo"]["grosor"]}"/>')
    color_sel = est["seleccion"]["color"]
    elegido = None
    for tipo, m, w in editor.vanos(t):
        x, z, a, al = editor.rect(tipo, w)
        sel = seleccion is not None and tuple(seleccion) == (tipo, m)
        if sel:
            elegido = (tipo, (x, z, a, al))
        out.append(_rect(v, largo, esp, x, z, a, al, alz[tipo], tipo, color_sel if sel else None))
        cx, cy = v.px(a_mundo(x + a / 2, z + al / 2, largo, esp))
        letra = "V" if tipo == "ventana" else "P"
        out.append(_texto(cx, cy, f"{letra}{m + 1} · {num(a)} × {num(al)}", tx))
    pe = alz.get("proteccion")
    if pe:
        for w in t.ventanas:
            for _, s0, s1, _, _, za, zb in protecciones.piezas(w, 0.0, pe.get("espesor_m", 0.03),
                                                               pe.get("max_lamas", 60)):
                out.append(_rect(v, largo, esp, s0, za, s1 - s0, zb - za, pe, "proteccion"))
    out += _obstaculos(u, k, i, j, v, largo, esp, alz)
    if asas and elegido is not None:
        out += _asas(v, largo, esp, elegido[0], elegido[1], alz.get("asa") or {}, color_sel)
    if previa is not None:
        tipo, (x, z, a, al) = previa
        out.append(_rect(v, largo, esp, x, z, a, al, alz[tipo], "previa", trazo=alz["previa"]["trazo"]))
        cx, cy = v.px(a_mundo(x + a / 2, z + al / 2, largo, esp))
        out.append(_texto(cx, cy, f"{num(a)} × {num(al)}", tx))
    if cursor is not None:
        cx, cy = v.px(a_mundo(cursor[0], cursor[1], largo, esp))
        c = alz["cursor"]["color"]
        out.append(f'<circle class="cursor" cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{c}" stroke="{c}"/>')
        out.append(_texto(cx + 10, cy - 12, f"{num(cursor[0])} ; {num(cursor[1])}", tx, c, "start"))
    x0, y0 = v.px((largo / 2, 0.0))
    out.append(_texto(x0, y0 + 18, f"{num(largo)} m", tx))
    x0, y0 = v.px((0.0, h / 2))
    out.append(_texto(x0 - 10, y0, f"{num(h)} m", tx, None, "end"))
    for s, nombre in zip((0.0, largo), nombres_extremos(n, i, j)):
        x0, y0 = v.px(a_mundo(s, h, largo, esp))
        out.append(_texto(x0, y0 - 14, nombre, tx, est["vertice"]["color_etiqueta"]))
    out += _rotulo(v, alz, nombre_muro(n, k, i, j), tx)
    return "".join(out)
