# -*- coding: utf-8 -*-
"""
FAR dibujado, capa C: Unidad (modelo.py) -> motor herramientas/far -> obstrucciones
remotas de la ficha 01 (fichas_cev.modelo.Obstruccion: 'CEV-CEVE' E127:H134,
J127:M134... division, A, B, D por orientacion) y el azimut de cada bloque
('CEV-CEVE' G125, L125, Q125, V125, G137, L137, Q137, V137).

Parametros: config/cev.yaml (far:).

Que orientaciones llevan FAR (far.orientaciones):
  unidad      (por defecto) cada orientacion en que la unidad tiene muros, exteriores o
              adiabaticos. Criterio de Lucas (2026-11-07): el motor gira la vivienda en
              los casos de referencia (3-10) y cada ventana girada lee el FAR de la
              orientacion a la que queda mirando; el entorno sigue ahi, asi que sin el FAR
              de esas orientaciones la referencia girada no tendria sombra. En la
              propuesta (casos 1 y 2) solo leen FAR las orientaciones con ventanas, asi
              que los bloques de las fachadas adiabaticas no la cambian.
  exteriores  solo las orientaciones con muros exteriores (lectura literal del Manual).

Un punto de referencia por orientacion de la ficha (N, NE, E, SE, S, SO, O, NO:
sectores de 45 grados centrados en cada una; coinciden con los rangos de 22,5
grados de la lista de azimut de la ficha), con el mismo criterio sea la fachada
exterior o adiabatica:
  - los muros de esa orientacion, si la altura libre supera far.muro_min;
  - en planta, el promedio de los centros de esos muros ponderado por su area
    bruta (Ecuacion 5 del Manual); queda sobre la cara interior;
  - z = npt + centro del rectangulo que envuelve esos muros en alzado; los
    niveles se apilan cada altura libre + far.losa_m;
  - semicirculo (far.semicirculo): real (por defecto, criterio de Lucas 2026-11-07)
    = paralelo a la fachada, centrado en la normal de esos muros (promedio ponderado
    por area); la orientacion solo clasifica el bloque de la ficha. nominal = centrado
    en el azimut nominal de la orientacion (N 0, NE 45...).
El motor trabaja en el sistema de la planta: el eje +y hace de "norte" y los
azimuts se pasan restando Unidad.azimut_y. Los volumenes de Unidad.contexto
entran tal cual (poligono en planta y h desde el terreno natural). La propia
unidad no es un volumen: su autosombra no cuenta en el FAR.

Azimut de cada bloque (azimuts): el texto de la lista de azimut de la ficha (los rangos
de 22,5 grados, recinto.a_ficha.azimut_texto); cada orientacion admite dos. Se usa la
normal de los muros de esa orientacion; si no tiene muros, la direccion de la unidad que
cae en ese sector (azimut_y + k 45 grados). El motor oficial lo exige si el bloque tiene
obstrucciones.

Sin volumenes de contexto (o con far.activo false) no hay obstrucciones y la
ficha queda como antes. tabla() resume el resultado para la interfaz (las mismas
filas que van a la ficha, con el nombre del volumen); punto() calcula una sola
orientacion (para dibujarla en la vista Contexto).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from herramientas.far import Parametros, Punto, ResultadoPunto, Volumen, calcular_punto
from herramientas.fichas_cev.modelo import Obstruccion

from .geometria import Geometria, normalizar_azimut
from .modelo import Unidad

ORIENTACIONES = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
NOMINAL = {o: normalizar_azimut(45.0 * i) for i, o in enumerate(ORIENTACIONES)}
SEMICIRCULOS = ("real", "nominal")
CRITERIOS = ("unidad", "exteriores")
DEFECTO = {
    "activo": True,
    "orientaciones": "unidad",
    "muro_min": 1.6,
    "semicirculo": "real",
    "losa_m": 0.2,
    "decimales": 1,
    "division": "División {k}",
    "motor": {},
}


def config(cfg: dict | None = None) -> dict:
    """Seccion far: de config/cev.yaml (o el cev.yaml completo) con los valores por defecto."""
    if cfg is None:
        from .cev import _cfg
        cfg = _cfg()
    c = cfg.get("far", cfg) if isinstance(cfg, dict) else {}
    out = {**DEFECTO, **{k: v for k, v in (c or {}).items() if k in DEFECTO}}
    if out["semicirculo"] not in SEMICIRCULOS:
        raise ValueError(f"far.semicirculo debe ser uno de {SEMICIRCULOS}: {out['semicirculo']!r}")
    if out["orientaciones"] not in CRITERIOS:
        raise ValueError(f"far.orientaciones debe ser uno de {CRITERIOS}: {out['orientaciones']!r}")
    return out


def parametros(c: dict) -> Parametros:
    p = Parametros(**(c.get("motor") or {}))
    p.validar()
    return p


def orientacion(az: float) -> str:
    """Orientacion de la ficha de un azimut: N para -22,5 <= az < 22,5, NE para 22,5 <= az < 67,5..."""
    a = normalizar_azimut(az)
    return ORIENTACIONES[int(math.floor((a + 22.5) / 45.0 + 1e-9)) % 8]


@dataclass(frozen=True)
class PuntoFar:
    orientacion: str
    punto: Punto                    # en el sistema de la planta (azimut relativo a +y)
    muros: tuple                    # ids de los panos que lo definen
    area: float                     # [m2] area bruta de esos muros
    exterior: bool = True           # algun muro de la orientacion es exterior
    normal: float = 0.0             # azimut absoluto de la normal de esos muros (ponderada por area)


@dataclass
class ResultadoFar:
    puntos: list = field(default_factory=list)          # PuntoFar
    resultados: dict = field(default_factory=dict)      # {orientacion: far.ResultadoPunto}
    obstrucciones: list = field(default_factory=list)   # fichas_cev.modelo.Obstruccion
    avisos: list = field(default_factory=list)


def puntos(u: Unidad, g: Geometria, cfg: dict | None = None) -> list:
    """Un PuntoFar por orientacion con muros (todos o solo exteriores, segun far.orientaciones),
    en el orden de ORIENTACIONES."""
    c = config(cfg)
    h = float(g.altura)
    if h <= float(c["muro_min"]):
        return []
    todos = c["orientaciones"] == "unidad"
    paso = h + float(c["losa_m"])
    grupos: dict = {}
    for x in g.panos:
        if (x.exterior or todos) and x.largo > 0:
            grupos.setdefault(orientacion(x.azimut), []).append(x)
    out = []
    for o in ORIENTACIONES:
        ps = grupos.get(o)
        if not ps:
            continue
        area = sum(p.area_bruta for p in ps)
        cx = sum((p.a[0] + p.b[0]) / 2 * p.area_bruta for p in ps) / area
        cy = sum((p.a[1] + p.b[1]) / 2 * p.area_bruta for p in ps) / area
        z0 = min(p.nivel for p in ps) * paso
        z1 = max(p.nivel for p in ps) * paso + h
        sx = sum(math.sin(math.radians(p.azimut)) * p.area_bruta for p in ps)
        sy = sum(math.cos(math.radians(p.azimut)) * p.area_bruta for p in ps)
        normal = normalizar_azimut(math.degrees(math.atan2(sx, sy)))
        az = normal if c["semicirculo"] == "real" else NOMINAL[o]
        rel = normalizar_azimut(az - u.azimut_y)
        out.append(PuntoFar(o, Punto(o, cx, cy, float(u.npt) + (z0 + z1) / 2, rel),
                            tuple(p.id for p in ps), area, any(p.exterior for p in ps), normal))
    return out


def azimuts(u: Unidad, g: Geometria | None, cfg: dict | None = None) -> dict:
    """{orientacion: texto de la lista de azimut de la ficha} de los 8 bloques: la normal de los
    muros de esa orientacion (todos, exteriores o no) o, si no tiene, la direccion de la unidad
    (azimut_y + k 45 grados) que cae en ese sector."""
    from herramientas.recinto.a_ficha import azimut_texto

    out = {}
    for k in range(8):
        a = normalizar_azimut(u.azimut_y + 45.0 * k)
        out.setdefault(orientacion(a), a)
    if g is not None:
        c = {**config(cfg), "orientaciones": "unidad", "semicirculo": "real"}
        for pf in puntos(u, g, c):
            out[pf.orientacion] = pf.normal
    return {o: azimut_texto(out[o]) for o in ORIENTACIONES if o in out}


def volumenes(u: Unidad) -> tuple:
    return tuple(Volumen(v.nombre, tuple(v.vertices), float(v.h)) for v in u.contexto)


def _redondeadas(r: ResultadoPunto, dec: int):
    """(obstruccion del motor, a, b, d) redondeadas."""
    for o in r.obstrucciones:
        yield o, round(o.a, dec), round(o.b, dec), round(o.d, dec)


def a_ficha(orientacion_: str, r: ResultadoPunto, c: dict) -> tuple:
    """([Obstruccion] de la ficha, avisos) de un punto, en el orden del motor (por division)."""
    obs, avisos = [], []
    for o, a, b, d in _redondeadas(r, int(c["decimales"])):
        if a <= 0 or b <= 0 or d <= 0:
            avisos.append(f"FAR {orientacion_}: {o.volumen} en la división {o.division} queda en cero al "
                          f"redondear (A {a}, B {b}, D {d}); no se declara")
            continue
        obs.append(Obstruccion(orientacion_, len(obs), str(c["division"]).format(k=o.division), a, b, d))
    return obs, avisos


def calcular(u: Unidad, g: Geometria, cfg: dict | None = None) -> ResultadoFar:
    """Obstrucciones remotas de la unidad para la ficha (vacio sin contexto)."""
    c = config(cfg)
    out = ResultadoFar()
    if not c["activo"] or not u.contexto:
        return out
    vols = volumenes(u)
    par = parametros(c)
    out.puntos = puntos(u, g, c)
    for pf in out.puntos:
        r = calcular_punto(pf.punto, vols, par)
        out.resultados[pf.orientacion] = r
        obs, avisos = a_ficha(pf.orientacion, r, c)
        out.obstrucciones += obs
        out.avisos += avisos
        out.avisos += [f"FAR {pf.orientacion}: {x}" for x in r.avisos]
        out.avisos += [f"FAR {pf.orientacion}: {m.obstruccion.volumen} en la división {m.obstruccion.division} "
                       f"se omite ({m.motivo})" for m in r.omitidas if m.motivo != "angosto"]
    return out


def punto(u: Unidad, g: Geometria, orientacion_: str, cfg: dict | None = None) -> tuple:
    """(PuntoFar, far.ResultadoPunto) de una sola orientacion, para dibujarla; (None, None) si
    esa orientacion no tiene punto de referencia. Sin volumenes, el resultado no tiene filas."""
    c = config(cfg)
    pf = next((p for p in puntos(u, g, c) if p.orientacion == orientacion_), None)
    if pf is None:
        return None, None
    vols = volumenes(u) if c["activo"] else ()
    return pf, calcular_punto(pf.punto, vols, parametros(c))


def tabla(r: ResultadoFar, cfg: dict | None = None) -> list:
    """Para la interfaz, una entrada por punto de referencia:
    {orientacion, z, exterior, filas: [(division, volumen, A, B, D)] (las mismas que van a la
     ficha), omitidas: [(division, volumen, motivo)] (sin las astillas "angosto")}."""
    dec = int(config(cfg)["decimales"])
    out = []
    for pf in r.puntos:
        res = r.resultados.get(pf.orientacion)
        filas = [] if res is None else [(o.division, o.volumen, a, b, d) for o, a, b, d in _redondeadas(res, dec)
                                        if a > 0 and b > 0 and d > 0]
        omitidas = [] if res is None else [(m.obstruccion.division, m.obstruccion.volumen, m.motivo)
                                           for m in res.omitidas if m.motivo != "angosto"]
        out.append({"orientacion": pf.orientacion, "z": pf.punto.z, "exterior": pf.exterior,
                    "filas": filas, "omitidas": omitidas})
    return out
