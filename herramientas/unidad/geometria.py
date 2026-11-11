# -*- coding: utf-8 -*-
"""
Geometria derivada de una Unidad (modelo.py): muros, ventanas, esquinas,
coberturas entre niveles y superficies horizontales.

Es comun a todas las herramientas: no decide puentes termicos ni nada propio de
CEV (eso lo hace cev.py con config/cev.yaml). Entrega:
  - por tramo de muro ("pano"): largo, azimut de su normal exterior, area bruta
    y de vanos de ventanas, sus ventanas con la distancia a cada extremo, sus
    puertas (area_puertas; todavia no se restan del muro, ver modelo.py), cuantos
    extremos de tabique llegan a el y que parte de su borde superior queda bajo
    el nivel de arriba (sup_cubierto) y de su borde inferior sobre el de abajo
    (inf_cubierto);
  - por vertice: el tipo de esquina (saliente, entrante o colineal) y los panos
    antes y despues; tambien entre tramos de un mismo lado (colineal);
  - superficies horizontales: piso del nivel 1 (Unidad.piso, con el perimetro de
    muros exteriores si es contra terreno), parte de un nivel que vuela sobre el
    de abajo (Unidad.piso_expuesto), techo del ultimo nivel (Unidad.techo) y
    parte de un nivel sin el de arriba encima (Unidad.techo_expuesto).
El orden de los panos es el del dibujo: nivel, lado, tramo.

VentanaGeo.fav1_obstruccion: (D, L) del FAV1 que aporta una obstruccion (voladizo u
obstruccion horizontal dibujada); VentanaGeo.fav2_obstruccion: ((P, S) izquierda o
None, (P, S) derecha o None) de las obstrucciones verticales dibujadas. Los pone
obstrucciones.aplicar; calcular() los deja en None.

Los lados pueden tener cualquier angulo; si config/unidad.yaml define
dibujo.angulo_obligatorio, errores() exige multiplos de ese angulo.
Vanos: rect = (x, z, ancho, alto); la puerta parte del piso (z = 0).

Largo cubierto: el muro se corta donde cruza el borde del otro nivel (cortes
exactos) y cada pedazo cuenta si su punto medio queda dentro o sobre ese borde
(con la tolerancia de config/unidad.yaml). Asi la tolerancia no alarga lo cubierto.
shapely hace las operaciones entre poligonos.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml

from .modelo import Unidad, Ventana, area_firmada

CONFIG = Path(__file__).parent / "config" / "unidad.yaml"


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return cargar_config()


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def normalizar_azimut(a: float) -> float:
    a = ((float(a) + 180.0) % 360.0) - 180.0
    return 180.0 if a == -180.0 else a + 0.0


def _dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo = math.hypot(dx, dy)
    return dx / largo, dy / largo, largo


@dataclass(frozen=True)
class VentanaGeo:
    indice: int                    # posicion dentro del tramo
    datos: Ventana
    x: float
    antepecho: float
    ancho: float
    alto: float
    area: float
    s_izq: float                   # distancia al extremo izquierdo del muro (vista interior)
    s_der: float
    fav1_obstruccion: tuple | None = None   # (D, L) de una obstruccion (obstrucciones.py)
    fav2_obstruccion: tuple | None = None   # ((P, S) izq o None, (P, S) der o None)


@dataclass(frozen=True)
class PanoGeo:
    indice: int
    id: str                        # "N1-L2" o "N1-L2-T1"
    nivel: int                     # 0..2
    lado: int
    tramo: int
    a: tuple
    b: tuple
    largo: float
    azimut: float
    condicion: str
    solucion: str
    area_bruta: float
    area_vanos: float              # ventanas
    ventanas: tuple = ()
    tabiques: int = 0              # extremos de tabique que llegan a este muro
    sup_cubierto: float = 0.0      # [m] del borde superior bajo el nivel de arriba
    inf_cubierto: float = 0.0      # [m] del borde inferior sobre el nivel de abajo
    puertas: tuple = ()            # modelo.Puerta
    area_puertas: float = 0.0

    @property
    def exterior(self) -> bool:
        return self.condicion == "exterior"

    @property
    def area_neta(self) -> float:
        return self.area_bruta - self.area_vanos

    @property
    def sup_expuesto(self) -> float:
        return self.largo - self.sup_cubierto

    @property
    def inf_expuesto(self) -> float:
        return self.largo - self.inf_cubierto


@dataclass(frozen=True)
class EsquinaGeo:
    nivel: int
    tipo: str                      # saliente | entrante | colineal
    antes: int                     # indice del pano que termina en el vertice
    despues: int                   # indice del pano que empieza


@dataclass(frozen=True)
class HorizontalGeo:
    destino: str                   # techo | piso
    nivel: int
    condicion: str
    area: float
    perimetro: float = 0.0         # perimetro contra terreno (piso del nivel 1)


@dataclass
class Geometria:
    panos: list
    esquinas: list
    horizontales: list
    areas: list                    # area de piso de cada nivel [m2]
    altura: float
    avisos: list = field(default_factory=list)

    @property
    def volumen(self) -> float:
        return sum(a * self.altura for a in self.areas)


# --------------------------------------------------------------------------- validacion
def se_montan(r, s, tol: float) -> bool:
    """Dos rectangulos (x, z, ancho, alto) se superponen mas que tol en ambos sentidos."""
    x = min(r[0] + r[2], s[0] + s[2]) - max(r[0], s[0])
    y = min(r[1] + r[3], s[1] + s[3]) - max(r[1], s[1])
    return x > tol and y > tol


def vanos_tramo(t) -> list:
    """[(nombre, rect)] de las ventanas y puertas de un tramo."""
    out = [(f"ventana {n}", (w.x, w.antepecho, w.ancho, w.alto)) for n, w in enumerate(t.ventanas, 1)]
    out += [(f"puerta {n}", (p.x, 0.0, p.ancho, p.alto)) for n, p in enumerate(t.puertas, 1)]
    return out


def errores(u: Unidad, cfg: dict | None = None) -> list:
    """Problemas del dibujo, con mensajes para el usuario (lista vacia = valido)."""
    from shapely.geometry import LineString, Polygon

    cfg = cfg or _cfg()
    d, lim = cfg["dibujo"], cfg["limites"]
    tol, paso = d["tolerancia_m"], d.get("angulo_obligatorio")
    out = []
    lo, hi = lim["altura"]
    if not lo <= u.altura <= hi:
        out.append(f"La altura ({u.altura} m) debe estar entre {lo} y {hi} m")
    if not u.niveles:
        return out + ["Dibuja y cierra el perímetro del nivel 1"]
    polys = []
    for k, n in enumerate(u.niveles, 1):
        et = f"Nivel {k}"
        vs = n.vertices
        if area_firmada(vs) >= 0:
            out.append(f"{et}: el perímetro debe recorrerse en sentido horario")
            polys.append(None)
            continue
        poly = Polygon(vs)
        if not poly.is_valid:
            out.append(f"{et}: el perímetro se cruza consigo mismo")
            polys.append(None)
            continue
        polys.append(poly)
        for i, lado in enumerate(n.lados):
            a, b = vs[i], vs[(i + 1) % len(vs)]
            largo_lado = math.hypot(b[0] - a[0], b[1] - a[1])
            etl = f"{et}, lado {i + 1}"
            if largo_lado < lim["lado_min"]:
                out.append(f"{etl}: mide {largo_lado:.2f} m (mínimo {lim['lado_min']} m)")
                continue
            if paso:
                ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % paso
                if min(ang, paso - ang) > d["tolerancia_angulo"]:
                    out.append(f"{etl}: el ángulo debe ser múltiplo de {paso}°")
            limites = (0.0,) + tuple(lado.cortes) + (largo_lado,)
            for j, t in enumerate(lado.tramos):
                largo = limites[j + 1] - limites[j]
                ett = f"{etl}, tramo {j + 1}" if len(lado.tramos) > 1 else etl
                if largo < lim["tramo_min"] - 1e-9:
                    out.append(f"{ett}: mide {largo:.2f} m (mínimo {lim['tramo_min']} m)")
                    continue
                vanos = vanos_tramo(t)
                for idx, (nombre, r) in enumerate(vanos):
                    etw = f"{ett}, {nombre}"
                    if r[0] < -tol or r[0] + r[2] > largo + tol:
                        out.append(f"{etw}: se sale del muro a lo largo")
                    if r[1] < -tol or r[1] + r[3] > u.altura + tol:
                        out.append(f"{etw}: se sale del muro en altura")
                    for o_nombre, o in vanos[:idx]:
                        if se_montan(r, o, tol):
                            out.append(f"{etw}: se monta con la {o_nombre}")
        for t_i, tb in enumerate(n.tabiques, 1):
            seg = LineString([tb.a, tb.b])
            if seg.length < lim["tramo_min"]:
                out.append(f"{et}, tabique {t_i}: es demasiado corto")
            elif not seg.within(poly.buffer(tol)):
                out.append(f"{et}, tabique {t_i}: debe quedar dentro del perímetro")
    for k in range(1, len(polys)):
        if polys[k] is not None and polys[k - 1] is not None \
                and polys[k].intersection(polys[k - 1]).area <= d["tolerancia_area_m2"]:
            out.append(f"Nivel {k + 1}: no se apoya sobre el nivel {k}")
    return out


def validar(u: Unidad, cfg: dict | None = None) -> None:
    e = errores(u, cfg)
    if e:
        raise ValueError("\n".join(e))


# --------------------------------------------------------------------------- calculo
def _cubierto(a, b, poly, poly_b, largo: float, tol: float) -> float:
    """[m] del segmento a-b dentro o sobre el borde del poligono (cortes exactos en su borde)."""
    from shapely.geometry import Point

    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    ts = {0.0, 1.0}
    cs = list(poly.exterior.coords)
    for (qx, qy), (rx, ry) in zip(cs, cs[1:]):
        ex, ey = rx - qx, ry - qy
        wx, wy = qx - ax, qy - ay
        cruz = dx * ey - dy * ex
        if abs(cruz) > 1e-12 * math.sqrt(l2) * math.hypot(ex, ey):
            t = (wx * ey - wy * ex) / cruz
            s = (wx * dy - wy * dx) / cruz
            if -1e-12 <= s <= 1 + 1e-12 and 0.0 < t < 1.0:
                ts.add(t)
        elif abs(wx * dy - wy * dx) / math.sqrt(l2) <= tol:          # lado sobre la misma recta
            for px, py in ((qx, qy), (rx, ry)):
                t = ((px - ax) * dx + (py - ay) * dy) / l2
                if 0.0 < t < 1.0:
                    ts.add(t)
    ts = sorted(ts)
    c = 0.0
    for t1, t2 in zip(ts, ts[1:]):
        if t2 - t1 <= 1e-12:
            continue
        tm = (t1 + t2) / 2.0
        if poly_b.covers(Point(ax + dx * tm, ay + dy * tm)):
            c += (t2 - t1) * largo
    if c >= largo - 1e-6:
        return largo
    return 0.0 if c <= 1e-6 else c


def calcular(u: Unidad, cfg: dict | None = None) -> Geometria:
    cfg = cfg or _cfg()
    validar(u, cfg)
    d = cfg["dibujo"]
    tol, tol_a = d["tolerancia_m"], d["tolerancia_area_m2"]
    h = float(u.altura)
    n_niv = len(u.niveles)
    areas = [abs(area_firmada(n.vertices)) for n in u.niveles]
    polys = bufs = None
    if n_niv > 1 or any(n.tabiques for n in u.niveles):
        from shapely.geometry import Polygon
        polys = [Polygon(n.vertices) for n in u.niveles]
        bufs = [p.buffer(tol) for p in polys]
    panos, esquinas = [], []
    for k, n in enumerate(u.niveles):
        vs, nv = n.vertices, len(n.vertices)
        inicio = len(panos)
        rangos = []
        for i, lado in enumerate(n.lados):
            a, b = vs[i], vs[(i + 1) % nv]
            ux, uy, largo_lado = _dir(a, b)
            az = round(normalizar_azimut(u.azimut_y + math.degrees(math.atan2(-uy, ux))), 9) + 0.0
            limites = (0.0,) + tuple(lado.cortes) + (largo_lado,)
            primero, ultimo_t = len(panos), len(lado.tramos) - 1
            for j, t in enumerate(lado.tramos):
                t0, t1 = limites[j], limites[j + 1]
                pa = a if j == 0 else (a[0] + ux * t0, a[1] + uy * t0)
                pb = b if j == ultimo_t else (a[0] + ux * t1, a[1] + uy * t1)
                largo = t1 - t0
                vents = tuple(VentanaGeo(m, w, w.x, w.antepecho, w.ancho, w.alto, w.alto * w.ancho,
                                         w.x, largo - w.x - w.ancho) for m, w in enumerate(t.ventanas))
                vanos = 0.0
                for v in vents:
                    vanos += v.area
                a_puertas = 0.0
                for p in t.puertas:
                    a_puertas += p.ancho * p.alto
                pid = f"N{k + 1}-L{i + 1}" + (f"-T{j + 1}" if ultimo_t else "")
                panos.append(PanoGeo(len(panos), pid, k, i, j, pa, pb, largo, az, t.condicion, t.solucion,
                                     largo * h, vanos, vents, puertas=tuple(t.puertas), area_puertas=a_puertas))
            rangos.append((primero, len(panos) - 1))
        for i in range(nv):
            p0, p1 = rangos[i]
            for x in range(p0, p1):
                esquinas.append(EsquinaGeo(k, "colineal", x, x + 1))
            d1 = _dir(vs[i], vs[(i + 1) % nv])
            d2 = _dir(vs[(i + 1) % nv], vs[(i + 2) % nv])
            cruz = d1[0] * d2[1] - d1[1] * d2[0]
            tipo = "colineal" if abs(cruz) < 1e-9 else ("saliente" if cruz < 0 else "entrante")
            esquinas.append(EsquinaGeo(k, tipo, p1, rangos[(i + 1) % nv][0]))
        if polys is None:
            continue
        from shapely.geometry import LineString, Point
        segs = {x: LineString([panos[x].a, panos[x].b]) for x in range(inicio, len(panos))}
        cont: Counter = Counter()
        for tb in n.tabiques:
            for p in (tb.a, tb.b):
                punto = Point(p)
                for x in range(inicio, len(panos)):
                    if segs[x].distance(punto) <= tol:
                        cont[x] += 1
                        break
        for x in range(inicio, len(panos)):
            p = panos[x]
            sup = _cubierto(p.a, p.b, polys[k + 1], bufs[k + 1], p.largo, tol) if k + 1 < n_niv else 0.0
            inf = _cubierto(p.a, p.b, polys[k - 1], bufs[k - 1], p.largo, tol) if k > 0 else 0.0
            panos[x] = replace(p, tabiques=cont[x], sup_cubierto=sup, inf_cubierto=inf)

    horiz = []
    perim = sum(p.largo for p in panos if p.nivel == 0 and p.exterior) if u.piso == "terreno" else 0.0
    horiz.append(HorizontalGeo("piso", 0, u.piso, areas[0], perim))
    for k in range(1, n_niv):
        v = areas[k] - polys[k].intersection(polys[k - 1]).area
        if v > tol_a:
            horiz.append(HorizontalGeo("piso", k, u.piso_expuesto, v))
    horiz.append(HorizontalGeo("techo", n_niv - 1, u.techo, areas[n_niv - 1]))
    for k in range(n_niv - 1):
        v = areas[k] - polys[k].intersection(polys[k + 1]).area
        if v > tol_a:
            horiz.append(HorizontalGeo("techo", k, u.techo_expuesto, v))
    return Geometria(panos, esquinas, horiz, areas, h)
