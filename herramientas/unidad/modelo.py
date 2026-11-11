# -*- coding: utf-8 -*-
"""
Modelo de una unidad de vivienda dibujada en planta (0 a 3 niveles).

Es la base comun de la caja de herramientas: no sabe nada de la ficha 01 ni de
la interfaz (CEV la traduce cev.py; otras herramientas leeran lo mismo). Se
guarda como JSON versionado (a_dict / desde_dict / guardar / cargar).

Convenciones
  - Planta en metros, por la cara INTERIOR de los muros. El eje +y apunta al
    azimut Unidad.azimut_y (grados desde el norte, sentido horario).
  - El perimetro de cada nivel se recorre en sentido HORARIO visto en planta:
    el interior queda a la derecha del recorrido y la normal exterior a la
    izquierda. horario() da vuelta un perimetro dibujado al reves.
  - Lado i = arista vertices[i] -> vertices[i+1]. Se puede partir en tramos
    (cortes: distancias desde su inicio); cada tramo es un muro con condicion
    (exterior / adiabatico) y solucion constructiva.
  - Vanos de un tramo exterior: ventanas y puertas. x: distancia desde el inicio
    del tramo, que es el extremo IZQUIERDO para un observador en el interior
    mirando hacia afuera. La ventana tiene antepecho (desde el piso); la puerta
    parte del piso. Los vanos completos (con marco) se restan del muro.
  - Protecciones solares de una ventana (Proteccion): ver protecciones.py.
  - Obstrucciones dibujadas (Obstaculo, en Nivel.obstaculos, como los tabiques):
    vertical: muro saliente o aleta (FAV2); horizontal: balcon, cornisa o alero
    (FAV1), SOBRE el nivel donde se dibuja; balcon: la losa de un balcon en el PISO
    del nivel (poligono, en L u otra forma), solo para su puente termico P04: no
    hace sombra. Las traduce obstrucciones.py.
  - Contexto (Unidad.contexto, FAR dibujado): volumenes del entorno, cada uno un
    poligono en planta (mismo sistema que la unidad) extruido desde el terreno
    natural hasta h. Unidad.npt es el nivel de piso terminado del nivel 1 sobre
    el terreno natural (terreno plano). Los traduce contexto_far.py con el motor
    herramientas/far.
  - Todos los niveles tienen la misma altura libre (Unidad.altura; el
    instructivo pide la altura media si varia).
  - Superficies horizontales (geometria.HorizontalGeo, una por destino y nivel):
    el piso del nivel 1 (condicion Unidad.piso) y el techo del ultimo nivel
    (Unidad.techo) son las principales; la parte de un nivel que vuela sobre el
    de abajo es un piso con condicion Unidad.piso_expuesto, y la parte de un
    nivel que no queda bajo el de arriba es un techo con Unidad.techo_expuesto.
  - tipo_vivienda: departamento, casa_aislada o casa_pareada (el texto de la
    ficha sale de config/cev.yaml).
  - Una unidad sin niveles es valida como dato (el editor la usa al empezar
    desde cero), pero geometria.errores la marca: no se puede calcular.

Soluciones (version 2): cada elemento usa la solucion GENERAL de su tipo (la que
viene por defecto) o una propia. Las generales estan en Unidad.generales y se
manejan con generales.py; cambiar una general no toca los elementos propios.
  - Muro (Tramo.solucion): GENERAL, DEFECTO (cumple norma) o la clave de un muro
    personalizado de Unidad.muros_personalizados (M1, M2...; el nombre de la
    ficha es datos["nombre"]).
  - Techo o piso: las principales en techo_personalizado y piso_personalizado,
    las demas en superficies_personalizadas["techo|k"] / ["piso|k"]. None (o sin
    clave) = general; NORMA = cumple norma; dict = personalizado.
    personalizado_horizontal() entrega la solucion efectiva (ya resuelta la
    general) y estado_horizontal() cual de las tres es.
  - Ventana: vidrio = GENERAL, el codigo de recinto/datos/vidrios.yaml, o
    vidrio_personalizado {nombre, u, fs} (manda si existe).
  - Puerta: tipo = GENERAL, la abreviatura de la ficha (config/cev.yaml
    puertas.tipos; "" = puertas.defecto) o personalizada {nombre, u, categoria}.
  - Unidad.generales: {muro, techo, piso_terreno, piso_ventilado: None (norma) o
    dict; vidrio: codigo o dict; puerta: tipo o dict}. Sin clave = la de
    config/cev.yaml (generales).
Los .json de la version 1 se migran al cargar: los muros "defecto", las
ventanas sin vidrio y las puertas sin tipo pasan a GENERAL (mismo resultado,
porque la general parte en la norma y en los valores de config/cev.yaml).
Los .json sin obstrucciones se leen igual (Nivel.obstaculos vacio), y los que no
traen npt ni contexto, con npt 0 y sin volumenes.
El ajuste del dibujo lo hace el editor (editor.py); geometria.validar revisa
la precision y, si config/unidad.yaml lo pide, el angulo de los lados.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 2
PISOS = ("adiabatico", "terreno", "ventilado")
PISOS_EXPUESTOS = ("ventilado", "adiabatico")
TECHOS = ("adiabatico", "exterior")
CONDICIONES = ("exterior", "adiabatico")
TIPOS_VIVIENDA = ("departamento", "casa_aislada", "casa_pareada")
CELOSIAS = ("horizontal", "vertical")
DESTINOS = ("techo", "piso")
OBSTACULOS = ("horizontal", "vertical", "balcon")
DEFECTO = "defecto"            # muro que cumple la norma de la zona
GENERAL = "general"            # sigue la solucion general de su tipo
NORMA = "norma"                # techo o piso propio que cumple la norma
MAX_NIVELES = 3


@dataclass(frozen=True)
class Proteccion:
    """Protecciones solares de una ventana (Manual CEV 6.7.3).

    FAV1 alero: L saliente desde el plomo del muro; D distancia del borde superior
    del vano al alero (None -> config/cev.yaml).
    FAV2 aletas izquierda y derecha (vistas desde el interior): P saliente; S
    separacion del borde del vano (aleta_izq_s / aleta_der_s; si faltan, aleta_s;
    si falta, config/cev.yaml).
    FAV3 celosia: E, T y el angulo de las lamas (celosia_beta). Lamas horizontales:
    el angulo va en la columna b de la ficha; verticales: en la columna a.
    """
    alero_l: float = 0.0
    alero_d: float | None = None
    aleta_izq_p: float = 0.0
    aleta_der_p: float = 0.0
    aleta_s: float | None = None
    celosia_e: float = 0.0
    celosia_t: float = 0.0
    celosia_beta: float = 0.0       # angulo de las lamas [grados]
    p04_aislacion: str | None = None
    aleta_izq_s: float | None = None
    aleta_der_s: float | None = None
    celosia_orientacion: str = "horizontal"

    def __post_init__(self):
        for n in ("alero_l", "aleta_izq_p", "aleta_der_p", "celosia_e", "celosia_t"):
            if getattr(self, n) < 0:
                raise ValueError(f"{n} no puede ser negativo")
        for n in ("alero_d", "aleta_s", "aleta_izq_s", "aleta_der_s"):
            v = getattr(self, n)
            if v is not None and v < 0:
                raise ValueError(f"{n} no puede ser negativo")
        if self.celosia_orientacion not in CELOSIAS:
            raise ValueError(f"celosia_orientacion debe ser una de {CELOSIAS}")
        lo = 0 if self.celosia_orientacion == "horizontal" else -90
        if not lo <= self.celosia_beta <= 90:
            raise ValueError(f"el ángulo de la celosía {self.celosia_orientacion} debe estar entre {lo} y 90")


@dataclass(frozen=True)
class Ventana:
    x: float                        # [m] desde el inicio del tramo
    antepecho: float                # [m] desde el piso
    ancho: float                    # [m] vano completo (con marco)
    alto: float                     # [m]
    vidrio: str = GENERAL           # GENERAL o codigo de recinto/datos/vidrios.yaml
    vidrio_personalizado: dict | None = None
    proteccion: Proteccion = field(default_factory=Proteccion)

    def __post_init__(self):
        if self.ancho <= 0 or self.alto <= 0:
            raise ValueError("la ventana debe tener ancho y alto positivos")


@dataclass(frozen=True)
class Puerta:
    x: float                        # [m] desde el inicio del tramo
    ancho: float                    # [m]
    alto: float                     # [m] desde el piso
    tipo: str = GENERAL             # GENERAL o abreviatura de la ficha; "" = puertas.defecto
    personalizada: dict | None = None   # {nombre, u, categoria} (recinto/config/personalizado.yaml)

    def __post_init__(self):
        if self.ancho <= 0 or self.alto <= 0:
            raise ValueError("la puerta debe tener ancho y alto positivos")


@dataclass(frozen=True)
class Tramo:
    condicion: str = "exterior"
    solucion: str = GENERAL
    ventanas: tuple = ()
    puertas: tuple = ()

    def __post_init__(self):
        if self.condicion not in CONDICIONES:
            raise ValueError(f"condicion debe ser una de {CONDICIONES}")
        if self.condicion != "exterior" and (self.ventanas or self.puertas):
            raise ValueError("un muro adiabatico no puede tener ventanas ni puertas")

    @property
    def exterior(self) -> bool:
        return self.condicion == "exterior"


@dataclass(frozen=True)
class Lado:
    tramos: tuple = (Tramo(),)
    cortes: tuple = ()              # [m] desde el inicio del lado, crecientes

    def __post_init__(self):
        if len(self.tramos) != len(self.cortes) + 1:
            raise ValueError("un lado con n cortes debe tener n + 1 tramos")
        if any(c <= 0 for c in self.cortes) or any(b <= a for a, b in zip(self.cortes, self.cortes[1:])):
            raise ValueError("los cortes de un lado deben ser positivos y crecientes")


@dataclass(frozen=True)
class Tabique:
    """Tabique interior: segmento de a a b (solo importa donde toca los muros)."""
    a: tuple
    b: tuple


@dataclass(frozen=True)
class Obstaculo:
    """Obstruccion dibujada en la planta de un nivel.

    vertical    muro saliente o aleta: segmento a-b que sale de un muro exterior hacia
                afuera. Ocupa de z a z + alto desde el piso del nivel (None: 0 y la
                altura libre). Es el FAV2 de las ventanas del mismo plano de fachada.
    horizontal  balcon, cornisa o alero SOBRE el nivel: rectangulo de lados paralelos a
                los ejes de la planta, de esquinas opuestas a y b. Su cara inferior esta
                a z del piso del nivel (None: la altura libre, sobre el muro) y alto es su
                espesor (None: el de config/editor.yaml, solo para el dibujo). Es el FAV1
                de las ventanas del nivel que quedan bajo ella.
    balcon      losa de balcon en el PISO del nivel: poligono `vertices` (en L u otra
                forma; a y b son las esquinas del rectangulo que lo envuelve). No hace
                sombra: solo cuenta su P04, el largo de sus bordes apoyados en los muros
                exteriores del nivel. alto: su espesor en el 3D (None: config/editor.yaml).
                Se arma con balcon_desde().
    P04: p04 (se cuenta), p04_elemento y p04_aislacion (textos de las listas de la
    ficha; None: config/cev.yaml) y p04_largo (None: automatico).
    """
    tipo: str
    a: tuple
    b: tuple
    z: float | None = None
    alto: float | None = None
    p04: bool = True
    p04_elemento: str | None = None
    p04_aislacion: str | None = None
    p04_largo: float | None = None
    vertices: tuple = ()            # solo el balcon: ((x, y), ...)

    def __post_init__(self):
        if self.tipo not in OBSTACULOS:
            raise ValueError(f"el tipo de obstrucción debe ser uno de {OBSTACULOS}")
        if self.tipo == "balcon":
            if len(self.vertices) < 3:
                raise ValueError("El balcón necesita al menos 3 vértices")
            if abs(area_firmada(self.vertices)) < 1e-4:
                raise ValueError("El balcón no encierra un área")
        else:
            dx, dy = abs(self.b[0] - self.a[0]), abs(self.b[1] - self.a[1])
            if self.tipo == "horizontal" and (dx < 1e-6 or dy < 1e-6):
                raise ValueError("La obstrucción horizontal debe ser un rectángulo con ancho y fondo")
            if self.tipo == "vertical" and math.hypot(dx, dy) < 1e-6:
                raise ValueError("La obstrucción vertical debe tener largo")
        if self.z is not None and self.z < 0:
            raise ValueError("la altura de la obstrucción no puede ser negativa")
        if self.alto is not None and self.alto <= 0:
            raise ValueError("el alto (o espesor) de la obstrucción debe ser positivo")
        if self.p04_largo is not None and self.p04_largo < 0:
            raise ValueError("el largo del P04 no puede ser negativo")


def balcon_desde(vertices, **kw) -> Obstaculo:
    """Obstaculo balcon de esos vertices (a y b: el rectangulo que lo envuelve)."""
    vs = tuple((float(x), float(y)) for x, y in vertices)
    if len(vs) < 3:
        raise ValueError("El balcón necesita al menos 3 vértices")
    xs, ys = [p[0] for p in vs], [p[1] for p in vs]
    return Obstaculo("balcon", (min(xs), min(ys)), (max(xs), max(ys)), vertices=vs, **kw)


@dataclass(frozen=True)
class Contexto:
    """Volumen del entorno (FAR dibujado): poligono en planta, en el mismo sistema que la
    unidad, extruido desde el terreno natural hasta h [m]. No hay volumenes flotantes."""
    nombre: str
    vertices: tuple                 # ((x, y), ...) en cualquier sentido
    h: float

    def __post_init__(self):
        if not str(self.nombre).strip():
            raise ValueError("el volumen de contexto necesita un nombre")
        if len(self.vertices) < 3:
            raise ValueError(f"{self.nombre}: el volumen de contexto necesita al menos 3 vértices")
        if abs(area_firmada(self.vertices)) < 1e-6:
            raise ValueError(f"{self.nombre}: el volumen de contexto no encierra un área")
        if self.h <= 0:
            raise ValueError(f"{self.nombre}: la altura del volumen de contexto debe ser positiva")


@dataclass(frozen=True)
class Nivel:
    vertices: tuple                 # ((x, y), ...) en sentido horario
    lados: tuple                    # un Lado por arista
    tabiques: tuple = ()
    obstaculos: tuple = ()          # Obstaculo dibujados en este nivel

    def __post_init__(self):
        if len(self.vertices) < 3:
            raise ValueError("un perimetro necesita al menos 3 vertices")
        if len(self.lados) != len(self.vertices):
            raise ValueError(f"el perimetro tiene {len(self.vertices)} vertices y {len(self.lados)} lados")


@dataclass(frozen=True)
class Unidad:
    comuna: str
    niveles: tuple
    altura: float                   # altura libre, piso a cielo [m]
    azimut_y: float = 0.0           # azimut del eje +y de la planta [grados]
    zona: str | None = None         # None -> unica opcion de la comuna
    dormitorios: int = 2
    piso: str = "adiabatico"        # piso del nivel 1
    techo: str = "adiabatico"       # techo del ultimo nivel
    piso_expuesto: str = "ventilado"   # parte de un nivel que vuela sobre el de abajo
    techo_expuesto: str = "exterior"   # parte de un nivel sin el de arriba encima
    muros_personalizados: dict = field(default_factory=dict)   # {clave: datos}
    techo_personalizado: dict | str | None = None    # techo del ultimo nivel (None general, NORMA, dict)
    piso_personalizado: dict | str | None = None     # piso del nivel 1
    tipo_vivienda: str = "departamento"
    superficies_personalizadas: dict = field(default_factory=dict)   # {"techo|k" o "piso|k": NORMA o datos}
    generales: dict = field(default_factory=dict)    # soluciones generales (generales.py)
    npt: float = 0.0                # nivel de piso terminado del nivel 1 sobre el terreno natural [m]
    contexto: tuple = ()            # Contexto: volumenes del entorno (FAR)
    version: int = VERSION

    def __post_init__(self):
        if len(self.niveles) > MAX_NIVELES:
            raise ValueError(f"una unidad tiene como maximo {MAX_NIVELES} niveles")
        for nombre, valor, validos in (("piso", self.piso, PISOS), ("techo", self.techo, TECHOS),
                                       ("piso_expuesto", self.piso_expuesto, PISOS_EXPUESTOS),
                                       ("techo_expuesto", self.techo_expuesto, TECHOS),
                                       ("tipo_vivienda", self.tipo_vivienda, TIPOS_VIVIENDA)):
            if valor not in validos:
                raise ValueError(f"{nombre} debe ser uno de {validos}")
        if self.altura <= 0:
            raise ValueError("la altura debe ser positiva")
        if self.dormitorios < 0:
            raise ValueError("dormitorios no puede ser negativo")
        faltan = sorted({t.solucion for n in self.niveles for l in n.lados for t in l.tramos
                         if t.exterior and t.solucion not in (DEFECTO, GENERAL)} - set(self.muros_personalizados))
        if faltan:
            raise ValueError(f"muros con soluciones que la unidad no define: {faltan}")
        nombres = [c.nombre for c in self.contexto]
        repetidos = sorted({x for x in nombres if nombres.count(x) > 1})
        if repetidos:
            raise ValueError(f"hay dos volúmenes de contexto llamados '{repetidos[0]}': cambia el nombre de uno")


# --------------------------------------------------------------------------- superficies horizontales
def clave_superficie(destino: str, nivel: int) -> str:
    return f"{destino}|{nivel}"


def es_principal(u: Unidad, destino: str, nivel: int) -> bool:
    """Piso del nivel 1 o techo del ultimo nivel."""
    return (destino == "piso" and nivel == 0) or (destino == "techo" and nivel == len(u.niveles) - 1)


def condicion_horizontal(u: Unidad, destino: str, nivel: int) -> str:
    if destino == "piso":
        return u.piso if nivel == 0 else u.piso_expuesto
    return u.techo if nivel == len(u.niveles) - 1 else u.techo_expuesto


def _crudo_horizontal(u: Unidad, destino: str, nivel: int):
    if es_principal(u, destino, nivel):
        return getattr(u, f"{destino}_personalizado")
    return u.superficies_personalizadas.get(clave_superficie(destino, nivel))


def estado_horizontal(u: Unidad, destino: str, nivel: int) -> str:
    """general | norma | personalizado: la solucion que eligio ese techo o piso."""
    d = _crudo_horizontal(u, destino, nivel)
    if isinstance(d, dict):
        return "personalizado"
    return "norma" if d == NORMA else "general"


def clave_general_horizontal(u: Unidad, destino: str, nivel: int) -> str:
    """Clave de Unidad.generales que usa ese techo o piso (techo, piso_terreno...)."""
    return "techo" if destino == "techo" else f"piso_{condicion_horizontal(u, destino, nivel)}"


def personalizado_horizontal(u: Unidad, destino: str, nivel: int) -> dict | None:
    """Solucion efectiva del techo o piso de ese nivel: los datos personalizados (los
    propios o los de la general) o None si cumple la norma."""
    d = _crudo_horizontal(u, destino, nivel)
    if isinstance(d, dict):
        return d
    if d == NORMA:
        return None
    g = u.generales.get(clave_general_horizontal(u, destino, nivel))
    return g if isinstance(g, dict) else None


# --------------------------------------------------------------------------- ayudas
def area_firmada(vertices) -> float:
    """Area con signo (negativa = sentido horario con y hacia arriba)."""
    s, n = 0.0, len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def horario(vertices) -> tuple:
    vs = tuple((float(x), float(y)) for x, y in vertices)
    return vs if area_firmada(vs) < 0 else tuple(reversed(vs))


def rectangulo(largo: float, ancho: float) -> tuple:
    """Horario desde la esquina frente-izquierda: lado 1 = frente (+y), lado 2 = derecha."""
    l, a = float(largo), float(ancho)
    return ((0.0, a), (l, a), (l, 0.0), (0.0, 0.0))


def nivel_simple(vertices, condicion: str = "exterior", solucion: str = GENERAL) -> Nivel:
    vs = horario(vertices)
    return Nivel(vs, tuple(Lado((Tramo(condicion, solucion),)) for _ in vs))


# --------------------------------------------------------------------------- JSON
def a_dict(u: Unidad) -> dict:
    return asdict(u)


def _punto(p) -> tuple:
    return (float(p[0]), float(p[1]))


def contexto_desde_dict(x: dict) -> Contexto:
    return Contexto(str(x["nombre"]), tuple(_punto(p) for p in x["vertices"]), float(x["h"]))


def desde_dict(d: dict) -> Unidad:
    version = int(d.get("version", VERSION))
    if version > VERSION:
        raise ValueError(f"la unidad es de una version mas nueva ({version}) que este programa ({VERSION})")
    viejo = version < 2                 # v1: "defecto" y vidrio / tipo vacios pasan a GENERAL

    def ventana(x):
        x = dict(x)
        x["proteccion"] = Proteccion(**(x.get("proteccion") or {}))
        if viejo and not x.get("vidrio"):
            x["vidrio"] = GENERAL
        return Ventana(**x)

    def puerta(x):
        x = dict(x)
        if viejo and not x.get("tipo"):
            x["tipo"] = GENERAL
        return Puerta(**x)

    def tramo(x):
        sol = x.get("solucion", GENERAL)
        if viejo and sol == DEFECTO:
            sol = GENERAL
        return Tramo(x.get("condicion", "exterior"), sol,
                     tuple(ventana(v) for v in x.get("ventanas") or ()),
                     tuple(puerta(p) for p in x.get("puertas") or ()))

    def lado(x):
        return Lado(tuple(tramo(t) for t in x["tramos"]), tuple(float(c) for c in x.get("cortes") or ()))

    def obstaculo(x):
        x = dict(x)
        x["a"], x["b"] = _punto(x["a"]), _punto(x["b"])
        x["vertices"] = tuple(_punto(p) for p in x.get("vertices") or ())
        return Obstaculo(**x)

    def nivel(x):
        return Nivel(tuple(_punto(p) for p in x["vertices"]), tuple(lado(l) for l in x["lados"]),
                     tuple(Tabique(_punto(t["a"]), _punto(t["b"])) for t in x.get("tabiques") or ()),
                     tuple(obstaculo(o) for o in x.get("obstaculos") or ()))

    claves = ("comuna", "altura", "azimut_y", "zona", "dormitorios", "piso", "techo", "piso_expuesto",
              "techo_expuesto", "muros_personalizados", "techo_personalizado", "piso_personalizado",
              "tipo_vivienda", "superficies_personalizadas", "generales")
    extra = {}
    if d.get("npt") is not None:
        extra["npt"] = float(d["npt"])
    return Unidad(niveles=tuple(nivel(n) for n in d.get("niveles") or ()),
                  contexto=tuple(contexto_desde_dict(c) for c in d.get("contexto") or ()),
                  **extra, **{k: d[k] for k in claves if k in d})


def guardar(u: Unidad, ruta) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a_dict(u), ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def cargar(ruta) -> Unidad:
    return desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
