# -*- coding: utf-8 -*-
"""
Vista axonometrica de la escena 3D (modelo3d.Escena) en SVG, sin navegador. La
usa el reporte PDF cuando no hay una captura de la vista 3D del editor.

Proyeccion ortogonal desde la camara inicial (modelo3d.camara: la fachada
frontal y su lateral izquierdo). Cada prisma (muros, losas) y caja (vidrios,
puertas, protecciones) se descompone en caras; se descartan las que miran hacia
atras y el resto se dibuja de la mas lejana a la mas cercana (algoritmo del
pintor), sombreadas segun su orientacion respecto de una luz, como el modo
solido del editor. Con ajustar (por defecto) el alto del SVG sigue la proporcion
de lo dibujado, asi no sobra fondo. Colores: config/editor.yaml (modelo3d.clases,
o lineas.clases con render: lineas); tamano, luz y fondo: reporte.axonometria.
"""
from __future__ import annotations

import math

from . import modelo3d


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _media(pts):
    n = len(pts)
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def _normal(cara):
    """Normal de un poligono plano (metodo de Newell)."""
    nx = ny = nz = 0.0
    for i, p in enumerate(cara):
        q = cara[(i + 1) % len(cara)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    return _unit((nx, ny, nz))


def _caras(inferior, superior) -> list:
    """Caras de un solido entre dos contornos iguales (abajo y arriba)."""
    n = len(inferior)
    out = [list(reversed(inferior)), list(superior)]
    for i in range(n):
        j = (i + 1) % n
        out.append([inferior[i], inferior[j], superior[j], superior[i]])
    return out


def caras_prisma(p) -> list:
    cont = list(p.contorno)
    z0, z1 = p.z, p.z + p.alto
    return _caras([(x, y, z0) for x, y in cont], [(x, y, z1) for x, y in cont])


def caras_caja(c) -> list:
    cx, cy, cz = c.centro
    L, E, H = c.tamano
    ux, uy = math.cos(c.giro), math.sin(c.giro)
    nx, ny = -uy, ux

    def pt(s, d, z):
        return (cx + ux * s + nx * d, cy + uy * s + ny * d, cz + z)

    lazo = ((-L / 2, -E / 2), (L / 2, -E / 2), (L / 2, E / 2), (-L / 2, E / 2))
    return _caras([pt(s, d, -H / 2) for s, d in lazo], [pt(s, d, H / 2) for s, d in lazo])


def _orientada(cara, centro):
    """Normal de la cara hacia afuera del solido."""
    n = _normal(cara)
    if _dot(n, _sub(_media(cara), centro)) < 0:
        n = (-n[0], -n[1], -n[2])
    return n


def _sombra(color: str, f: float) -> str:
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x * f))) for x in (r, g, b))


def caras_visibles(esc, est: dict, cfg: dict | None = None) -> list:
    """[(profundidad, [(x, y) proyectados], color, opacidad)] de las caras que miran a la camara."""
    cfg = cfg or {}
    cl = modelo3d.paleta(est, cfg.get("render", "solido"))
    cam = modelo3d.camara(esc, est)
    pos = (cam["x"], cam["y"], cam["z"])
    obj = (cam["look_at_x"], cam["look_at_y"], cam["look_at_z"])
    f = _unit(_sub(obj, pos))
    r = _unit(_cross(f, (0.0, 0.0, 1.0)))
    if r == (0.0, 0.0, 0.0):
        r = (1.0, 0.0, 0.0)
    u = _cross(r, f)
    luz = _unit(tuple(cfg.get("luz", (-0.4, -0.7, 1.0))))
    amb = float(cfg.get("ambiente", 0.55))
    techos = cfg.get("techos", True)
    objetos = [(caras_prisma(p), p.clase) for p in esc.muros]
    objetos += [(caras_prisma(p), p.clase) for p in esc.losas if techos or not p.nombre.startswith("techo|")]
    objetos += [(caras_caja(c), c.clase) for c in esc.cajas]
    out = []
    for cs, clase in objetos:
        e = cl.get(clase) or {"color": "#cccccc", "opacidad": 1.0}
        centro = _media([p for c in cs for p in c])
        for c in cs:
            n = _orientada(c, centro)
            if _dot(n, f) > -1e-6:
                continue                                   # mira hacia atras
            luzf = amb + (1 - amb) * max(0.0, _dot(n, luz))
            out.append((sum(_dot(p, f) for p in c) / len(c), [(_dot(p, r), _dot(p, u)) for p in c],
                        _sombra(e["color"], luzf), float(e["opacidad"])))
    out.sort(key=lambda x: -x[0])
    return out


def svg(esc, est: dict, cfg: dict | None = None) -> str:
    cfg = cfg or {}
    W, H, M = cfg.get("ancho_px", 1200), cfg.get("alto_px", 800), cfg.get("margen_px", 30)
    fondo, borde = cfg.get("fondo", "#ffffff"), cfg.get("borde")
    caras = caras_visibles(esc, est, cfg)
    partes = []
    if caras:
        xs = [x for _, pp, _, _ in caras for x, _ in pp]
        ys = [y for _, pp, _, _ in caras for _, y in pp]
        dx, dy = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
        if cfg.get("ajustar", True):
            H = round((W - 2 * M) * dy / dx + 2 * M)
        e = min((W - 2 * M) / dx, (H - 2 * M) / dy)
        ox = W / 2 - e * (min(xs) + max(xs)) / 2
        oy = H / 2 + e * (min(ys) + max(ys)) / 2
        for _, pp, col, op in caras:
            pts = " ".join(f"{ox + e * x:.1f},{oy - e * y:.1f}" for x, y in pp)
            o = f' fill-opacity="{op}" stroke-opacity="{op}"' if op < 1 else ""
            trazo = borde or col
            partes.append(f'<polygon points="{pts}" fill="{col}"{o} stroke="{trazo}" stroke-width="0.7" '
                          'stroke-linejoin="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<rect width="100%" height="100%" fill="{fondo}"/>' + "".join(partes) + "</svg>")
