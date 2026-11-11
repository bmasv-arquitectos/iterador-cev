# -*- coding: utf-8 -*-
"""
Edicion de los volumenes de contexto de una unidad (FAR dibujado), sin interfaz.

Un volumen (modelo.Contexto) es un poligono en planta, en el mismo sistema que la
unidad, extruido desde el terreno natural hasta h. Lo usa contexto_far.py para las
obstrucciones remotas de la ficha. Todas las funciones devuelven una Unidad nueva
(la validacion la hacen modelo.Contexto y modelo.Unidad: area, altura positiva y
nombres sin repetir, mas _poner: sin cruces y sin darse vuelta) o lanzan
ValueError con un mensaje para el usuario.

Dibujo ortogonal (criterio de Lucas, 2026-11-06: sin diagonales en planta, para
evitar geometrias complejas; el motor FAR acepta cualquier poligono):
  - rectangulo(a, b): dos esquinas opuestas.
  - polilinea: cada punto se ajusta con ajustar_ortogonal(anterior, p) y se cierra
    con cerrar_ortogonal (agrega la esquina que falta si el ultimo punto no esta
    alineado con el primero).
  - mover_lado: un lado en paralelo (sus vecinos se estiran); mover_esquina: un
    vertice y los dos lados que llegan a el. Asi nunca aparece una diagonal.

Cotas (referencia desde la unidad): las caras EXTERIORES de la unidad son sus
lados paralelos a los ejes corridos `espesor` hacia afuera (el editor usa
modelo3d.espesor_muro; 0 = cara interior). cotas() da, por eje, la distancia a la
cara perpendicular mas cercana (usando su prolongacion si hace falta):
  - separacion: el punto o el volumen queda del lado de afuera de la cara; es la
    distancia libre entre la cara y el borde del volumen que la mira;
  - desfase: si en ese eje el volumen no queda libre de ninguna cara (por ejemplo
    el desplazamiento este-oeste de un edificio que esta al norte), es cuanto
    sobresale su borde exterior del plano de la cara del mismo lado (negativo:
    queda por dentro).
separar() mueve el volumen hasta que esa cota valga lo pedido, y ajustar_a_cotas()
lleva el cursor a cotas redondas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .geometria import normalizar_azimut
from .modelo import Contexto, Unidad, area_firmada

PREFIJO = "Volumen"
TOL = 1e-9
TOL_EJE = 1e-6
EJES = ("x", "y")


def nombre_libre(u: Unidad, prefijo: str = PREFIJO) -> str:
    """Primer "Volumen k" que no usa la unidad."""
    usados = {c.nombre for c in u.contexto}
    k = 1
    while f"{prefijo} {k}" in usados:
        k += 1
    return f"{prefijo} {k}"


def _revisar(u: Unidad, i: int) -> None:
    if not 0 <= i < len(u.contexto):
        raise ValueError("No existe ese volumen de contexto")


def _con(u: Unidad, i: int, c: Contexto) -> Unidad:
    lst = list(u.contexto)
    lst[i] = c
    return replace(u, contexto=tuple(lst))


# --------------------------------------------------------------------------- poligonos ortogonales
def valido(vs) -> bool:
    """El poligono encierra un area sin cruzarse."""
    if len(vs) < 3:
        return False
    from shapely.geometry import Polygon

    p = Polygon(vs)
    return p.is_valid and p.area > 1e-6


def es_ortogonal(vs, tol: float = TOL_EJE) -> bool:
    """Todos los lados son paralelos a los ejes de la planta."""
    n = len(vs)
    return all(abs(vs[i][0] - vs[(i + 1) % n][0]) <= tol or abs(vs[i][1] - vs[(i + 1) % n][1]) <= tol
               for i in range(n))


def ajustar_ortogonal(desde, p) -> tuple:
    """p alineado con desde en horizontal o en vertical (el eje con mas recorrido)."""
    if abs(p[0] - desde[0]) >= abs(p[1] - desde[1]):
        return (float(p[0]), float(desde[1]))
    return (float(desde[0]), float(p[1]))


def limpiar(vs, tol: float = TOL) -> tuple:
    """Sin puntos repetidos ni intermedios en un mismo tramo recto (los retrocesos se dejan:
    el poligono queda invalido y se avisa)."""
    vs = [(float(x), float(y)) for x, y in vs]
    cambio = True
    while cambio and len(vs) >= 3:
        cambio = False
        n = len(vs)
        for i in range(n):
            a, b, c = vs[i - 1], vs[i], vs[(i + 1) % n]
            ux, uy = b[0] - a[0], b[1] - a[1]
            vx, vy = c[0] - b[0], c[1] - b[1]
            if math.hypot(ux, uy) <= tol or (abs(ux * vy - uy * vx) <= tol and ux * vx + uy * vy > 0):
                del vs[i]
                cambio = True
                break
    return tuple(vs)


def cerrar_ortogonal(puntos) -> tuple:
    """Vertices de la polilinea cerrada; si el ultimo punto no esta alineado con el primero,
    agrega la esquina que deja un poligono valido."""
    pts = [(float(x), float(y)) for x, y in puntos]
    if len(pts) < 3:
        raise ValueError("Se necesitan al menos 3 puntos para cerrar el volumen")
    a, b = pts[0], pts[-1]
    if abs(a[0] - b[0]) <= TOL_EJE or abs(a[1] - b[1]) <= TOL_EJE:
        opciones = [pts]
    else:
        opciones = [pts + [(b[0], a[1])], pts + [(a[0], b[1])]]
    for vs in opciones:
        vs = limpiar(vs)
        if len(vs) >= 4 and es_ortogonal(vs) and valido(vs):
            return vs
    raise ValueError("El contorno se cruza consigo mismo: no se puede cerrar")


def _poner(u: Unidad, i: int, vs) -> Unidad:
    """Nuevos vertices del volumen i, si no se cruza ni se da vuelta."""
    vs = tuple((float(x), float(y)) for x, y in vs)
    antes = area_firmada(u.contexto[i].vertices)
    if not valido(vs) or area_firmada(vs) * antes <= 0:
        raise ValueError("El volumen quedaría cruzado o sin área")
    return _con(u, i, replace(u.contexto[i], vertices=vs))


# --------------------------------------------------------------------------- crear y editar
def agregar(u: Unidad, vertices, h: float, nombre: str | None = None) -> Unidad:
    vs = tuple((float(x), float(y)) for x, y in vertices)
    if not valido(vs):
        raise ValueError("El volumen de contexto se cruza consigo mismo o no tiene área")
    c = Contexto(nombre or nombre_libre(u), vs, float(h))
    return replace(u, contexto=u.contexto + (c,))


def rectangulo(u: Unidad, a, b, h: float, nombre: str | None = None) -> Unidad:
    """Volumen rectangular de esquinas opuestas a y b (lados paralelos a los ejes de la planta)."""
    x0, x1 = sorted((float(a[0]), float(b[0])))
    y0, y1 = sorted((float(a[1]), float(b[1])))
    if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
        raise ValueError("El volumen de contexto debe tener ancho y fondo")
    return agregar(u, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), h, nombre)


def polilinea(u: Unidad, puntos, h: float, nombre: str | None = None) -> Unidad:
    """Volumen ortogonal desde los puntos de una polilinea (se cierra con cerrar_ortogonal)."""
    return agregar(u, cerrar_ortogonal(puntos), h, nombre)


def editar(u: Unidad, i: int, **cambios) -> Unidad:
    """Cambia nombre, h o vertices del volumen i."""
    _revisar(u, i)
    if "h" in cambios:
        cambios["h"] = float(cambios["h"])
    if "nombre" in cambios:
        cambios["nombre"] = str(cambios["nombre"]).strip()
    return _con(u, i, replace(u.contexto[i], **cambios))


def mover(u: Unidad, i: int, dx: float, dy: float) -> Unidad:
    _revisar(u, i)
    c = u.contexto[i]
    return _con(u, i, replace(c, vertices=tuple((x + dx, y + dy) for x, y in c.vertices)))


def mover_vertice(u: Unidad, i: int, j: int, p) -> Unidad:
    """Mueve solo un vertice (puede dejar diagonales; el editor ortogonal usa mover_esquina)."""
    _revisar(u, i)
    c = u.contexto[i]
    if not 0 <= j < len(c.vertices):
        raise ValueError("No existe ese vértice del volumen")
    vs = list(c.vertices)
    vs[j] = (float(p[0]), float(p[1]))
    return _con(u, i, replace(c, vertices=tuple(vs)))


def normal_lado(vs, j: int) -> tuple:
    """Normal exterior unitaria del lado j (vs[j] -> vs[j + 1]) de un poligono en cualquier sentido."""
    a, b = vs[j], vs[(j + 1) % len(vs)]
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo = math.hypot(dx, dy)
    if largo <= TOL:
        raise ValueError("El lado no tiene largo")
    ux, uy = dx / largo, dy / largo
    return (uy, -ux) if area_firmada(vs) > 0 else (-uy, ux)


def mover_lado(u: Unidad, i: int, j: int, d: float) -> Unidad:
    """Corre el lado j del volumen i d metros hacia afuera (negativo: hacia adentro); los lados
    vecinos se estiran."""
    _revisar(u, i)
    vs = list(u.contexto[i].vertices)
    if not 0 <= j < len(vs):
        raise ValueError("No existe ese lado del volumen")
    nx, ny = normal_lado(vs, j)
    for k in (j, (j + 1) % len(vs)):
        vs[k] = (vs[k][0] + nx * d, vs[k][1] + ny * d)
    return _poner(u, i, vs)


def mover_esquina(u: Unidad, i: int, j: int, p) -> Unidad:
    """Lleva el vertice j a p y corre los dos lados que llegan a el (siguen ortogonales)."""
    _revisar(u, i)
    vs = list(u.contexto[i].vertices)
    n = len(vs)
    if not 0 <= j < n:
        raise ValueError("No existe ese vértice del volumen")
    x, y = float(p[0]), float(p[1])
    b = vs[j]
    for k in ((j - 1) % n, (j + 1) % n):
        a = vs[k]
        if abs(a[1] - b[1]) <= TOL_EJE:          # lado horizontal: el vecino toma la nueva y
            vs[k] = (a[0], y)
        elif abs(a[0] - b[0]) <= TOL_EJE:        # lado vertical: el vecino toma la nueva x
            vs[k] = (x, a[1])
    vs[j] = (x, y)
    return _poner(u, i, vs)


def eliminar(u: Unidad, i: int) -> Unidad:
    _revisar(u, i)
    return replace(u, contexto=u.contexto[:i] + u.contexto[i + 1:])


# --------------------------------------------------------------------------- elegir
def _dentro(p, vs) -> bool:
    x, y = p
    dentro = False
    n = len(vs)
    for k in range(n):
        x1, y1 = vs[k]
        x2, y2 = vs[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def distancia_segmento(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def tocar_vertice(u: Unidad, i: int, p, radio: float) -> int | None:
    """Vertice del volumen i a menos de radio de p (el mas cercano)."""
    _revisar(u, i)
    d = [(math.hypot(p[0] - x, p[1] - y), j) for j, (x, y) in enumerate(u.contexto[i].vertices)]
    dist, j = min(d)
    return j if dist <= radio else None


def tocar_lado(u: Unidad, i: int, p, radio: float) -> int | None:
    """Lado del volumen i a menos de radio de p (el mas cercano)."""
    _revisar(u, i)
    vs = u.contexto[i].vertices
    d = [(distancia_segmento(p, vs[j], vs[(j + 1) % len(vs)]), j) for j in range(len(vs))]
    dist, j = min(d)
    return j if dist <= radio else None


def tocar(u: Unidad, p, radio: float = 0.0) -> int | None:
    """Indice del volumen que contiene p o cuyo borde queda a menos de radio (manda el
    ultimo dibujado), o None."""
    for i in range(len(u.contexto) - 1, -1, -1):
        vs = u.contexto[i].vertices
        if _dentro(p, vs) or any(distancia_segmento(p, vs[k], vs[(k + 1) % len(vs)]) <= radio
                                  for k in range(len(vs))):
            return i
    return None


# --------------------------------------------------------------------------- cotas desde la unidad
@dataclass(frozen=True)
class Cara:
    """Cara de la unidad paralela a un eje: la recta eje = pos (x = pos o y = pos)."""
    id: str              # "N1-L2" (nivel y lado de la unidad)
    eje: str             # "x": cara vertical en planta (mide en x); "y": horizontal (mide en y)
    pos: float           # coordenada de la cara (exterior si espesor > 0)
    signo: int           # +1 si su normal exterior apunta hacia +eje
    desde: float         # extension de la cara en el otro eje
    hasta: float
    azimut: float        # de su normal exterior [grados]


@dataclass(frozen=True)
class Cota:
    eje: str
    tipo: str            # separacion | desfase
    distancia: float     # [m]
    cara: Cara
    desde: tuple         # (x, y) sobre la cara (o su prolongacion)
    hasta: tuple         # (x, y) en el punto o en el borde del volumen


def caras(u: Unidad, espesor: float = 0.0) -> list:
    """Caras de la unidad paralelas a los ejes (todos los niveles), corridas espesor hacia afuera."""
    out = []
    for k, n in enumerate(u.niveles):
        vs = n.vertices
        m = len(vs)
        for i in range(m):
            a, b = vs[i], vs[(i + 1) % m]
            dx, dy = b[0] - a[0], b[1] - a[1]
            largo = math.hypot(dx, dy)
            if largo <= TOL:
                continue
            ux, uy = dx / largo, dy / largo
            nx, ny = -uy, ux                      # perimetro horario: normal exterior a la izquierda
            az = normalizar_azimut(u.azimut_y + math.degrees(math.atan2(nx, ny)))
            cid = f"N{k + 1}-L{i + 1}"
            if abs(uy) <= TOL_EJE:
                s = 1 if ny > 0 else -1
                out.append(Cara(cid, "y", a[1] + s * espesor, s, min(a[0], b[0]), max(a[0], b[0]), az))
            elif abs(ux) <= TOL_EJE:
                s = 1 if nx > 0 else -1
                out.append(Cara(cid, "x", a[0] + s * espesor, s, min(a[1], b[1]), max(a[1], b[1]), az))
    return out


def _cota(cs, eje: str, lo: float, hi: float, centro: float) -> Cota | None:
    """Cota en un eje de lo que ocupa [lo, hi] en ese eje (centro: su centro en el otro eje)."""
    opciones = [c for c in cs if c.eje == eje]
    if not opciones:
        return None

    def lejos(c):
        return not (c.desde - 1e-9 <= centro <= c.hasta + 1e-9)

    libres = [(c.signo * ((lo if c.signo > 0 else hi) - c.pos), c) for c in opciones]
    libres = [(d, c) for d, c in libres if d >= -1e-9]
    if libres:
        d, c = min(libres, key=lambda t: (round(t[0], 9), lejos(t[1])))
        tipo, borde = "separacion", (lo if c.signo > 0 else hi)
    else:
        des = [(c.signo * ((hi if c.signo > 0 else lo) - c.pos), c) for c in opciones]
        d, c = min(des, key=lambda t: (round(abs(t[0]), 9), lejos(t[1])))
        tipo, borde = "desfase", (hi if c.signo > 0 else lo)
    if eje == "y":
        return Cota(eje, tipo, d, c, (centro, c.pos), (centro, borde))
    return Cota(eje, tipo, d, c, (c.pos, centro), (borde, centro))


def cotas(u: Unidad, vertices, espesor: float = 0.0) -> dict:
    """{"x": Cota o None, "y": Cota o None} de un volumen (sus vertices) o de un punto ([p])."""
    cs = caras(u, espesor)
    xs = [float(p[0]) for p in vertices]
    ys = [float(p[1]) for p in vertices]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return {"x": _cota(cs, "x", x0, x1, (y0 + y1) / 2), "y": _cota(cs, "y", y0, y1, (x0 + x1) / 2)}


def cotas_punto(u: Unidad, p, espesor: float = 0.0) -> dict:
    return cotas(u, [p], espesor)


def ajustar_a_cotas(u: Unidad, p, paso: float, espesor: float = 0.0) -> tuple:
    """p corrido para que sus dos cotas a la unidad sean multiplos de paso."""
    x, y = float(p[0]), float(p[1])
    if not paso:
        return (x, y)
    for eje, c in cotas_punto(u, (x, y), espesor).items():
        if c is None:
            continue
        delta = c.cara.signo * (round(c.distancia / paso) * paso - c.distancia)
        if eje == "x":
            x += delta
        else:
            y += delta
    return (x, y)


def separar(u: Unidad, i: int, eje: str, distancia: float, espesor: float = 0.0) -> Unidad:
    """Mueve el volumen i en ese eje hasta que su cota a la unidad valga distancia."""
    _revisar(u, i)
    if eje not in EJES:
        raise ValueError(f"eje debe ser uno de {EJES}")
    c = cotas(u, u.contexto[i].vertices, espesor)[eje]
    if c is None:
        raise ValueError("La unidad no tiene caras en ese eje para medir")
    delta = c.cara.signo * (float(distancia) - c.distancia)
    return mover(u, i, delta, 0.0) if eje == "x" else mover(u, i, 0.0, delta)
