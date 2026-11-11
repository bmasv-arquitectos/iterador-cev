# -*- coding: utf-8 -*-
"""
Tablas de la envolvente de una unidad, sin interfaz: muros (con sus puentes),
techos y pisos (cada superficie horizontal, tambien las del descalce entre
niveles), ventanas y puertas. Las usa la caja Detalles modelo del editor y el
reporte; las columnas que se muestran y sus decimales estan en config/editor.yaml
(envolvente.tablas) y los textos en envolvente.textos.

Las soluciones generales se resuelven antes (generales.resolver) y se aplican las
obstrucciones (obstrucciones.aplicar): cada fila muestra lo que de verdad usa el
calculo. Una ventana con FAV de una obstruccion lo indica en Protecciones
(envolvente.textos.obstruccion_fav1 / obstruccion_fav2); el P04 de cada muro suma
el de sus ventanas y el de las obstrucciones dibujadas que se apoyan en el.
Cada fila es un dict con numeros sin formatear (None = no aplica). U: el de la
solucion (norma de la zona o personalizada); el piso contra terreno no lleva U
porque lo calcula la ficha (NCh3117), y el de las puertas de fabrica es el
efectivo de la ficha (config/cev.yaml).
"""
from __future__ import annotations

from herramientas.recinto import catalogo, envolvente, zonas
from herramientas.recinto.vista import rumbo

from . import cev, generales, obstrucciones, protecciones
from .modelo import DEFECTO, Unidad, personalizado_horizontal


def soluciones(u: Unidad):
    try:
        return envolvente.soluciones(zonas.zona_de(u.comuna, u.zona))
    except (ValueError, KeyError):
        return None


def _az(a: float) -> str:
    return f"{a:.0f}° {rumbo(a)}"


def muros(u: Unidad, g, tx: dict, sols=None, p04_pano: dict | None = None) -> list:
    cond = tx.get("condiciones") or {}
    pt = cev.puentes(u, g)
    p04_pano = p04_pano or {}
    out = []
    for x in g.panos:
        p = pt[x.indice]
        if not x.exterior:
            sol, uu = tx.get("sin_dato", "—"), None
        elif x.solucion == DEFECTO:
            sol, uu = tx.get("norma", "Norma"), sols["muro"].u if sols else None
        else:
            d = u.muros_personalizados.get(x.solucion) or {}
            sol, uu = d.get("nombre") or x.solucion, d.get("u")
        out.append({"id": x.id, "az": _az(x.azimut), "cond": cond.get(x.condicion, x.condicion),
                    "solucion": sol, "u": uu, "largo": x.largo, "bruta": x.area_bruta,
                    "neta": x.area_neta - x.area_puertas, "p01": p["p01"], "p02": p["p02"], "p03": p["p03"],
                    "p04": sum(cev.largo_p04(cev.fav_ventana(v), v) for v in x.ventanas)
                           + p04_pano.get(x.indice, 0.0)})
    return out


def horizontales(u: Unidad, g, tx: dict, sols=None) -> list:
    cond = tx.get("condiciones") or {}
    nombres = tx.get("destinos") or {}
    out = []
    for h in g.horizontales:
        d = None if h.condicion == "adiabatico" else personalizado_horizontal(u, h.destino, h.nivel)
        if h.condicion == "adiabatico":
            sol, uu = tx.get("sin_dato", "—"), None
        elif d:
            sol, uu = d.get("nombre"), d.get("u")
        else:
            clave = "techo" if h.destino == "techo" else f"piso_{h.condicion}"
            sol, uu = tx.get("norma", "Norma"), (sols[clave].u if sols else None)
        if h.condicion == "terreno":
            uu = None
        out.append({"id": f"{nombres.get(h.destino, h.destino)} N{h.nivel + 1}", "destino": h.destino,
                    "nivel": h.nivel, "cond": cond.get(h.condicion, h.condicion), "solucion": sol, "u": uu,
                    "area": h.area, "perimetro": h.perimetro or None})
    return out


def ventanas(g, tx: dict, etiquetas_proteccion: dict | None = None) -> list:
    ep = etiquetas_proteccion or {}
    out = []
    for x in g.panos:
        for v in x.ventanas:
            w = v.datos
            if w.vidrio_personalizado:
                d = w.vidrio_personalizado
                nombre, uu, fs = d.get("nombre"), d.get("u"), d.get("fs")
            elif w.vidrio in catalogo.vidrios():
                d = catalogo.vidrio(w.vidrio)
                nombre, uu, fs = d["nombre"], d["u"], d["fs"]
            else:
                nombre, uu, fs = tx.get("sin_dato", "—"), None, None
            pr = w.proteccion
            prot = [ep.get(a, a) for a in protecciones.activas(pr)]
            if v.fav1_obstruccion and not pr.alero_l > 0:
                prot.append(tx.get("obstruccion_fav1") or "Obstrucción (FAV1)")
            f2 = v.fav2_obstruccion or (None, None)
            if (f2[0] and not pr.aleta_izq_p > 0) or (f2[1] and not pr.aleta_der_p > 0):
                prot.append(tx.get("obstruccion_fav2") or "Obstrucción (FAV2)")
            out.append({"id": f"{x.id}-V{v.indice + 1}", "muro": x.id, "az": _az(x.azimut), "ancho": v.ancho,
                        "alto": v.alto, "area": v.area, "vidrio": nombre, "u": uu, "fs": fs,
                        "protecciones": ", ".join(prot) or tx.get("sin_dato", "—")})
    return out


def puertas(g, tx: dict) -> list:
    pc = cev.cargar_config()["puertas"]
    out = []
    for x in g.panos:
        for n, p in enumerate(x.puertas):
            if p.personalizada:
                nombre, uu = p.personalizada.get("nombre"), p.personalizada.get("u")
            else:
                tipo = p.tipo or pc["defecto"]
                nombre, uu = tipo, (pc["tipos"].get(tipo) or {}).get("u")
            out.append({"id": f"{x.id}-P{n + 1}", "muro": x.id, "az": _az(x.azimut), "ancho": p.ancho,
                        "alto": p.alto, "area": p.ancho * p.alto, "tipo": nombre, "u": uu})
    return out


def tablas(u: Unidad, g, cfg: dict) -> dict:
    """{muros, horizontales, ventanas, puertas}. cfg: config/editor.yaml."""
    tx = (cfg.get("envolvente") or {}).get("textos") or {}
    sols = soluciones(u)
    ep = (cfg.get("protecciones") or {}).get("etiquetas") or {}
    ru, rg = generales.resolver(u, g)
    rg = obstrucciones.aplicar(ru, rg)
    p04_pano = {}
    for q in obstrucciones.p04(ru, rg):
        p04_pano[q.pano] = p04_pano.get(q.pano, 0.0) + q.largo
    return {"muros": muros(ru, rg, tx, sols, p04_pano), "horizontales": horizontales(ru, rg, tx, sols),
            "ventanas": ventanas(rg, tx, ep), "puertas": puertas(rg, tx)}
