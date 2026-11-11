# -*- coding: utf-8 -*-
"""
Edicion de una Unidad (modelo.py) sin interfaz: la usa el editor de planta
(herramientas/app_unidad) y se prueba sin NiceGUI.

Todas las funciones devuelven una Unidad NUEVA (los modelos son inmutables), asi
deshacer es guardar la anterior. Indices desde 0: k = nivel, i = lado, j = tramo.
Las distancias a lo largo de un lado (s, cortes) se miden desde su vertice inicial.

Ajuste del dibujo (config/editor.yaml, snap:; la interfaz lo apaga con Shift):
  - dibujando, cada punto queda desde el anterior en un angulo multiplo de
    snap.angulo (10 grados) y a un largo multiplo de snap.largo_m (10 cm); si va
    horizontal o vertical y pasa cerca de la x o la y de otro punto, se alinea;
  - al arrastrar un vertice se alinea en x o en y con sus vecinos u otros
    vertices; si no, se pega a un angulo multiplo de snap.angulo desde un vecino;
  - los lados pueden quedar en cualquier angulo (config/unidad.yaml).
fijar_largo cambia el largo de un muro moviendo el muro vecino en paralelo, asi
ninguna esquina cambia de angulo. abrir_perimetro quita un muro del nivel mas
alto y devuelve el resto como polilinea abierta, para redibujarla.

Vanos (ventanas y puertas) de un tramo exterior: agregar_vano, mover_vano,
redimensionar_vano (posicion y medidas), eliminar_vano y vano_desde_esquinas
(dos clics en el alzado; la puerta parte del piso; los dos nacen siguiendo la
solucion general). redimensionar_rect calcula el rectangulo al arrastrar sus
bordes en el alzado. No pueden salirse del muro ni montarse entre si. Conservan
su posicion absoluta al cortar, unir o mover un corte; un corte no puede
atravesarlos. Un tramo que pasa a adiabatico los pierde.
Tabiques: agregar, eliminar y mover_tabique (sus extremos; edicion_tabiques.py lo
usa con la herramienta Mover).
Obstrucciones dibujadas (modelo.Obstaculo, en Nivel.obstaculos): obstaculo_nuevo
(dos clics; la horizontal es un rectangulo de lados paralelos a los ejes),
balcon_nuevo (polilinea cerrada: el balcon, solo P04), ajustar_obstaculo y
ajustar_balcon (el primer punto se pega al muro), agregar, eliminar, cambiar, mover
y pasar a otro nivel.
Desplazar un lado (mover_lado) corre sus extremos sobre los lados vecinos; si un
vecino sigue la misma recta, se agrega un lado corto que hace el quiebre (asi se
arma una L desde un rectangulo: insertar_vertice + mover_lado).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml

from . import geometria
from .modelo import (DEFECTO, GENERAL, MAX_NIVELES, Lado, Nivel, Obstaculo, Puerta, Tabique, Tramo, Unidad,
                     Ventana, area_firmada, balcon_desde, horario, nivel_simple, rectangulo)

CONFIG = Path(__file__).parent / "config" / "editor.yaml"
EPS = 1e-9
TIPOS = ("vertice", "corte", "tramo", "tabique", "obstaculo")
CAMPOS = {"ventana": "ventanas", "puerta": "puertas"}


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def config() -> dict:
    return cargar_config()


@lru_cache(maxsize=1)
def _dib() -> dict:
    c = geometria.cargar_config()
    return {**c["dibujo"], **c["limites"]}


def _snap() -> dict:
    return config()["snap"]


# --------------------------------------------------------------------------- puntos
def _r(v: float) -> float:
    return round(float(v), 6) + 0.0


def _rp(p) -> tuple:
    return (_r(p[0]), _r(p[1]))


def redondear(v: float, precision: float | None = None) -> float:
    q = precision or _dib()["precision_m"]
    return _r(round(float(v) / q) * q)


def ajustar(p, precision: float | None = None) -> tuple:
    return (redondear(p[0], precision), redondear(p[1], precision))


def distancia(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def direccion(a, b) -> tuple:
    """(ux, uy, largo) de a hacia b."""
    largo = distancia(a, b)
    return (b[0] - a[0]) / largo, (b[1] - a[1]) / largo, largo


def angulo(a, b) -> float:
    """Direccion de a hacia b en grados (0 = +x, antihorario)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def dentro(p, vertices) -> bool:
    """p esta dentro del poligono (rayo hacia +x; el borde puede caer de cualquier lado)."""
    x, y = p
    n = len(vertices)
    adentro = False
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            adentro = not adentro
    return adentro


def atraer(p, puntos, radio: float):
    """El punto de `puntos` mas cercano a p si esta a menos de radio (si no, None)."""
    mejor = min(puntos, key=lambda q: distancia(p, q), default=None)
    return _rp(mejor) if mejor is not None and distancia(p, mejor) <= radio else None


def ajustar_desde(origen, p, paso: float | None = None, largo: float | None = None,
                  alinear=(), radio: float = 0.0) -> tuple:
    """p visto desde origen: angulo multiplo de paso y largo multiplo de `largo`."""
    paso = paso or _snap()["angulo"]
    q = largo or _snap()["largo_m"]
    if distancia(origen, p) < EPS:
        return _rp(origen)
    a = math.radians(round(angulo(origen, p) / paso) * paso)
    ux, uy = _r(math.cos(a)), _r(math.sin(a))
    dist = (p[0] - origen[0]) * ux + (p[1] - origen[1]) * uy
    dist = max(q, round(dist / q) * q)
    x, y = origen[0] + ux * dist, origen[1] + uy * dist
    if radio > 0 and (ux == 0.0 or uy == 0.0):
        eje = 0 if uy == 0.0 else 1               # coordenada que avanza
        actual = (x, y)[eje]
        mejor = None
        for pt in alinear:
            dd = abs(pt[eje] - actual)
            mismo_lado = (pt[eje] - origen[eje]) * (actual - origen[eje]) > EPS
            if dd <= radio and mismo_lado and (mejor is None or dd < mejor[0]):
                mejor = (dd, pt[eje])
        if mejor is not None:
            x, y = (mejor[1], y) if eje == 0 else (x, mejor[1])
    return (_r(x), _r(y))


def ajustar_vertice(p, vecinos, otros=(), radio: float = 0.0, paso: float | None = None) -> tuple:
    """Vertice arrastrado: se alinea en x o en y con vecinos u otros puntos; si no,
    queda en un angulo multiplo de paso desde un vecino; si no, a 1 cm."""
    mx = my = None
    for q in list(vecinos) + list(otros):
        dx, dy = abs(q[0] - p[0]), abs(q[1] - p[1])
        if dx <= radio and (mx is None or dx < mx[0]):
            mx = (dx, q[0])
        if dy <= radio and (my is None or dy < my[0]):
            my = (dy, q[1])
    if mx or my:
        return _rp((mx[1] if mx else redondear(p[0]), my[1] if my else redondear(p[1])))
    paso = paso or _snap()["angulo"]
    mejor = None
    for q in vecinos:
        if distancia(q, p) < EPS:
            continue
        a = math.radians(round(angulo(q, p) / paso) * paso)
        ux, uy = math.cos(a), math.sin(a)
        s = (p[0] - q[0]) * ux + (p[1] - q[1]) * uy
        c = (q[0] + ux * s, q[1] + uy * s)
        dd = distancia(c, p)
        if dd <= radio and (mejor is None or dd < mejor[0]):
            mejor = (dd, c)
    return _rp(mejor[1]) if mejor else ajustar(p)


def _interseccion(p, d, q, e):
    """Punto comun de las rectas p + t d y q + s e (None si son paralelas)."""
    cruz = d[0] * e[1] - d[1] * e[0]
    if abs(cruz) < 1e-12 * max(1.0, math.hypot(*d) * math.hypot(*e)):
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / cruz
    return (p[0] + t * d[0], p[1] + t * d[1])


def proyeccion(a, b, p) -> tuple:
    """(punto del segmento a-b mas cercano a p, distancia, s desde a)."""
    largo = distancia(a, b)
    if largo < EPS:
        return a, distancia(a, p), 0.0
    ux, uy = (b[0] - a[0]) / largo, (b[1] - a[1]) / largo
    s = min(max((p[0] - a[0]) * ux + (p[1] - a[1]) * uy, 0.0), largo)
    q = (a[0] + ux * s, a[1] + uy * s)
    return q, distancia(q, p), s


def cerrar(vertices) -> tuple:
    """Polilinea dibujada -> vertices del perimetro en sentido horario (sin repetir el primero)."""
    limpio = []
    for v in (_rp(v) for v in vertices):
        if not limpio or distancia(limpio[-1], v) > EPS:
            limpio.append(v)
    while len(limpio) > 1 and distancia(limpio[-1], limpio[0]) <= EPS:
        limpio.pop()
    if len(limpio) < 3:
        raise ValueError("Un perímetro necesita al menos 3 vértices")
    if abs(area_firmada(limpio)) < 1e-6:
        raise ValueError("El perímetro no encierra un área")
    return horario(limpio)


# --------------------------------------------------------------------------- consultas
def extremos(n: Nivel, i: int) -> tuple:
    return n.vertices[i], n.vertices[(i + 1) % len(n.vertices)]


def largo_lado(n: Nivel, i: int) -> float:
    return distancia(*extremos(n, i))


def limites(n: Nivel, i: int) -> tuple:
    """(0, cortes..., largo del lado)."""
    return (0.0,) + tuple(n.lados[i].cortes) + (largo_lado(n, i),)


def largo_tramo(n: Nivel, i: int, j: int) -> float:
    lim = limites(n, i)
    return lim[j + 1] - lim[j]


def tramo_en(n: Nivel, i: int, s: float) -> int:
    lim = limites(n, i)
    for j in range(len(lim) - 1):
        if s < lim[j + 1]:
            return j
    return len(lim) - 2


def punto_en(n: Nivel, i: int, s: float) -> tuple:
    a, b = extremos(n, i)
    ux, uy, _ = direccion(a, b)
    return (a[0] + ux * s, a[1] + uy * s)


def normal_exterior(n: Nivel, i: int) -> tuple:
    """Perimetro horario: el exterior queda a la izquierda del recorrido."""
    ux, uy, _ = direccion(*extremos(n, i))
    return (-uy, ux)


def rect(tipo: str, w) -> tuple:
    """(x, z, ancho, alto) de una ventana o puerta (la puerta parte del piso)."""
    return (w.x, w.antepecho if tipo == "ventana" else 0.0, w.ancho, w.alto)


def vanos(t: Tramo) -> list:
    """[(tipo, indice, ventana o puerta)] de un tramo."""
    return [("ventana", m, w) for m, w in enumerate(t.ventanas)] + \
           [("puerta", m, p) for m, p in enumerate(t.puertas)]


@dataclass(frozen=True)
class Toque:
    """Lo que hay bajo el cursor."""
    tipo: str                      # vertice | corte | tramo | tabique | obstaculo | punto (de un perimetro abierto)
    lado: int = -1
    tramo: int = -1                # tramo del lado; en un tabique que se arrastra: extremo 0 (a), 1 (b), -1 cuerpo
    indice: int = -1               # vertice, corte (dentro del lado), tabique, obstaculo o punto
    s: float = 0.0                 # distancia desde el inicio del lado (o del tabique)
    punto: tuple = (0.0, 0.0)


def _toca_obstaculo(o, p, radio: float):
    """(s, punto) si p cae sobre la obstruccion (a menos de radio), o None."""
    if o.tipo == "vertical":
        q, dist, s = proyeccion(o.a, o.b, p)
        return (s, q) if dist <= radio else None
    if o.tipo == "balcon":
        vs, m = o.vertices, len(o.vertices)
        if dentro(p, vs) or any(proyeccion(vs[i], vs[(i + 1) % m], p)[1] <= radio for i in range(m)):
            return (0.0, _rp(p))
        return None
    x0, x1 = sorted((o.a[0], o.b[0]))
    y0, y1 = sorted((o.a[1], o.b[1]))
    if x0 - radio <= p[0] <= x1 + radio and y0 - radio <= p[1] <= y1 + radio:
        return (0.0, _rp(p))
    return None


def tocar(n: Nivel, p, radio: float, tipos=TIPOS) -> Toque | None:
    """Prioridad: vertice, corte, muro (el mas cercano), tabique, obstruccion; solo los tipos pedidos."""
    if "vertice" in tipos:
        for i, v in enumerate(n.vertices):
            if distancia(v, p) <= radio:
                return Toque("vertice", indice=i, punto=v)
    if "corte" in tipos:
        for i, lado in enumerate(n.lados):
            for c_i, c in enumerate(lado.cortes):
                q = punto_en(n, i, c)
                if distancia(q, p) <= radio:
                    return Toque("corte", lado=i, tramo=c_i, indice=c_i, s=c, punto=q)
    if "tramo" in tipos:
        mejor = None
        for i in range(len(n.vertices)):
            q, dist, s = proyeccion(*extremos(n, i), p)
            if dist <= radio and (mejor is None or dist < mejor[0]):
                mejor = (dist, i, s, q)
        if mejor is not None:
            _, i, s, q = mejor
            return Toque("tramo", lado=i, tramo=tramo_en(n, i, s), s=s, punto=q)
    if "tabique" in tipos:
        for t_i, tb in enumerate(n.tabiques):
            q, dist, s = proyeccion(tb.a, tb.b, p)
            if dist <= radio:
                return Toque("tabique", indice=t_i, s=s, punto=q)
    if "obstaculo" in tipos:
        for t_i, o in enumerate(n.obstaculos):
            hit = _toca_obstaculo(o, p, radio)
            if hit is not None:
                return Toque("obstaculo", indice=t_i, s=hit[0], punto=hit[1])
    return None


def proyectar_a_muro(n: Nivel, p, radio: float) -> tuple:
    """p pegado al muro mas cercano si esta a menos de radio."""
    mejor = None
    for i in range(len(n.vertices)):
        q, dist, _ = proyeccion(*extremos(n, i), p)
        if dist <= radio and (mejor is None or dist < mejor[0]):
            mejor = (dist, q)
    return _rp(mejor[1]) if mejor else p


def extender_a_muro(n: Nivel, origen, p, radio: float) -> tuple:
    """p llevado, sobre la recta origen-p, hasta el muro que cruza a menos de radio."""
    if distancia(origen, p) < EPS:
        return p
    d = (p[0] - origen[0], p[1] - origen[1])
    mejor = None
    for i in range(len(n.vertices)):
        a, b = extremos(n, i)
        q = _interseccion(origen, d, a, (b[0] - a[0], b[1] - a[1]))
        if q is None or proyeccion(a, b, q)[1] > 1e-6:
            continue
        dist = distancia(q, p)
        if dist <= radio and (mejor is None or dist < mejor[0]):
            mejor = (dist, q)
    return _rp(mejor[1]) if mejor else p


# --------------------------------------------------------------------------- reemplazos
def _con_nivel(u: Unidad, k: int, n: Nivel) -> Unidad:
    niveles = list(u.niveles)
    niveles[k] = n
    return replace(u, niveles=tuple(niveles))


def _con_lado(u: Unidad, k: int, i: int, lado: Lado) -> Unidad:
    n = u.niveles[k]
    lados = list(n.lados)
    lados[i] = lado
    return _con_nivel(u, k, replace(n, lados=tuple(lados)))


def _con_tramo(u: Unidad, k: int, i: int, j: int, t: Tramo) -> Unidad:
    lado = u.niveles[k].lados[i]
    tramos = list(lado.tramos)
    tramos[j] = t
    return _con_lado(u, k, i, Lado(tuple(tramos), lado.cortes))


def _correr(t: Tramo, delta: float) -> Tramo:
    """Todos los vanos del tramo corridos delta metros (x + delta)."""
    return replace(t, ventanas=tuple(replace(w, x=_r(w.x + delta)) for w in t.ventanas),
                   puertas=tuple(replace(p, x=_r(p.x + delta)) for p in t.puertas))


def _partir(t: Tramo, s: float) -> tuple:
    """Un tramo en dos a s metros de su inicio; los vanos van a su lado."""
    izq = {"ventanas": [], "puertas": []}
    der = {"ventanas": [], "puertas": []}
    for campo in izq:
        for w in getattr(t, campo):
            if w.x + w.ancho <= s + EPS:
                izq[campo].append(w)
            elif w.x >= s - EPS:
                der[campo].append(replace(w, x=_r(max(w.x - s, 0.0))))
            else:
                raise ValueError("El corte atraviesa una ventana o puerta: muévela primero")
    return (replace(t, **{c: tuple(v) for c, v in izq.items()}),
            replace(t, **{c: tuple(v) for c, v in der.items()}))


# --------------------------------------------------------------------------- perimetro
def unidad_inicial(cfg: dict | None = None) -> Unidad:
    c = (cfg or config())["inicial"]
    lados = tuple(Lado((Tramo(cond),)) for cond in c["condiciones"])
    return Unidad(c["comuna"], (Nivel(rectangulo(c["largo"], c["ancho"]), lados),), float(c["altura"]),
                  azimut_y=float(c.get("azimut_y", 0)), dormitorios=int(c.get("dormitorios", 2)),
                  piso=c.get("piso", "adiabatico"), techo=c.get("techo", "adiabatico"),
                  tipo_vivienda=c.get("tipo_vivienda", "departamento"))


def vaciar(u: Unidad) -> Unidad:
    """Sin niveles; conserva los datos de la unidad (comuna, altura, pisos, etc.)."""
    return replace(u, niveles=())


def con_perimetro(u: Unidad, k: int, vertices, condicion: str = "exterior") -> Unidad:
    """Reemplaza el perimetro del nivel k (sin tabiques) o agrega uno si k == len(niveles)."""
    if k > len(u.niveles):
        raise ValueError(f"Dibuja primero el nivel {len(u.niveles) + 1}")
    if len(u.niveles) >= MAX_NIVELES and k == len(u.niveles):
        raise ValueError(f"Una unidad tiene como máximo {MAX_NIVELES} niveles")
    n = nivel_simple(vertices, condicion)
    niveles = list(u.niveles)
    if k == len(niveles):
        niveles.append(n)
    else:
        niveles[k] = n
    return replace(u, niveles=tuple(niveles))


def abrir_perimetro(u: Unidad, k: int, i: int) -> tuple:
    """Quita el muro i del nivel k (el mas alto): (unidad sin ese nivel, polilinea abierta).

    La polilinea va del final del muro quitado a su inicio dando la vuelta, asi
    seguir dibujando desde su ultimo punto rehace ese muro. Se pierden los
    tabiques, las obstrucciones, los vanos y las condiciones de los muros del nivel."""
    if k != len(u.niveles) - 1:
        raise ValueError("Solo se puede quitar un muro del nivel más alto: quita primero los de arriba")
    vs = u.niveles[k].vertices
    m = len(vs)
    return replace(u, niveles=u.niveles[:k]), tuple(vs[(i + 1 + x) % m] for x in range(m))


def mover_vertice(u: Unidad, k: int, i: int, p) -> Unidad:
    n = u.niveles[k]
    vs = list(n.vertices)
    vs[i] = _rp(p)
    return _con_nivel(u, k, replace(n, vertices=tuple(vs)))


def insertar_vertice(u: Unidad, k: int, i: int, s: float) -> Unidad:
    """Vertice nuevo sobre el lado i, a s metros de su inicio (el lado queda en dos)."""
    n = u.niveles[k]
    lado, lim = n.lados[i], limites(n, i)
    s = redondear(s)
    lmin = _dib()["lado_min"]
    if s < lmin - EPS or s > lim[-1] - lmin + EPS:
        raise ValueError("El vértice queda demasiado cerca de un extremo del lado")
    p = _rp(punto_en(n, i, s))
    c_igual = next((c for c, x in enumerate(lado.cortes) if abs(x - s) <= 1e-6), None)
    if c_igual is not None:
        izq = Lado(lado.tramos[:c_igual + 1], lado.cortes[:c_igual])
        der = Lado(lado.tramos[c_igual + 1:], tuple(_r(x - s) for x in lado.cortes[c_igual + 1:]))
    else:
        j = tramo_en(n, i, s)
        a, b = _partir(lado.tramos[j], s - lim[j])
        izq = Lado(lado.tramos[:j] + (a,), lado.cortes[:j])
        der = Lado((b,) + lado.tramos[j + 1:], tuple(_r(x - s) for x in lado.cortes[j:]))
    vs = n.vertices[:i + 1] + (p,) + n.vertices[i + 1:]
    lados = n.lados[:i] + (izq, der) + n.lados[i + 1:]
    return _con_nivel(u, k, replace(n, vertices=vs, lados=lados))


def eliminar_vertice(u: Unidad, k: int, i: int) -> Unidad:
    """Si los dos lados siguen la misma recta se unen con sus tramos; si no, queda un lado nuevo."""
    n = u.niveles[k]
    vs, m = n.vertices, len(n.vertices)
    if m <= 3:
        raise ValueError("Un perímetro necesita al menos 3 vértices: borra un muro para abrirlo "
                         "o usa «Eliminar todo»")
    ia = (i - 1) % m
    d1 = direccion(vs[ia], vs[i])
    d2 = direccion(vs[i], vs[(i + 1) % m])
    cruz = d1[0] * d2[1] - d1[1] * d2[0]
    la, lb = n.lados[ia], n.lados[i]
    if abs(cruz) < 1e-9 and d1[0] * d2[0] + d1[1] * d2[1] > 0:
        largo = d1[2]
        nuevo = Lado(la.tramos + lb.tramos, la.cortes + (_r(largo),) + tuple(_r(c + largo) for c in lb.cortes))
    else:
        t = la.tramos[0]
        nuevo = Lado((Tramo(t.condicion, t.solucion),))
    lados = list(n.lados)
    lados[ia] = nuevo
    del lados[i]
    vs2 = list(vs)
    del vs2[i]
    return _con_nivel(u, k, replace(n, vertices=tuple(vs2), lados=tuple(lados)))


def mover_lado(u: Unidad, k: int, i: int, d: float, ajustar_d: bool = True) -> Unidad:
    """Desplaza el lado i d metros en perpendicular (+ hacia afuera)."""
    n = u.niveles[k]
    vs, m = n.vertices, len(n.vertices)
    if ajustar_d:
        d = redondear(d)
    if abs(d) < EPS:
        return u
    a, b = vs[i], vs[(i + 1) % m]
    ux, uy, _ = direccion(a, b)
    nx, ny = -uy, ux
    a2 = (a[0] + nx * d, a[1] + ny * d)
    b2 = (b[0] + nx * d, b[1] + ny * d)
    prev, sig = vs[(i - 1) % m], vs[(i + 2) % m]
    pa = _interseccion(prev, (a[0] - prev[0], a[1] - prev[1]), a2, (ux, uy))
    pb = _interseccion(sig, (b[0] - sig[0], b[1] - sig[1]), a2, (ux, uy))
    lado = n.lados[i]
    t0, t1 = lado.tramos[0], lado.tramos[-1]
    out = []                       # (vertice, lado que empieza en el)
    for x in range(m):
        v, l = vs[x], n.lados[x]
        if x == i:
            out += [(_rp(pa), l)] if pa is not None else [(v, Lado((Tramo(t0.condicion, t0.solucion),))),
                                                          (_rp(a2), l)]
        elif x == (i + 1) % m:
            out += [(_rp(pb), l)] if pb is not None else [(_rp(b2), Lado((Tramo(t1.condicion, t1.solucion),))),
                                                          (v, l)]
        else:
            out.append((v, l))
    return _con_nivel(u, k, replace(n, vertices=tuple(v for v, _ in out), lados=tuple(l for _, l in out)))


def _desplazar_inicio(lado: Lado, delta: float) -> Lado:
    """El inicio del lado retrocede delta metros: cortes y vanos quedan donde estaban."""
    cortes = tuple(_r(c + delta) for c in lado.cortes)
    if any(c <= EPS for c in cortes):
        raise ValueError("Un corte quedaría fuera del muro: quítalo o fija el otro extremo")
    t0 = _correr(lado.tramos[0], delta)
    if any(w.x < -EPS for _, _, w in vanos(t0)):
        raise ValueError("Una ventana o puerta quedaría fuera del muro")
    return Lado((t0,) + lado.tramos[1:], cortes)


def fijar_largo(u: Unidad, k: int, i: int, largo: float, ancla: str = "inicio") -> Unidad:
    """Largo del lado i; queda fijo su inicio (ancla='inicio') o su final ('fin').

    Se desplaza en paralelo el muro vecino del extremo que se mueve, asi todas
    las esquinas conservan su angulo."""
    n = u.niveles[k]
    m = len(n.vertices)
    d = _dib()
    largo = redondear(largo)
    if largo < d["lado_min"] - EPS:
        raise ValueError(f"Un muro mide como mínimo {d['lado_min']} m")
    ux, uy, actual = direccion(*extremos(n, i))
    delta = largo - actual
    if abs(delta) < 1e-9:
        return u
    lado = n.lados[i]
    if ancla == "inicio":
        if lado.cortes and lado.cortes[-1] > largo - d["tramo_min"] + EPS:
            raise ValueError("Un corte quedaría fuera del muro: quítalo o fija el otro extremo")
        j, signo = (i + 1) % m, 1.0
    elif ancla == "fin":
        u = _con_lado(u, k, i, _desplazar_inicio(lado, delta))
        j, signo = (i - 1) % m, -1.0
    else:
        raise ValueError("ancla debe ser 'inicio' o 'fin'")
    wx, wy, _ = direccion(*extremos(n, j))
    f = -ux * wy + uy * wx                 # u . normal exterior del vecino
    if abs(f) < 0.05:
        raise ValueError("El muro vecino sigue casi la misma dirección: cambia el largo moviendo un vértice")
    return mover_lado(u, k, j, signo * delta * f, ajustar_d=False)


# --------------------------------------------------------------------------- tramos
def partir_tramo(u: Unidad, k: int, i: int, s: float) -> Unidad:
    """Corte nuevo en el lado i a s metros de su inicio."""
    n = u.niveles[k]
    lado, lim = n.lados[i], limites(n, i)
    s = redondear(s)
    tmin = _dib()["tramo_min"]
    j = tramo_en(n, i, s)
    if s - lim[j] < tmin - EPS or lim[j + 1] - s < tmin - EPS:
        raise ValueError("El corte queda demasiado cerca de un extremo o de otro corte")
    a, b = _partir(lado.tramos[j], s - lim[j])
    tramos = lado.tramos[:j] + (a, b) + lado.tramos[j + 1:]
    return _con_lado(u, k, i, Lado(tramos, lado.cortes[:j] + (s,) + lado.cortes[j:]))


def unir_tramos(u: Unidad, k: int, i: int, j: int) -> Unidad:
    """Quita el corte j del lado i (une los tramos j y j + 1; manda la condicion del j)."""
    n = u.niveles[k]
    lado = n.lados[i]
    if not 0 <= j < len(lado.cortes):
        raise ValueError("No hay un corte que quitar")
    lim = limites(n, i)
    a, b = lado.tramos[j], _correr(lado.tramos[j + 1], lim[j + 1] - lim[j])
    if a.exterior:
        nuevo = Tramo(a.condicion, a.solucion, a.ventanas + b.ventanas, a.puertas + b.puertas)
    else:
        nuevo = Tramo(a.condicion, a.solucion)
    tramos = lado.tramos[:j] + (nuevo,) + lado.tramos[j + 2:]
    return _con_lado(u, k, i, Lado(tramos, lado.cortes[:j] + lado.cortes[j + 1:]))


def mover_corte(u: Unidad, k: int, i: int, j: int, s: float) -> Unidad:
    n = u.niveles[k]
    lado, lim = n.lados[i], limites(n, i)
    s = redondear(s)
    tmin = _dib()["tramo_min"]
    if not lim[j] + tmin - EPS <= s <= lim[j + 2] - tmin + EPS:
        raise ValueError("El corte debe quedar entre los cortes vecinos")
    a, b = lado.tramos[j], lado.tramos[j + 1]
    if any(w.x + w.ancho > s - lim[j] + EPS for _, _, w in vanos(a)):
        raise ValueError("Una ventana o puerta quedaría cortada")
    b2 = _correr(b, -(s - lim[j + 1]))
    if any(w.x < -EPS for _, _, w in vanos(b2)):
        raise ValueError("Una ventana o puerta quedaría cortada")
    tramos = lado.tramos[:j] + (a, b2) + lado.tramos[j + 2:]
    return _con_lado(u, k, i, Lado(tramos, lado.cortes[:j] + (s,) + lado.cortes[j + 1:]))


def _tramo_nuevo(u: Unidad, t: Tramo, condicion, solucion) -> Tramo:
    cond = condicion or t.condicion
    sol = t.solucion if solucion is None else solucion
    if sol not in (DEFECTO, GENERAL) and sol not in u.muros_personalizados:
        raise ValueError(f"No existe el muro personalizado '{sol}'")
    if cond != "exterior":
        return Tramo(cond, sol)
    return Tramo(cond, sol, t.ventanas, t.puertas)


def cambiar_tramo(u: Unidad, k: int, i: int, j: int, condicion: str | None = None,
                  solucion: str | None = None) -> Unidad:
    t = u.niveles[k].lados[i].tramos[j]
    return _con_tramo(u, k, i, j, _tramo_nuevo(u, t, condicion, solucion))


def cambiar_lado(u: Unidad, k: int, i: int, condicion: str | None = None,
                 solucion: str | None = None) -> Unidad:
    lado = u.niveles[k].lados[i]
    return _con_lado(u, k, i, Lado(tuple(_tramo_nuevo(u, t, condicion, solucion) for t in lado.tramos),
                                   lado.cortes))


# --------------------------------------------------------------------------- vanos
def _revisar_vano(u: Unidad, k: int, i: int, j: int, tipo: str, w, excluir=None) -> None:
    n = u.niveles[k]
    t = n.lados[i].tramos[j]
    if not t.exterior:
        raise ValueError("Solo los muros exteriores llevan ventanas y puertas")
    tol = _dib()["tolerancia_m"]
    x, z, a, al = rect(tipo, w)
    if x < -tol or x + a > largo_tramo(n, i, j) + tol:
        raise ValueError("El vano se sale del muro")
    if z < -tol or z + al > u.altura + tol:
        raise ValueError("El vano se sale del muro en altura")
    for tp, m, o in vanos(t):
        if (tp, m) != excluir and geometria.se_montan((x, z, a, al), rect(tp, o), tol):
            raise ValueError(f"Se monta con la {tp} {m + 1}")


def vano_desde_esquinas(tipo: str, p, q, largo: float, altura: float, vidrio: str = GENERAL):
    """Ventana o puerta entre dos esquinas (s, z) del alzado; la puerta parte del piso.
    vidrio: GENERAL (sigue al vidrio general) o un codigo del catalogo."""
    x0, x1 = sorted(min(max(c[0], 0.0), largo) for c in (p, q))
    z0, z1 = sorted(min(max(c[1], 0.0), altura) for c in (p, q))
    if tipo == "puerta":
        z0 = 0.0
    tmin = _dib()["tramo_min"]
    if x1 - x0 < tmin or z1 - z0 < tmin:
        raise ValueError("El vano es demasiado pequeño")
    if tipo == "puerta":
        return Puerta(_r(x0), _r(x1 - x0), _r(z1 - z0))
    return Ventana(_r(x0), _r(z0), _r(x1 - x0), _r(z1 - z0), vidrio=vidrio or GENERAL)


def agregar_vano(u: Unidad, k: int, i: int, j: int, tipo: str, w) -> Unidad:
    _revisar_vano(u, k, i, j, tipo, w)
    t = u.niveles[k].lados[i].tramos[j]
    campo = CAMPOS[tipo]
    return _con_tramo(u, k, i, j, replace(t, **{campo: getattr(t, campo) + (w,)}))


def mover_vano(u: Unidad, k: int, i: int, j: int, tipo: str, m: int, x: float, z: float | None = None) -> Unidad:
    """Nueva posicion de un vano: x desde el inicio del tramo; z = antepecho (solo ventanas)."""
    t = u.niveles[k].lados[i].tramos[j]
    campo = CAMPOS[tipo]
    lista = list(getattr(t, campo))
    w = replace(lista[m], x=_r(x))
    if tipo == "ventana" and z is not None:
        w = replace(w, antepecho=_r(z))
    _revisar_vano(u, k, i, j, tipo, w, excluir=(tipo, m))
    lista[m] = w
    return _con_tramo(u, k, i, j, replace(t, **{campo: tuple(lista)}))


def redimensionar_rect(r, bordes, ds: float, dz: float, paso: float | None = None,
                       minimo: float | None = None) -> tuple:
    """(x, z, ancho, alto) de un vano r al arrastrar sus bordes ds y dz metros.

    bordes: izq, der, inf, sup (en el sentido del modelo: izq = inicio del tramo). Cada
    borde que se mueve queda en un multiplo de paso (None: la precision del dibujo) y el
    vano no baja de minimo (None: tramo_min de config/unidad.yaml)."""
    x0, z0, a, al = r
    x1, z1 = x0 + a, z0 + al
    mn = _dib()["tramo_min"] if minimo is None else minimo
    if "izq" in bordes:
        x0 = min(redondear(x0 + ds, paso), x1 - mn)
    if "der" in bordes:
        x1 = max(redondear(x1 + ds, paso), x0 + mn)
    if "inf" in bordes:
        z0 = min(redondear(z0 + dz, paso), z1 - mn)
    if "sup" in bordes:
        z1 = max(redondear(z1 + dz, paso), z0 + mn)
    return (_r(x0), _r(z0), _r(x1 - x0), _r(z1 - z0))


def redimensionar_vano(u: Unidad, k: int, i: int, j: int, tipo: str, m: int, x: float | None = None,
                       z: float | None = None, ancho: float | None = None, alto: float | None = None) -> Unidad:
    """Posicion y medidas de un vano (None conserva cada una): x desde el inicio del tramo,
    z = antepecho (la puerta parte del piso y lo ignora). Conserva su vidrio, tipo y
    protecciones. No puede salirse del muro ni montarse con otro."""
    t = u.niveles[k].lados[i].tramos[j]
    campo = CAMPOS[tipo]
    lista = list(getattr(t, campo))
    if not 0 <= m < len(lista):
        raise ValueError("No existe ese vano")
    cambios = {c: _r(v) for c, v in (("x", x), ("ancho", ancho), ("alto", alto)) if v is not None}
    if tipo == "ventana" and z is not None:
        cambios["antepecho"] = _r(z)
    if any(cambios.get(c, 1.0) <= 0 for c in ("ancho", "alto")):
        raise ValueError("El ancho y el alto deben ser positivos")
    w = replace(lista[m], **cambios)
    _revisar_vano(u, k, i, j, tipo, w, excluir=(tipo, m))
    lista[m] = w
    return _con_tramo(u, k, i, j, replace(t, **{campo: tuple(lista)}))


def eliminar_vano(u: Unidad, k: int, i: int, j: int, tipo: str, m: int) -> Unidad:
    t = u.niveles[k].lados[i].tramos[j]
    campo = CAMPOS[tipo]
    lista = getattr(t, campo)
    if not 0 <= m < len(lista):
        raise ValueError("No existe ese vano")
    return _con_tramo(u, k, i, j, replace(t, **{campo: lista[:m] + lista[m + 1:]}))


# --------------------------------------------------------------------------- tabiques y niveles
def agregar_tabique(u: Unidad, k: int, a, b) -> Unidad:
    if distancia(a, b) < _dib()["tramo_min"]:
        raise ValueError("El tabique es demasiado corto")
    n = u.niveles[k]
    return _con_nivel(u, k, replace(n, tabiques=n.tabiques + (Tabique(_rp(a), _rp(b)),)))


def eliminar_tabique(u: Unidad, k: int, t: int) -> Unidad:
    n = u.niveles[k]
    if not 0 <= t < len(n.tabiques):
        raise ValueError("No existe ese tabique")
    return _con_nivel(u, k, replace(n, tabiques=n.tabiques[:t] + n.tabiques[t + 1:]))


def mover_tabique(u: Unidad, k: int, t: int, a=None, b=None) -> Unidad:
    """Extremos nuevos del tabique t del nivel k (None conserva cada uno)."""
    n = u.niveles[k]
    if not 0 <= t < len(n.tabiques):
        raise ValueError("No existe ese tabique")
    tb = n.tabiques[t]
    nuevo = Tabique(_rp(a) if a is not None else tb.a, _rp(b) if b is not None else tb.b)
    if distancia(nuevo.a, nuevo.b) < _dib()["tramo_min"]:
        raise ValueError("El tabique es demasiado corto")
    lista = list(n.tabiques)
    lista[t] = nuevo
    return _con_nivel(u, k, replace(n, tabiques=tuple(lista)))


def agregar_nivel(u: Unidad) -> Unidad:
    """Copia el perimetro y las condiciones del ultimo nivel, sin vanos, tabiques ni obstrucciones."""
    if not u.niveles:
        raise ValueError("Dibuja primero el nivel 1")
    if len(u.niveles) >= MAX_NIVELES:
        raise ValueError(f"Una unidad tiene como máximo {MAX_NIVELES} niveles")
    top = u.niveles[-1]
    lados = tuple(Lado(tuple(Tramo(t.condicion, t.solucion) for t in l.tramos), l.cortes) for l in top.lados)
    return replace(u, niveles=u.niveles + (Nivel(top.vertices, lados),))


def eliminar_nivel(u: Unidad, k: int) -> Unidad:
    if len(u.niveles) <= 1:
        raise ValueError("La unidad necesita al menos un nivel: usa «Eliminar todo»")
    return replace(u, niveles=u.niveles[:k] + u.niveles[k + 1:])


# --------------------------------------------------------------------------- obstrucciones
def obstaculo_nuevo(tipo: str, a, b) -> Obstaculo:
    """Obstruccion dibujada con dos clics: vertical, de a a b; horizontal, el rectangulo de
    esquinas opuestas a y b (lados paralelos a los ejes de la planta)."""
    if tipo == "horizontal":
        a, b = (min(a[0], b[0]), min(a[1], b[1])), (max(a[0], b[0]), max(a[1], b[1]))
    if distancia(a, b) < _dib()["tramo_min"]:
        raise ValueError("La obstrucción es demasiado pequeña")
    return Obstaculo(tipo, _rp(a), _rp(b))


def con_vertices(vertices) -> dict:
    """Cambios (a, b, vertices) de un balcon con esos vertices, para cambiar_obstaculo."""
    vs = tuple(_rp(p) for p in vertices)
    xs, ys = [p[0] for p in vs], [p[1] for p in vs]
    return {"a": (min(xs), min(ys)), "b": (max(xs), max(ys)), "vertices": vs}


def balcon_nuevo(puntos) -> Obstaculo:
    """Balcon de una polilinea dibujada (se cierra sola: el ultimo punto vuelve al primero)."""
    limpio = []
    for p in (_rp(p) for p in puntos):
        if not limpio or distancia(limpio[-1], p) > EPS:
            limpio.append(p)
    while len(limpio) > 1 and distancia(limpio[-1], limpio[0]) <= EPS:
        limpio.pop()
    if len(limpio) < 3:
        raise ValueError("El balcón necesita al menos 3 puntos")
    if abs(area_firmada(limpio)) < 1e-4:
        raise ValueError("El balcón no encierra un área")
    return balcon_desde(limpio)


def ajustar_obstaculo(n: Nivel | None, p, a, tipo: str, libre: bool, radio: float, paso: float) -> tuple:
    """Punto de una obstruccion que se dibuja. El primero (a None) se pega al muro mas
    cercano; el segundo, en la vertical, a un angulo multiplo de snap.angulo y un largo
    multiplo de snap.largo_m desde el primero; en la horizontal, a la grilla de paso."""
    if libre:
        return ajustar(p)
    if a is None:
        q = ajustar(p, paso)
        return proyectar_a_muro(n, q, radio) if n is not None else q
    if tipo == "vertical":
        return ajustar_desde(a, p)
    return ajustar(p, paso)


def ajustar_balcon(n: Nivel | None, p, previos, libre: bool, radio: float, paso: float) -> tuple:
    """Punto de un balcon que se dibuja: el primero a la grilla de paso y pegado al muro mas
    cercano; los siguientes a un angulo multiplo de snap.angulo y un largo multiplo de
    snap.largo_m desde el anterior (alineados con los demas puntos) y, si quedan cerca de un
    muro, pegados a el."""
    if libre:
        return ajustar(p)
    previos = list(previos)
    q = ajustar_desde(previos[-1], p, alinear=previos, radio=radio) if previos else ajustar(p, paso)
    return proyectar_a_muro(n, q, radio) if n is not None else q


def _revisar_obstaculo(u: Unidad, k: int, t: int) -> None:
    if not 0 <= k < len(u.niveles) or not 0 <= t < len(u.niveles[k].obstaculos):
        raise ValueError("No existe esa obstrucción")


def agregar_obstaculo(u: Unidad, k: int, o: Obstaculo) -> Unidad:
    n = u.niveles[k]
    return _con_nivel(u, k, replace(n, obstaculos=n.obstaculos + (o,)))


def eliminar_obstaculo(u: Unidad, k: int, t: int) -> Unidad:
    _revisar_obstaculo(u, k, t)
    n = u.niveles[k]
    return _con_nivel(u, k, replace(n, obstaculos=n.obstaculos[:t] + n.obstaculos[t + 1:]))


def cambiar_obstaculo(u: Unidad, k: int, t: int, **cambios) -> Unidad:
    """Cambia campos de la obstruccion t del nivel k (z, alto, p04, p04_elemento,
    p04_aislacion, p04_largo, a, b, vertices); None vuelve al valor automatico."""
    _revisar_obstaculo(u, k, t)
    n = u.niveles[k]
    lista = list(n.obstaculos)
    lista[t] = replace(lista[t], **{c: (_r(v) if isinstance(v, float) else v) for c, v in cambios.items()})
    return _con_nivel(u, k, replace(n, obstaculos=tuple(lista)))


def mover_obstaculo(u: Unidad, k: int, t: int, dx: float, dy: float) -> Unidad:
    _revisar_obstaculo(u, k, t)
    o = u.niveles[k].obstaculos[t]
    if o.vertices:
        return cambiar_obstaculo(u, k, t, **con_vertices([(p[0] + dx, p[1] + dy) for p in o.vertices]))
    return cambiar_obstaculo(u, k, t, a=_rp((o.a[0] + dx, o.a[1] + dy)), b=_rp((o.b[0] + dx, o.b[1] + dy)))


def pasar_obstaculo(u: Unidad, k: int, t: int, k2: int) -> Unidad:
    """Lleva la obstruccion t del nivel k al nivel k2 (queda al final de su lista)."""
    _revisar_obstaculo(u, k, t)
    if not 0 <= k2 < len(u.niveles):
        raise ValueError("No existe ese nivel")
    if k2 == k:
        return u
    o = u.niveles[k].obstaculos[t]
    return agregar_obstaculo(eliminar_obstaculo(u, k, t), k2, o)
