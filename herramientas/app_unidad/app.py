# -*- coding: utf-8 -*-
"""
Iterador CEV: editor de la unidad. Ejecutar: python -m herramientas.app_unidad

El dibujo ocupa toda la ventana: Planta del nivel activo, Alzado del muro elegido o
Contexto (SVG sobre ui.interactive_image), o el modelo 3D (ui.scene, vista3d_ui.py).
Arriba a la izquierda: rotulo, deshacer, archivo, herramientas y niveles; arriba a la
derecha: modo del 3D, Mostrar FAR, vistas, navegacion y el boton del panel de
resultados. Izquierda: cajas Unidad y Envolvente (arbol de componentes, paneles.py).
Derecha: Resultados (calculo_ui.py) y Detalles modelo (tablas, tabla FAR y los botones
CSV y Ficha 01, que entrega la ficha 01 oficial llenada: unidad/ficha01.py).

Herramientas: Seleccionar, Mover (vertices, muros en paralelo, cortes, tabiques,
obstrucciones y, en el alzado, vanos; Ctrl + clic en un muro crea un vertice), Dibujar
muro, Dibujar tabique, Obstruccion horizontal y vertical y Balcon (polilinea en el piso
del nivel, solo P04; obstaculos_ui.py), Dibujar ventana y puerta (en el alzado de un
muro exterior), Cortar y Borrar.
Con Mover, la obstruccion elegida muestra asas (unidad/edicion_obstaculos.py): el
rectangulo se estira por sus esquinas y bordes, la vertical por sus extremos y el
balcon por sus vertices; arrastrar el cuerpo la mueve entera. El tabique elegido
muestra asas en sus extremos (unidad/edicion_tabiques.py); su cuerpo lo mueve entero.
Los tabiques tambien se eligen en el 3D (elegir_tabique); su detalle (con Eliminar)
aparece arriba del arbol y Supr lo borra.
Vista Contexto (contexto_ui.py): volumenes del entorno para el FAR dibujado, con la
unidad solo como referencia y cotas desde sus caras exteriores; herramientas Volumen
rectangular y Volumen poligonal (ortogonales), Seleccionar, Mover (asas) y Borrar. El
volumen elegido (st["sel_ctx"], tambien desde el 3D) se edita en su fila del arbol.
Mostrar FAR (contexto_ui.boton_far / alternar_far): en la vista Contexto prende o apaga
el dibujo del FAR (parte con la fachada de arriba; un clic en una fachada cambia la
orientacion, st["far_o"]); en las otras vistas aparece con un muro con FAR elegido y
lleva a la vista Contexto con el FAR de ese muro.
Doble clic: en un muro abre su alzado; en una ventana o puerta, el alzado con ella
elegida y Mover; en una obstruccion o un tabique (3D o planta), la planta de su nivel
con el elegido y Mover; dibujando un balcon, lo cierra. Rueda = zoom; boton de la rueda
= desplazar; Shift apaga el ajuste; Esc cancela o deja de elegir; Supr borra lo elegido.

Apariencia: estilo.css; textos y comportamiento: config/editor.yaml (se releen con
F5). La logica esta en herramientas/unidad; aqui solo se conectan eventos.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from nicegui import app, events, run, ui

from herramientas.recinto import zonas
from herramientas.unidad import (edicion_obstaculos, edicion_tabiques, editor, exportar, ficha01, geometria, inicial,
                                 modelo, reporte, resumen, vista_alzado, vista_contexto, vista_planta)

from . import calculo_ui, contexto_ui, obstaculos_ui, paneles, vista3d_ui
from .piezas import ICONOS, Piezas, descargar_bytes, num
from .scripts import CLIC_SIN_ARRASTRE, SIN_AUTOSCROLL, VENTANA_JS, superficie_losa  # noqa: F401

CARPETA = Path(__file__).parent
ESTILO = CARPETA / "estilo.css"
MODELOS = Path(editor.__file__).parent / "modelos"
VANOS = ("ventana", "puerta")
DIBUJO_PLANTA = ("dibujar", "tabique", "cortar", *obstaculos_ui.TIPOS)   # herramientas que dibujan en planta
AYUDA_VISTA = {"planta": "ayuda_planta", "alzado": "ayuda_alzado", "contexto": "ayuda_contexto",
               "3d": "ayuda_3d"}                                         # claves de textos:
VISTAS = ("planta", "alzado", "contexto", "3d")
VISTA_DE = {"alzado": "vista_alz", "contexto": "vista_ctx"}              # el resto usa st["vista"]


async def pagina(cfg: dict) -> None:
    geo_cfg = geometria.cargar_config()
    est, e3, cap, lz, snap = cfg["planta"], cfg["modelo3d"], cfg["captura"], cfg["lienzo"], cfg["snap"]
    alz, hcfg, bt, icfg = cfg["alzado"], cfg["herramientas"], cfg["botones"], cfg["interfaz"]
    tx = cfg["textos"]
    esp = vista_alzado.espejo(alz)
    dim = {"w": lz["ancho_px"], "h": lz["alto_px"], "medida": False}
    u0 = inicial.unidad(cfg)
    st = {"u": u0, "ab": {}, "k": 0, "herr": cfg["herramienta_inicial"], "cursor": None, "tabique": None,
          "sel": None, "sel_vano": None, "sel_hz": None, "sel_ctx": None, "arrastre": None, "arr_alz": None,
          "esq": None, "previa": None, "g": None, "camara": True, "raton": None, "pan": None, "ctx": False,
          "modo": "3d" if cfg.get("vista_inicial") == "3d" else "planta", "vista": None, "vista_alz": None,
          "vista_ctx": None, "render": e3.get("render_defecto", "lineas"),
          "techos": bool(e3.get("techos_visibles", True)), "ultima": None, "tablas": {}, "css": None,
          "asa_obs": None, "far_o": None, "balcon": None, "snap": None}
    pila = {"atras": [], "adelante": []}
    v3 = None                                      # vista3d_ui.Vista3D (se crea con el layout)
    calc = {"panel": None}
    cajas = {}
    der = {"visible": bool(icfg.get("resultados_visible", True))}
    comunas = sorted(zonas.cargar(), key=zonas._norm)
    P = Piezas(cfg)
    boton, grupo, numero, selector, accion = P.boton, P.grupo, P.numero, P.selector, P.accion
    et = cfg["etiquetas"]

    # ================================================================ estado
    def doc():
        return st["u"], tuple(sorted((k, tuple(v)) for k, v in st["ab"].items() if v))

    def restaurar(d):
        st["u"], st["ab"] = d[0], {k: list(v) for k, v in d[1]}

    def n_vista():
        return max(len(st["u"].niveles), max(st["ab"], default=-1) + 1, 1)

    def actual():
        return st["previa"] or st["u"]

    def nivel():
        u = actual()
        return u.niveles[st["k"]] if st["k"] < len(u.niveles) else None

    def abierto():
        return st["ab"].get(st["k"], [])

    def sel_valida():
        t, n = st["sel"], nivel()
        if t is None:
            return None
        if t.tipo == "punto":
            return t if t.indice < len(abierto()) else None
        if n is None:
            return None
        if t.tipo == "vertice":
            return t if t.indice < len(n.vertices) else None
        if t.tipo == "tabique":
            return t if t.indice < len(n.tabiques) else None
        if t.tipo == "obstaculo":
            return t if t.indice < len(n.obstaculos) else None
        if not 0 <= t.lado < len(n.lados):
            return None
        lado = n.lados[t.lado]
        if t.tipo == "tramo":
            return t if t.tramo < len(lado.tramos) else None
        return t if t.indice < len(lado.cortes) else None

    def muro_activo():
        t = sel_valida()
        return (st["k"], t.lado, t.tramo) if t is not None and t.tipo == "tramo" else None

    def obstaculo_activo():
        """(nivel, indice) de la obstruccion dibujada elegida, o None."""
        t = sel_valida()
        return (st["k"], t.indice) if t is not None and t.tipo == "obstaculo" else None

    def tramo_activo():
        ma = muro_activo()
        return actual().niveles[ma[0]].lados[ma[1]].tramos[ma[2]] if ma else None

    def vano_valido():
        t, sv = tramo_activo(), st["sel_vano"]
        if t is None or sv is None:
            return None
        return sv if sv[1] < len(getattr(t, editor.CAMPOS[sv[0]])) else None

    def vano_activo():
        """(tipo, k, i, j, m) de la ventana o puerta elegida, o None."""
        ma, sv = muro_activo(), vano_valido()
        return (sv[0], *ma, sv[1]) if ma and sv else None

    def hz_valida():
        """(destino, nivel) del techo o piso elegido, si todavia existe."""
        h, g = st["sel_hz"], st["g"]
        if h is None or g is None:
            return None
        return h if any((x.destino, x.nivel) == h for x in g.horizontales) else None

    def hay_eleccion():
        return any(x is not None for x in (st["sel"], st["sel_vano"], st["sel_hz"], st["sel_ctx"]))

    def confirmar(nueva=None, abiertos=None, paneles_=True):
        antes = doc()
        if nueva is not None:
            st["u"] = nueva
        if abiertos is not None:
            st["ab"] = {k: list(v) for k, v in abiertos.items() if v}
        st["previa"] = None
        if doc() == antes:
            refrescar_lienzo()
            return
        pila["atras"].append(antes)
        del pila["atras"][:-cfg["deshacer_max"]]
        pila["adelante"].clear()
        st["k"] = min(st["k"], n_vista() - 1)
        st["sel"] = sel_valida()
        st["sel_vano"] = vano_valido()
        contexto()
        refrescar(paneles_)

    def aplicar(f, *args, _paneles=True, **kw) -> bool:
        try:
            nueva = f(st["u"], *args, **kw)
        except ValueError as ex:
            ui.notify(str(ex), type="warning")
            refrescar_lienzo()
            return False
        confirmar(nueva, paneles_=_paneles)
        return True

    def cambiar(paneles_=False, **kw):
        if all(getattr(st["u"], c) == v for c, v in kw.items()):
            return
        aplicar(lambda u: replace(u, **kw), _paneles=paneles_)

    def mover_historial(desde, hacia):
        if not pila[desde]:
            return
        pila[hacia].append(doc())
        restaurar(pila[desde].pop())
        st["k"] = min(st["k"], n_vista() - 1)
        st.update(cursor=None, tabique=None, arrastre=None, arr_alz=None, previa=None, esq=None, balcon=None,
                  snap=None)
        st["sel"] = sel_valida()
        st["sel_vano"] = vano_valido()
        contexto()
        refrescar()

    def deshacer():
        mover_historial("atras", "adelante")

    def rehacer():
        mover_historial("adelante", "atras")

    def cancelar():
        st.update(cursor=None, tabique=None, arrastre=None, arr_alz=None, previa=None, esq=None, balcon=None,
                  snap=None)
        refrescar_lienzo()

    # ================================================================ elegir
    def elegir_muro(k, i, j, vano=None):
        """Elige el muro (k, i, j) y, si se indica, una de sus ventanas o puertas (tipo, m)."""
        n = st["u"].niveles[k]
        lim = editor.limites(n, i)
        s = (lim[j] + lim[j + 1]) / 2
        otro = muro_activo() != (k, i, j)
        st["k"] = k
        st["sel"] = editor.Toque("tramo", lado=i, tramo=j, s=s, punto=editor.punto_en(n, i, s))
        st["sel_vano"], st["sel_hz"], st["sel_ctx"] = vano, None, None
        if otro and st["modo"] == "alzado":
            st["vista_alz"] = encuadre_alzado()
        contexto()
        refrescar()

    def elegir_hz(destino, k):
        st["k"] = min(k, max(len(st["u"].niveles) - 1, 0))
        st["sel"], st["sel_vano"], st["sel_hz"], st["sel_ctx"] = None, None, (destino, k), None
        if st["modo"] == "alzado":
            ir_a("planta")
        contexto()
        refrescar()

    def elegir_obstaculo(k, t):
        n = st["u"].niveles[k]
        if not 0 <= t < len(n.obstaculos):
            return
        st["k"] = k
        st["sel"] = editor.Toque("obstaculo", indice=t, punto=n.obstaculos[t].a)
        st["sel_vano"], st["sel_hz"], st["sel_ctx"] = None, None, None
        if st["modo"] == "alzado":
            ir_a("planta")
        contexto()
        refrescar()

    def editar_obstaculo(k, t):
        """La obstruccion elegida, en la planta de su nivel y con Mover (sus asas)."""
        elegir_obstaculo(k, t)
        if st["modo"] != "planta":
            ir_a("planta")
        poner_herramienta("mover")
        refrescar_lienzo()

    def elegir_tabique(k, t, editar=False):
        """Elige el tabique t del nivel k (desde el 3D); editar: la planta de su nivel con Mover
        (las asas de sus extremos)."""
        n = st["u"].niveles[k]
        if not 0 <= t < len(n.tabiques):
            return
        st["k"] = k
        st["sel"] = editor.Toque("tabique", indice=t, punto=n.tabiques[t].a)
        st["sel_vano"], st["sel_hz"], st["sel_ctx"] = None, None, None
        if st["modo"] == "alzado" or (editar and st["modo"] != "planta"):
            ir_a("planta")
        if editar:
            poner_herramienta("mover")
        contexto()
        refrescar()

    def deseleccionar():
        st["sel"], st["sel_vano"], st["sel_hz"], st["sel_ctx"] = None, None, None, None
        if st["modo"] == "alzado":
            ir_a("planta")
        contexto()
        propiedades.refresh()
        refrescar_lienzo()
        dibujar_3d()

    def refrescar_seleccion():
        """Despues de cambiar lo elegido sin cambiar la unidad (contexto_ui, vista3d_ui)."""
        contexto()
        propiedades.refresh()
        refrescar_lienzo()
        dibujar_3d()

    def abrir_alzado(editar=False):
        """Alzado del muro elegido; editar: con la herramienta Mover (el vano elegido muestra sus asas)."""
        if tramo_activo() is None:
            return
        ir_a("alzado")
        if editar:
            poner_herramienta("mover")
        refrescar_lienzo()

    def doble_clic(p):
        """Planta: un muro abre su alzado; una obstruccion queda elegida con Mover.
        Alzado: una ventana o puerta queda elegida con Mover."""
        r = metros(cap["radio_px"])
        if st["modo"] == "alzado":
            ma = muro_activo()
            if ma is None:
                return
            k, i, j = ma
            n = st["u"].niveles[k]
            s, z = vista_alzado.desde_mundo(p, editor.largo_tramo(n, i, j), esp)
            hit = vista_alzado.tocar_vano(n.lados[i].tramos[j], s, z, r / 2)
            if hit is not None:
                st["sel_vano"], st["esq"] = hit, None
                poner_herramienta("mover")
                propiedades.refresh()
                refrescar_lienzo()
            return
        n = nivel()
        if n is None:
            return
        t = editor.tocar(n, p, r, ("tramo",))
        if t is not None:
            elegir_muro(st["k"], t.lado, t.tramo)
            abrir_alzado()
            return
        t = editor.tocar(n, p, r, ("obstaculo",))
        if t is not None:
            editar_obstaculo(st["k"], t.indice)

    # ================================================================ herramientas
    def visibles():
        cc = cfg["contexto"]
        if st["modo"] == "contexto":
            return cc.get("en_contexto") or list(contexto_ui.VISIBLES)
        return cc["con_muro" if muro_activo() is not None else "sin_muro"]

    def actualizar_estado():
        """Barra de estado (solo con interfaz.ayudas: texto): ayuda de la herramienta y de la vista."""
        for lbl, t in ((lbl_estado_herr, hcfg[st["herr"]].get("ayuda")), (lbl_estado_vista, tx.get(AYUDA_VISTA[st["modo"]]))):
            lbl.set_text(t or "")
            lbl.set_visibility(bool(t))

    def poner_cursor(css):
        if css != st["css"]:
            st["css"] = css
            img.style(f"cursor: {css}")

    def poner_herramienta(h):
        st["herr"] = h
        st.update(esq=None, cursor=None, tabique=None, balcon=None, snap=None)
        poner_cursor(hcfg[h]["cursor"])
        actualizar_estado()
        barra_herr.refresh()

    def contexto():
        con = muro_activo() is not None
        if st["herr"] not in visibles():
            poner_herramienta("seleccionar")
        if con != st["ctx"]:
            st["ctx"] = con
            barra_herr.refresh()
        o = contexto_ui.orientacion_muro(E)        # otro muro con FAR elegido: su orientacion
        if o and st["far_o"]:
            st["far_o"] = o
        if contexto_ui.boton_far(E) != st.get("_far_boton"):
            vistas_ui.refresh()

    def elegir_herramienta(h):
        if h == st["herr"]:
            return
        if h in VANOS:
            t = tramo_activo()
            if t is None or not t.exterior:
                ui.notify(tx["elige_muro"] if t is None else tx["solo_exterior"], type="warning")
                return
            poner_herramienta(h)
            ir_a("alzado")
            refrescar_lienzo()
            return
        poner_herramienta(h)
        if h in DIBUJO_PLANTA and st["modo"] != "planta":
            ir_a("planta")
        elif h in contexto_ui.HERRAMIENTAS and st["modo"] != "contexto":
            ir_a("contexto")
        refrescar_lienzo()

    @ui.refreshable
    def barra_herr():
        with grupo():
            for h in visibles():
                boton(h, hcfg[h]["texto"], partial(elegir_herramienta, h), activo=h == st["herr"],
                      detalle=hcfg[h].get("ayuda"))

    # ================================================================ vistas y tamano
    def lienzo():
        return dict(lz, ancho_px=dim["w"], alto_px=dim["h"])

    def encuadre_planta(u=None):
        u = u or st["u"]
        v = vista_planta.encuadrar_unidad(u, lienzo(), [p for pts in st["ab"].values() for p in pts])
        return v.desplazar(*lz.get("centro_px", (0, 0)))

    def encuadre_contexto(u=None):
        """Vista Contexto: la unidad y todos los volumenes del entorno."""
        v = vista_contexto.encuadre(u or st["u"], lienzo())
        return v.desplazar(*lz.get("centro_px", (0, 0)))

    def encuadre_alzado():
        k, i, j = muro_activo()
        n = st["u"].niveles[k]
        v = vista_alzado.encuadrar_alzado(editor.largo_tramo(n, i, j), st["u"].altura, lienzo(), alz)
        return v.desplazar(*lz.get("centro_px", (0, 0)))

    def vista_activa():
        return st[VISTA_DE.get(st["modo"], "vista")]

    def poner_vista(v):
        st[VISTA_DE.get(st["modo"], "vista")] = v

    def redimensionar(w, h):
        w, h = int(w or 0), int(h or 0)
        if w < 200 or h < 200 or (dim["medida"] and (w, h) == (dim["w"], dim["h"])):
            return
        primera = not dim["medida"]
        dim.update(w=w, h=h, medida=True)
        img.set_source(vista_planta.fuente_vacia(w, h, est["fondo"]))
        if primera:
            st["vista"] = encuadre_planta()
            if st["vista_ctx"] is not None:
                st["vista_ctx"] = encuadre_contexto()
        else:
            st["vista"] = st["vista"].redimensionar(w, h)
            for clave in VISTA_DE.values():
                if st[clave] is not None:
                    st[clave] = st[clave].redimensionar(w, h)
        if st["modo"] == "3d":
            v3.crear()
        else:
            refrescar_lienzo()

    def al_ventana(e):
        a = e.args[0] if isinstance(e.args, list) and e.args else e.args
        if isinstance(a, dict):
            redimensionar(a.get("w"), a.get("h"))

    def mostrar_vista():
        en_3d = st["modo"] == "3d"
        img.set_visibility(not en_3d)
        cont3d.set_visibility(en_3d)
        actualizar_estado()

    def ir_a(modo):
        previo = st["modo"]
        if modo == previo:
            return
        st["modo"] = modo
        st.update(raton=None, pan=None, arrastre=None, arr_alz=None, previa=None, esq=None, cursor=None)
        if modo == "alzado":
            st["vista_alz"] = encuadre_alzado()
            st["sel_vano"] = vano_valido()
        elif modo == "planta":
            st["sel_vano"] = None
        elif modo == "contexto":
            st["sel_vano"] = None
            if st["vista_ctx"] is None:
                st["vista_ctx"] = encuadre_contexto()
        if modo != "alzado" and st["herr"] in VANOS:
            poner_herramienta("seleccionar")
        if st["herr"] not in visibles():
            poner_herramienta("seleccionar")
        if previo == "3d":
            v3.quitar()
        mostrar_vista()
        vistas_ui.refresh()
        barra_herr.refresh()
        if modo == "3d":
            v3.crear()
        else:
            refrescar_lienzo()
        propiedades.refresh()

    def cambiar_vista(modo):
        if modo == st["modo"]:
            return
        if modo == "alzado" and muro_activo() is None:
            ui.notify(tx["elige_muro"], type="warning")
            return
        ir_a(modo)

    def cambiar_render(r):
        if r == st["render"]:
            return
        st["render"] = r
        vistas_ui.refresh()
        dibujar_3d()

    def alternar_techos():
        st["techos"] = not st["techos"]
        vistas_ui.refresh()
        dibujar_3d()

    def encuadrar():
        if st["modo"] == "3d":
            v3.encuadrar()
            return
        if st["modo"] == "alzado":
            st["vista_alz"] = encuadre_alzado()
        elif st["modo"] == "contexto":
            st["vista_ctx"] = encuadre_contexto()
        else:
            st["vista"] = encuadre_planta()
        refrescar_lienzo()

    def zoom(f):
        if st["modo"] == "3d":
            return
        v = vista_activa()
        poner_vista(v.zoom_en(f, v.centro(), lz["escala_min"], lz["escala_max"]))
        refrescar_lienzo()

    def al_rueda(e):
        a = e.args if isinstance(e.args, dict) else {}
        dy = a.get("deltaY") or 0
        if not dy or st["modo"] == "3d":
            return
        f = lz["zoom_rueda"] if dy < 0 else 1 / lz["zoom_rueda"]
        v = vista_activa()
        poner_vista(v.zoom_en(f, st["raton"] or v.centro(), lz["escala_min"], lz["escala_max"]))
        refrescar_lienzo()

    @ui.refreshable
    def vistas_ui():
        if st["modo"] == "3d":
            with grupo():
                for r in ("lineas", "solido"):
                    boton(r, bt[r], partial(cambiar_render, r), activo=st["render"] == r)
                boton("techos", bt["techos"], alternar_techos, activo=st["techos"])
        st["_far_boton"] = contexto_ui.boton_far(E)
        if st["_far_boton"]:
            # en la vista Contexto prende o apaga el FAR; en las otras lleva al Contexto con el del muro
            with grupo():
                boton("far", bt.get("far") or contexto_ui.textos(cfg)["far_boton"],
                      partial(contexto_ui.alternar_far, E), activo=st["modo"] == "contexto" and bool(st["far_o"]))
        with grupo():
            for m in VISTAS:
                boton(m, bt[m], partial(cambiar_vista, m), activo=st["modo"] == m, detalle=tx.get(AYUDA_VISTA[m]))

    # ================================================================ acciones
    def vaciar():
        st["k"], st["sel"], st["sel_vano"], st["sel_hz"] = 0, None, None, None
        confirmar(editor.vaciar(st["u"]), {})
        poner_herramienta("dibujar")

    def cargar_unidad(nueva):
        """Reemplaza la unidad (se puede deshacer) y encuadra."""
        st.update(k=0, sel=None, sel_vano=None, sel_hz=None, sel_ctx=None, camara=True, far_o=None)
        st["vista"] = encuadre_planta(nueva)
        st["vista_ctx"] = encuadre_contexto(nueva)
        cancelar()
        confirmar(nueva, {})
        poner_herramienta("seleccionar")
        if st["modo"] == "3d":
            v3.encuadrar()

    def caja_inicial():
        cargar_unidad(replace(st["u"], niveles=inicial.unidad(cfg).niveles))

    def cargar_modelo(archivo):
        try:
            nueva = modelo.cargar(MODELOS / archivo)
        except Exception as ex:
            ui.notify(f"No se pudo cargar {archivo}: {ex}", type="negative")
            return
        cargar_unidad(nueva)

    def opcion_cargar(op):
        if op.get("accion") == "inicial":
            caja_inicial()
        elif op.get("accion") == "json":
            subida.run_method("pickFiles")
        else:
            cargar_modelo(op["archivo"])

    def menu_cargar():
        with ui.menu():
            for op in cfg["cargar"].values():
                disponible = bool(op.get("accion")) or (op.get("archivo") and (MODELOS / op["archivo"]).is_file())
                if disponible:
                    ui.menu_item(op["texto"], partial(opcion_cargar, op))
                else:
                    ui.menu_item(f"{op['texto']} · {tx['proximamente']}").props("disable")

    def cerrar_abierto():
        k = st["k"]
        try:
            nueva = editor.con_perimetro(st["u"], k, editor.cerrar(abierto()))
        except ValueError as ex:
            ui.notify(str(ex), type="warning")
            refrescar_lienzo()
            return
        ab = dict(st["ab"])
        ab.pop(k, None)
        st["cursor"], st["sel"], st["camara"] = None, None, True
        confirmar(nueva, ab)
        poner_herramienta("seleccionar")

    def descartar_abierto():
        ab = dict(st["ab"])
        ab.pop(st["k"], None)
        st["sel"] = None
        confirmar(abiertos=ab)

    def borrar(t):
        if t is None:
            return
        st["sel"] = None
        k = st["k"]
        if t.tipo == "punto":
            pts = list(abierto())
            del pts[t.indice]
            confirmar(abiertos={**st["ab"], k: pts})
        elif t.tipo == "vertice":
            aplicar(editor.eliminar_vertice, k, t.indice)
        elif t.tipo == "corte":
            aplicar(editor.unir_tramos, k, t.lado, t.indice)
        elif t.tipo == "tabique":
            aplicar(editor.eliminar_tabique, k, t.indice)
        elif t.tipo == "obstaculo":
            aplicar(editor.eliminar_obstaculo, k, t.indice)
        elif t.tipo == "tramo":                   # muro: el perimetro queda abierto
            try:
                nueva, pts = editor.abrir_perimetro(st["u"], k, t.lado)
            except ValueError as ex:
                ui.notify(str(ex), type="warning")
                refrescar()
                return
            confirmar(nueva, {**st["ab"], k: list(pts)})
            if tx.get("abierto_al_borrar"):
                ui.notify(tx["abierto_al_borrar"])
            poner_herramienta("dibujar")

    def suprimir():
        if st["modo"] == "contexto":
            contexto_ui.suprimir(E)
            return
        sv, ma = vano_valido(), muro_activo()
        if sv is not None and ma is not None:
            st["sel_vano"] = None
            aplicar(editor.eliminar_vano, *ma, *sv)
        elif st["modo"] != "alzado" and st["sel_hz"] is None:
            borrar(sel_valida())

    def escape():
        if st["modo"] == "contexto" and contexto_ui.escape(E):
            return
        if any(st[c] is not None for c in ("esq", "tabique", "arrastre", "arr_alz", "balcon")):
            cancelar()
            return
        if st["sel_vano"] is not None or st["sel_hz"] is not None:
            st["sel_vano"], st["sel_hz"] = None, None
            propiedades.refresh()
            refrescar_lienzo()
            dibujar_3d()
            return
        if st["modo"] == "alzado":
            ir_a("planta")
            return
        deseleccionar()

    # ================================================================ raton
    def metros(px):
        return vista_activa().metros(px)

    def referencias():
        return [v for n in st["u"].niveles for v in n.vertices]

    def pan(tipo, x, y, boton_, botones) -> bool:
        if tipo == "mousedown" and boton_ == 1:
            st["pan"] = (x, y, vista_activa())
            img.style("cursor: grabbing")
            st["css"] = "grabbing"
            return True
        if st["pan"] is None:
            return False
        if tipo == "mouseup" or (botones is not None and not botones & 4):
            st["pan"] = None
            poner_cursor(hcfg[st["herr"]]["cursor"])
            return True
        x0, y0, v0 = st["pan"]
        poner_vista(v0.desplazar(x - x0, y - y0))
        refrescar_lienzo()
        return True

    def al_raton(e: events.MouseEventArguments):
        boton_ = getattr(e, "button", 0)
        if pan(e.type, e.image_x, e.image_y, boton_, getattr(e, "buttons", None)):
            return
        if e.type == "mousedown" and boton_ != 0:
            return
        p = vista_activa().mundo(e.image_x, e.image_y)
        st["raton"] = p
        libre = bool(getattr(e, "shift", False))
        if st["modo"] == "contexto":
            if e.type != "dblclick" or boton_ == 0:
                contexto_ui.raton(E, e.type, p, libre)
            return
        if e.type == "dblclick":
            if boton_ == 0 and st["modo"] == "planta" and st["herr"] == "balcon":
                obstaculos_ui.raton(E, "balcon", e.type, p, libre)       # cierra el balcon
            elif boton_ == 0:
                doble_clic(p)
            return
        if st["modo"] == "alzado":
            raton_alzado(e.type, p, libre)
            return
        h = st["herr"]
        if h == "dibujar":
            raton_dibujar(e.type, p, libre)
        elif h == "tabique":
            raton_tabique(e.type, p, libre)
        elif h in obstaculos_ui.TIPOS:
            obstaculos_ui.raton(E, h, e.type, p, libre)
        elif h == "mover":
            raton_mover(e.type, p, libre, bool(getattr(e, "ctrl", False)))
        elif e.type == "mousedown":
            if h == "seleccionar":
                seleccionar_en(p)
            else:
                raton_clic(h, p, libre)

    def seleccionar_en(p):
        n = nivel()
        st["sel"] = editor.tocar(n, p, metros(cap["radio_px"])) if n is not None else None
        st["sel_vano"], st["sel_hz"], st["sel_ctx"] = None, None, None
        contexto()
        propiedades.refresh()
        refrescar_lienzo()
        dibujar_3d()

    def raton_dibujar(tipo, p, libre):
        k, b = st["k"], abierto()
        r = metros(cap["radio_px"])
        if libre:
            q = editor.ajustar(p)
        elif b:
            q = editor.ajustar_desde(b[-1], p, alinear=b + referencias(), radio=metros(cap["alinear_px"]))
        else:
            q = editor.atraer(p, referencias(), r) or editor.ajustar(p, snap["largo_m"])
        st["cursor"] = q
        if tipo != "mousedown":
            refrescar_lienzo()
            return
        if len(b) >= 3 and editor.distancia(p, b[0]) <= metros(cap["cierre_px"]):
            cerrar_abierto()
            return
        if b and editor.distancia(q, b[-1]) <= 1e-6:
            return
        if k > len(st["u"].niveles):
            ui.notify(tx["nivel_abajo"], type="warning")
            return
        confirmar(abiertos={**st["ab"], k: b + [q]})

    def raton_tabique(tipo, p, libre):
        n = nivel()
        if n is None:
            return
        r = metros(cap["radio_px"])
        a = st["tabique"]
        if a is None:
            q = editor.ajustar(p) if libre else editor.proyectar_a_muro(n, editor.ajustar(p), r)
        else:
            q = editor.ajustar(p) if libre else editor.extender_a_muro(n, a, editor.ajustar_desde(a, p), r)
        st["cursor"] = q
        if tipo == "mousedown":
            if a is None:
                st["tabique"] = q
            elif aplicar(editor.agregar_tabique, st["k"], a, q):
                st["tabique"] = None
        refrescar_lienzo()

    def arrastrar(t, p0, p, libre):
        u, k = st["u"], st["k"]
        n = u.niveles[k]
        if t.tipo == "vertice":
            i, m = t.indice, len(n.vertices)
            if libre:
                q = editor.ajustar(p)
            else:
                vecinos = (n.vertices[i - 1], n.vertices[(i + 1) % m])
                otros = [v for kk, nn in enumerate(u.niveles) for j, v in enumerate(nn.vertices)
                         if not (kk == k and j in (i, (i - 1) % m, (i + 1) % m))]
                q = editor.ajustar_vertice(p, vecinos, otros, metros(cap["alinear_px"]))
            return editor.mover_vertice(u, k, i, q)
        if t.tipo == "tramo":
            nx, ny = editor.normal_exterior(n, t.lado)
            d = (p[0] - p0[0]) * nx + (p[1] - p0[1]) * ny
            return editor.mover_lado(u, k, t.lado, d if libre else editor.redondear(d, snap["largo_m"]))
        if t.tipo == "corte":
            a, b = editor.extremos(n, t.lado)
            ux, uy, _ = editor.direccion(a, b)
            s = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
            return editor.mover_corte(u, k, t.lado, t.indice, s if libre else editor.redondear(s, snap["largo_m"]))
        if t.tipo == "tabique":                   # t.tramo: extremo 0 (a), 1 (b) o -1 (el cuerpo)
            return edicion_tabiques.arrastrar(u, k, t.indice, t.tramo, p0, p, libre, snap["largo_m"],
                                              metros(cap["radio_px"]))
        if t.tipo == "obstaculo":
            dx, dy = p[0] - p0[0], p[1] - p0[1]
            if not libre:
                dx, dy = editor.redondear(dx, snap["largo_m"]), editor.redondear(dy, snap["largo_m"])
            return editor.mover_obstaculo(u, k, t.indice, dx, dy)
        if t.tipo == "asa":                       # asa de la obstruccion elegida
            return edicion_obstaculos.redimensionar(u, k, t.indice, st["asa_obs"], p, libre, snap["largo_m"],
                                                    metros(cap["alinear_px"]))
        return None

    def raton_mover(tipo, p, libre, ctrl):
        n = nivel()
        if n is None:
            return
        r = metros(cap["radio_px"])
        oa = obstaculo_activo()
        o_sel = n.obstaculos[oa[1]] if oa is not None else None
        if tipo == "mousedown":
            if o_sel is not None and not ctrl:
                asa = edicion_obstaculos.tocar_asa(o_sel, p, r)
                if asa is not None:
                    st["arrastre"] = (editor.Toque("asa", indice=oa[1], punto=p), p)
                    st["asa_obs"], st["previa"] = asa, None
                    return
            ts = sel_valida()
            if ts is not None and ts.tipo == "tabique" and not ctrl:     # los extremos del tabique elegido mandan
                ext = edicion_tabiques.tocar_extremo(n.tabiques[ts.indice], p, r)
                if ext is not None:
                    st["arrastre"], st["previa"] = (replace(ts, tramo=ext), p), None
                    return
            t = None
            if ctrl:
                t2 = editor.tocar(n, p, r, ("tramo",))
                if t2 is not None:
                    s = t2.s if libre else editor.redondear(t2.s, snap["largo_m"])
                    if aplicar(editor.insertar_vertice, st["k"], t2.lado, s):
                        i = t2.lado + 1
                        t = editor.Toque("vertice", indice=i, punto=st["u"].niveles[st["k"]].vertices[i])
            if t is None and o_sel is not None:      # la obstruccion elegida manda sobre el muro
                t2 = editor.tocar(n, p, r, ("obstaculo",))
                if t2 is not None and t2.indice == oa[1]:
                    t = t2
            if t is None:
                t = editor.tocar(n, p, r, ("vertice", "corte", "tramo", "tabique", "obstaculo"))
            st["sel"], st["sel_vano"], st["sel_hz"], st["previa"] = t, None, None, None
            st["arrastre"] = (t, p) if t is not None else None
            contexto()
            propiedades.refresh()
            refrescar_lienzo()
        elif tipo == "mousemove" and st["arrastre"] is not None:
            t, p0 = st["arrastre"]
            try:
                st["previa"] = arrastrar(t, p0, p, libre)
            except ValueError:
                pass
            refrescar_lienzo()
        elif tipo == "mouseup" and st["arrastre"] is not None:
            previa = st["previa"]
            st["arrastre"], st["previa"] = None, None
            if previa is not None and previa != st["u"]:
                confirmar(previa)
            else:
                refrescar_lienzo()
        elif tipo == "mousemove" and o_sel is not None:
            asa = edicion_obstaculos.tocar_asa(o_sel, p, r)
            poner_cursor(edicion_obstaculos.cursor(asa, o_sel.tipo) or hcfg["mover"]["cursor"])

    def raton_clic(h, p, libre):
        k, r = st["k"], metros(cap["radio_px"])
        if h == "borrar":
            for idx, q in enumerate(abierto()):
                if editor.distancia(q, p) <= r:
                    borrar(editor.Toque("punto", indice=idx, punto=q))
                    return
        n = nivel()
        if n is None:
            return
        t = editor.tocar(n, p, r)
        if t is None:
            return
        if h == "cortar" and t.tipo == "tramo":
            aplicar(editor.partir_tramo, k, t.lado, t.s if libre else editor.redondear(t.s, snap["largo_m"]))
        elif h == "borrar":
            borrar(t)

    def punto_alzado(p, largo, libre):
        s, z = vista_alzado.desde_mundo(p, largo, esp)
        paso = None if libre else alz["snap_m"]
        return (min(max(editor.redondear(s, paso), 0.0), largo),
                min(max(editor.redondear(z, paso), 0.0), st["u"].altura))

    def raton_alzado(tipo, p, libre):
        """Dibujar ventana o puerta (dos esquinas); Seleccionar; Mover: arrastra el vano desde
        adentro o estira sus bordes y esquinas; Borrar."""
        ma = muro_activo()
        if ma is None:
            return
        k, i, j = ma
        u = st["u"]
        n = u.niveles[k]
        largo = editor.largo_tramo(n, i, j)
        h = st["herr"]
        if h in VANOS:
            q = punto_alzado(p, largo, libre)
            st["cursor"] = q
            if tipo == "mousedown":
                if st["esq"] is None:
                    st["esq"] = q
                elif editor.distancia(st["esq"], q) > 1e-9:       # el segundo clic de un doble clic no cuenta
                    try:
                        w = editor.vano_desde_esquinas(h, st["esq"], q, largo, u.altura, alz["vidrio_defecto"])
                    except ValueError as ex:
                        ui.notify(str(ex), type="warning")
                        return
                    st["esq"] = None
                    if aplicar(editor.agregar_vano, k, i, j, h, w):
                        st["sel_vano"] = (h, len(getattr(tramo_activo(), editor.CAMPOS[h])) - 1)
                        propiedades.refresh()
            refrescar_lienzo()
            return
        s, z = vista_alzado.desde_mundo(p, largo, esp)
        t = n.lados[i].tramos[j]
        tol_vano = metros(cap["radio_px"]) / 2
        tol_borde = metros(cap.get("borde_px", 6))
        if tipo == "mousedown":
            if h == "borrar":
                hit = vista_alzado.tocar_vano(t, s, z, tol_vano)
                if hit is not None:
                    st["sel_vano"] = None
                    aplicar(editor.eliminar_vano, k, i, j, *hit)
                return
            borde = vista_alzado.tocar_borde(t, s, z, tol_borde, st["sel_vano"]) if h == "mover" else None
            hit = borde[:2] if borde else vista_alzado.tocar_vano(t, s, z, tol_vano)
            st["sel_vano"], st["previa"] = hit, None
            if h == "mover" and hit is not None:
                st["arr_alz"] = {"hit": hit, "q0": (s, z), "bordes": borde[2] if borde else None,
                                 "r0": editor.rect(hit[0], getattr(t, editor.CAMPOS[hit[0]])[hit[1]])}
            propiedades.refresh()
            refrescar_lienzo()
        elif tipo == "mousemove" and st["arr_alz"] is not None:
            a = st["arr_alz"]
            paso = None if libre else alz["snap_m"]
            ds, dz = s - a["q0"][0], z - a["q0"][1]
            tp, m = a["hit"]
            try:
                if a["bordes"]:
                    x, zz, an, al = editor.redimensionar_rect(a["r0"], a["bordes"], ds, dz, paso)
                    st["previa"] = editor.redimensionar_vano(u, k, i, j, tp, m, x=x, z=zz, ancho=an, alto=al)
                else:
                    x = editor.redondear(a["r0"][0] + ds, paso)
                    zz = editor.redondear(a["r0"][1] + dz, paso)
                    st["previa"] = editor.mover_vano(u, k, i, j, tp, m, x, zz)
            except ValueError:
                pass
            refrescar_lienzo()
        elif tipo == "mouseup" and st["arr_alz"] is not None:
            previa = st["previa"]
            st["arr_alz"], st["previa"] = None, None
            if previa is not None and previa != st["u"]:
                confirmar(previa)
            else:
                refrescar_lienzo()
        elif tipo == "mousemove" and h == "mover":
            borde = vista_alzado.tocar_borde(t, s, z, tol_borde, st["sel_vano"])
            poner_cursor(vista_alzado.cursor_borde(borde[2] if borde else None, esp) or hcfg["mover"]["cursor"])

    def al_tecla(e: events.KeyEventArguments):
        if not e.action.keydown:
            return
        nombre = (e.key.name or "").lower()
        if e.key.escape:
            escape()
        elif e.key.delete or e.key.backspace:
            suprimir()
        elif e.modifiers.ctrl and nombre == "z":
            deshacer()
        elif e.modifiers.ctrl and nombre == "y":
            rehacer()

    # ================================================================ dibujo
    def dibujar_alzado():
        ma = muro_activo()
        if ma is None or st["vista_alz"] is None:
            return
        k, i, j = ma
        u, h = actual(), st["herr"]
        largo = editor.largo_tramo(u.niveles[k], i, j)
        previa = None
        if h in VANOS and st["esq"] is not None and st["cursor"] is not None:
            try:
                w = editor.vano_desde_esquinas(h, st["esq"], st["cursor"], largo, u.altura, alz["vidrio_defecto"])
                previa = (h, editor.rect(h, w))
            except ValueError:
                pass
        img.set_content(vista_alzado.contenido(u, k, i, j, st["vista_alz"], est, alz, seleccion=st["sel_vano"],
                                               previa=previa, cursor=st["cursor"] if h in VANOS else None,
                                               asas=h == "mover"))

    def refrescar_lienzo():
        if st["modo"] == "alzado":
            dibujar_alzado()
        elif st["modo"] == "contexto" and st["vista_ctx"] is not None:
            img.set_content(contexto_ui.svg(E))
        elif st["modo"] == "planta" and st["vista"] is not None:
            h = st["herr"]
            ob = obstaculos_ui.TIPOS.get(h)
            svg = vista_planta.contenido(
                actual(), st["k"], st["vista"], est, seleccion=st["sel"], borrador=abierto(),
                cursor=st["cursor"] if h in ("dibujar", "tabique") or ob else None,
                tabique=st["tabique"] if h == "tabique" else None, dibujando=h == "dibujar",
                obstaculo=obstaculos_ui.previa(E) if ob else None)
            if h == "mover":
                oa, ts = obstaculo_activo(), sel_valida()
                if oa is not None:
                    svg += edicion_obstaculos.svg_asas(nivel().obstaculos[oa[1]], st["vista"], est)
                elif ts is not None and ts.tipo == "tabique":
                    svg += edicion_tabiques.svg_asas(nivel().tabiques[ts.indice], st["vista"], est)
            img.set_content(svg)

    def refrescar(paneles_=True):
        if st["modo"] == "alzado" and muro_activo() is None:
            ir_a("planta")
        refrescar_lienzo()
        u = st["u"]
        errs = []
        if u.niveles:
            errs = geometria.errores(u, geo_cfg)
        elif not st["ab"]:
            errs = [tx["vacio"]]
        st["g"] = None
        if u.niveles and not errs:
            try:
                st["g"] = geometria.calcular(u, geo_cfg)
            except ValueError as ex:
                errs = [str(ex)]
        avisos = [tx["abierto"].format(nivel=k + 1) for k in sorted(st["ab"])] if tx.get("abierto") else []
        errs = [x for x in errs if x]
        lbl_err.set_content("\n".join(f"- {x}" for x in errs + avisos))
        lbl_err.set_visibility(bool(errs + avisos))
        g = st["g"]
        st["tablas"] = {}
        if g is not None:
            try:
                st["tablas"] = resumen.tablas(u, g, cfg)
            except (ValueError, KeyError) as ex:
                print(f"Envolvente: {type(ex).__name__}: {ex}", flush=True)
            try:
                zona = f"Zona {zonas.zona_de(u.comuna, u.zona)}"
            except (ValueError, KeyError):
                zona = "Elige la zona térmica"
            lbl_resumen.set_text(f"{zona} · {num(sum(g.areas), 1)} m² · {num(g.volumen, 1)} m³ · "
                                 f"{len(g.panos)} muros")
        else:
            lbl_resumen.set_text((tx.get("con_problemas") if u.niveles else tx.get("sin_modelo")) or "")
        envolvente_ui.refresh()
        if paneles_:
            niveles_ui.refresh()
            datos_ui.refresh()
            propiedades.refresh()
        if calc["panel"] is not None:
            calc["panel"].revisar(u)
        if contexto_ui.boton_far(E) != st.get("_far_boton"):
            vistas_ui.refresh()                    # la unidad gano o perdio fachadas con FAR
        dibujar_3d()

    def dibujar_3d():
        if v3 is not None:
            v3.dibujar()

    # ================================================================ archivo
    def guardar():
        if st["ab"]:
            ui.notify("Los perímetros abiertos no se guardan: ciérralos antes", type="warning")
        datos = json.dumps(modelo.a_dict(st["u"]), ensure_ascii=False, indent=1).encode("utf-8")
        descargar_bytes(datos, "unidad.json")

    async def abrir(e):
        try:
            f = getattr(e, "file", None)
            datos = await f.read() if f is not None else e.content.read()
            nueva = modelo.desde_dict(json.loads(datos.decode("utf-8")))
        except Exception as ex:
            ui.notify(f"No se pudo abrir el archivo: {ex}", type="negative")
            return
        finally:
            subida.reset()
        cargar_unidad(nueva)

    def exportar_csv():
        """Las tablas de la caja Detalles modelo en CSV."""
        if not st["tablas"]:
            ui.notify(tx["con_problemas"], type="warning")
            return
        ec = cfg["envolvente"]
        xc = ec["exportar"]
        lineas = [lbl_resumen.text, f"{st['u'].comuna} · {datetime.now():%Y-%m-%d %H:%M}", xc["nota"]]
        descargar_bytes(exportar.csv_bytes(st["tablas"], ec, [xc["titulo"]] + lineas), f"{xc['archivo']}.csv")

    async def exportar_ficha01():
        """La ficha 01 oficial (.xlsm) llenada con la unidad, sin Excel (unidad/ficha01.py)."""
        if st["g"] is None or st["ab"]:
            ui.notify(tx["con_problemas"], type="warning")
            return
        xc = cfg["envolvente"]["exportar"]
        aviso = ui.notification(xc.get("ficha01_generando") or "Generando la ficha 01…", spinner=True, timeout=None)
        try:
            r = await run.io_bound(ficha01.exportar, st["u"], cfg["calculo"].get("salida"))
        except ValueError as ex:
            ui.notify(str(ex), type="warning")
            return
        except Exception as ex:
            ui.notify(f"No se pudo generar la ficha 01: {type(ex).__name__}: {ex}", type="negative")
            return
        finally:
            aviso.dismiss()
        descargar_bytes(r.datos, r.nombre)
        if xc.get("ficha01_listo"):
            ui.notify(xc["ficha01_listo"].format(ruta=r.ruta), multi_line=True, timeout=8000)

    async def generar_reporte():
        """Reporte PDF: modelo 3D, plantas, etiqueta y detalle de la envolvente."""
        if not st["tablas"] or st["g"] is None:
            ui.notify(tx["con_problemas"], type="warning")
            return
        rc = cfg["reporte"]
        imagen = None
        if rc.get("vista_3d", "navegador") == "navegador" and st["modo"] == "3d":
            if rc.get("deseleccionar", True) and hay_eleccion():
                deseleccionar()
                await asyncio.sleep(0.4)
            imagen = await v3.captura()
        panel = calc["panel"]
        res = panel.res if panel is not None and panel.res and panel.calculado == st["u"] else None
        lineas = [f"{lbl_resumen.text} · {st['u'].comuna}"]
        if res:
            motor = panel.motores.get(res.get("backend"), res.get("backend") or "")
            lineas.append(rc["resultado"].format(letra=res.get("letra") or "-",
                                                 ahorro=num(res.get("ahorro_pct") or 0, 0), motor=motor))
        else:
            lineas.append(rc["sin_calculo"])
        try:
            datos = reporte.pdf(st["u"], st["g"], st["tablas"], cfg, res, imagen, lineas)
        except Exception as ex:
            ui.notify(f"No se pudo generar el reporte: {ex}", type="negative")
            return
        descargar_bytes(datos, f"{rc['archivo']}.pdf")

    # ================================================================ cajas
    def elegir_nivel(k):
        if k == st["k"]:
            return
        st["k"], st["sel"], st["sel_vano"], st["sel_hz"] = k, None, None, None
        cancelar()
        contexto()
        refrescar()

    def nuevo_nivel():
        if aplicar(editor.agregar_nivel):
            st["k"], st["sel"] = len(st["u"].niveles) - 1, None
            contexto()
            refrescar()

    def quitar_nivel():
        k, u = st["k"], st["u"]
        ab = {(kk if kk < k else kk - 1): v for kk, v in st["ab"].items() if kk != k}
        if k < len(u.niveles):
            nueva = editor.vaciar(u) if len(u.niveles) == 1 else editor.eliminar_nivel(u, k)
        else:
            nueva = u
        st["sel"], st["sel_hz"] = None, None
        confirmar(nueva, ab)

    @ui.refreshable
    def niveles_ui():
        with grupo():
            if icfg.get("nivel"):
                ui.label(icfg["nivel"]).classes("etiqueta-grupo")
            for k in range(n_vista()):
                boton(None, None, partial(elegir_nivel, k), activo=k == st["k"], etiqueta=str(k + 1))
            boton("nivel_mas", bt["nivel_mas"], nuevo_nivel)
            boton("nivel_menos", bt["nivel_menos"], quitar_nivel)

    @ui.refreshable
    def datos_ui():
        """Datos generales de la unidad (techos y pisos se eligen en el 3D o en el arbol)."""
        u = st["u"]
        ui.select(comunas, value=u.comuna, with_input=True, label="Comuna",
                  on_change=lambda e: e.value and cambiar(True, comuna=e.value, zona=None)
                  ).props("dense").classes("w-full")
        ops = ({o.zona: o.etiqueta() for o in zonas.opciones(u.comuna)} if u.comuna in zonas.cargar() else {})
        valor = u.zona if u.zona in ops else (next(iter(ops)) if len(ops) == 1 else None)
        z = selector("Zona térmica (NCh1079)", ops, valor, lambda v: cambiar(True, zona=v))
        if len(ops) <= 1:
            z.disable()
        selector("Tipo de vivienda", et["tipo_vivienda"], u.tipo_vivienda, lambda v: cambiar(tipo_vivienda=v))
        with ui.row().classes("w-full no-wrap gap-2"):
            numero("Altura libre [m]", u.altura, lambda v: cambiar(altura=float(v)),
                   *geo_cfg["limites"]["altura"], 0.05)
            campo_npt = numero(tx.get("npt") or "NPT [m]", u.npt, lambda v: cambiar(npt=float(v)), 0.0, None, 0.1)
            with campo_npt:
                P.ayuda_explicativa(tx.get("npt_ayuda"))
        with ui.row().classes("w-full no-wrap gap-2"):
            numero("Dormitorios", u.dormitorios, lambda v: cambiar(dormitorios=int(v)), 0, 10, 1, "%d")
            numero("Azimut del eje +y [°]", u.azimut_y, lambda v: cambiar(azimut_y=float(v)), -180, 180, 5, "%.0f")
        selector("Piso del nivel 1", et["piso"], u.piso, lambda v: cambiar(True, piso=v))
        selector("Techo del último nivel", et["techo"], u.techo, lambda v: cambiar(True, techo=v))

    @ui.refreshable
    def propiedades():
        contexto_ui.detalle(E)                     # volumen de contexto elegido (si no hay arbol)
        paneles.propiedades(E)
        # al elegir algo nuevo se pliega Unidad (sus datos se ingresan una vez) y se abre Envolvente
        clave = (sel_valida(), vano_valido(), hz_valida(), contexto_ui.activo(E))
        if (icfg.get("plegar_unidad_al_elegir", True) and clave != st["ultima"]
                and any(x is not None for x in clave) and "edificio" in cajas):
            cajas["edificio"].set_value(False)
            cajas["componente"].set_value(True)
        st["ultima"] = clave

    @ui.refreshable
    def envolvente_ui():
        paneles.envolvente_tablas(E, st["tablas"])
        contexto_ui.far(E)                         # obstrucciones remotas que van a la ficha

    def caja(clave):
        cajas[clave] = (ui.expansion(icfg["cajas"][clave], value=clave in icfg["cajas_abiertas"])
                        .props("dense header-class=caja-titulo").classes("caja"))
        return cajas[clave]

    def problema_calculo():
        return cfg["calculo"]["textos"]["sin_modelo"] if st["g"] is None or st["ab"] else None

    # panel de resultados (derecha): se muestra u oculta con su boton
    def poner_derecha():
        panel_der.set_visibility(der["visible"])
        if der["visible"]:
            estado_el.classes(add="con-derecha")
        else:
            estado_el.classes(remove="con-derecha")

    def alternar_resultados():
        der["visible"] = not der["visible"]
        poner_derecha()
        boton_resultados.refresh()

    @ui.refreshable
    def boton_resultados():
        with grupo():
            boton("resultados", bt["resultados"], alternar_resultados, activo=der["visible"])

    # contexto que reciben las cajas (paneles.py), las obstrucciones (obstaculos_ui.py), la vista
    # Contexto (contexto_ui.py) y el 3D
    E = SimpleNamespace(st=st, cfg=cfg, P=P, aplicar=aplicar, suprimir=suprimir, ir_a=ir_a, borrar=borrar,
                        sel_valida=sel_valida, nivel=nivel, abierto=abierto, muro_activo=muro_activo,
                        tramo_activo=tramo_activo, vano_activo=vano_activo, hz_activa=hz_valida,
                        obstaculo_activo=obstaculo_activo, elegir_obstaculo=elegir_obstaculo,
                        editar_obstaculo=editar_obstaculo, elegir_tabique=elegir_tabique,
                        abrir_alzado=abrir_alzado, hay_eleccion=hay_eleccion,
                        cerrar_abierto=cerrar_abierto, descartar_abierto=descartar_abierto,
                        elegir_muro=elegir_muro, elegir_hz=elegir_hz, deseleccionar=deseleccionar,
                        metros=metros, refrescar_lienzo=refrescar_lienzo, actual=actual,
                        poner_cursor=poner_cursor, refrescar_seleccion=refrescar_seleccion,
                        refrescar_vistas=vistas_ui.refresh)

    # ================================================================ layout
    ui.add_css(ESTILO.read_text(encoding="utf-8"))
    ui.add_head_html(SIN_AUTOSCROLL)
    ui.add_head_html(CLIC_SIN_ARRASTRE % int(icfg.get("clic_tolerancia_px", 4)))
    ui.keyboard(on_key=al_tecla)
    with ui.dialog() as dlg_vaciar, ui.card():
        ui.label(tx["confirmar_vaciar"])
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancelar", on_click=dlg_vaciar.close).props("flat no-caps")
            ui.button("Eliminar todo", color="negative",
                      on_click=lambda: (dlg_vaciar.close(), vaciar())).props("no-caps")
    subida = ui.upload(auto_upload=True, on_upload=abrir).props("accept=.json").classes("hidden")

    # lienzo a pantalla completa (debajo de todo)
    st["css"] = hcfg[st["herr"]]["cursor"]
    img = (ui.interactive_image(vista_planta.fuente_vacia(dim["w"], dim["h"], est["fondo"]),
                                on_mouse=al_raton, events=["mousedown", "mousemove", "mouseup", "dblclick"])
           .classes("lienzo lienzo-editor").style(f"cursor: {st['css']}"))
    img.on("wheel", al_rueda, args=["deltaY"], throttle=lz["rueda_throttle_s"])
    cont3d = ui.element("div").classes("lienzo")
    v3 = vista3d_ui.Vista3D(E, cont3d, dim)

    # barra superior: rotulo, edicion, archivo, herramientas, niveles
    with ui.element("div").classes("barra barra-sup"):
        if icfg.get("titulo_corto"):
            ui.label(icfg["titulo_corto"]).classes("barra-titulo")
        with grupo():
            boton("deshacer", bt["deshacer"], deshacer)
            boton("rehacer", bt["rehacer"], rehacer)
        with grupo():
            with boton("abrir", bt["abrir"], None):
                menu_cargar()
            boton("guardar", bt["guardar"], guardar)
            boton("vaciar", bt["vaciar"], dlg_vaciar.open)
        barra_herr()
        niveles_ui()

    # arriba a la derecha: modo del 3D, Mostrar FAR, vistas, navegacion y panel de resultados
    with ui.element("div").classes("barra barra-nav"):
        vistas_ui()
        with grupo():
            boton("encuadrar", bt["encuadrar"], encuadrar)
            boton("zoom_mas", bt["zoom_mas"], lambda: zoom(lz["zoom"]))
            boton("zoom_menos", bt["zoom_menos"], lambda: zoom(1 / lz["zoom"]))
        boton_resultados()

    # izquierda: Unidad y Envolvente
    with ui.element("div").classes("toolbox"):
        with caja("edificio"):
            datos_ui()
        with caja("componente"):
            propiedades()

    # derecha: Resultados (etiqueta, Calcular, motor, descargas y reporte) y Detalles modelo
    panel_der = ui.element("div").classes("toolbox toolbox-der")
    with panel_der:
        with caja("resultados"):
            lbl_err = ui.markdown("").classes("errores")
            calc["panel"] = calculo_ui.PanelCalculo(
                cfg["calculo"], lambda: st["u"], problema_calculo, P, descargar_bytes,
                extras=[(cfg["reporte"].get("boton", "Reporte (PDF)"), generar_reporte)])
        with caja("detalle"):
            lbl_resumen = ui.label("").classes("resumen")
            xc = cfg["envolvente"]["exportar"]
            with ui.element("div").classes("acciones"):
                accion(xc["csv"], exportar_csv)
                accion(xc.get("ficha01") or "Ficha 01 (.xlsm)", exportar_ficha01, ayuda=xc.get("ficha01_ayuda"))
            envolvente_ui()

    # barra de estado (ayudas como texto); con ayudas: tooltip van en los botones
    estado_el = ui.element("div").classes("estado")
    with estado_el:
        lbl_estado_herr = ui.label("")
        lbl_estado_vista = ui.label("")
    estado_el.set_visibility(P.con_texto)
    poner_derecha()

    st["vista"] = encuadre_planta()
    mostrar_vista()
    refrescar()
    if st["modo"] == "3d":
        v3.crear()

    ui.on("ventana", al_ventana, throttle=0.2)
    try:
        await ui.context.client.connected(timeout=15)
        d = await ui.run_javascript("({w: window.innerWidth, h: window.innerHeight})", timeout=5)
        if isinstance(d, dict):
            redimensionar(d.get("w"), d.get("h"))
        ui.run_javascript(VENTANA_JS)
    except Exception as ex:                        # sin medir la ventana el lienzo queda en lienzo.ancho_px x alto_px
        print(f"No se pudo medir la ventana: {type(ex).__name__}: {ex}", flush=True)


def main() -> None:
    cfg0 = editor.config()
    app.add_static_files("/iconos", str(ICONOS))

    @ui.page("/", title=cfg0["titulo"])
    async def _inicio():
        await pagina(editor.cargar_config())       # se relee en cada carga (F5) para iterar el estilo

    ui.run(title=cfg0["titulo"], host=cfg0.get("host", "127.0.0.1"), port=cfg0["puerto"],
           show=cfg0["abrir_navegador"], reload=False)
