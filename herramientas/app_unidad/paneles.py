# -*- coding: utf-8 -*-
"""
Caja Envolvente (la de los componentes, a la izquierda) y tablas de la caja
Detalles modelo.

La caja es un arbol con todos los componentes de la unidad (al estilo de
DesignBuilder), en grupos separados por una linea: muros (por nivel si hay
varios), ventanas, puertas, techos, pisos, obstrucciones y contexto.
  - Un clic en el titulo de un grupo despliega su solucion GENERAL (la que usan
    todos los elementos del grupo que estan en "General", que es como parten) y el
    boton "Sobrescribir todos", que vuelve a la general los que tienen una propia.
  - Un clic en un elemento despliega su configuracion debajo de su fila: el modo
    (General, Cumple norma / Listado, Personalizado) y sus datos. Cambiar la
    general no toca los elementos con solucion propia. Otro clic la cierra.
  - Ventanas y puertas muestran sus medidas editables (ancho, alto, distancia al
    inicio del muro y antepecho): es lo mismo que arrastrar sus bordes en el alzado.
  - Obstrucciones: las dibujadas (horizontales y verticales; su detalle esta en
    obstaculos_ui.py) y las detectadas en el dibujo (unidad/obstrucciones.py): los
    voladizos del nivel de arriba (FAV1: L, D y cobertura) y la autosombra de los
    rincones entrantes de una unidad en L (FAV2: P, S y el muro que hace sombra),
    con su estado (se usa, manda la proteccion propia, manda otra, no cubre lo
    minimo). El criterio esta en config/cev.yaml (obstrucciones:), no en la interfaz.
  - Contexto (contexto_ui.py): los volumenes del entorno (FAR dibujado); un clic en
    uno despliega su nombre, altura y ubicacion desde la unidad. Lo que entra a la
    ficha (la tabla FAR por orientacion) esta en la caja Detalles modelo.
Lo que se elige en el dibujo (3D, planta, alzado o contexto) se abre igual en el
arbol, y la caja se desplaza hasta la fila solo si quedo fuera de la vista
(componentes.lista.desplazar). Lo desplegado aparece con una animacion
(estilo.css, --arbol-despliegue). Vertices, cortes, tabiques y perimetros
abiertos se muestran arriba del arbol.

Textos (config/editor.yaml): uno vacio ("" o null) no se muestra. Las
explicaciones (lista.titulo, general.ayuda, alzado_sin_seleccion, como_cerrar,
condicion_compartida, general.particulares, obstrucciones.ayuda) van en el
tooltip de su fila o boton o como texto gris, segun interfaz.ayudas (piezas.py).
Los textos de las obstrucciones detectadas tienen valores por defecto (TX_OBS); se
cambian con una seccion obstrucciones: en editor.yaml (mismas claves). Los del
contexto, en vista_contexto.textos (contexto_ui.TX).

No tienen estado propio, salvo E.st["general"] (el grupo cuya general esta
abierta), E.st["obs"] (la obstruccion detectada abierta: clave_obs) y E.st["_obs"]
(las obstrucciones detectadas): reciben E, el contexto del editor que arma app.py
(st, cfg, P = piezas, y las acciones aplicar, suprimir, ir_a, borrar, elegir_muro,
elegir_hz, elegir_obstaculo, deseleccionar...).
La logica esta en herramientas/unidad (editor, componentes, generales,
obstrucciones, protecciones, resumen, exportar, contexto, contexto_far).
"""
from __future__ import annotations

import math
from dataclasses import replace
from functools import partial

from nicegui import ui

from herramientas.recinto import catalogo, envolvente, zonas
from herramientas.recinto.a_ficha import cargar_config as cargar_ficha01
from herramientas.recinto.vista import rumbo
from herramientas.unidad import (cev, editor, exportar, generales, geometria, modelo, obstrucciones, protecciones,
                                 vista_alzado)
from herramientas.unidad import componentes as co

from . import contexto_ui, obstaculos_ui
from .campos import campos
from .piezas import num

NUEVO = "__nuevo__"
CONDICIONES_PISO = ("terreno", "ventilado")
DETECTADAS = ("voladizo", "autosombra")         # obstrucciones que salen del dibujo (no se dibujan)
TX_OBS = {
    "grupo": "Obstrucciones",
    "ayuda": "Lo que hace sombra a las ventanas: las obstrucciones dibujadas (horizontal = FAV1, vertical = "
             "FAV2), los voladizos del nivel de arriba (FAV1, alero) y la autosombra de los rincones de una "
             "unidad en L (FAV2: el muro propio que sale hacia afuera).",
    "tipos": {"voladizo": "Voladizo N{nivel}", "autosombra": "Autosombra {muro}"},
    "usada": "FAV1",
    "usada_fav2": "FAV2 {lado}",
    "lados": {"izq": "izq.", "der": "der."},
    "no_usada": "no se considera",
    "otra": "manda otra",
    "manual": "alero propio",
    "manual_fav2": "aleta propia",
    "ventana": "Ventana",
    "l": "L · saliente",
    "d": "D · sobre la ventana",
    "p": "P · saliente",
    "s": "S · separación",
    "origen": "Muro que hace sombra",
    "cobertura": "Cubre la ventana",
    "estado_usada": "Se declara como el FAV1 de la ventana.",
    "estado_usada_fav2": "Se declara como el FAV2 {lado} de la ventana.",
    "estado_otra": "Otra obstrucción más cercana manda en ese FAV.",
    "estado_no_usada": "Cubre menos del mínimo ({min} % de la ventana): no se considera.",
    "estado_manual": "La ventana tiene un alero propio: manda el alero.",
    "estado_manual_fav2": "La ventana tiene su propia aleta de ese lado: manda la aleta.",
    "ir": "Ir a la ventana",
}
# Lleva la fila elegida cerca del borde superior de la caja, solo si quedo fuera de la
# zona visible de arriba (id, fraccion de la altura, margen px, espera ms)
DESPLAZAR = ("setTimeout(()=>{const e=document.getElementById('c%d');if(!e)return;"
             "const c=e.closest('.toolbox');if(!c)return;"
             "const y=e.getBoundingClientRect().top-c.getBoundingClientRect().top;"
             "if(y<0||y>c.clientHeight*%s){c.scrollTo({top:c.scrollTop+y-%d,behavior:'smooth'});}},%d)")


def soluciones(u):
    """Soluciones de la zona de la unidad (None si la comuna o la zona no estan definidas)."""
    try:
        return envolvente.soluciones(zonas.zona_de(u.comuna, u.zona))
    except (ValueError, KeyError):
        return None


def _tx_obs(E) -> dict:
    extra = E.cfg.get("obstrucciones") or {}
    t = {**TX_OBS, **extra}
    for c in ("tipos", "lados"):
        t[c] = {**TX_OBS[c], **(extra.get(c) or {})}
    return t


def _norma(E, s) -> None:
    """Composicion y U de la solucion de la zona."""
    cc = E.cfg["componentes"]
    E.P.nota(" + ".join(f"{c.material} {c.espesor * 1000:.0f} mm" for c in s.capas))
    maximo = f" · máx. {num(s.u_max)}" if s.u_max is not None else ""
    E.P.dato(cc["u"], f"{num(s.u, 3)}{maximo}")


def _sin_general(modos: dict) -> dict:
    return {k: v for k, v in modos.items() if k != "general"}


# ==================================================================== soluciones generales
def describir(E, cat: str) -> str:
    """Texto corto de la solucion general de una categoria (generales.CATEGORIAS)."""
    u = E.st["u"]
    gc = E.cfg["componentes"]["general"]
    v = generales.valor(u, cat)
    if isinstance(v, dict):
        uu = v.get("u")
        return (v.get("nombre") or gc.get("personalizado") or "") + (
            f" · U {num(uu)}" if isinstance(uu, (int, float)) else "")
    if cat == "vidrio":
        return catalogo.vidrio(v)["nombre"] if v in catalogo.vidrios() else str(v)
    if cat == "puerta":
        t = cev.cargar_config()["puertas"]["tipos"].get(v)
        return t["texto"] if t else str(v)
    norma = gc.get("norma") or ""
    s = soluciones(u)
    if s is not None and cat != "piso_terreno":
        return f"{norma} · U {num(s[cat].u)}" if norma else f"U {num(s[cat].u)}"
    return norma


def _conds_piso(E) -> list:
    g = E.st["g"]
    hay = {h.condicion for h in (g.horizontales if g else ()) if h.destino == "piso"}
    return [c for c in CONDICIONES_PISO if c in hay]


def describir_grupo(E, grupo: str) -> str:
    if grupo == "ventana":
        return describir(E, "vidrio")
    if grupo == "piso":
        nombres = E.cfg["componentes"]["general"].get("condiciones") or {}
        partes = [f"{nombres.get(c, c)}: {describir(E, f'piso_{c}')}" for c in _conds_piso(E)]
        return " · ".join(partes) or E.cfg["envolvente"]["textos"]["sin_dato"]
    return describir(E, grupo)


def _lista_vidrios(E, actual, elegir) -> None:
    """Tipo de vidrio (grupos de recinto/datos/vidrios.yaml) y luego el vidrio."""
    P, cc = E.P, E.cfg["componentes"]
    grupos = catalogo.grupos()
    actual = actual if actual in catalogo.vidrios() else None
    grupo = catalogo.vidrio(actual)["grupo"] if actual else next(iter(grupos))
    P.selector(cc["vidrio_grupo"], {x: x for x in grupos}, grupo, lambda v: elegir(grupos[v][0]))
    P.selector(cc["vidrio_lista"], {c: catalogo.etiqueta_vidrio(c) for c in grupos[grupo]},
               actual if actual in grupos[grupo] else None, elegir)


def _lista_puertas(E, actual, elegir) -> None:
    pc = cev.cargar_config()["puertas"]
    E.P.selector(E.cfg["componentes"]["puerta_lista"], {t: d["texto"] for t, d in pc["tipos"].items()},
                 actual if actual in pc["tipos"] else pc["defecto"], elegir)


def _general_opaco(E, cat: str, piso: str) -> None:
    """Cumple norma | Personalizado de un muro, techo o piso general."""
    u, cc = E.st["u"], E.cfg["componentes"]
    modo = generales.modo(u, cat)
    E.P.segmentado(_sin_general(cc["modos_solucion"]), modo,
                   lambda v: E.aplicar(generales.poner, cat, v, soluciones(E.st["u"])))
    if modo == "personalizado":
        campos("piso" if cat.startswith("piso") else cat, generales.valor(u, cat),
               lambda c, v: E.aplicar(generales.editar, cat, c, v, _paneles=False),
               piso=piso, debounce=E.cfg["debounce_ms"])
        return
    s = soluciones(u)
    if s is not None:
        _norma(E, s[cat])


def general(E, grupo: str) -> None:
    """Solucion general de un grupo y Sobrescribir todos."""
    st, P = E.st, E.P
    cc = E.cfg["componentes"]
    gc = cc["general"]
    u = st["u"]
    P.explicacion((gc.get("ayuda") or {}).get(grupo))
    if grupo == "muro":
        _general_opaco(E, "muro", u.piso)
    elif grupo == "techo":
        _general_opaco(E, "techo", "exterior")
    elif grupo == "piso":
        conds = _conds_piso(E)
        if not conds:
            P.nota(gc.get("sin_pisos"))
        for c in conds:
            P.subtitulo((gc.get("condiciones") or {}).get(c, c))
            _general_opaco(E, f"piso_{c}", c)
    elif grupo == "ventana":
        modo = generales.modo(u, "vidrio")
        P.segmentado(_sin_general(cc["modos_lista"]), modo, lambda v: E.aplicar(generales.poner, "vidrio", v))
        if modo == "personalizado":
            campos("vidrio", generales.valor(u, "vidrio"),
                   lambda c, v: E.aplicar(generales.editar, "vidrio", c, v, _paneles=False),
                   debounce=E.cfg["debounce_ms"])
        else:
            _lista_vidrios(E, generales.valor(u, "vidrio"),
                           lambda cod: E.aplicar(generales.poner, "vidrio", "listado", None, cod))
    else:
        modo = generales.modo(u, "puerta")
        P.segmentado(_sin_general(cc["modos_lista"]), modo, lambda v: E.aplicar(generales.poner, "puerta", v))
        if modo == "personalizado":
            campos("puerta", generales.valor(u, "puerta"),
                   lambda c, v: E.aplicar(generales.editar, "puerta", c, v, _paneles=False),
                   debounce=E.cfg["debounce_ms"])
        else:
            _lista_puertas(E, generales.valor(u, "puerta"),
                           lambda t: E.aplicar(generales.poner, "puerta", "listado", None, t))
    n = generales.particulares(u, grupo, st["g"])
    estado = (gc.get("particulares") or "").format(n=n) if n else gc.get("sin_particulares")
    with ui.element("div").classes("acciones"):
        P.accion(gc.get("sobrescribir") or "Sobrescribir todos", lambda: E.aplicar(generales.sobrescribir, grupo),
                 peligro=True, ayuda=estado)
    P.explicacion(estado)


def abrir_general(E, grupo: str) -> None:
    """Abre (o cierra) la solucion general del grupo; deja de elegir lo que hubiera."""
    E.st["general"] = None if E.st.get("general") == grupo else grupo
    E.st["obs"] = None
    E.deseleccionar()


def _usa_general(E, cat: str) -> None:
    t = E.cfg["componentes"]["general"].get("usa")
    E.P.nota(t.format(desc=describir(E, cat)) if t else None)


# ==================================================================== obstrucciones detectadas
def clave_obs(o) -> tuple:
    """Identifica una obstruccion detectada en el arbol (una ventana puede tener varias)."""
    return (o.tipo, o.pano, o.ventana, o.lado)


def abrir_obstruccion(E, clave) -> None:
    E.st["obs"] = None if E.st.get("obs") == clave else clave
    E.st["general"] = None
    E.deseleccionar()


def _estado_obs(o, to: dict) -> str:
    """Texto corto del estado (fila del arbol)."""
    fav2 = o.fav == 2
    if o.manual:
        return to["manual_fav2" if fav2 else "manual"]
    if o.usada:
        return to["usada_fav2"].format(lado=to["lados"].get(o.lado, o.lado)) if fav2 else to["usada"]
    return to["otra"] if o.aplica else to["no_usada"]


def obstruccion(E, o) -> None:
    """Datos de una obstruccion detectada (voladizo o autosombra) y un boton para ir a su ventana."""
    P, to = E.P, _tx_obs(E)
    lc = E.cfg["componentes"]["lista"]
    minimo = obstrucciones.config()["cobertura_min"]
    fav2 = o.fav == 2
    P.dato(to["ventana"], lc["ventana"].format(muro=o.muro, n=o.ventana + 1))
    if fav2:
        if o.origen:
            P.dato(to["origen"], o.origen)
        P.dato(to["p"], f"{num(o.l)} m")
        P.dato(to["s"], f"{num(o.d)} m")
    else:
        P.dato(to["l"], f"{num(o.l)} m")
        P.dato(to["d"], f"{num(o.d)} m")
    P.dato(to["cobertura"], f"{num(o.cobertura * 100, 0)} %")
    lado = to["lados"].get(o.lado, o.lado or "")
    if o.manual:
        P.nota(to["estado_manual_fav2" if fav2 else "estado_manual"])
    elif o.usada:
        P.nota(to["estado_usada_fav2"].format(lado=lado) if fav2 else to["estado_usada"])
    elif o.aplica:
        P.nota(to["estado_otra"])
    else:
        P.nota((to["estado_no_usada"] or "").format(min=num(minimo * 100, 0)))
    g = E.st["g"]
    if g is not None and o.pano < len(g.panos):
        x = g.panos[o.pano]
        with ui.element("div").classes("acciones"):
            P.accion(to["ir"], lambda: E.elegir_muro(x.nivel, x.lado, x.tramo, ("ventana", o.ventana)))


def _nota_obstruccion(E, k, i, j, m) -> None:
    """En la ventana elegida: todo lo que le hace sombra (detectado y dibujado)."""
    g = E.st["g"]
    if g is None:
        return
    x = next((p for p in g.panos if (p.nivel, p.lado, p.tramo) == (k, i, j)), None)
    mias = [o for o in E.st.get("_obs") or () if x is not None and o.clave == (x.indice, m)]
    if not mias:
        return
    E.P.subtitulo(_tx_obs(E).get("grupo"))
    for o in mias:
        E.P.nota(obstrucciones.avisos([o])[0].split(": ", 1)[-1])


# ==================================================================== arbol
def arbol(E) -> None:
    """Muros | ventanas | puertas | techos | pisos | obstrucciones | contexto; lo elegido se
    despliega en su fila."""
    st, P = E.st, E.P
    lc = E.cfg["componentes"]["lista"]
    gc = E.cfg["componentes"]["general"]
    cond = E.cfg["etiquetas"]["condicion"]
    tx_env = E.cfg["envolvente"]["textos"]
    g = st["g"]
    if g is None:
        st["_obs"] = []
        P.nota(E.cfg["textos"].get("sin_seleccion"))
        return
    try:
        obs = obstrucciones.detectar(st["u"], g)
    except Exception as ex:                       # la deteccion no debe impedir ver el arbol
        print(f"Obstrucciones: {type(ex).__name__}: {ex}", flush=True)
        obs = []
    st["_obs"] = obs
    detectadas = [o for o in obs if o.tipo in DETECTADAS]
    ma, va, hz, oa = E.muro_activo(), E.vano_activo(), E.hz_activa(), E.obstaculo_activo()
    ci = contexto_ui.activo(E)
    if ma is not None or hz is not None or oa is not None or ci is not None:
        st["general"], st["obs"] = None, None
    if st.get("obs") is not None and not any(clave_obs(o) == st["obs"] for o in detectadas):
        st["obs"] = None
    abierta, obs_abierta = st.get("general"), st.get("obs")
    clave_sel = (ma, va, hz, oa, ci, abierta, obs_abierta)
    nuevo = clave_sel != st.get("_arbol")          # recien elegido: se anima y se desplaza
    st["_arbol"] = clave_sel
    if all(x is None for x in (ma, hz, oa, ci, abierta, obs_abierta)):
        P.explicacion(lc.get("titulo"))
    elegida = {"fila": None}

    def fila(nombre, detalle, accion, activa=False, padre=False):
        el = ui.element("div").classes("item-lista" + (" activo" if activa else "") + (" padre" if padre else ""))
        with el:
            ui.label(nombre).classes("item-nombre")
            ui.label(detalle).classes("item-detalle")
        el.on("click", accion)
        if activa:
            elegida["fila"] = el

    def desplegar(panel):
        with ui.element("div").classes("detalle-item" + (" abre" if nuevo else "")):
            panel()

    def cabecera(grupo, primero=False):
        if not primero:
            ui.element("div").classes("divisor")
        act = abierta == grupo
        el = ui.element("div").classes("item-lista grupo" + (" activo" if act else ""))
        with el:
            ui.label(lc["grupos"][grupo]).classes("grupo-nombre")
            ui.label(describir_grupo(E, grupo)).classes("item-detalle")
            P.ayuda_explicativa((gc.get("ayuda") or {}).get(grupo))
        el.on("click", partial(abrir_general, E, grupo))
        if act:
            elegida["fila"] = el
            desplegar(lambda: general(E, grupo))

    def vacio(lista):
        if not lista:
            P.nota(lc.get("vacio"), "subnivel")

    propio = f" · {lc['propio']}" if lc.get("propio") else ""

    # ---------------------------------------------------------------- muros
    cabecera("muro", primero=True)
    varios = len(st["u"].niveles) > 1
    previo = None
    vents, puerts = [], []
    for x in g.panos:
        if varios and x.nivel != previo:
            P.nota(lc["nivel"].format(nivel=x.nivel + 1) if lc.get("nivel") else None, "subnivel")
            previo = x.nivel
        clave = (x.nivel, x.lado, x.tramo)
        act = ma == clave and va is None and hz is None
        sol = ""
        if x.exterior and x.solucion != modelo.GENERAL:
            sol = (lc.get("norma") or "") if x.solucion == modelo.DEFECTO else \
                (st["u"].muros_personalizados.get(x.solucion) or {}).get("nombre", x.solucion)
            sol = f" · {sol}" if sol else ""
        detalle = f"{x.azimut:.0f}° {rumbo(x.azimut)} · {cond.get(x.condicion, x.condicion)}{sol}"
        if (x.ventanas or x.puertas) and lc.get("vanos"):
            detalle += f" · {lc['vanos'].format(v=len(x.ventanas), p=len(x.puertas))}"
        fila(x.id, detalle, E.deseleccionar if act else partial(E.elegir_muro, *clave), activa=act,
             padre=ma == clave and va is not None)
        if act:
            desplegar(lambda: muro(E, E.sel_valida(), E.nivel(), st["k"], titulo=False))
        vents += [(x, v.indice, v) for v in x.ventanas]
        puerts += [(x, m, p) for m, p in enumerate(x.puertas)]

    # ---------------------------------------------------------------- ventanas
    cabecera("ventana")
    vacio(vents)
    for x, m, v in vents:
        clave = (x.nivel, x.lado, x.tramo)
        act = va == ("ventana", *clave, m)
        w = v.datos
        marca = propio if (w.vidrio_personalizado or w.vidrio != modelo.GENERAL) else ""
        fila(lc["ventana"].format(muro=x.id, n=m + 1), f"{num(v.ancho)} × {num(v.alto)} m · {rumbo(x.azimut)}{marca}",
             E.deseleccionar if act else partial(E.elegir_muro, *clave, ("ventana", m)), activa=act)
        if act:
            desplegar(lambda: ventana(E, titulo=False))

    # ---------------------------------------------------------------- puertas
    cabecera("puerta")
    vacio(puerts)
    for x, m, p in puerts:
        clave = (x.nivel, x.lado, x.tramo)
        act = va == ("puerta", *clave, m)
        marca = propio if (p.personalizada or p.tipo != modelo.GENERAL) else ""
        fila(lc["puerta"].format(muro=x.id, n=m + 1), f"{num(p.ancho)} × {num(p.alto)} m · {rumbo(x.azimut)}{marca}",
             E.deseleccionar if act else partial(E.elegir_muro, *clave, ("puerta", m)), activa=act)
        if act:
            desplegar(lambda: puerta(E, titulo=False))

    # ---------------------------------------------------------------- techos y pisos
    destinos, cond_h = tx_env["destinos"], tx_env["condiciones"]
    for destino in ("techo", "piso"):
        cabecera(destino)
        for h in (h for h in g.horizontales if h.destino == destino):
            act = hz == (h.destino, h.nivel)
            marca = propio if (h.condicion != "adiabatico"
                               and modelo.estado_horizontal(st["u"], h.destino, h.nivel) != "general") else ""
            fila(f"{destinos.get(h.destino, h.destino)} N{h.nivel + 1}",
                 f"{cond_h.get(h.condicion, h.condicion)} · {num(h.area)} m²{marca}",
                 E.deseleccionar if act else partial(E.elegir_hz, h.destino, h.nivel), activa=act)
            if act:
                desplegar(lambda: superficie(E, titulo=False))

    # ---------------------------------------------------------------- obstrucciones
    to = _tx_obs(E)
    total = obstaculos_ui.cuantas(st["u"]) + len(detectadas)
    ui.element("div").classes("divisor")
    with ui.element("div").classes("item-lista grupo"):
        ui.label(lc["grupos"].get("obstruccion") or to["grupo"]).classes("grupo-nombre")
        ui.label(str(total) if total else "").classes("item-detalle")
        P.ayuda_explicativa(to.get("ayuda"))
    vacio(total)
    obstaculos_ui.filas(E, fila, desplegar, obs)
    for o in detectadas:
        clave = clave_obs(o)
        act = obs_abierta == clave
        nombre = to["tipos"].get(o.tipo, o.tipo).format(nivel=o.nivel + 1, muro=o.origen or "")
        medida = f"P {num(o.l)} · S {num(o.d)}" if o.fav == 2 else \
            f"L {num(o.l)} · {num(o.cobertura * 100, 0)} %"
        detalle = f"{lc['ventana'].format(muro=o.muro, n=o.ventana + 1)} · {medida} · {_estado_obs(o, to)}"
        fila(nombre, detalle, partial(abrir_obstruccion, E, clave), activa=act)
        if act:
            desplegar(lambda o=o: obstruccion(E, o))

    # ---------------------------------------------------------------- contexto (FAR dibujado)
    tc = contexto_ui.textos(E.cfg)
    ui.element("div").classes("divisor")
    with ui.element("div").classes("item-lista grupo"):
        ui.label(lc["grupos"].get("contexto") or tc["grupo"]).classes("grupo-nombre")
        ui.label(contexto_ui.resumen(E)).classes("item-detalle")
        P.ayuda_explicativa(tc.get("grupo_ayuda"))
    contexto_ui.filas(E, fila, desplegar)

    # lo recien elegido (tambien desde el dibujo) queda a la vista
    dz = lc.get("desplazar")
    if elegida["fila"] is not None and nuevo and dz:
        try:
            ui.run_javascript(DESPLAZAR % (elegida["fila"].id, float(dz.get("zona", 0.4)),
                                           int(dz.get("margen_px", 8)), int(dz.get("espera_ms", 380))))
        except Exception:
            pass


# ==================================================================== techo o piso
def _solucion_horizontal(E, destino, nivel, condicion) -> None:
    """General | Cumple norma | Personalizado del techo o piso de ese nivel."""
    u, cc = E.st["u"], E.cfg["componentes"]
    estado = modelo.estado_horizontal(u, destino, nivel)
    cat = "techo" if destino == "techo" else f"piso_{condicion}"
    E.P.subtitulo(cc.get(destino))
    E.P.segmentado(cc["modos_solucion"], estado,
                   lambda v: E.aplicar(co.superficie, destino, nivel, v, soluciones(E.st["u"])))
    if estado == "personalizado":
        campos(destino, modelo.personalizado_horizontal(u, destino, nivel),
               lambda c, v: E.aplicar(co.editar_superficie, destino, nivel, c, v, _paneles=False),
               piso=condicion, debounce=E.cfg["debounce_ms"])
    elif estado == "general":
        _usa_general(E, cat)
    else:
        s = soluciones(u)
        if s is not None:
            _norma(E, s[cat])


def superficie(E, titulo: bool = True) -> None:
    st, P = E.st, E.P
    cc, et, tx = E.cfg["componentes"], E.cfg["etiquetas"], E.cfg["textos"]
    destino, k = E.hz_activa()
    u, g = st["u"], st["g"]
    hz = next((h for h in g.horizontales if (h.destino, h.nivel) == (destino, k)), None) if g else None
    if hz is None:
        return
    principal = modelo.es_principal(u, destino, k)
    campo = destino if principal else f"{destino}_expuesto"
    if titulo:
        ui.label(cc["titulos"][campo].format(nivel=k + 1)).classes("titulo-componente")
    compartida = None if principal else cc.get("condicion_compartida")
    P.selector(cc["condicion"], et[campo], getattr(u, campo),
               lambda v: E.aplicar(lambda x: replace(x, **{campo: v})), ayuda=compartida)
    P.explicacion(compartida)
    if hz.condicion != "adiabatico":
        _solucion_horizontal(E, destino, k, hz.condicion)
    P.subtitulo(tx.get("resumen"))
    P.dato("Área", f"{num(hz.area)} m²")
    if hz.perimetro:
        P.dato("Perímetro contra terreno", f"{num(hz.perimetro)} m")


# ==================================================================== muro
def _solucion_muro(E, k, i, j, tramo) -> None:
    u, P, cc = E.st["u"], E.P, E.cfg["componentes"]
    P.subtitulo(cc.get("muro"))
    modo = "general" if tramo.solucion == modelo.GENERAL else (
        "norma" if tramo.solucion == modelo.DEFECTO else "personalizado")
    P.segmentado(cc["modos_solucion"], modo,
                 lambda v: E.aplicar(co.solucion_muro, k, i, j, v, soluciones(E.st["u"])))
    if modo == "general":
        _usa_general(E, "muro")
        return
    if modo == "norma":
        s = soluciones(u)
        if s is not None:
            _norma(E, s["muro"])
        return
    clave = tramo.solucion
    ops = {c: d.get("nombre") or c for c, d in u.muros_personalizados.items()}
    ops[NUEVO] = cc["nuevo_muro"]

    def elegir(v):
        if v == NUEVO:
            E.aplicar(lambda x: co.solucion_muro(co.solucion_muro(x, k, i, j, "norma"), k, i, j,
                                                 "personalizado", soluciones(x)))
        else:
            E.aplicar(co.asignar_muro, k, i, j, v)

    P.selector(cc["muro_usar"], ops, clave, elegir)
    usan = sum(1 for n in u.niveles for l in n.lados for t in l.tramos if t.exterior and t.solucion == clave)
    if usan > 1 and cc.get("muro_compartido"):
        P.nota(cc["muro_compartido"].format(n=usan))
    campos("muro", u.muros_personalizados[clave],
           lambda c, v: E.aplicar(co.editar_muro, clave, c, v, _paneles=False),
           piso=u.piso, debounce=E.cfg["debounce_ms"])


def muro(E, t, n, k, titulo: bool = True) -> None:
    """Condicion, solucion constructiva y al final el resumen."""
    st, P = E.st, E.P
    et, tx = E.cfg["etiquetas"], E.cfg["textos"]
    if t is None or n is None:
        return
    lado = n.lados[t.lado]
    tramo = lado.tramos[t.tramo]
    lim = editor.limites(n, t.lado)
    ini, fin = vista_alzado.nombres_extremos(n, t.lado, t.tramo)
    a, b = editor.extremos(n, t.lado)
    ux, uy, _ = editor.direccion(a, b)
    az = geometria.normalizar_azimut(st["u"].azimut_y + math.degrees(math.atan2(-uy, ux)))
    pano = None
    if st["g"] is not None:
        pano = next((x for x in st["g"].panos if (x.nivel, x.lado, x.tramo) == (k, t.lado, t.tramo)), None)
    if titulo:
        ui.label(f"Muro {vista_alzado.nombre_muro(n, k, t.lado, t.tramo)}").classes("titulo-componente")
    if st["modo"] == "alzado":
        P.explicacion(tx.get("alzado_sin_seleccion"))
    P.segmentado(et["condicion"], tramo.condicion,
                 lambda v: E.aplicar(editor.cambiar_tramo, k, t.lado, t.tramo, condicion=v))
    if len(lado.tramos) > 1:
        with ui.element("div").classes("acciones"):
            P.accion("Todo el lado igual", lambda: E.aplicar(editor.cambiar_lado, k, t.lado,
                                                             condicion=tramo.condicion, solucion=tramo.solucion))
    if tramo.exterior:
        _solucion_muro(E, k, t.lado, t.tramo, tramo)
    P.subtitulo(tx.get("resumen"))
    P.dato("Extremos", f"{ini} → {fin}")
    P.dato("Largo", f"{num(lim[t.tramo + 1] - lim[t.tramo])} m")
    P.dato("Orientación", f"{az:.0f}° {rumbo(az)}")
    if pano is not None:
        P.dato("Área bruta", f"{num(pano.area_bruta)} m²")
        P.dato("Área neta", f"{num(pano.area_neta - pano.area_puertas)} m²")
    P.dato("Vanos", f"{len(tramo.ventanas)} ventanas · {len(tramo.puertas)} puertas")
    if st["modo"] == "alzado":
        with ui.element("div").classes("acciones"):
            P.accion("Volver a la planta", lambda: E.ir_a("planta"))


# ==================================================================== vanos
def _acciones_vano(E, texto) -> None:
    with ui.element("div").classes("acciones"):
        if E.st["modo"] == "alzado":
            E.P.accion("Volver a la planta", lambda: E.ir_a("planta"))
        E.P.accion(texto, E.suprimir, peligro=True)


def _medidas(E, tipo, k, i, j, m, w, ini) -> None:
    """Ancho, alto, distancia al inicio del muro y (ventanas) antepecho, editables."""
    P = E.P
    md = E.cfg["textos"].get("medidas") or {}
    if not isinstance(md, dict):
        md = {"titulo": md}

    def campo(etiqueta, clave, valor):
        P.numero(etiqueta, valor,
                 lambda v: E.aplicar(editor.redimensionar_vano, k, i, j, tipo, m, _paneles=False, **{clave: float(v)}),
                 0.0, None, 0.05)

    P.subtitulo(md.get("titulo", "Medidas"))
    with ui.row().classes("w-full no-wrap gap-2"):
        campo(md.get("ancho", "Ancho [m]"), "ancho", w.ancho)
        campo(md.get("alto", "Alto [m]"), "alto", w.alto)
    with ui.row().classes("w-full no-wrap gap-2"):
        campo(md.get("distancia", "Desde {inicio} [m]").format(inicio=ini), "x", w.x)
        if tipo == "ventana":
            campo(md.get("antepecho", "Antepecho [m]"), "z", w.antepecho)
    P.dato("Área", f"{num(w.ancho * w.alto)} m²")


def _vidrio(E, k, i, j, m, w) -> None:
    """General, listado (tipo y luego vidrio) o personalizado."""
    cc = E.cfg["componentes"]
    modo = "personalizado" if w.vidrio_personalizado else ("general" if w.vidrio == modelo.GENERAL else "listado")
    E.P.subtitulo(cc.get("vidrio"))
    E.P.segmentado(cc["modos_lista"], modo, lambda v: E.aplicar(co.vidrio, k, i, j, m, v))
    if modo == "personalizado":
        campos("vidrio", w.vidrio_personalizado,
               lambda c, v: E.aplicar(co.editar_vidrio, k, i, j, m, c, v, _paneles=False),
               debounce=E.cfg["debounce_ms"])
    elif modo == "general":
        _usa_general(E, "vidrio")
    else:
        _lista_vidrios(E, w.vidrio, lambda cod: E.aplicar(co.vidrio, k, i, j, m, "listado", cod))


def ventana(E, titulo: bool = True) -> None:
    """Vidrio, obstrucciones que le hacen sombra, protecciones solares y al final las medidas."""
    st, P = E.st, E.P
    pcfg = E.cfg["protecciones"]
    p04 = cargar_ficha01()["p04"]
    _, k, i, j, m = E.vano_activo()
    n = st["u"].niveles[k]
    w = n.lados[i].tramos[j].ventanas[m]
    pr = w.proteccion
    ini, _ = vista_alzado.nombres_extremos(n, i, j)
    cp = pcfg["campos"]

    def cambio(**c):
        E.aplicar(protecciones.cambiar, k, i, j, m, _paneles=False, **c)

    def campo(etiqueta, clave, valor, minimo=0.0, maximo=None, paso=0.05, fmt="%.2f"):
        P.numero(etiqueta, valor, lambda v: cambio(**{clave: float(v)}), minimo, maximo, paso, fmt)

    if titulo:
        ui.label(f"Ventana {m + 1} · muro {vista_alzado.nombre_muro(n, k, i, j)}").classes("titulo-componente")
    _vidrio(E, k, i, j, m, w)
    _nota_obstruccion(E, k, i, j, m)
    P.subtitulo(pcfg.get("titulo"))
    activas = protecciones.activas(pr)
    (ui.select(pcfg["etiquetas"], multiple=True, value=activas, label=pcfg["seleccionar"],
               on_change=lambda e: E.aplicar(protecciones.con_tipos, k, i, j, m, e.value or [], pcfg["defecto"]))
     .props("dense use-chips options-dense").classes("w-full"))
    if "alero" in activas:
        P.subtitulo(pcfg["etiquetas"]["alero"])
        with ui.row().classes("w-full no-wrap gap-2"):
            campo(cp["alero_l"], "alero_l", pr.alero_l, 0.01)
            campo(cp["alero_d"], "alero_d", pr.alero_d or 0.0)
    for lado in ("izq", "der"):
        if f"aleta_{lado}" in activas:
            P.subtitulo(pcfg["etiquetas"][f"aleta_{lado}"])
            with ui.row().classes("w-full no-wrap gap-2"):
                campo(cp["aleta_p"], f"aleta_{lado}_p", getattr(pr, f"aleta_{lado}_p"), 0.01)
                campo(cp["aleta_s"], f"aleta_{lado}_s", protecciones.separacion(pr, lado))
    if "celosia" in activas:
        P.subtitulo(pcfg["etiquetas"]["celosia"])
        P.segmentado(pcfg["orientacion"], pr.celosia_orientacion,
                     lambda v: E.aplicar(protecciones.cambiar, k, i, j, m, celosia_orientacion=v,
                                         celosia_beta=max(min(pr.celosia_beta, 90.0), 0.0)
                                         if v == "horizontal" else pr.celosia_beta))
        horizontal = pr.celosia_orientacion == "horizontal"
        with ui.row().classes("w-full no-wrap gap-2"):
            campo(cp["celosia_e"], "celosia_e", pr.celosia_e, 0.01, None, 0.01)
            campo(cp["celosia_t"], "celosia_t", pr.celosia_t, 0.01, None, 0.01)
            campo(cp["angulo_horizontal" if horizontal else "angulo_vertical"], "celosia_beta",
                  pr.celosia_beta, 0.0 if horizontal else -90.0, 90.0, 5, "%.0f")
    if {"alero", "aleta_izq", "aleta_der"} & set(activas):
        P.selector(cp["p04"], p04["aislaciones"], pr.p04_aislacion or p04["aislacion_defecto"],
                   lambda v: cambio(p04_aislacion=v))
    _medidas(E, "ventana", k, i, j, m, w, ini)
    _acciones_vano(E, "Eliminar ventana")


def puerta(E, titulo: bool = True) -> None:
    """Tipo de puerta (general, listado de la ficha o personalizada) y las medidas."""
    st, P = E.st, E.P
    cc = E.cfg["componentes"]
    _, k, i, j, m = E.vano_activo()
    n = st["u"].niveles[k]
    p = n.lados[i].tramos[j].puertas[m]
    ini, _ = vista_alzado.nombres_extremos(n, i, j)
    if titulo:
        ui.label(f"Puerta {m + 1} · muro {vista_alzado.nombre_muro(n, k, i, j)}").classes("titulo-componente")
    modo = "personalizado" if p.personalizada else ("general" if p.tipo == modelo.GENERAL else "listado")
    P.subtitulo(cc.get("puerta"))
    P.segmentado(cc["modos_lista"], modo, lambda v: E.aplicar(co.puerta, k, i, j, m, v))
    if modo == "personalizado":
        campos("puerta", p.personalizada,
               lambda c, v: E.aplicar(co.editar_puerta, k, i, j, m, c, v, _paneles=False),
               debounce=E.cfg["debounce_ms"])
    elif modo == "general":
        _usa_general(E, "puerta")
    else:
        _lista_puertas(E, p.tipo, lambda v: E.aplicar(co.puerta, k, i, j, m, "listado", v))
    _medidas(E, "puerta", k, i, j, m, p, ini)
    _acciones_vano(E, "Eliminar puerta")


# ==================================================================== otros
def abierto(E) -> None:
    b = E.abierto()
    if not b:
        return
    P = E.P
    como = E.cfg["textos"].get("como_cerrar")
    ui.label(f"Perímetro abierto · nivel {E.st['k'] + 1} · {len(b)} puntos").classes("titulo-componente")
    P.explicacion(como)
    with ui.element("div").classes("acciones"):
        if len(b) >= 3:
            P.accion("Cerrar perímetro", E.cerrar_abierto, ayuda=como)
        P.accion("Descartar", E.descartar_abierto, peligro=True)


def _punto(E, t, n, k) -> None:
    """Vertice, corte o tabique elegido en la planta (arriba del arbol)."""
    P = E.P
    with ui.element("div").classes("detalle-suelto"):
        if t.tipo == "vertice":
            p = n.vertices[t.indice]
            ui.label(f"Vértice V{t.indice + 1} · nivel {k + 1}").classes("titulo-componente")
            P.dato("x ; y", f"{num(p[0])} ; {num(p[1])} m")
            with ui.element("div").classes("acciones"):
                P.accion("Eliminar vértice", lambda: E.borrar(t), peligro=True)
        elif t.tipo == "corte":
            ui.label(f"Corte {t.indice + 1} del lado L{t.lado + 1} · nivel {k + 1}").classes("titulo-componente")
            P.dato(f"Distancia desde V{t.lado + 1}", f"{num(n.lados[t.lado].cortes[t.indice])} m")
            with ui.element("div").classes("acciones"):
                P.accion("Quitar corte (unir tramos)", lambda: E.borrar(t))
        else:
            tb = n.tabiques[t.indice]
            ui.label(f"Tabique {t.indice + 1} · nivel {k + 1}").classes("titulo-componente")
            P.dato("Largo", f"{num(editor.distancia(tb.a, tb.b))} m")
            with ui.element("div").classes("acciones"):
                P.accion("Eliminar tabique", lambda: E.borrar(t), peligro=True)


def propiedades(E) -> None:
    """Contenido de la caja: lo suelto (perimetro abierto, vertice, corte, tabique)
    arriba y el arbol de componentes debajo (las obstrucciones y el contexto se abren en el
    arbol)."""
    abierto(E)
    t, n = E.sel_valida(), E.nivel()
    if t is not None and n is not None and t.tipo in ("vertice", "corte", "tabique"):
        _punto(E, t, n, E.st["k"])
    arbol(E)


# ==================================================================== caja Detalles modelo
def envolvente_tablas(E, tablas: dict) -> None:
    """Una tabla por grupo con filas (resumen.tablas), con las columnas de envolvente.tablas."""
    for titulo, cab, filas, nums in exportar.secciones(tablas, E.cfg["envolvente"]):
        E.P.subtitulo(titulo)
        cols = [{"name": f"c{i}", "label": c, "field": f"c{i}", "align": "right" if n else "left"}
                for i, (c, n) in enumerate(zip(cab, nums))]
        rows = [dict({f"c{i}": v for i, v in enumerate(f)}, _k=r) for r, f in enumerate(filas)]
        (ui.table(columns=cols, rows=rows, row_key="_k", pagination=0)
         .props("dense flat hide-bottom").classes("w-full tabla"))
