# -*- coding: utf-8 -*-
"""
Obstrucciones solares de una unidad, sin interfaz: lo que hace sombra a una
ventana y en la ficha 01 se declara como factor de proteccion (FAV). Cuatro tipos:

  voladizo    detectado: la parte del nivel de arriba que vuela sobre una ventana
              del nivel de abajo -> FAV1 (alero).
  horizontal  dibujada (modelo.Obstaculo): balcon, cornisa o alero, un rectangulo en
              la planta de un nivel, SOBRE ese nivel (cara inferior a z del piso; por
              defecto la altura libre) -> FAV1 de las ventanas del nivel bajo ella.
  vertical    dibujada: muro saliente o aleta que sale de un muro exterior (de z a
              z + alto; por defecto todo el nivel) -> FAV2 de las ventanas del MISMO
              PLANO de fachada: el tramo donde nace y los tramos alineados con el
              (aunque el muro este cortado en varios tramos), a la izquierda o a la
              derecha segun el lado en que quede.
  autosombra  detectada: en un rincon ENTRANTE del perimetro (unidad en L, en U...), el
              muro propio que sale hacia afuera desde el extremo de un lado le hace
              sombra a las ventanas de ese lado -> FAV2 de ese lado (izq en el inicio
              del lado, der en su fin). Se saltan los vertices colineales: cuenta todo
              el plano de fachada. P = cuanto sale ese muro, perpendicular al plano y
              por la CARA INTERIOR (como el dibujo); S = del borde de la ventana al
              rincon. Ocupa todo el alto del nivel. Las esquinas salientes no hacen
              sombra. Solo dentro de un mismo nivel. No suma P04 (es la misma unidad).
              Criterio de Lucas (2026-11-07); se apaga con obstrucciones.autosombra:
              false en config/cev.yaml.
El balcon dibujado (Obstaculo tipo balcon: la losa en el PISO del nivel, un poligono)
NO hace sombra: solo suma su P04 (ver abajo). Criterio de Lucas (2026-11-07).

Medidas (Manual CEV 6.7.3):
  FAV1  L saliente perpendicular al muro, con rayos desde puntos repartidos a lo
        ancho de la ventana (muestras; largo: promedio | minimo | maximo de los que
        tocan); D del dintel a la cara inferior.
  FAV2  P saliente perpendicular al muro; S distancia, a lo largo de la fachada, del
        borde de la ventana a la aleta. En Obstruccion: l = P y d = S.
Cobertura: fraccion del ANCHO (FAV1) o del ALTO (FAV2) de la ventana que cubre. El
Manual no dice que hacer si es parcial; criterio provisorio de Lucas (2026-11-05):
se considera si la cobertura es MAYOR que cobertura_min.

Prioridad por ventana (Lucas 2026-11-06): FAV1 = alero propio > horizontal dibujada
(la de menor D) > voladizo; FAV2 de cada lado = aleta propia > vertical dibujada o
autosombra, la mas cercana (menor S). Obstruccion.usada marca la que entra a la ficha.

P04 de las obstrucciones dibujadas (p04): se cuentan por defecto (Obstaculo.p04).
Largo automatico: horizontal = lo que se apoya en cada muro exterior que toca;
vertical = su alto; balcon = el largo de sus bordes apoyados en cada muro exterior
del nivel (contacto_balcon: los dos extremos del borde entre -contacto_m y
contacto_balcon_m de la cara interior, para aceptar un balcon dibujado desde la cara
exterior, y el balcon hacia afuera). Obstaculo.p04_largo lo fija a mano (todo en el
muro donde mas se apoya). El voladizo y la autosombra no suman P04. cev.py los
agrupa en filas de la ficha por tipo, muro, orientacion, elemento y aislacion: la
ficha reparte los puentes por orientacion ('CEV-CEVE' filas 169-177, columna N) y el
motor los multiplica por la temperatura sol-aire de cada orientacion (calculo_py,
qs[k]), asi que NO se pueden juntar orientaciones distintas.

proyecciones(): lo que se ve de las obstrucciones dibujadas en el alzado de un tramo
(el balcon no se dibuja en el alzado).
Criterio en config/cev.yaml (obstrucciones:), fuera de la interfaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml

from . import editor
from . import geometria as geo
from .modelo import Unidad

CONFIG = Path(__file__).parent / "config" / "cev.yaml"
P04_DEFECTO = {"elementos": ["Muro ", "Cornisa desplazada", "Marco Madera", "Marco Metalico"],
               "elemento": {"horizontal": "Muro ", "vertical": "Muro ", "balcon": "Muro "}, "aislacion": None}
DEFECTOS = {"activo": True, "cobertura_min": 0.5, "largo": "promedio", "muestras": 41, "decimales": 2,
            "alcance_m": 30.0, "contacto_m": 0.05, "contacto_balcon_m": 0.3, "autosombra": True,
            "p04": P04_DEFECTO}
AGRUPAR = {"promedio": lambda xs: sum(xs) / len(xs), "minimo": min, "maximo": max}
FAV2 = ("vertical", "autosombra")


@lru_cache(maxsize=1)
def _cev() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def config(cfg: dict | None = None) -> dict:
    """Criterio de deteccion. cfg: config/cev.yaml completo (None: el del archivo)."""
    base = cfg if cfg is not None else _cev()
    o = base.get("obstrucciones") or {}
    c = {**DEFECTOS, **o}
    p = o.get("p04") or {}
    c["p04"] = {**P04_DEFECTO, **p, "elemento": {**P04_DEFECTO["elemento"], **(p.get("elemento") or {})}}
    return c


def _tol() -> float:
    return geo._cfg()["dibujo"]["tolerancia_m"]


@dataclass(frozen=True)
class Obstruccion:
    tipo: str            # voladizo | horizontal | vertical | autosombra
    nivel: int           # nivel de lo que hace sombra (voladizo: el de arriba; las demas: el suyo)
    pano: int            # indice del pano (geometria) que tiene la ventana
    muro: str            # id del pano (N1-L1)
    ventana: int         # indice de la ventana en su tramo
    d: float             # FAV1: D [m]; FAV2: S [m]
    l: float             # FAV1: L [m]; FAV2: P [m]
    cobertura: float     # 0..1 del ancho (FAV1) o del alto (FAV2) de la ventana
    aplica: bool         # cumple el criterio de cobertura
    manual: bool         # la ventana tiene su propia proteccion de ese tipo (manda)
    obstaculo: int | None = None   # indice en Nivel.obstaculos (dibujadas)
    lado: str | None = None        # FAV2: izq | der (vistos desde el interior)
    usada: bool = False            # es la que entra a la ficha
    origen: str | None = None      # autosombra: id del muro propio que hace sombra

    @property
    def clave(self) -> tuple:
        return (self.pano, self.ventana)

    @property
    def fav(self) -> int:
        return 2 if self.tipo in FAV2 else 1


# --------------------------------------------------------------------------- geometria
def _ejes(a, b) -> tuple:
    largo = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / largo, (b[1] - a[1]) / largo
    return ux, uy, -uy, ux


def _dot(p, q, v) -> float:
    return (p[0] - q[0]) * v[0] + (p[1] - q[1]) * v[1]


def _cubre(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def rect(o) -> tuple:
    """(x0, y0, x1, y1) de una obstruccion horizontal."""
    return min(o.a[0], o.b[0]), min(o.a[1], o.b[1]), max(o.a[0], o.b[0]), max(o.a[1], o.b[1])


def z_horizontal(o, altura: float) -> float:
    """Cara inferior de una obstruccion horizontal desde el piso de su nivel."""
    return float(altura) if o.z is None else float(o.z)


def z_vertical(o, altura: float) -> tuple:
    """(base, tope) de una obstruccion vertical desde el piso de su nivel."""
    z0 = 0.0 if o.z is None else float(o.z)
    return z0, z0 + (float(altura) if o.alto is None else float(o.alto))


def contacto_vertical(o, a, b, contacto: float):
    """(s, P, punto) si la obstruccion vertical sale hacia afuera desde la recta a-b: un
    extremo a menos de contacto de la recta y el otro hacia el exterior. s se mide a lo
    largo de la recta desde a; P es la saliente perpendicular. None si no."""
    ux, uy, nx, ny = _ejes(a, b)
    mejor = None
    for pt, otro in ((o.a, o.b), (o.b, o.a)):
        d = abs(_dot(pt, a, (nx, ny)))
        p = _dot(otro, pt, (nx, ny))
        if d <= contacto and p > _tol() and (mejor is None or d < mejor[0]):
            mejor = (d, _dot(pt, a, (ux, uy)), p, pt)
    return None if mejor is None else mejor[1:]


def contacto_horizontal(o, a, b, contacto: float):
    """(s0, s1) a lo largo de la recta a-b (desde a) de una obstruccion horizontal que se
    apoya en ella: alguna parte a menos de contacto de la recta y otra hacia el
    exterior. Con muros a 90 grados es exacto; con muros en diagonal es la sombra del
    rectangulo sobre la recta. None si no se apoya."""
    ux, uy, nx, ny = _ejes(a, b)
    x0, y0, x1, y1 = rect(o)
    esq = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    ds = [_dot(c, a, (nx, ny)) for c in esq]
    if min(ds) > contacto or max(ds) <= _tol():
        return None
    ss = [_dot(c, a, (ux, uy)) for c in esq]
    return min(ss), max(ss)


def contacto_balcon(o, a, b, contacto: float, alcance: float) -> list:
    """[(s0, s1)] (desde a, a lo largo de la recta a-b, sin recortar a su largo) de los bordes
    del balcon que se apoyan en ella: los dos extremos del borde entre -contacto (hacia
    adentro) y alcance (hacia afuera: el espesor del muro, si se dibujo desde la cara
    exterior) y el balcon hacia afuera de ese borde. Intervalos unidos."""
    ux, uy, nx, ny = _ejes(a, b)
    vs = o.vertices
    m = len(vs)
    tramos = []
    for q in range(m):
        p1, p2 = vs[q], vs[(q + 1) % m]
        d1, d2 = _dot(p1, a, (nx, ny)), _dot(p2, a, (nx, ny))
        if not (-contacto <= d1 <= alcance and -contacto <= d2 <= alcance):
            continue
        s1, s2 = sorted((_dot(p1, a, (ux, uy)), _dot(p2, a, (ux, uy))))
        if s2 - s1 <= _tol():
            continue
        sm, dm = (s1 + s2) / 2, (d1 + d2) / 2 + 0.01
        if not editor.dentro((a[0] + ux * sm + nx * dm, a[1] + uy * sm + ny * dm), vs):
            continue                                 # el balcon queda hacia adentro del muro
        tramos.append((s1, s2))
    tramos.sort()
    unidos = []
    for s0, s1 in tramos:
        if unidos and s0 <= unidos[-1][1] + 1e-9:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], s1))
        else:
            unidos.append((s0, s1))
    return unidos


def _profundidad(poligono, p, n, alcance: float, tol: float) -> float:
    """[m] que recorre dentro del poligono el rayo que sale de p en la direccion n, si
    entra desde p (lo que esta mas lejos, separado del muro, no cuenta)."""
    from shapely.geometry import LineString, Point

    rayo = LineString([p, (p[0] + n[0] * alcance, p[1] + n[1] * alcance)])
    inter = rayo.intersection(poligono)
    if inter.is_empty:
        return 0.0
    origen = Point(p)
    mejor = 0.0
    for parte in getattr(inter, "geoms", [inter]):
        if parte.geom_type == "LineString" and parte.distance(origen) <= tol:
            mejor = max(mejor, parte.length)
    return mejor


def _rayos(poly, x, v, c, tol_origen) -> list:
    """Profundidad de cada rayo (desde puntos repartidos a lo ancho de la ventana v del
    pano x, hacia afuera) dentro del poligono."""
    ux, uy, nx, ny = _ejes(x.a, x.b)
    m = max(int(c["muestras"]), 1)
    out = []
    for q in range(m):
        s = v.x + v.ancho * (q + 0.5) / m
        out.append(_profundidad(poly, (x.a[0] + ux * s, x.a[1] + uy * s), (nx, ny), c["alcance_m"], tol_origen))
    return out


def _sobre_plano(pt, x, panos, contacto: float) -> bool:
    """El punto esta sobre algun muro del mismo plano de fachada que el pano x."""
    _, _, nx, ny = _ejes(x.a, x.b)
    for y in panos:
        if y.largo <= 0:
            continue
        _, _, mx, my = _ejes(y.a, y.b)
        if nx * mx + ny * my < 0.9999 or abs(_dot(y.a, x.a, (nx, ny))) > contacto:
            continue
        if editor.proyeccion(y.a, y.b, pt)[1] <= contacto:
            return True
    return False


def esquina_saliente(vs, i: int, al_fin: bool):
    """(P, lado, desfase) del muro propio que sale hacia afuera en el extremo del lado i
    (inicio o fin), saltando los vertices colineales del mismo plano de fachada: P =
    cuanto sale, perpendicular al lado (cara interior); lado = indice del muro que sale;
    desfase = metros del plano entre el extremo del lado i y el rincon. None si la
    esquina no es entrante (no hace sombra)."""
    m = len(vs)
    tol = _tol()
    a, b = vs[i], vs[(i + 1) % m]
    ux, uy, nx, ny = _ejes(a, b)
    c = (i + 1) % m if al_fin else i            # vertice del rincon
    desfase = 0.0
    for _ in range(m):
        lado = c if al_fin else (c - 1) % m     # muro que llega al rincon desde afuera del lado i
        q = vs[(c + 1) % m] if al_fin else vs[lado]
        dx, dy = q[0] - vs[c][0], q[1] - vs[c][1]
        largo = math.hypot(dx, dy)
        if largo <= tol:
            return None
        along = (dx * ux + dy * uy) / largo
        normal = dx * nx + dy * ny
        if abs(normal) <= tol and (along > 0 if al_fin else along < 0):
            desfase += largo                    # sigue el mismo plano de fachada
            c = (c + 1) % m if al_fin else lado
            continue
        return (normal, lado, desfase) if normal > tol else None
    return None


# --------------------------------------------------------------------------- deteccion
def _voladizos(u: Unidad, g, c: dict) -> list:
    if len(u.niveles) < 2:
        return []
    from shapely.geometry import Polygon

    tol = _tol()
    polys = [Polygon(n.vertices) for n in u.niveles]
    agrupar = AGRUPAR.get(c["largo"], AGRUPAR["promedio"])
    dec, cmin = int(c["decimales"]), float(c["cobertura_min"])
    out = []
    for x in g.panos:
        k = x.nivel
        if not x.exterior or not x.ventanas or k + 1 >= len(u.niveles) or x.largo <= 0:
            continue
        for v in x.ventanas:
            largos = _rayos(polys[k + 1], x, v, c, tol)
            bajo = [l for l in largos if l > tol]
            if not bajo:
                continue
            cob = len(bajo) / len(largos)
            out.append(Obstruccion(
                "voladizo", k + 1, x.indice, x.id, v.indice,
                d=round(max(u.altura - v.antepecho - v.alto, 0.0), dec), l=round(agrupar(bajo), dec),
                cobertura=cob, aplica=cob > cmin + 1e-9, manual=v.datos.proteccion.alero_l > 0))
    return out


def _horizontales(u: Unidad, g, c: dict) -> list:
    from shapely.geometry import box

    tol = _tol()
    agrupar = AGRUPAR.get(c["largo"], AGRUPAR["promedio"])
    dec, cmin = int(c["decimales"]), float(c["cobertura_min"])
    out = []
    for k, n in enumerate(u.niveles):
        hs = [(t, o) for t, o in enumerate(n.obstaculos) if o.tipo == "horizontal"]
        if not hs:
            continue
        for x in g.panos:
            if x.nivel != k or not x.exterior or not x.ventanas or x.largo <= 0:
                continue
            for t, o in hs:
                poly, zb = box(*rect(o)), z_horizontal(o, u.altura)
                for v in x.ventanas:
                    largos = _rayos(poly, x, v, c, c["contacto_m"])
                    bajo = [l for l in largos if l > tol]
                    if not bajo:
                        continue
                    d = zb - (v.antepecho + v.alto)
                    if d < -tol:                     # la losa no queda sobre la ventana
                        continue
                    cob = len(bajo) / len(largos)
                    out.append(Obstruccion(
                        "horizontal", k, x.indice, x.id, v.indice, d=round(max(d, 0.0), dec),
                        l=round(agrupar(bajo), dec), cobertura=cob, aplica=cob > cmin + 1e-9,
                        manual=v.datos.proteccion.alero_l > 0, obstaculo=t))
    return out


def _verticales(u: Unidad, g, c: dict) -> list:
    tol = _tol()
    dec, cmin, contacto = int(c["decimales"]), float(c["cobertura_min"]), float(c["contacto_m"])
    out = []
    for k, n in enumerate(u.niveles):
        vs = [(t, o) for t, o in enumerate(n.obstaculos) if o.tipo == "vertical"]
        if not vs:
            continue
        panos = [x for x in g.panos if x.nivel == k]
        for t, o in vs:
            z0, z1 = z_vertical(o, u.altura)
            for x in panos:
                if not x.exterior or not x.ventanas or x.largo <= 0:
                    continue
                ct = contacto_vertical(o, x.a, x.b, contacto)
                if ct is None or not _sobre_plano(ct[2], x, panos, contacto):
                    continue
                st, p = ct[0], ct[1]
                for v in x.ventanas:
                    w0, w1 = v.x, v.x + v.ancho
                    if st <= w0 + tol:
                        lado, s = "izq", max(w0 - st, 0.0)
                    elif st >= w1 - tol:
                        lado, s = "der", max(st - w1, 0.0)
                    else:
                        continue                     # la aleta cae dentro del ancho de la ventana
                    cob = _cubre(z0, z1, v.antepecho, v.antepecho + v.alto) / v.alto
                    pr = v.datos.proteccion
                    propia = (pr.aleta_izq_p if lado == "izq" else pr.aleta_der_p) > 0
                    out.append(Obstruccion(
                        "vertical", k, x.indice, x.id, v.indice, d=round(s, dec), l=round(p, dec),
                        cobertura=cob, aplica=cob > cmin + 1e-9, manual=propia, obstaculo=t, lado=lado))
    return out


def _autosombra(u: Unidad, g, c: dict) -> list:
    """FAV2 de los muros propios que salen en los rincones entrantes de cada nivel."""
    dec, cmin = int(c["decimales"]), float(c["cobertura_min"])
    panos = {(x.nivel, x.lado, x.tramo): x for x in g.panos}
    out = []
    for k, n in enumerate(u.niveles):
        vs = n.vertices
        for i, lado in enumerate(n.lados):
            if not any(t.exterior and t.ventanas for t in lado.tramos):
                continue
            largo = editor.largo_lado(n, i) if hasattr(editor, "largo_lado") else editor.limites(n, i)[-1]
            lim = editor.limites(n, i)
            aletas = []                              # (lado de la ventana, s del rincon, P, id del muro)
            ini, fin = esquina_saliente(vs, i, False), esquina_saliente(vs, i, True)
            if ini is not None:
                p, j, des = ini
                y = panos.get((k, j, len(n.lados[j].tramos) - 1))
                aletas.append(("izq", -des, p, y.id if y else f"N{k + 1}-L{j + 1}"))
            if fin is not None:
                p, j, des = fin
                y = panos.get((k, j, 0))
                aletas.append(("der", largo + des, p, y.id if y else f"N{k + 1}-L{j + 1}"))
            if not aletas:
                continue
            for jt, t in enumerate(lado.tramos):
                x = panos.get((k, i, jt))
                if x is None or not x.exterior or not x.ventanas:
                    continue
                for v in x.ventanas:
                    w0 = lim[jt] + v.x
                    w1 = w0 + v.ancho
                    cob = _cubre(0.0, u.altura, v.antepecho, v.antepecho + v.alto) / v.alto
                    pr = v.datos.proteccion
                    for ld, s_a, p, origen in aletas:
                        s = w0 - s_a if ld == "izq" else s_a - w1
                        propia = (pr.aleta_izq_p if ld == "izq" else pr.aleta_der_p) > 0
                        out.append(Obstruccion(
                            "autosombra", k, x.indice, x.id, v.indice, d=round(max(s, 0.0), dec),
                            l=round(p, dec), cobertura=cob, aplica=cob > cmin + 1e-9, manual=propia,
                            lado=ld, origen=origen))
    return out


def _elegir(obs: list) -> list:
    """Marca usada en la que entra a la ficha: FAV1, horizontal (menor D) antes que voladizo;
    FAV2 de cada lado, la de menor S (dibujada o autosombra; a igual S, la dibujada). Las que
    la ventana ya cubre con lo suyo no entran."""
    mejor = {}
    for i, o in enumerate(obs):
        if not o.aplica or o.manual:
            continue
        if o.fav == 2:
            clave, rango = (o.clave, o.lado), (o.d, 0 if o.tipo == "vertical" else 1)
        else:
            clave, rango = (o.clave, "fav1"), (0 if o.tipo == "horizontal" else 1, o.d)
        if clave not in mejor or rango < mejor[clave][0]:
            mejor[clave] = (rango, i)
    usadas = {i for _, i in mejor.values()}
    return [replace(o, usada=i in usadas) for i, o in enumerate(obs)]


def detectar(u: Unidad, g, cfg: dict | None = None) -> list:
    """[Obstruccion] de la unidad (g: su geometria): voladizos, horizontales y verticales
    dibujadas y autosombra, una por ventana afectada, con la que se usa marcada. Los
    balcones no hacen sombra."""
    c = config(cfg)
    if not c["activo"] or g is None:
        return []
    obs = _voladizos(u, g, c) + _horizontales(u, g, c) + _verticales(u, g, c)
    if c.get("autosombra", True):
        obs += _autosombra(u, g, c)
    return _elegir(obs)


def aplicar(u: Unidad, g, cfg: dict | None = None, obs: list | None = None):
    """La geometria con VentanaGeo.fav1_obstruccion = (D, L) y fav2_obstruccion = ((P, S) izq,
    (P, S) der) de las obstrucciones usadas (cev.fav_ventana las declara). obs: lo que
    entrego detectar (None: lo detecta)."""
    obs = detectar(u, g, cfg) if obs is None else obs
    f1, f2 = {}, {}
    for o in obs:
        if not o.usada:
            continue
        if o.fav == 1:
            f1[o.clave] = (o.d, o.l)
        else:
            f2.setdefault(o.clave, {})[o.lado] = (o.l, o.d)
    if not f1 and not f2:
        return g
    panos = []
    for x in g.panos:
        if any((x.indice, v.indice) in f1 or (x.indice, v.indice) in f2 for v in x.ventanas):
            vs = []
            for v in x.ventanas:
                cl = (x.indice, v.indice)
                lados = f2.get(cl)
                vs.append(replace(v, fav1_obstruccion=f1.get(cl),
                                  fav2_obstruccion=(lados.get("izq"), lados.get("der")) if lados else None))
            x = replace(x, ventanas=tuple(vs))
        panos.append(x)
    return replace(g, panos=panos)


def _n(v, d=2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def avisos(obs: list, cfg: dict | None = None) -> list:
    """Una linea por obstruccion, para el detalle del calculo."""
    minimo = float(config(cfg)["cobertura_min"])
    out = []
    for o in obs:
        if o.tipo == "voladizo":
            quien = f"voladizo del nivel {o.nivel + 1}"
        elif o.tipo == "autosombra":
            quien = f"autosombra del muro {o.origen}"
        else:
            quien = f"obstrucción {o.tipo} {(o.obstaculo or 0) + 1} del nivel {o.nivel + 1}"
        et = f"{o.muro}, ventana {o.ventana + 1}: {quien}"
        if o.fav == 1:
            fav, medidas = "FAV1", f"L {_n(o.l)} m, D {_n(o.d)} m"
        else:
            fav = "FAV2 " + ("izquierdo" if o.lado == "izq" else "derecho")
            medidas = f"P {_n(o.l)} m, S {_n(o.d)} m"
        cubre = f"cubre {_n(o.cobertura * 100, 0)} %"
        if o.manual:
            out.append(f"{et} ignorada (la ventana tiene su propia protección)")
        elif o.usada:
            out.append(f"{et} como {fav} ({medidas}, {cubre})")
        elif o.aplica:
            out.append(f"{et} no se usa: otra obstrucción manda en el {fav}")
        else:
            out.append(f"{et} {cubre} de la ventana: no se considera (criterio: más de {_n(minimo * 100, 0)} %)")
    return out


# --------------------------------------------------------------------------- P04
@dataclass(frozen=True)
class P04Obstaculo:
    nivel: int
    obstaculo: int
    tipo: str
    pano: int            # muro exterior donde se aloja (geometria)
    largo: float         # [m]
    elemento: str
    aislacion: str


def contactos(u: Unidad, g, k: int, o, cfg_o: dict | None = None) -> list:
    """[(indice del pano, largo apoyado [m])] de una obstruccion dibujada en los muros
    exteriores de su nivel k (vertical: su alto, en el muro donde nace; balcon: el largo
    de sus bordes apoyados en cada muro)."""
    c = cfg_o if cfg_o is not None else config()
    contacto, tol = float(c["contacto_m"]), _tol()
    out = []
    for x in g.panos:
        if x.nivel != k or not x.exterior or x.largo <= 0:
            continue
        if o.tipo == "horizontal":
            iv = contacto_horizontal(o, x.a, x.b, contacto)
            largo = _cubre(iv[0], iv[1], 0.0, x.largo) if iv else 0.0
            if largo > tol:
                out.append((x.indice, largo))
        elif o.tipo == "balcon":
            ivs = contacto_balcon(o, x.a, x.b, contacto, float(c.get("contacto_balcon_m", 0.3)))
            largo = sum(_cubre(s0, s1, 0.0, x.largo) for s0, s1 in ivs)
            if largo > tol:
                out.append((x.indice, largo))
        elif o.tipo == "vertical":
            ct = contacto_vertical(o, x.a, x.b, contacto)
            if ct is not None and editor.proyeccion(x.a, x.b, ct[2])[1] <= contacto:
                z0, z1 = z_vertical(o, u.altura)
                out.append((x.indice, z1 - z0))
                break
    return out


def p04(u: Unidad, g, cfg: dict | None = None, aislacion_defecto: str | None = None) -> list:
    """[P04Obstaculo] de las obstrucciones dibujadas que lo cuentan (Obstaculo.p04)."""
    c = config(cfg)
    pc = c["p04"]
    ais = pc.get("aislacion") or aislacion_defecto or "Sin Aislación"
    out = []
    if g is None:
        return out
    for k, n in enumerate(u.niveles):
        for t, o in enumerate(n.obstaculos):
            if not o.p04:
                continue
            piezas = contactos(u, g, k, o, c)
            if not piezas:
                continue
            if o.p04_largo is not None:
                principal = max(piezas, key=lambda q: q[1])[0]
                piezas = [(principal, float(o.p04_largo))]
            el = o.p04_elemento or pc["elemento"].get(o.tipo) or "Muro "
            out += [P04Obstaculo(k, t, o.tipo, x, round(l, 4), el, o.p04_aislacion or ais)
                    for x, l in piezas if l > 0]
    return out


# --------------------------------------------------------------------------- alzado
def proyecciones(u: Unidad, k: int, i: int, j: int, cfg: dict | None = None, espesor_h: float = 0.15,
                 espesor_v: float = 0.15) -> list:
    """[(indice, tipo, s0, s1, z0, z1)] de las obstrucciones dibujadas del nivel k que se
    apoyan en el plano del tramo (k, i, j), en sus coordenadas: s desde el inicio del
    tramo y z desde el piso. espesor_h: el de una horizontal sin espesor propio;
    espesor_v: el ancho con que se dibuja una vertical. Los balcones no se proyectan."""
    c = config(cfg)
    n = u.niveles[k]
    if not n.obstaculos:
        return []
    lim = editor.limites(n, i)
    a0, b0 = editor.extremos(n, i)
    ux, uy, _ = editor.direccion(a0, b0)
    a = (a0[0] + ux * lim[j], a0[1] + uy * lim[j])
    b = (a0[0] + ux * lim[j + 1], a0[1] + uy * lim[j + 1])
    largo = lim[j + 1] - lim[j]
    out = []
    for t, o in enumerate(n.obstaculos):
        if o.tipo == "horizontal":
            iv = contacto_horizontal(o, a, b, c["contacto_m"])
            if iv is None or _cubre(iv[0], iv[1], 0.0, largo) <= 0:
                continue
            z0 = z_horizontal(o, u.altura)
            out.append((t, "horizontal", iv[0], iv[1], z0, z0 + (espesor_h if o.alto is None else float(o.alto))))
        elif o.tipo == "vertical":
            ct = contacto_vertical(o, a, b, c["contacto_m"])
            if ct is None or not -0.5 <= ct[0] <= largo + 0.5:
                continue
            z0, z1 = z_vertical(o, u.altura)
            out.append((t, "vertical", ct[0] - espesor_v / 2, ct[0] + espesor_v / 2, z0, z1))
    return out
