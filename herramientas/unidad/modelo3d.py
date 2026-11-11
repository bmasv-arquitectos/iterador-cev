# -*- coding: utf-8 -*-
"""
Modelo 3D de una Unidad para ui.scene, descrito sin NiceGUI (se prueba solo).

  - Muros: prismas (Prisma) de espesor_muro hacia AFUERA de la cara interior (el
    dibujo es por la cara interior). En cada vertice los dos muros se encuentran
    en INGLETE: la cara exterior de cada uno llega hasta donde se cruzan las dos
    caras exteriores, asi comparten el corte diagonal (45 grados en esquinas a
    90 grados) y no se superponen, sea la esquina saliente o entrante. Si el
    angulo es tan agudo que el inglete pasa de inglete_max espesores, ese
    extremo se corta recto. Entre tramos de un mismo lado el corte es recto.
    Con muros_cubren_losas los muros suben un espesor de losa (tapan el canto
    de la losa de arriba) y los del nivel 1 bajan otro (tapan el piso).
    Cada muro se recorta por sus ventanas y puertas (piezas_muro), asi el
    vidrio se ve transparente. Todas las piezas se llaman "tramo|k|i|j" (un
    clic en cualquiera elige el muro).
  - Lineas (Linea): aristas para la vista en lineas ocultas: contorno de cada
    muro (abajo, arriba y verticales en sus esquinas), por cada vano su
    rectangulo en ambas caras y los cuatro derrames, y las aristas de las
    protecciones solares, de las obstrucciones, de los balcones y de los
    tabiques. Se corren lineas.desfase_m hacia afuera de la cara para que no
    parpadeen con ella; las ocultas las tapa el propio dibujo.
  - Vidrio ("ventana|k|i|j|m") y puerta ("puerta|k|i|j|m"): cajas delgadas al
    centro del muro (espesor_vidrio, espesor_puerta).
  - Protecciones solares ("proteccion|k|i|j|m", m = ventana): alero, aletas y
    lamas de la celosia (protecciones.piezas), cajas de proteccion.espesor_m.
  - Obstrucciones dibujadas ("obstaculo|k|t", en Escena.losas): la horizontal
    (clase obstaculo) es su rectangulo con la cara inferior a z del piso del nivel
    (por defecto la altura libre) y espesor obstaculo.espesor_m si no tiene alto;
    la vertical (clase obstaculo), su segmento con ancho obstaculo.ancho_m, de z
    (0) a z + alto (por defecto la altura libre); el balcon (clase balcon, verde),
    su poligono bajo el piso del nivel (cara superior en el piso terminado), de
    espesor obstaculo.balcon_espesor_m (por defecto espesor_losa) si no tiene alto.
  - Tabiques ("tabique|k|t", clase tabique, en Escena.losas): su segmento con
    ancho tabique.espesor_m, del piso al cielo del nivel. Un clic los elige.
  - Losas de espesor_losa: piso del nivel 1 (segun Unidad.piso), losa entre
    niveles (lo que se apoya en el nivel de abajo), voladizo (piso_expuesto),
    techo del ultimo nivel (Unidad.techo) y lo que un nivel deja sin cubrir
    (techo_expuesto). Los niveles se apilan: z_k = k (altura + espesor_losa).
  - Contexto (contexto()): los volumenes del entorno (Unidad.contexto, FAR
    dibujado), prismas "contexto|i" de clase contexto desde el terreno natural
    hasta h, con sus aristas (clase contexto). El piso terminado del nivel 1 esta
    en z = 0, asi que el terreno queda en z = -Unidad.npt. No entran en Escena: la
    vista los dibuja aparte (tambien con un dibujo con problemas). Por defecto la
    camara inicial no los encuadra (modelo3d.contexto.encuadre).
  - Un perimetro abierto (o un dibujo con problemas) no se levanta: la
    interfaz lo marca en el suelo (poligono_valido, encuadre).
  - Camara inicial (camara): mira la fachada frontal (lado 1 del nivel 1,
    Escena.frente = su normal exterior) y el lateral que queda a su izquierda
    para quien la mira desde afuera. Brujula (brujula): circulo y flecha al
    norte en el suelo, junto a ese lateral.
Un Prisma es un contorno en planta extruido desde z con un alto (ui.scene:
extrusion). Colores, espesores, camara y norte: config/editor.yaml (modelo3d:).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import protecciones
from .geometria import Geometria
from .modelo import Unidad

EPS = 1e-6
INFINITO = 1e9
CONTEXTO_DEFECTO = {"color": "#94a3b8", "opacidad": 0.35}
TABIQUE_DEFECTO = {"color": "#d1d5db", "opacidad": 1.0}
BALCON_DEFECTO = {"color": "#86efac", "opacidad": 1.0}


@dataclass(frozen=True)
class Caja:
    nombre: str
    clase: str
    centro: tuple                  # (x, y, z)
    tamano: tuple                  # (largo, espesor, alto)
    giro: float                    # [rad] en torno a z


@dataclass(frozen=True)
class Prisma:
    nombre: str
    clase: str
    contorno: tuple                # ((x, y), ...) en planta
    z: float                       # cara inferior
    alto: float


Losa = Prisma


@dataclass(frozen=True)
class Linea:
    a: tuple                       # (x, y, z)
    b: tuple
    clase: str                     # muro | vano | proteccion | obstaculo | balcon | tabique | contexto | norte


@dataclass
class Escena:
    cajas: list                    # vidrios, puertas y protecciones
    losas: list                    # losas, obstrucciones dibujadas, balcones y tabiques
    centro: tuple
    radio: float
    muros: list = field(default_factory=list)
    lineas: list = field(default_factory=list)
    frente: tuple = (0.0, 1.0)     # normal exterior (en planta) de la fachada frontal


def z_nivel(k: int, altura: float, losa: float) -> float:
    return k * (altura + losa)


def _partes(geom) -> list:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def poligono_valido(puntos, area_min: float = 1e-4) -> bool:
    """La polilinea cerrada encierra un area sin cruzarse (para pintarla en el suelo)."""
    if len(puntos) < 3:
        return False
    from shapely.geometry import Polygon

    p = Polygon(puntos)
    return p.is_valid and p.area > area_min


def encuadre(puntos, alto: float, est: dict) -> Escena:
    """Escena vacia centrada en los puntos, para ubicar la camara."""
    pts = list(puntos) or [(0.0, 0.0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    centro = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, alto / 2)
    radio = max(max(xs) - min(xs), max(ys) - min(ys), alto) / 2 + est["espesor_muro"]
    return Escena([], [], centro, radio)


def piezas_muro(largo: float, alto: float, vanos) -> list:
    """Rectangulos (s0, s1, z0, z1) del muro menos los vanos (x, z, ancho, alto).

    Franjas verticales entre los bordes de los vanos; en cada franja, lo que no
    tapan los vanos. Franjas vecinas con la misma altura se unen."""
    xs = {0.0, float(largo)}
    for x, _, a, _ in vanos:
        xs.update((min(max(x, 0.0), largo), min(max(x + a, 0.0), largo)))
    xs = sorted(xs)
    out, abiertas = [], {}
    for s0, s1 in zip(xs, xs[1:]):
        if s1 - s0 <= EPS:
            continue
        m = (s0 + s1) / 2
        huecos = sorted((max(z, 0.0), min(z + al, alto)) for x, z, a, al in vanos if x < m < x + a)
        franjas, z = [], 0.0
        for h0, h1 in huecos:
            if h0 > z + EPS:
                franjas.append((z, h0))
            z = max(z, h1)
        if alto > z + EPS:
            franjas.append((z, alto))
        nuevas = {}
        for f in franjas:
            idx = abiertas.get(f)
            if idx is not None and abs(out[idx][1] - s0) <= EPS:
                out[idx] = (out[idx][0], s1, f[0], f[1])
            else:
                out.append((s0, s1, f[0], f[1]))
                idx = len(out) - 1
            nuevas[f] = idx
        abiertas = nuevas
    return out


def _ejes(p) -> tuple:
    """(ux, uy, nx, ny): direccion del muro y normal exterior."""
    ux, uy = (p.b[0] - p.a[0]) / p.largo, (p.b[1] - p.a[1]) / p.largo
    return ux, uy, -uy, ux


def _cruce(p, d, q, e):
    cruz = d[0] * e[1] - d[1] * e[0]
    if abs(cruz) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / cruz
    return (p[0] + t * d[0], p[1] + t * d[1])


def inglete(p, q, vertice, em: float, limite: float) -> float:
    """Distancia a lo largo de p (desde p.a) donde termina su cara exterior junto al
    muro vecino q, que se encuentra con p en `vertice`."""
    ux, uy, nx, ny = _ejes(p)
    vx, vy, mx, my = _ejes(q)
    m = _cruce((vertice[0] + nx * em, vertice[1] + ny * em), (ux, uy),
               (q.a[0] + mx * em, q.a[1] + my * em), (vx, vy))
    if m is None or math.hypot(m[0] - vertice[0], m[1] - vertice[1]) > limite * em:
        m = (vertice[0] + nx * em, vertice[1] + ny * em)            # corte recto
    return (m[0] - p.a[0]) * ux + (m[1] - p.a[1]) * uy


def planta_muro(p, ea: float, eb: float, em: float) -> tuple:
    """Contorno local (s, d) del muro: cara interior 0..largo, exterior ea..eb."""
    if eb - ea < EPS:
        ea, eb = 0.0, p.largo
    return ((0.0, 0.0), (p.largo, 0.0), (eb, em), (ea, em))


def aristas_locales(planta, vanos, z_lo: float, z_hi: float, em: float, eps: float) -> list:
    """Aristas ((s, d, z), (s, d, z), clase) de un muro en coordenadas locales.

    planta: contorno (s, d) del muro; vanos: (x, z, ancho, alto) desde el piso;
    el muro va de z_lo a z_hi. Cada punto se corre eps hacia afuera de la cara
    en la que esta (las de los derrames, hacia el centro del vano)."""
    out = []
    zm = (z_lo + z_hi) / 2

    def fuera(s, d, z):
        return (s, d + (eps if d > em / 2 else -eps), z + (eps if z > zm else -eps))

    n = len(planta)
    for z in (z_lo, z_hi):
        for i in range(n):
            (s1, d1), (s2, d2) = planta[i], planta[(i + 1) % n]
            out.append((fuera(s1, d1, z), fuera(s2, d2, z), "muro"))
    for s, d in planta:
        out.append((fuera(s, d, z_lo), fuera(s, d, z_hi), "muro"))
    for x, z, a, al in vanos:
        esq = ((x, z), (x + a, z), (x + a, z + al), (x, z + al))
        cx, cz = x + a / 2, z + al / 2
        for d in (-eps, em + eps):
            for i in range(4):
                (s1, z1), (s2, z2) = esq[i], esq[(i + 1) % 4]
                out.append(((s1, d, z1), (s2, d, z2), "vano"))
        for s, zz in esq:
            ss = s + (eps if s < cx else -eps)
            z2 = zz + (eps if zz < cz else -eps)
            out.append(((ss, 0.0, z2), (ss, em, z2), "vano"))
    return out


def caja_aristas(s0, s1, d0, d1, z0, z1, eps: float = 0.0) -> list:
    """Las 12 aristas ((s, d, z), (s, d, z)) de una caja alineada con el muro."""
    s0, d0, z0 = s0 - eps, d0 - eps, z0 - eps
    s1, d1, z1 = s1 + eps, d1 + eps, z1 + eps
    out = []
    for d in (d0, d1):
        for z in (z0, z1):
            out.append(((s0, d, z), (s1, d, z)))
    for s in (s0, s1):
        for z in (z0, z1):
            out.append(((s, d0, z), (s, d1, z)))
    for s in (s0, s1):
        for d in (d0, d1):
            out.append(((s, d, z0), (s, d, z1)))
    return out


def _banda(a, b, ancho: float) -> tuple | None:
    """Contorno en planta de un segmento a-b con ese ancho (centrado), o None si no tiene largo."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo = math.hypot(dx, dy)
    if largo < EPS:
        return None
    nx, ny = -dy / largo * ancho / 2, dx / largo * ancho / 2
    return tuple((round(x, 6), round(y, 6)) for x, y in (
        (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)))


def obstaculo_prisma(o, altura: float, espesor_h: float, ancho_v: float, espesor_b: float = 0.2) -> tuple:
    """(contorno en planta, z de la cara inferior desde el piso del nivel, alto) de una
    obstruccion dibujada (modelo.Obstaculo)."""
    if o.tipo == "horizontal":
        x0, x1 = sorted((o.a[0], o.b[0]))
        y0, y1 = sorted((o.a[1], o.b[1]))
        cont = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        return cont, float(altura if o.z is None else o.z), float(espesor_h if o.alto is None else o.alto)
    if o.tipo == "balcon":
        e = float(espesor_b if o.alto is None else o.alto)
        return tuple((round(x, 6), round(y, 6)) for x, y in o.vertices), -e, e
    return _banda(o.a, o.b, ancho_v), float(0.0 if o.z is None else o.z), float(altura if o.alto is None else o.alto)


def tabique_prisma(tb, espesor: float):
    """Contorno en planta de un tabique (su segmento con ese espesor), o None."""
    return _banda(tb.a, tb.b, espesor)


def aristas_prisma(cont, z: float, alto: float, clase: str = "obstaculo") -> list:
    """Aristas (Linea) de un prisma: contorno abajo y arriba y las verticales."""
    out = []
    n = len(cont)
    for zz in (z, z + alto):
        for i in range(n):
            a, b = cont[i], cont[(i + 1) % n]
            out.append(Linea((a[0], a[1], zz), (b[0], b[1], zz), clase))
    for p in cont:
        out.append(Linea((p[0], p[1], z), (p[0], p[1], z + alto), clase))
    return out


def contexto(u: Unidad) -> tuple:
    """(prismas, lineas) de los volumenes de contexto: "contexto|i", desde el terreno natural
    (z = -npt; el piso terminado del nivel 1 esta en z = 0) hasta h."""
    prismas, lineas = [], []
    z0 = -float(u.npt)
    for i, c in enumerate(u.contexto):
        cont = tuple((round(x, 6), round(y, 6)) for x, y in c.vertices)
        prismas.append(Prisma(f"contexto|{i}", "contexto", cont, z0, float(c.h)))
        lineas += aristas_prisma(cont, z0, float(c.h), "contexto")
    return prismas, lineas


def construir(u: Unidad, g: Geometria, est: dict) -> Escena:
    from shapely.geometry import Polygon, box

    em, el = est["espesor_muro"], est["espesor_losa"]
    limite = est.get("inglete_max", 4.0)
    cubrir = est.get("muros_cubren_losas", True)
    eps = (est.get("lineas") or {}).get("desfase_m", 0.004)
    pe = est.get("proteccion") or {}
    esp_p, max_l = pe.get("espesor_m", 0.03), pe.get("max_lamas", 60)
    h = u.altura
    antes = {e.despues: e.antes for e in g.esquinas}
    despues = {e.antes: e.despues for e in g.esquinas}
    cajas, muros, lineas = [], [], []
    for p in g.panos:
        ux, uy, nx, ny = _ejes(p)
        z0 = z_nivel(p.nivel, h, el)
        bajo = el if cubrir and p.nivel == 0 else 0.0
        alto_muro = h + el if cubrir else h
        giro = math.atan2(uy, ux)
        nombre = f"tramo|{p.nivel}|{p.lado}|{p.tramo}"
        clase = "exterior" if p.exterior else "adiabatico"
        ea = inglete(p, g.panos[antes[p.indice]], p.a, em, limite) if p.indice in antes else 0.0
        eb = inglete(p, g.panos[despues[p.indice]], p.b, em, limite) if p.indice in despues else p.largo
        planta = planta_muro(p, ea, eb, em)
        base = Polygon(planta)

        def mundo(s, d):
            return (round(p.a[0] + ux * s + nx * d, 6), round(p.a[1] + uy * s + ny * d, 6))

        def linea(a3, b3, cl):
            lineas.append(Linea(mundo(a3[0], a3[1]) + (round(z0 + a3[2], 6),),
                                mundo(b3[0], b3[1]) + (round(z0 + b3[2], 6),), cl))

        vanos = [(w.x, w.antepecho, w.ancho, w.alto) for w in p.ventanas]
        vanos += [(d.x, 0.0, d.ancho, d.alto) for d in p.puertas]
        corridos = [(x, z + bajo, a, al) for x, z, a, al in vanos]
        for s0, s1, za, zb in piezas_muro(p.largo, alto_muro + bajo, corridos):
            lo = -INFINITO if s0 <= EPS else s0
            hi = INFINITO if s1 >= p.largo - EPS else s1
            for parte in _partes(base.intersection(box(lo, -1.0, hi, em + 1.0))):
                if parte.area > EPS:
                    cont = tuple(mundo(s, d) for s, d in list(parte.exterior.coords)[:-1])
                    muros.append(Prisma(nombre, clase, cont, z0 - bajo + za, zb - za))
        for a3, b3, cl in aristas_locales(planta, vanos, -bajo, alto_muro, em, eps):
            linea(a3, b3, cl)

        def en(s, z, d=em / 2):
            return (p.a[0] + ux * s + nx * d, p.a[1] + uy * s + ny * d, z0 + z)

        for w in p.ventanas:
            sufijo = f"{p.nivel}|{p.lado}|{p.tramo}|{w.indice}"
            cajas.append(Caja(f"ventana|{sufijo}", "vidrio",
                              en(w.x + w.ancho / 2, w.antepecho + w.alto / 2),
                              (w.ancho, est["espesor_vidrio"], w.alto), giro))
            for _, s0, s1, d0, d1, za, zb in protecciones.piezas(w.datos, em, esp_p, max_l):
                cajas.append(Caja(f"proteccion|{sufijo}", "proteccion", en((s0 + s1) / 2, (za + zb) / 2, (d0 + d1) / 2),
                                  (s1 - s0, d1 - d0, zb - za), giro))
                for a3, b3 in caja_aristas(s0, s1, d0, d1, za, zb, eps / 2):
                    linea(a3, b3, "proteccion")
        for m, d in enumerate(p.puertas):
            cajas.append(Caja(f"puerta|{p.nivel}|{p.lado}|{p.tramo}|{m}", "puerta",
                              en(d.x + d.ancho / 2, d.alto / 2), (d.ancho, est["espesor_puerta"], d.alto), giro))

    polys = [Polygon(n.vertices) for n in u.niveles]
    losas = []

    def agregar(nombre, clase, geom, z):
        for i, parte in enumerate(_partes(geom)):
            if parte.area > est["area_min_m2"]:
                cont = tuple((round(x, 6), round(y, 6)) for x, y in list(parte.exterior.coords)[:-1])
                losas.append(Prisma(f"{nombre}|{i}", clase, cont, z, el))

    top = len(polys) - 1
    for k, poly in enumerate(polys):
        z0 = z_nivel(k, h, el)
        if k == 0:
            agregar("piso|0", f"piso_{u.piso}", poly, z0 - el)
        else:
            agregar(f"piso|{k}", "losa_entre_niveles", poly.intersection(polys[k - 1]), z0 - el)
            agregar(f"voladizo|{k}", f"piso_{u.piso_expuesto}", poly.difference(polys[k - 1]), z0 - el)
        if k == top:
            agregar(f"techo|{k}", f"techo_{u.techo}", poly, z0 + h)
        else:
            agregar(f"techo|{k}", f"techo_{u.techo_expuesto}", poly.difference(polys[k + 1]), z0 + h)

    eo = est.get("obstaculo") or {}
    esp_h, ancho_v = float(eo.get("espesor_m", 0.15)), float(eo.get("ancho_m", 0.15))
    esp_b = float(eo.get("balcon_espesor_m", el))
    esp_t = float((est.get("tabique") or {}).get("espesor_m", 0.10))
    obst_pts = []
    for k, n in enumerate(u.niveles):
        zk = z_nivel(k, h, el)
        for t, o in enumerate(n.obstaculos):
            cont, zb, alto = obstaculo_prisma(o, h, esp_h, ancho_v, esp_b)
            if cont is None:
                continue
            clase = "balcon" if o.tipo == "balcon" else "obstaculo"
            losas.append(Prisma(f"obstaculo|{k}|{t}", clase, cont, zk + zb, alto))
            lineas += aristas_prisma(cont, zk + zb, alto, clase)
            obst_pts += list(cont)
        for t, tb in enumerate(n.tabiques):
            cont = tabique_prisma(tb, esp_t)
            if cont is None:
                continue
            losas.append(Prisma(f"tabique|{k}|{t}", "tabique", cont, zk, h))
            lineas += aristas_prisma(cont, zk, h, "tabique")
    if (est.get("contexto") or {}).get("encuadre"):    # la camara tambien encuadra el contexto
        obst_pts += [p for c in u.contexto for p in c.vertices]

    xs = [p[0] for n in u.niveles for p in n.vertices] + [p[0] for p in obst_pts]
    ys = [p[1] for n in u.niveles for p in n.vertices] + [p[1] for p in obst_pts]
    alto = z_nivel(top, h, el) + h + el
    centro = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, alto / 2)
    radio = max(max(xs) - min(xs), max(ys) - min(ys), alto) / 2 + em
    p0 = next((p for p in g.panos if p.nivel == 0 and p.lado == 0), None)
    frente = (round(_ejes(p0)[2], 9) + 0.0, round(_ejes(p0)[3], 9) + 0.0) if p0 is not None else (0.0, 1.0)
    return Escena(cajas, losas, centro, radio, muros, lineas, frente)


def lateral(esc: Escena) -> tuple:
    """Direccion (en planta) del lateral que queda a la izquierda de la fachada frontal
    para quien la mira desde afuera."""
    fx, fy = esc.frente
    return (fy, -fx)


def camara(esc: Escena, est: dict) -> dict:
    """Vista axonometrica que muestra la fachada frontal y su lateral izquierdo (visto
    desde afuera), mirando al centro. Pesos en est['camara']: frente, lado, alto."""
    cx, cy, cz = esc.centro
    r = esc.radio * est["distancia_camara"]
    c = est.get("camara") or {}
    a, b, h = c.get("frente", 0.8), c.get("lado", 0.6), c.get("alto", 0.7)
    fx, fy = esc.frente
    lx, ly = lateral(esc)
    return dict(x=cx + r * (a * fx + b * lx), y=cy + r * (a * fy + b * ly), z=cz + h * r,
                look_at_x=cx, look_at_y=cy, look_at_z=cz)


def norte(azimut_y: float) -> tuple:
    """Direccion del norte en planta: +y apunta al azimut azimut_y (grados, horario)."""
    a = math.radians(azimut_y)
    return (-math.sin(a), math.cos(a))


def brujula(esc: Escena, azimut_y: float, est: dict) -> tuple:
    """(lineas, (x, y, z) de la letra): circulo y flecha al norte en el suelo, al lado
    del lateral visible desde la camara inicial. Medidas en est['norte']."""
    n = est.get("norte") or {}
    R, sep, z = n.get("radio_m", 0.8), n.get("separacion_m", 1.0), n.get("z_m", 0.01)
    seg = max(8, int(n.get("segmentos", 48)))
    lx, ly = lateral(esc)
    d = esc.radio + sep + R
    cx, cy = esc.centro[0] + lx * d, esc.centro[1] + ly * d
    nx, ny = norte(azimut_y)
    px, py = ny, -nx
    out = []
    pts = [(cx + R * math.cos(2 * math.pi * k / seg), cy + R * math.sin(2 * math.pi * k / seg))
           for k in range(seg + 1)]
    for p, q in zip(pts, pts[1:]):
        out.append(Linea((p[0], p[1], z), (q[0], q[1], z), "norte"))
    punta = (cx + nx * R, cy + ny * R)
    out.append(Linea((cx - nx * R, cy - ny * R, z), punta + (z,), "norte"))
    w = R * n.get("punta", 0.3)
    for s in (1, -1):
        base = (punta[0] - nx * w + s * px * w * 0.6, punta[1] - ny * w + s * py * w * 0.6)
        out.append(Linea(base + (z,), punta + (z,), "norte"))
    f = n.get("letra_factor", 1.4)
    return out, (cx + nx * R * f, cy + ny * R * f, z)


BOTONES = {"rotar": 0, "zoom": 1, "desplazar": 2}     # THREE.MOUSE


def botones_raton(est: dict) -> dict:
    """mouseButtons de OrbitControls segun config/editor.yaml (modelo3d.raton)."""
    r = est.get("raton") or {}
    return {"LEFT": BOTONES[r.get("izquierdo", "rotar")], "MIDDLE": BOTONES[r.get("medio", "desplazar")],
            "RIGHT": BOTONES[r.get("derecho", "desplazar")]}


def paleta(est: dict, render: str) -> dict:
    """Colores de las caras: clases:, y en el modo lineas lo que redefina lineas.clases.
    Sin color propio, las obstrucciones usan el de las protecciones, el contexto un gris
    transparente (CONTEXTO_DEFECTO), los tabiques un gris claro (TABIQUE_DEFECTO) y los
    balcones un verde (BALCON_DEFECTO)."""
    p = dict(est["clases"])
    if render == "lineas":
        p.update((est.get("lineas") or {}).get("clases") or {})
    p.setdefault("obstaculo", p.get("proteccion") or {"color": "#d6d3d1", "opacidad": 1.0})
    p.setdefault("contexto", dict(CONTEXTO_DEFECTO))
    p.setdefault("tabique", dict(TABIQUE_DEFECTO))
    p.setdefault("balcon", dict(BALCON_DEFECTO))
    return p
