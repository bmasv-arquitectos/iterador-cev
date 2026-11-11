# -*- coding: utf-8 -*-
"""
Recinto -> Ficha de fichas_cev (sin Excel): lo que despues escribe
fichas_cev.escritor.generar en la plantilla oficial.

No inventa textos: los de listas salen de config/ficha01.yaml, las comunas y
regiones de datos/comunas.yaml, los vidrios de datos/vidrios.yaml y los
componentes personalizados de config/personalizado.yaml.
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml
from openpyxl.utils import column_index_from_string

from herramientas.comun.xlsx_inspeccion import normalizar
from herramientas.fichas_cev.modelo import (
    ADIABATICOS, CLAVE_AZIMUT_FAR, CLAVE_CATALOGO, Ficha, FilaCatalogo,
    Horizontal, Muro, Nivel, Ventana, calcular_paquetes,
)

from . import envolvente, personalizado, zonas
from .catalogo import vidrio as buscar_vidrio
from .geometria import Resultado, etiqueta, normalizar_azimut
from .modelo import Fachada, Recinto

CONFIG = Path(__file__).parent / "config" / "ficha01.yaml"


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- textos
def _grados(x: float) -> str:
    x = round(x + 0.0, 1)
    return str(int(x)) if x == int(x) else f"{x:g}".replace(".", ",")


def azimut_texto(az: float) -> str:
    """Azimut -> opcion de la lista Azimut_Muros, p. ej. '0° ≤ Az < 22,5°'."""
    a = normalizar_azimut(az)
    if a >= 180:
        a = -180.0
    lo = math.floor(a / 22.5 + 1e-9) * 22.5
    return f"{_grados(lo)}° ≤ Az < {_grados(lo + 22.5)}°"


def fav_ficha(fav) -> list:
    """[D, L, P, S, P, S, E, T, b] (o con a al final si fav trae 10 valores); None en los
    grupos sin proteccion. La celosia lleva su angulo en b (lamas horizontales) o en a
    (verticales): el que no aplica viene en None y queda vacio."""
    n = len(fav) if fav else 9
    out = [None] * n
    if not fav:
        return out
    D, L, Pi, Si, Pd, Sd, E, T, b = fav[:9]
    if L > 0:
        out[0:2] = [D, L]
    if Pi > 0:
        out[2:4] = [Pi, Si]
    if Pd > 0:
        out[4:6] = [Pd, Sd]
    if E > 0 and T > 0:
        out[6:9] = [E, T, b]
        if n > 9:
            out[9] = fav[9]
    return out


def aislacion_p04(f: Fachada, cfg: dict) -> str:
    c = cfg["p04"]
    a = f.proteccion.p04_aislacion or c["aislacion_defecto"]
    if a not in c["aislaciones"]:
        raise ValueError(f"aislación P04 desconocida: {a!r}")
    return a


# --------------------------------------------------------------------------- catalogo
def _fila(bloque: str, fila: int, valores: dict) -> FilaCatalogo:
    return FilaCatalogo(bloque, int(fila), {
        column_index_from_string(k): v for k, v in valores.items() if v not in (None, "")})


def _espesores(sol, aislante: str) -> tuple:
    solido = sum(c.espesor for c in sol.capas if c.material != aislante)
    return int(round(solido * 1000)), int(sol.espesor_aislante_mm)


def vidrio_de(f: Fachada) -> dict:
    """{nombre, u, fs, ficha} del vidrio de una fachada (personalizado o de catalogo)."""
    d = f.vidrio_personalizado
    if d:
        return {"nombre": d["nombre"], "u": float(d["u"]), "fs": float(d["fs"]), "ficha": None}
    return buscar_vidrio(f.vidrio)


def _vidrios(r: Recinto, res: Resultado, cfg: dict, filas: list) -> dict:
    """{fachada: abreviatura} y agrega una fila por cada vidrio propio distinto."""
    ini, fin = cfg["catalogo"]["vidrio"]["filas"]
    propios: dict = {}           # nombre -> (u, fs)
    out = {}
    for m, f in zip(res.muros, r.fachadas):
        if not m.ventana:
            continue
        v = vidrio_de(f)
        if v["ficha"]:
            out[m.nombre] = v["ficha"]                    # fila de fabrica
            continue
        valores = (v["u"], v["fs"])
        previo = propios.get(v["nombre"])
        if previo is None:
            fila = ini + len(propios)
            if fila > fin:
                raise ValueError("no quedan filas libres de vidrio en la ficha 01")
            propios[v["nombre"]] = valores
            filas.append(_fila("Vidrios", fila, {
                "B": v["nombre"], "C": v["nombre"], "D": v["u"], "E": v["fs"]}))
        elif previo != valores:
            raise ValueError(f"hay dos vidrios distintos llamados '{v['nombre']}': "
                             "cambia el nombre de uno")
        out[m.nombre] = v["nombre"]
    return out


def catalogo(r: Recinto, res: Resultado, sols: dict, zona: str, cfg: dict,
             env_cfg: dict) -> tuple:
    """Filas propias de '3. Tablas Envolvente' y abreviatura por elemento."""
    ais = env_cfg["aislante"]["material"]
    cat = cfg["catalogo"]
    pers = r.personalizados or {}
    filas, ab = [], {}

    def propia(el):
        sp, d = personalizado.spec(el), pers[el]
        ab[el] = d["nombre"]
        filas.append(_fila(sp["bloque"], sp["fila"], personalizado.valores_ficha(el, d, r.piso)))

    ab["vidrios"] = _vidrios(r, res, cfg, filas)

    def opaco(clave, bloque, sol, extra):
        c = cat[clave]
        smm, amm = _espesores(sol, ais)
        fmt = dict(solido_mm=smm, aislante_mm=amm)
        ab[clave] = c["abreviatura"].format(**fmt)
        valores = {"B": c["nombre"].format(**fmt), "C": ab[clave]}
        valores.update(extra(c, smm, amm))
        filas.append(_fila(bloque, c["fila"], valores))

    if "muro" in pers:
        propia("muro")
    else:
        opaco("muro", "Muros", sols["muro"], lambda c, smm, amm: {
            "D": c["materialidad"], "E": round(sols["muro"].u, 3), "F": smm / 10,
            "G": amm / 10, "H": c["posicion"] if amm else "Sin"})

    if any(m.muro_ficticio for m in res.muros):
        c = cat["muro_ficticio"]
        ab["muro_ficticio"] = c["abreviatura"]
        filas.append(_fila("Muros", c["fila"], {
            "B": c["nombre"], "C": c["abreviatura"], "D": c["materialidad"],
            "E": envolvente.u_max(zona, "muro", env_cfg),
            "F": c["espesor_solido_cm"], "G": 0, "H": c["posicion"]}))

    if r.techo == "exterior":
        if "techo" in pers:
            propia("techo")
        else:
            opaco("techo", "Techos", sols["techo"], lambda c, smm, amm: {
                "D": round(sols["techo"].u, 3), "F": smm / 10, "G": amm / 10,
                "H": c["posicion"] if amm else "Sin"})

    if r.piso in ("ventilado", "terreno"):
        if "piso" in pers:
            propia("piso")
        else:
            sol = sols["piso_ventilado" if r.piso == "ventilado" else "piso_terreno"]
            lam = envolvente.lambdas()[ais]

            def piso(c, smm, amm):
                v = {"M": c["posicion"] if amm else "Sin"}
                if r.piso == "ventilado":
                    v["D"] = round(sol.u, 3)
                elif amm:
                    v.update({"E": lam, "F": amm / 10})
                return v
            opaco("piso", "Pisos", sol, piso)
    return filas, ab


# --------------------------------------------------------------------------- ficha
def portada(r: Recinto, zona: str, cfg: dict) -> dict:
    p, v = cfg["portada"], cfg["ventana"]
    return {
        "Tipo de Calificación": p["tipo_calificacion"],
        "Región": zonas.region(r.comuna),
        "Comuna": r.comuna,
        "Zona Térmica Proyecto": zonas.zona_de(r.comuna, zona),
        "Nombre del proyecto": p["nombre_proyecto"],
        "Tipo de vivienda": p["tipo_vivienda"],
        "Ventana: Aislación con/sin retorno": v["aislacion_retorno"],
        "Ventana: Categoría para PT y Infilt": v["categoria_marco"],
        "Ventana: Tipo marco": v["tipo_marco"],
    }


def construir(r: Recinto, res: Resultado, sols: dict, zona: str, cfg: dict | None = None,
              env_cfg: dict | None = None, unidad: str = "iterador") -> tuple:
    """(Ficha, proyecto) listos para fichas_cev.escritor.generar."""
    cfg = cfg or cargar_config()
    env_cfg = env_cfg or envolvente.cargar_config()
    pers = r.personalizados or {}
    filas, ab = catalogo(r, res, sols, zona, cfg, env_cfg)
    v = cfg["ventana"]

    muros, ventanas = [], []
    for m, f in zip(res.muros, r.fachadas):
        az = azimut_texto(m.azimut)
        if not m.exterior:
            muros.append(Muro(ADIABATICOS["muros"], az, round(m.area_bruta, 4), None, None, None,
                              etiqueta=m.nombre, area_bruta=round(m.area_bruta, 4)))
            continue
        tipo = ab["muro_ficticio"] if m.muro_ficticio else ab["muro"]
        con_p04 = m.p04 > 0
        muros.append(Muro(
            tipo, az, round(m.area_neta, 4), round(m.p01, 4), round(m.p02, 4), round(m.p03, 4),
            p04=round(m.p04, 4) if con_p04 else None,
            p04_elemento=cfg["p04"]["elemento"] if con_p04 else "",
            p04_aislacion=aislacion_p04(f, cfg) if con_p04 else "",
            etiqueta=m.nombre, area_bruta=round(m.area_bruta, 4),
            area_vanos=round(m.ventana.area, 4) if m.ventana else 0.0))
        if m.ventana:
            ventanas.append(Ventana(
                tipo=ab["vidrios"][m.nombre], azimut=az, elemento=tipo,
                cierre=v["cierre"], posicion=v["posicion"],
                alto=round(m.ventana.alto, 4), ancho=round(m.ventana.ancho, 4),
                fav=fav_ficha(m.fav), muro=m.nombre))

    area = round(res.area_piso, 4)
    dens = cfg["densidad"]
    if r.techo == "exterior":
        pt = pers.get("techo") or {}
        techo = Horizontal("techo", "Techo 1", ab["techo"], pt.get("densidad", dens),
                           pt.get("cubierta", cfg["techo"]["cubierta"]), area,
                           pt.get("camaras", cfg["techo"]["camaras_aire"]))
    else:
        techo = Horizontal("techo", "Techo 1", ADIABATICOS["techos"], dens, "", area, None)
    if r.piso == "adiabatico":
        piso = Horizontal("piso", "Piso 1", ADIABATICOS["pisos"], dens, "", area, None)
    else:
        pp = pers.get("piso") or {}
        piso = Horizontal("piso", "Piso 1", ab["piso"], pp.get("densidad", dens),
                          cfg["pisos_tipo"][r.piso], area, None)

    ficha = Ficha(
        unidad=unidad, piso=1, plantilla="iterador", dormitorios=r.dormitorios,
        perimetro_terreno=round(res.perimetro_terreno, 4) if r.piso == "terreno" else None,
        niveles=[Nivel(area, r.altura)], horizontales=[techo, piso],
        muros=muros, ventanas=ventanas)
    proyecto = {normalizar(k): val for k, val in portada(r, zona, cfg).items()}
    proyecto[CLAVE_CATALOGO] = filas
    proyecto[CLAVE_AZIMUT_FAR] = {}
    ficha.paquetes = calcular_paquetes(ficha, proyecto)
    return ficha, proyecto
