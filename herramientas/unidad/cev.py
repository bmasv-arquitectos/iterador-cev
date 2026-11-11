# -*- coding: utf-8 -*-
"""
Unidad (modelo.py) -> Ficha de fichas_cev, la entrada del motor (ficha_virtual y
motor_py.calcular). Es la herramienta CEV sobre el modelo comun.

Soluciones generales: construir() las resuelve primero (generales.resolver), asi
el resto de este modulo ve solo soluciones concretas (DEFECTO o un muro
personalizado; codigos de vidrio y tipos de puerta; los techos y pisos los
resuelve modelo.personalizado_horizontal).

Obstrucciones (obstrucciones.py, criterio en config/cev.yaml obstrucciones:): un
voladizo del nivel de arriba o una obstruccion horizontal dibujada entra como el
FAV1 de la ventana (VentanaGeo.fav1_obstruccion) y una vertical dibujada o la
autosombra de un rincon como su FAV2 de ese lado (fav2_obstruccion), salvo que la
ventana tenga su propio alero o aleta, que mandan. Cada obstruccion deja una linea
en los avisos.
P04 de las obstrucciones dibujadas: filas propias de CEV-CEVE 87-91 (FilaP04 en
ficha.p04_extra; las escribe fichas_cev.escritor despues de las de los muros),
agrupadas por tipo (horizontal o vertical), muro donde se alojan, orientacion,
elemento y aislacion. El voladizo detectado no suma P04.

FAR dibujado (contexto_far.py, config/cev.yaml far:): los volumenes de
Unidad.contexto se convierten en las obstrucciones remotas de la ficha
(ficha.obstrucciones: division, A, B, D por orientacion; 'CEV-CEVE' E127:H134...)
y, si hay volumenes, en el azimut de cada bloque (proyecto[CLAVE_AZIMUT_FAR]:
G125, L125... los escribe fichas_cev.escritor; el motor oficial lo exige).
Traduccion.far guarda el detalle (puntos, tramos y omitidas). Sin volumenes, la
ficha queda como antes.

Puentes termicos (config/cev.yaml, criterio de Lucas 2026-11-04):
  - esquinas verticales entre muros exteriores: salientes P01, entrantes P02,
    contadas una vez en el muro que termina en el vertice;
  - union de un muro exterior con uno adiabatico (esquina o tramos alineados):
    P03 en el muro exterior (Manual CEV);
  - borde superior de un muro exterior: bajo el nivel de arriba P03 (losa entre
    niveles); lo demas segun el techo (exterior P01, adiabatico P03);
  - borde inferior: sobre el nivel de abajo P03; lo demas segun el piso (ventilado
    P01, terreno nada, adiabatico P03). La parte que vuela usa piso_expuesto;
  - cada tabique interior que llega a un muro exterior suma la altura como P03;
  - P04: aleros propios (ancho de la ventana) y aletas propias (alto + D), en la fila
    del muro; las obstrucciones dibujadas, en sus filas propias.
Areas: muro = bruta menos ventanas y puertas (el motor no descuenta nada);
vanos que ocupan todo el muro -> muro de 0,05 m2 (Manual 6.7).

Protecciones (FAV, columnas P..Y de la ficha): alero D y L; aletas P y S de cada
lado; celosia E, T y el angulo en b (lamas horizontales) o en a (verticales).

Puertas (CEV-CEVE 96-98): tipo de fabrica (cev.yaml puertas.tipos, con su
materialidad para infiltraciones) o personalizada (filas 18-23 de '3. Tablas
Envolvente': B y C nombre, D U, sin vidrio ni marco).

Techos y pisos: cada superficie horizontal de la geometria (el piso del nivel 1,
los voladizos, el techo del ultimo nivel y lo que un nivel deja sin cubrir) tiene
su solucion (modelo.personalizado_horizontal). Las superficies con la misma
condicion y la misma solucion se suman en una fila de la ficha; asi una unidad sin
personalizar da las mismas filas que antes.

Catalogo ('3. Tablas Envolvente'): una fila por solucion de muro usada (DEFECTO o
personalizada; filas 62-75 sin la del muro ficticio), por solucion de techo exterior
(80-82) y por condicion y solucion de piso (terreno y ventilado, 88-91).
Un muro personalizado va a la ficha con datos["nombre"] (si falta, su clave).
Tipo de vivienda: texto de config/cev.yaml (tipos_vivienda).
Si la unidad supera las filas de la planilla (16 muros, 20 ventanas, 3 puertas,
5 filas de P04, 5 techos, 4 pisos) se avisa: el agrupador es la etapa F4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from herramientas.comun.xlsx_inspeccion import normalizar
from herramientas.fichas_cev.modelo import (
    ADIABATICOS, CLAVE_AZIMUT_FAR, CLAVE_CATALOGO, Ficha, Horizontal, Muro, Nivel, calcular_paquetes,
)
from herramientas.fichas_cev.modelo import Puerta as PuertaFicha
from herramientas.fichas_cev.modelo import Ventana as VentanaFicha
from herramientas.recinto import catalogo as cat_vidrios
from herramientas.recinto import envolvente, personalizado, zonas
from herramientas.recinto.a_ficha import (
    _espesores, _fila, aislacion_p04, azimut_texto, fav_ficha, portada, vidrio_de,
)
from herramientas.recinto.a_ficha import cargar_config as cargar_ficha01

from . import contexto_far, generales, obstrucciones
from . import geometria as geo
from .modelo import DEFECTO, Unidad, personalizado_horizontal

CONFIG = Path(__file__).parent / "config" / "cev.yaml"
TOPES = {"muros": 16, "ventanas": 20, "puertas": 3, "p04": 5, "techos": 5, "pisos": 4}
NOMBRE_DESTINO = {"techo": "Techo", "piso": "Piso"}


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return cargar_config()


@dataclass(frozen=True)
class FilaP04:
    """Fila propia de P04 en CEV-CEVE 87-91 (obstrucciones dibujadas)."""
    muro: str            # abreviatura del muro donde se aloja
    azimut: str          # texto del rango de azimut
    elemento: str        # Elemento_Terraza
    aislacion: str       # Aislacion_Terraza
    longitud: float      # [m]


@dataclass
class Traduccion:
    ficha: Ficha
    proyecto: dict
    geometria: geo.Geometria
    zona: str
    puentes: dict                  # {id del pano: {p01, p02, p03, p04}} [m]
    avisos: list = field(default_factory=list)
    obstrucciones: list = field(default_factory=list)
    p04_obstaculos: list = field(default_factory=list)
    far: object = None             # contexto_far.ResultadoFar


# --------------------------------------------------------------------------- puentes
def puentes(u: Unidad, g: geo.Geometria, cfg: dict | None = None) -> dict:
    """{indice del pano: {p01, p02, p03}} [m] (P04 sale de las ventanas y las obstrucciones)."""
    c = (cfg or _cfg())["puentes"]
    h = g.altura
    p = {x.indice: {"p01": 0.0, "p02": 0.0, "p03": 0.0} for x in g.panos}

    def sumar(i, tipo, largo):
        if tipo and largo > 0:
            p[i][tipo] += largo

    for e in g.esquinas:
        a, b = g.panos[e.antes], g.panos[e.despues]
        if a.exterior and b.exterior:
            sumar(a.indice, c["esquina"].get(e.tipo), h)
        elif a.exterior or b.exterior:
            sumar((a if a.exterior else b).indice, c["esquina_con_adiabatico"].get(e.tipo), h)
    ultimo = len(u.niveles) - 1
    for x in g.panos:
        if not x.exterior:
            continue
        if x.nivel == ultimo:
            sumar(x.indice, c["borde_techo"][u.techo], x.largo)
        else:
            sumar(x.indice, c["losa_entre_niveles"], x.sup_cubierto)
            sumar(x.indice, c["borde_techo"][u.techo_expuesto], x.sup_expuesto)
        if x.nivel == 0:
            sumar(x.indice, c["borde_piso"][u.piso], x.largo)
        else:
            sumar(x.indice, c["losa_entre_niveles"], x.inf_cubierto)
            sumar(x.indice, c["borde_piso"][u.piso_expuesto], x.inf_expuesto)
        sumar(x.indice, c["tabique"], x.tabiques * h)
    return p


def fav_ventana(v: geo.VentanaGeo, cfg: dict | None = None) -> list:
    """[D, L, P_izq, S_izq, P_der, S_der, E, T, b, a] de una ventana.

    FAV1: el alero propio; si no tiene, el de una obstruccion (v.fav1_obstruccion =
    (D, L)). FAV2 de cada lado: la aleta propia; si no tiene, la de una obstruccion
    vertical (v.fav2_obstruccion = ((P, S) izq, (P, S) der)). S de una aleta propia:
    aleta_izq_s / aleta_der_s, si no aleta_s, si no config/cev.yaml (proteccion.aletas_en).
    La celosia lleva su angulo en b si sus lamas son horizontales y en a si son
    verticales; el otro queda en None."""
    c = (cfg or _cfg())["proteccion"]
    pr = v.datos.proteccion
    auto = getattr(v, "fav1_obstruccion", None)
    auto2 = getattr(v, "fav2_obstruccion", None) or (None, None)
    if pr.alero_l > 0:
        fav1 = [pr.alero_d if pr.alero_d is not None else c["alero_d"], pr.alero_l]
    elif auto:
        fav1 = [float(auto[0]), float(auto[1])]
    else:
        fav1 = [0.0, 0.0]
    if pr.aleta_s is not None:
        d_i = d_d = pr.aleta_s
    elif c["aletas_en"] == "borde_muro":
        d_i, d_d = v.s_izq, v.s_der
    else:
        d_i = d_d = 0.0
    s_i = pr.aleta_izq_s if pr.aleta_izq_s is not None else d_i
    s_d = pr.aleta_der_s if pr.aleta_der_s is not None else d_d
    fav2 = []
    for propia, s_propia, obs in ((pr.aleta_izq_p, s_i, auto2[0]), (pr.aleta_der_p, s_d, auto2[1])):
        if propia > 0:
            fav2 += [propia, s_propia]
        elif obs:
            fav2 += [float(obs[0]), float(obs[1])]
        else:
            fav2 += [propia, 0.0]
    ang = pr.celosia_beta
    fav3 = [pr.celosia_e, pr.celosia_t] + ([ang, None] if pr.celosia_orientacion == "horizontal" else [None, ang])
    return fav1 + fav2 + fav3


def largo_p04(fav: list, v: geo.VentanaGeo, cfg: dict | None = None) -> float:
    """[m] de P04 de una ventana: su alero PROPIO (ancho) y sus aletas PROPIAS (alto + D del
    alero propio). Las obstrucciones no suman aca (tienen sus propias filas de P04)."""
    c = (cfg or _cfg())["puentes"].get("p04") or {}
    pr = v.datos.proteccion
    D = fav[0] if pr.alero_l > 0 else 0.0
    total = 0.0
    if c.get("alero", True) and pr.alero_l > 0:
        total += v.ancho
    if c.get("aletas", True):
        total += sum(v.alto + D for P in (pr.aleta_izq_p, pr.aleta_der_p) if P > 0)
    return total


# --------------------------------------------------------------------------- soluciones
def _personalizados(u: Unidad) -> dict:
    muros = {k: personalizado.validar("muro", dict(d, nombre=d.get("nombre") or k), u.piso)
             for k, d in u.muros_personalizados.items()}
    nombres = [d["nombre"] for d in muros.values()]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise ValueError(f"hay dos muros personalizados llamados '{repetidos[0]}': cambia el nombre de uno")
    return muros


def grupos_horizontales(u: Unidad, g: geo.Geometria) -> dict:
    """{destino: {(condicion, nombre de la solucion o None): {area, perimetro, datos}}} en el
    orden de la geometria. datos: el personalizado validado (None = solucion de la norma)."""
    out = {"techo": {}, "piso": {}}
    for hz in g.horizontales:
        d = None
        if hz.condicion != "adiabatico":
            crudo = personalizado_horizontal(u, hz.destino, hz.nivel)
            if crudo:
                try:
                    d = personalizado.validar(hz.destino, crudo, hz.condicion)
                except ValueError as ex:
                    raise ValueError(f"{NOMBRE_DESTINO[hz.destino]} del nivel {hz.nivel + 1}: {ex}") from None
        gr = out[hz.destino].setdefault((hz.condicion, d["nombre"] if d else None),
                                        {"area": 0.0, "perimetro": 0.0, "datos": d})
        if d is not None and gr["datos"] != d:
            raise ValueError(f"hay dos soluciones de {hz.destino} distintas llamadas '{d['nombre']}': "
                             "cambia el nombre de una")
        gr["area"] += hz.area
        gr["perimetro"] += hz.perimetro
    vistos = {}
    for cond, nombre in out["piso"]:
        if nombre and vistos.setdefault(nombre, cond) != cond:
            raise ValueError(f"el piso personalizado '{nombre}' se usa contra terreno y ventilado: "
                             "usa un nombre distinto para cada uno")
    return out


def _puertas(g, cfg, filas) -> dict:
    """{(pano, n): (abreviatura, categoria)}; agrega a filas las personalizadas (una por nombre)."""
    pc = cfg["puertas"]
    ini, fin = pc["filas"]
    propias, out = {}, {}
    for x in g.panos:
        for n, p in enumerate(x.puertas):
            et = f"{x.id}, puerta {n + 1}"
            if not p.personalizada:
                tipo = p.tipo or pc["defecto"]
                if tipo not in pc["tipos"]:
                    raise ValueError(f"{et}: tipo de puerta desconocido '{tipo}'")
                out[(x.indice, n)] = (tipo, pc["tipos"][tipo]["categoria"])
                continue
            try:
                d = personalizado.validar("puerta", p.personalizada)
            except ValueError as ex:
                raise ValueError(f"{et}: {ex}") from None
            previo = propias.get(d["nombre"])
            if previo is None:
                fila = ini + len(propias)
                if fila > fin:
                    raise ValueError(f"hay más de {fin - ini + 1} puertas personalizadas distintas")
                propias[d["nombre"]] = d["u"]
                filas.append(_fila("Puertas", fila, {"B": d["nombre"], "C": d["nombre"], "D": d["u"],
                                                     "F": 0, "G": 0, "H": 0}))
            elif previo != d["u"]:
                raise ValueError(f"hay dos puertas distintas llamadas '{d['nombre']}': cambia el nombre de una")
            out[(x.indice, n)] = (d["nombre"], d["categoria"])
    return out


def catalogo(u, g, sols, zona, cfg, fcfg, env_cfg, ficticio: bool, grupos: dict, muros_p: dict) -> tuple:
    """(filas de '3. Tablas Envolvente', abreviaturas, vidrio de cada ventana, puerta de cada puerta).

    abreviaturas: muros {solucion: abrev}, techos {nombre o None: abrev},
    pisos {(condicion, nombre o None): abrev}, muro_ficticio."""
    ais = env_cfg["aislante"]["material"]
    cat = fcfg["catalogo"]
    filas, ab, ab_v = [], {"muros": {}, "techos": {}, "pisos": {}}, {}

    def opaco(clave, bloque, sol, fila, extra, sufijo=""):
        c = cat[clave]
        smm, amm = _espesores(sol, ais)
        fmt = dict(solido_mm=smm, aislante_mm=amm)
        abrev = c["abreviatura"].format(**fmt) + sufijo
        valores = {"B": c["nombre"].format(**fmt) + sufijo, "C": abrev}
        valores.update(extra(c, smm, amm))
        filas.append(_fila(bloque, fila, valores))
        return abrev

    # vidrios: los de fabrica tienen su fila; los demas, una fila por vidrio distinto
    ini, fin = cat["vidrio"]["filas"]
    propios: dict = {}
    for x in g.panos:
        for v in x.ventanas:
            d = vidrio_de(v.datos)
            if d["ficha"]:
                ab_v[(x.indice, v.indice)] = d["ficha"]
                continue
            valores = (d["u"], d["fs"])
            previo = propios.get(d["nombre"])
            if previo is None:
                fila = ini + len(propios)
                if fila > fin:
                    raise ValueError(f"hay más de {fin - ini + 1} vidrios personalizados distintos")
                propios[d["nombre"]] = valores
                filas.append(_fila("Vidrios", fila, {"B": d["nombre"], "C": d["nombre"], "D": d["u"], "E": d["fs"]}))
            elif previo != valores:
                raise ValueError(f"hay dos vidrios distintos llamados '{d['nombre']}': cambia el nombre de uno")
            ab_v[(x.indice, v.indice)] = d["nombre"]
    ab_p = _puertas(g, cfg, filas)

    # muros: una fila por solucion usada, saltando la del muro ficticio
    f0, f1 = cfg["catalogo"]["muros"]["filas"]
    libres = [f for f in range(f0, f1 + 1) if f != cat["muro_ficticio"]["fila"]]
    usadas = list(dict.fromkeys(x.solucion for x in g.panos if x.exterior))
    if len(usadas) > len(libres):
        raise ValueError(f"la unidad usa {len(usadas)} soluciones de muro y la planilla admite {len(libres)}")
    s_muro = sols["muro"]
    for nombre, fila in zip(usadas, libres):
        if nombre == DEFECTO:
            ab["muros"][nombre] = opaco("muro", "Muros", s_muro, fila, lambda c, smm, amm: {
                "D": c["materialidad"], "E": round(s_muro.u, 3), "F": smm / 10, "G": amm / 10,
                "H": c["posicion"] if amm else "Sin"})
        else:
            d = muros_p[nombre]
            ab["muros"][nombre] = d["nombre"]
            filas.append(_fila("Muros", fila, personalizado.valores_ficha("muro", d, u.piso)))
    if ficticio:
        c = cat["muro_ficticio"]
        ab["muro_ficticio"] = c["abreviatura"]
        filas.append(_fila("Muros", c["fila"], {
            "B": c["nombre"], "C": c["abreviatura"], "D": c["materialidad"],
            "E": envolvente.u_max(zona, "muro", env_cfg), "F": c["espesor_solido_cm"], "G": 0,
            "H": c["posicion"]}))

    # techos exteriores: una fila por solucion
    tf0, tf1 = (cfg["catalogo"].get("techos") or {}).get("filas", [cat["techo"]["fila"]] * 2)
    libres_t = iter(range(tf0, tf1 + 1))
    s_t = sols["techo"]
    for (cond, nombre), gr in grupos["techo"].items():
        if cond != "exterior" or nombre in ab["techos"]:
            continue
        fila = next(libres_t, None)
        if fila is None:
            raise ValueError(f"hay más de {tf1 - tf0 + 1} soluciones de techo distintas")
        if nombre:
            ab["techos"][nombre] = nombre
            filas.append(_fila("Techos", fila, personalizado.valores_ficha("techo", gr["datos"], u.piso)))
        else:
            ab["techos"][None] = opaco("techo", "Techos", s_t, fila, lambda c, smm, amm: {
                "D": round(s_t.u, 3), "F": smm / 10, "G": amm / 10, "H": c["posicion"] if amm else "Sin"})

    # pisos terreno y ventilado: una fila por condicion y solucion
    cp = cfg["catalogo"]["pisos"]
    lam = envolvente.lambdas()[ais]
    libres_p = iter(range(cp["filas"][0], cp["filas"][1] + 1))
    for (cond, nombre), gr in grupos["piso"].items():
        if cond not in ("terreno", "ventilado"):
            continue
        fila = next(libres_p, None)
        if fila is None:
            raise ValueError(f"hay más de {cp['filas'][1] - cp['filas'][0] + 1} soluciones de piso distintas")
        if nombre:
            ab["pisos"][(cond, nombre)] = nombre
            filas.append(_fila("Pisos", fila, personalizado.valores_ficha("piso", gr["datos"], cond)))
            continue
        sol = sols["piso_ventilado" if cond == "ventilado" else "piso_terreno"]

        def extra(c, smm, amm, cond=cond, sol=sol):
            v = {"M": c["posicion"] if amm else "Sin"}
            if cond == "ventilado":
                v["D"] = round(sol.u, 3)
            elif amm:
                v.update({"E": lam, "F": amm / 10})
            return v
        smm, amm = _espesores(sol, ais)
        base = cat["piso"]["abreviatura"].format(solido_mm=smm, aislante_mm=amm)
        sufijo = cp["sufijo"][cond] if base in ab["pisos"].values() else ""
        ab["pisos"][(cond, None)] = opaco("piso", "Pisos", sol, fila, extra, sufijo)
    return filas, ab, ab_v, ab_p


# --------------------------------------------------------------------------- ficha
def _validar_vidrios(g: geo.Geometria) -> None:
    for x in g.panos:
        for v in x.ventanas:
            w = v.datos
            et = f"{x.id}, ventana {v.indice + 1}"
            if w.vidrio_personalizado:
                try:
                    personalizado.validar("vidrio", w.vidrio_personalizado)
                except ValueError as ex:
                    raise ValueError(f"{et}: {ex}") from None
            elif w.vidrio not in cat_vidrios.vidrios():
                raise ValueError(f"{et}: elige un vidrio")


def _topes(muros, ventanas, puertas, filas_p04, techos, pisos) -> None:
    n = {"muros": len(muros), "ventanas": len(ventanas), "puertas": len(puertas), "p04": filas_p04,
         "techos": techos, "pisos": pisos}
    exceso = [f"{k}: {v} (la planilla admite {TOPES[k]})" for k, v in n.items() if v > TOPES[k]]
    if exceso:
        raise ValueError("La unidad no cabe en la ficha 01: " + "; ".join(exceso)
                         + ". Hay que agrupar elementos de igual orientación y materialidad.")


def filas_p04(p04_obs: list, g: geo.Geometria, ab: dict, ficticios: set) -> tuple:
    """([FilaP04] agrupadas por tipo, muro, orientacion, elemento y aislacion, {pano: largo})."""
    grupos, por_pano = {}, {}
    for q in p04_obs:
        x = g.panos[q.pano]
        por_pano[x.indice] = por_pano.get(x.indice, 0.0) + q.largo
        muro = ab["muro_ficticio"] if x.indice in ficticios else ab["muros"][x.solucion]
        clave = (q.tipo, muro, azimut_texto(x.azimut), q.elemento, q.aislacion)
        grupos[clave] = grupos.get(clave, 0.0) + q.largo
    filas = [FilaP04(m, az, el, ai, round(l, 4)) for (_, m, az, el, ai), l in grupos.items() if l > 0]
    return filas, por_pano


def construir(u: Unidad, g: geo.Geometria | None = None, cfg: dict | None = None,
              unidad: str = "iterador") -> Traduccion:
    cfg = cfg or _cfg()
    fcfg = cargar_ficha01()
    env_cfg = envolvente.cargar_config()
    g = g or geo.calcular(u)
    u, g = generales.resolver(u, g)                        # soluciones generales -> concretas
    obs = obstrucciones.detectar(u, g, cfg)                # voladizos y obstrucciones dibujadas -> FAV
    g = obstrucciones.aplicar(u, g, cfg, obs)
    zona = zonas.zona_de(u.comuna, u.zona)
    sols = envolvente.soluciones(zona, env_cfg)
    muros_p = _personalizados(u)
    _validar_vidrios(g)
    pt = puentes(u, g, cfg)
    h = g.altura
    cv = cfg["ventana"]
    ficticios = {x.indice for x in g.panos
                 if x.exterior and (x.ventanas or x.puertas)
                 and x.area_neta - x.area_puertas <= cv["tolerancia_fachada_completa"] * h}
    grupos = grupos_horizontales(u, g)
    filas, ab, ab_v, ab_p = catalogo(u, g, sols, zona, cfg, fcfg, env_cfg, bool(ficticios), grupos, muros_p)
    p04_obs = obstrucciones.p04(u, g, cfg, fcfg["p04"]["aislacion_defecto"])
    p04_extra, p04_pano = filas_p04(p04_obs, g, ab, ficticios)

    vf = fcfg["ventana"]
    avisos, muros, ventanas, puertas_f, tabla = list(g.avisos), [], [], [], {}
    avisos += obstrucciones.avisos(obs, cfg)
    for x in g.panos:
        az = azimut_texto(x.azimut)
        pp = pt[x.indice]
        if not x.exterior:
            muros.append(Muro(ADIABATICOS["muros"], az, round(x.area_bruta, 4), None, None, None,
                              etiqueta=x.id, area_bruta=round(x.area_bruta, 4)))
            tabla[x.id] = dict(pp, p04=0.0)
            continue
        fic = x.indice in ficticios
        tipo = ab["muro_ficticio"] if fic else ab["muros"][x.solucion]
        neta = cv["muro_ficticio_area"] if fic else x.area_neta - x.area_puertas
        if fic:
            avisos.append(f"{x.id}: los vanos ocupan todo el muro; muro de {neta} m2 (Manual 6.7)")
        p04, aisl = 0.0, ""
        for v in x.ventanas:
            fav = fav_ventana(v, cfg)
            l04 = largo_p04(fav, v, cfg)
            if l04 > 0:
                p04 += l04
                aisl = aisl or aislacion_p04(v.datos, fcfg)
            pr = v.datos.proteccion
            if pr.alero_l > 0 and pr.alero_l / v.alto < 0.1:
                avisos.append(f"{x.id}, ventana {v.indice + 1}: L/H < 0,1, el FAV1 se podría desestimar (6.7.3.1)")
            ventanas.append(VentanaFicha(
                tipo=ab_v[(x.indice, v.indice)], azimut=az, elemento=tipo, cierre=vf["cierre"],
                posicion=vf["posicion"], alto=round(v.alto, 4), ancho=round(v.ancho, 4),
                fav=fav_ficha(fav), muro=x.id))
        for n, p in enumerate(x.puertas):
            abrev, categoria = ab_p[(x.indice, n)]
            puertas_f.append(PuertaFicha(f"Puerta {len(puertas_f) + 1}", abrev, az, categoria,
                                         round(p.alto, 4), round(p.ancho, 4), muro=x.id))
        con_p04 = p04 > 0
        muros.append(Muro(
            tipo, az, round(neta, 4), round(pp["p01"], 4), round(pp["p02"], 4), round(pp["p03"], 4),
            p04=round(p04, 4) if con_p04 else None,
            p04_elemento=fcfg["p04"]["elemento"] if con_p04 else "",
            p04_aislacion=aisl if con_p04 else "",
            etiqueta=x.id, area_bruta=round(x.area_bruta, 4),
            area_vanos=round(x.area_vanos + x.area_puertas, 4)))
        tabla[x.id] = dict(pp, p04=p04 + p04_pano.get(x.indice, 0.0))

    dens = fcfg["densidad"]
    horiz = []
    for i, ((cond, nombre), gr) in enumerate(grupos["techo"].items(), 1):
        if cond == "exterior":
            t = gr["datos"] or {}
            horiz.append(Horizontal("techo", f"Techo {i}", ab["techos"][nombre], t.get("densidad", dens),
                                    t.get("cubierta", fcfg["techo"]["cubierta"]), round(gr["area"], 4),
                                    t.get("camaras", fcfg["techo"]["camaras_aire"])))
        else:
            horiz.append(Horizontal("techo", f"Techo {i}", ADIABATICOS["techos"], dens, "",
                                    round(gr["area"], 4), None))
    for i, ((cond, nombre), gr) in enumerate(grupos["piso"].items(), 1):
        if cond == "adiabatico":
            horiz.append(Horizontal("piso", f"Piso {i}", ADIABATICOS["pisos"], dens, "", round(gr["area"], 4), None))
            continue
        d = (gr["datos"] or {}).get("densidad", dens)
        horiz.append(Horizontal("piso", f"Piso {i}", ab["pisos"][(cond, nombre)], d, fcfg["pisos_tipo"][cond],
                                round(gr["area"], 4),
                                round(gr["perimetro"], 4) if cond == "terreno" else None))
    _topes(muros, ventanas, puertas_f, sum(1 for m in muros if m.p04) + len(p04_extra),
           len(grupos["techo"]), len(grupos["piso"]))

    far = contexto_far.calcular(u, g, cfg)                 # volumenes de contexto -> obstrucciones remotas
    avisos += far.avisos
    ficha = Ficha(unidad=unidad, piso=1, plantilla="iterador", dormitorios=u.dormitorios,
                  perimetro_terreno=None, niveles=[Nivel(round(a, 4), u.altura) for a in g.areas],
                  horizontales=horiz, muros=muros, ventanas=ventanas, puertas=puertas_f,
                  obstrucciones=list(far.obstrucciones))
    ficha.p04_extra = p04_extra                            # filas propias de P04 (fichas_cev.escritor)
    proyecto = {normalizar(k): val for k, val in portada(u, zona, fcfg).items()}
    proyecto[normalizar("Tipo de vivienda")] = cfg["tipos_vivienda"][u.tipo_vivienda]
    proyecto[CLAVE_CATALOGO] = filas
    # azimut de cada bloque FAR ('CEV-CEVE' G125...): solo con volumenes de contexto (sin ellos la
    # ficha queda igual que antes)
    proyecto[CLAVE_AZIMUT_FAR] = contexto_far.azimuts(u, g, cfg) if u.contexto else {}
    ficha.paquetes = calcular_paquetes(ficha, proyecto)
    return Traduccion(ficha, proyecto, g, zona, tabla, avisos, obs, p04_obs, far)


def calificar(u: Unidad, antes_de_caso=None):
    """(Traduccion, FichaVirtual, Calificacion): la unidad calculada con el motor Python."""
    from herramientas.motor_cev.motor_py import ficha_virtual
    from herramientas.motor_cev.motor_py.calcular import calcular

    t = construir(u)
    fv = ficha_virtual.construir(t.ficha, t.proyecto)
    return t, fv, calcular(fv.ficha, antes_de_caso=antes_de_caso)
