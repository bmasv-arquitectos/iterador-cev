# -*- coding: utf-8 -*-
"""
Vista 3D del editor (ui.scene), sacada de app.py.

La escena se crea al entrar a la vista y se borra al salir; la camara se ubica
despues de modelo3d.espera_camara_s y los botones del raton se asignan por
JavaScript a los OrbitControls. La grilla del suelo se vuelve transparente y se dibuja
detras de las losas (modelo3d.grilla_opacidad y grilla_detras; scripts.grilla_js).
Clic: elige el muro, ventana, puerta, techo, piso, obstruccion, balcon o tabique bajo el
cursor (en el vacio, deja de elegir). Doble clic: en un muro abre su alzado; en una
ventana o puerta, el alzado con ella elegida y Mover; en una obstruccion o balcon, la
planta de su nivel con ella elegida y Mover (E.editar_obstaculo); en un tabique, lo
mismo (E.elegir_tabique con editar). Los tabiques se ven con los techos ocultos.

Terreno: la grilla de ui.scene esta en z = 0, que es el terreno natural. Todo se arma
con el piso del nivel 1 en z = 0 (modelo3d) y el grupo sube Unidad.npt: un
departamento alto queda flotando sobre la grilla, los volumenes de contexto
(modelo3d.contexto, desde z = -npt) quedan apoyados en ella y la brujula se dibuja en
el terreno.

Volumenes de contexto (FAR dibujado): prismas transparentes con sus aristas en el modo
lineas (y en el solido si modelo3d.contexto.aristas_solido). Un clic los elige
(st["sel_ctx"]; su detalle se abre en la caja Envolvente) solo si el rayo no toca
antes una pieza de la unidad: asi un edificio transparente delante no le quita los
clics a la unidad.

captura() devuelve la imagen del canvas para el reporte (se vuelve a dibujar justo
antes, sin la grilla, porque el canvas no guarda la imagen entre cuadros).
E: el contexto del editor (app.py). Colores y medidas: config/editor.yaml (modelo3d:).
"""
from __future__ import annotations

import base64

from nicegui import events, ui

from herramientas.unidad import modelo3d

from .scripts import BOTONES_3D, CAPTURA_3D, grilla_js, superficie_losa


class Vista3D:
    def __init__(self, E, cont, dim: dict):
        self.E, self.cont, self.dim = E, cont, dim
        self.escena = None
        self.grupo = None

    @property
    def st(self) -> dict:
        return self.E.st

    @property
    def e3(self) -> dict:
        return self.E.cfg["modelo3d"]

    def contexto_activo(self):
        """Indice del volumen de contexto elegido (si todavia existe), o None."""
        i = self.st.get("sel_ctx")
        return i if i is not None and 0 <= i < len(self.st["u"].contexto) else None

    def elegidos(self) -> set:
        """Nombres de las piezas a resaltar: el muro, la ventana, la puerta, la obstruccion, el
        tabique o el volumen de contexto elegido."""
        E = self.E
        ci = self.contexto_activo()
        extra = {f"contexto|{ci}"} if ci is not None else set()
        va = E.vano_activo()
        if va is not None and self.st["modo"] != "planta":
            suf = "|".join(map(str, va[1:]))
            return extra | ({f"ventana|{suf}", f"proteccion|{suf}"} if va[0] == "ventana" else {f"puerta|{suf}"})
        oa = E.obstaculo_activo()
        if oa is not None:
            return extra | {f"obstaculo|{oa[0]}|{oa[1]}"}
        t = E.sel_valida()
        if t is not None and t.tipo == "tabique":
            return extra | {f"tabique|{self.st['k']}|{t.indice}"}
        ma = E.muro_activo()
        return extra | ({f"tramo|{ma[0]}|{ma[1]}|{ma[2]}"} if ma else set())

    def _lineas_suelo(self, pts, z, cerrado, color):
        pts = list(pts)
        pares = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if cerrado and len(pts) > 2 else [])
        for a, b in pares:
            self.escena.line([a[0], a[1], z], [b[0], b[1], z]).material(color)

    def _contexto(self, cl, elegidos, color_sel, colores_linea) -> None:
        """Volumenes de contexto: prismas transparentes y sus aristas."""
        st, e3, escena = self.st, self.e3, self.escena
        prismas, lineas = modelo3d.contexto(st["u"])
        e = cl["contexto"]
        for s in prismas:
            (escena.extrusion([list(p) for p in s.contorno], s.alto).move(0, 0, s.z)
             .material(color_sel if s.nombre in elegidos else e["color"], e["opacidad"])
             .with_name(s.nombre))
        if st["render"] == "lineas" or (e3.get("contexto") or {}).get("aristas_solido", True):
            color = colores_linea.get("contexto", "#6b7280")
            for ln in lineas:
                escena.line(list(ln.a), list(ln.b)).material(color)

    def dibujar(self) -> None:
        st, e3, escena = self.st, self.e3, self.escena
        if st["modo"] != "3d" or escena is None:
            return
        if self.grupo is not None:
            self.grupo.delete()
            self.grupo = None
        u = st["u"]
        npt = float(u.npt)                         # el grupo sube npt: la grilla queda en el terreno
        el, elegidos, hz = e3["espesor_losa"], self.elegidos(), self.E.hz_activa()
        color_sel = e3["seleccion"]["color"]
        cl = modelo3d.paleta(e3, st["render"])
        colores_linea = (e3.get("lineas") or {}).get("color") or {}
        esc = modelo3d.construir(u, st["g"], e3) if st["g"] is not None else None
        marco = esc
        if marco is None:
            pts = [p for n in u.niveles for p in n.vertices] + [p for v in st["ab"].values() for p in v]
            if (e3.get("contexto") or {}).get("encuadre") or not pts:
                pts += [p for c in u.contexto for p in c.vertices]
            marco = modelo3d.encuadre(pts, u.altura * max(1, len(u.niveles)), e3)
        nc = e3.get("norte")
        with escena:
            with escena.group() as grp:
                if esc is not None:
                    for s in esc.muros:
                        e = cl[s.clase]
                        (escena.extrusion([list(p) for p in s.contorno], s.alto).move(0, 0, s.z)
                         .material(color_sel if s.nombre in elegidos else e["color"], e["opacidad"])
                         .with_name(s.nombre))
                    for c in esc.cajas:
                        e = cl[c.clase]
                        resaltar = c.nombre in elegidos
                        (escena.box(*c.tamano).move(*c.centro).rotate(0, 0, c.giro)
                         .material(color_sel if resaltar else e["color"],
                                   max(e["opacidad"], 0.6) if resaltar else e["opacidad"])
                         .with_name(c.nombre))
                    for s in esc.losas:
                        if not st["techos"] and s.nombre.startswith("techo|"):
                            continue
                        e = cl[s.clase]
                        resaltar = s.nombre in elegidos or (hz is not None and superficie_losa(s.nombre) == hz)
                        (escena.extrusion([list(p) for p in s.contorno], s.alto).move(0, 0, s.z)
                         .material(color_sel if resaltar else e["color"], e["opacidad"]).with_name(s.nombre))
                    if st["render"] == "lineas":
                        for ln in esc.lineas:
                            escena.line(list(ln.a), list(ln.b)).material(colores_linea.get(ln.clase, "#4b5563"))
                else:
                    for k, n in enumerate(u.niveles):
                        self._lineas_suelo(n.vertices, modelo3d.z_nivel(k, u.altura, el) + 0.01, True,
                                           e3["contorno"]["color"])
                b3 = e3["borrador"]
                for k, pts in st["ab"].items():
                    z = modelo3d.z_nivel(k, u.altura, el)
                    self._lineas_suelo(pts, z + b3["alto"] + 0.01, False, b3["color"])
                    if modelo3d.poligono_valido(pts):
                        (escena.extrusion([list(p) for p in pts], b3["alto"]).move(0, 0, z)
                         .material(b3["color"], b3["opacidad"]))
                # el contexto va al final: los transparentes se mezclan mejor sobre lo opaco
                self._contexto(cl, elegidos, color_sel, colores_linea)
                if nc:                             # en el terreno (el grupo sube npt)
                    lineas_n, letra = modelo3d.brujula(marco, u.azimut_y, e3)
                    for ln in lineas_n:
                        (escena.line([ln.a[0], ln.a[1], ln.a[2] - npt], [ln.b[0], ln.b[1], ln.b[2] - npt])
                         .material(nc.get("color", "#2b3440")))
                    escena.text(nc.get("letra", "N"), style=nc.get("estilo", "")).move(letra[0], letra[1],
                                                                                       letra[2] - npt)
        if npt:
            grp.move(0, 0, npt)
        self.grupo = grp
        if st["camara"]:
            st["camara"] = False
            cam = modelo3d.camara(marco, e3)
            cam["z"] += npt
            cam["look_at_z"] += npt

            def ubicar():
                if self.escena is escena:
                    escena.move_camera(**cam)

            with self.cont:
                ui.timer(e3["espera_camara_s"], ubicar, once=True)

    def crear(self) -> None:
        e3 = self.e3
        self.cont.clear()
        with self.cont:
            escena = (ui.scene(width=self.dim["w"], height=self.dim["h"], grid=e3["grilla"],
                               background_color=e3["fondo"], on_click=self.al_click)
                      .classes("lienzo-editor"))
            b = modelo3d.botones_raton(e3)
            js = BOTONES_3D % (escena.id, b["LEFT"], b["MIDDLE"], b["RIGHT"])
            if e3["grilla"]:
                js += ";" + grilla_js(escena.id, e3)

            def botones():
                if self.escena is escena:
                    ui.run_javascript(js)

            ui.timer(0.1, botones, once=True)
        self.escena, self.grupo = escena, None
        self.st["camara"] = True
        self.dibujar()

    def quitar(self) -> None:
        self.cont.clear()
        self.escena, self.grupo = None, None

    def encuadrar(self) -> None:
        self.st["camara"] = True
        self.dibujar()

    def elegir_contexto(self, i) -> None:
        """Elige el volumen de contexto i (None: ninguno) y abre su detalle; deja de elegir lo de
        la unidad."""
        self.st.update(sel=None, sel_vano=None, sel_hz=None, sel_ctx=i)
        self.E.refrescar_seleccion()

    def al_click(self, e: events.SceneClickEventArguments) -> None:
        E = self.E
        tipo_clic = getattr(e, "click_type", "click")
        if tipo_clic not in ("click", "dblclick") or getattr(e, "button", 0) != 0:
            return
        doble = tipo_clic == "dblclick"
        ctx = None                                 # primer volumen de contexto que toca el rayo
        for h in e.hits:
            nombre = h.object_name or ""
            partes = nombre.split("|")
            if partes[0] == "contexto" and len(partes) == 2:
                if ctx is None:
                    ctx = int(partes[1])
                continue
            sup = superficie_losa(nombre)
            if sup is not None:
                E.elegir_hz(*sup)
                return
            if partes[0] == "obstaculo" and len(partes) == 3:
                k, t = int(partes[1]), int(partes[2])
                (E.editar_obstaculo if doble else E.elegir_obstaculo)(k, t)
                return
            if partes[0] == "tabique" and len(partes) == 3:
                E.elegir_tabique(int(partes[1]), int(partes[2]), editar=doble)
                return
            if partes[0] == "tramo" and len(partes) == 4:
                E.elegir_muro(*map(int, partes[1:]))
                if doble:
                    E.abrir_alzado()
                return
            if partes[0] in ("ventana", "proteccion", "puerta") and len(partes) == 5:
                k, i, j, m = map(int, partes[1:])
                E.elegir_muro(k, i, j, ("puerta" if partes[0] == "puerta" else "ventana", m))
                if doble:
                    E.abrir_alzado(editar=True)
                return
        if ctx is not None:
            self.elegir_contexto(ctx)
            return
        if doble or not E.cfg["interfaz"].get("deseleccionar_al_clic_vacio", True):
            return
        if E.hay_eleccion():
            E.deseleccionar()

    async def captura(self):
        """Imagen (JPEG) de la vista 3D tal como se ve, o None."""
        escena = self.escena
        if self.st["modo"] != "3d" or escena is None:
            return None
        sin_grilla = "true" if self.E.cfg["reporte"].get("ocultar_grilla", True) else "false"
        try:
            d = await ui.run_javascript(CAPTURA_3D % (escena.id, sin_grilla), timeout=10)
        except Exception as ex:
            print(f"Captura 3D: {type(ex).__name__}: {ex}", flush=True)
            return None
        if isinstance(d, str) and "," in d and d.startswith("data:image/"):
            return base64.b64decode(d.split(",", 1)[1])
        return None
