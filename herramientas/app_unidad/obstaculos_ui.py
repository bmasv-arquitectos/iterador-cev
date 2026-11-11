# -*- coding: utf-8 -*-
"""
Obstrucciones dibujadas en el editor (herramientas obstaculo_h, obstaculo_v y balcon):
dibujo con el raton en la planta, sus filas en el arbol de la caja Envolvente y
su detalle (altura, nivel, P04 y las ventanas a las que hace sombra).

modelo.Obstaculo:
  - horizontal (balcon, cornisa, alero que hace sombra): rectangulo con dos clics en
    esquinas opuestas; el primero se pega al muro mas cercano. Queda SOBRE el nivel:
    su cara inferior a la altura libre (se cambia en el detalle).
  - vertical (muro saliente, aleta): segmento desde el muro hacia afuera (10 grados,
    10 cm); ocupa todo el alto del nivel (se cambia en el detalle).
  - balcon (losa de balcon en el piso del nivel, solo P04, no hace sombra): polilinea
    con un clic por esquina. Cada punto se pega (edicion_obstaculos.snap_balcon, con el
    radio captura.balcon_px) al primer punto para cerrar, a un vertice de la unidad o
    al muro bajo el cursor; si no, 10 grados y 10 cm desde el anterior. La planta
    marca a que se pego (planta.snap). Se cierra con un clic en el primer punto o con
    doble clic (el ultimo punto vuelve al primero). Sirve para balcones en L.
Shift apaga el ajuste; Esc cancela. El primer punto de la horizontal y la vertical se
guarda en st["tabique"] (el mismo que usa el tabique), los puntos del balcon en
st["balcon"] y su ultimo snap en st["snap"]; Esc y el cambio de herramienta los
limpian. previa() entrega lo que vista_planta dibuja mientras tanto.

Textos: TX; cualquier clave se cambia en config/editor.yaml (obstaculos:). Un texto
vacio no se muestra. La logica esta en unidad/editor.py, unidad/edicion_obstaculos.py
y unidad/obstrucciones.py.
"""
from __future__ import annotations

from functools import partial

from nicegui import ui

from herramientas.recinto.a_ficha import cargar_config as cargar_ficha01
from herramientas.unidad import edicion_obstaculos, editor, obstrucciones
from herramientas.unidad.modelo import area_firmada

from .piezas import num

TIPOS = {"obstaculo_h": "horizontal", "obstaculo_v": "vertical", "balcon": "balcon"}
TX = {
    "tipos": {"horizontal": "Horizontal {n}", "vertical": "Vertical {n}", "balcon": "Balcón {n}"},
    "nivel_fila": "N{nivel}",
    "medidas_h": "{ancho} × {fondo} m",
    "medidas_v": "{largo} m",
    "medidas_b": "{area} m²",
    "usa": "{fav} en {n} ventana(s)",
    "sin_uso": "sin ventanas",
    "sin_sombra": "no hace sombra",
    "p04_fila": "P04",
    "titulo_medidas": "Posición",
    "ancho": "Ancho × fondo",
    "largo": "Largo (saliente)",
    "area": "Área",
    "nivel": "Nivel (queda sobre él)",
    "nivel_balcon": "Nivel (en su piso)",
    "nivel_opcion": "Nivel {nivel}",
    "z_h": "Cara inferior desde el piso [m]",
    "alto_h": "Espesor [m]",
    "z_v": "Desde el piso [m]",
    "alto_v": "Alto [m]",
    "espesor_b": "Espesor (solo el dibujo 3D) [m]",
    "balcon_ayuda": "Losa de balcón en el piso del nivel: no hace sombra, solo suma su puente térmico P04 "
                    "(el largo de sus bordes apoyados en los muros exteriores). Para la sombra de un balcón "
                    "de arriba usa una obstrucción horizontal.",
    "automatico": "Altura automática",
    "automatico_ayuda": "Horizontal: cara inferior a la altura libre del nivel. Vertical: todo el alto del nivel.",
    "p04": "Puente térmico P04",
    "p04_modos": {"si": "Cuenta", "no": "No cuenta"},
    "p04_elemento": "Elemento perpendicular",
    "p04_aislacion": "Aislación",
    "p04_largo": {"auto": "Largo automático", "manual": "Largo a mano"},
    "p04_largo_valor": "Largo P04 [m]",
    "p04_auto": "Largo automático: {largo} m",
    "p04_sin_muro": "No se apoya en un muro exterior del nivel: no suma P04.",
    "ventanas": "Ventanas a las que hace sombra",
    "sin_ventanas": "Ninguna ventana del nivel queda bajo ella o en su plano de fachada.",
    "eliminar": "Eliminar obstrucción",
    "eliminar_balcon": "Eliminar balcón",
}


def textos(cfg: dict) -> dict:
    extra = cfg.get("obstaculos") or {}
    t = {**TX, **extra}
    for c in ("tipos", "p04_modos", "p04_largo"):
        t[c] = {**TX[c], **(extra.get(c) or {})}
    return t


# ==================================================================== dibujo
def previa(E):
    """Lo que vista_planta dibuja mientras se dibuja con la herramienta activa: (tipo, primer
    punto) o ("balcon", puntos, snap); None si no es una herramienta de obstrucciones."""
    tipo = TIPOS.get(E.st["herr"])
    if tipo is None:
        return None
    if tipo == "balcon":
        return ("balcon", tuple(E.st.get("balcon") or ()), E.st.get("snap"))
    return (tipo, E.st["tabique"])


def _crear_balcon(E, puntos) -> None:
    st = E.st
    try:
        o = editor.balcon_nuevo(puntos)
    except ValueError as ex:
        ui.notify(str(ex), type="warning")
        return
    k = st["k"]
    st["balcon"], st["cursor"], st["snap"] = None, None, None
    if E.aplicar(editor.agregar_obstaculo, k, o):
        E.elegir_obstaculo(k, len(st["u"].niveles[k].obstaculos) - 1)


def _raton_balcon(E, tipo_ev: str, p, libre: bool) -> None:
    """Un clic por esquina; clic en el primer punto o doble clic: cierra el balcon."""
    st = E.st
    pts = list(st.get("balcon") or ())
    if tipo_ev == "dblclick":
        if len(pts) >= 3:
            _crear_balcon(E, pts)
        return
    cap = E.cfg["captura"]
    radio = E.metros(cap.get("balcon_px", cap["radio_px"]))
    q, snap = edicion_obstaculos.snap_balcon(E.nivel(), p, pts, libre, radio, E.cfg["snap"]["largo_m"],
                                             E.metros(cap["cierre_px"]))
    st["cursor"], st["snap"] = q, snap
    if tipo_ev == "mousedown":
        if snap == "cierre":
            _crear_balcon(E, pts)
            return
        if not pts or editor.distancia(q, pts[-1]) > 1e-9:   # el segundo clic de un doble clic no cuenta
            st["balcon"] = pts + [q]
    E.refrescar_lienzo()


def raton(E, herr: str, tipo_ev: str, p, libre: bool) -> None:
    """Horizontal y vertical: dos clics (el primero fija st["tabique"], el segundo crea la
    obstruccion y la elige). Balcon: polilinea (_raton_balcon)."""
    st = E.st
    n = E.nivel()
    if n is None:
        return
    tipo = TIPOS[herr]
    if tipo == "balcon":
        _raton_balcon(E, tipo_ev, p, libre)
        return
    if tipo_ev == "dblclick":
        return
    a = st["tabique"]
    r = E.metros(E.cfg["captura"]["radio_px"])
    q = editor.ajustar_obstaculo(n, p, a, tipo, libre, r, E.cfg["snap"]["largo_m"])
    st["cursor"] = q
    if tipo_ev == "mousedown":
        if a is None:
            st["tabique"] = q
        elif editor.distancia(a, q) > 1e-9:            # el segundo clic de un doble clic no cuenta
            try:
                o = editor.obstaculo_nuevo(tipo, a, q)
            except ValueError as ex:
                ui.notify(str(ex), type="warning")
                return
            k = st["k"]
            if E.aplicar(editor.agregar_obstaculo, k, o):
                st["tabique"] = None
                E.elegir_obstaculo(k, len(st["u"].niveles[k].obstaculos) - 1)
                return
    E.refrescar_lienzo()


# ==================================================================== arbol
def cuantas(u) -> int:
    return sum(len(n.obstaculos) for n in u.niveles)


def _medidas(o, T: dict) -> str:
    if o.tipo == "balcon":
        return T["medidas_b"].format(area=num(abs(area_firmada(o.vertices))))
    if o.tipo == "horizontal":
        return T["medidas_h"].format(ancho=num(abs(o.b[0] - o.a[0])), fondo=num(abs(o.b[1] - o.a[1])))
    return T["medidas_v"].format(largo=num(editor.distancia(o.a, o.b)))


def _de(obs, k: int, t: int, o) -> list:
    """Las Obstruccion detectadas que vienen de la obstruccion dibujada t del nivel k."""
    return [x for x in obs if x.obstaculo == t and x.nivel == k and x.tipo == o.tipo]


def filas(E, fila, desplegar, obs) -> None:
    """Una fila por obstruccion dibujada (fila y desplegar: los del arbol de paneles.py)."""
    st = E.st
    T = textos(E.cfg)
    u = st["u"]
    elegida = E.obstaculo_activo()
    varios = len(u.niveles) > 1
    for k, n in enumerate(u.niveles):
        for t, o in enumerate(n.obstaculos):
            nombre = T["tipos"].get(o.tipo, o.tipo).format(n=t + 1)
            if varios and T.get("nivel_fila"):
                nombre += f" · {T['nivel_fila'].format(nivel=k + 1)}"
            if o.tipo == "balcon":
                partes = [_medidas(o, T), T.get("sin_sombra")]
            else:
                usadas = sum(1 for x in _de(obs, k, t, o) if x.usada)
                fav = "FAV1" if o.tipo == "horizontal" else "FAV2"
                partes = [_medidas(o, T), T["usa"].format(fav=fav, n=usadas) if usadas else T.get("sin_uso")]
            if o.p04:
                partes.append(T.get("p04_fila"))
            act = elegida == (k, t)
            fila(nombre, " · ".join(x for x in partes if x),
                 E.deseleccionar if act else partial(E.elegir_obstaculo, k, t), activa=act)
            if act:
                desplegar(lambda k=k, t=t: detalle(E, k, t))


# ==================================================================== detalle
def _largo_auto(E, k: int, o) -> float:
    g = E.st["g"]
    if g is None:
        return 0.0
    try:
        return sum(l for _, l in obstrucciones.contactos(E.st["u"], g, k, o))
    except Exception:
        return 0.0


def pasar(E, k: int, t: int, k2: int) -> None:
    if k2 != k and E.aplicar(editor.pasar_obstaculo, k, t, k2):
        E.elegir_obstaculo(k2, len(E.st["u"].niveles[k2].obstaculos) - 1)


def eliminar(E, k: int, t: int) -> None:
    E.st["sel"] = None
    E.aplicar(editor.eliminar_obstaculo, k, t)


def _p04(E, k: int, o, cambio, T: dict) -> None:
    P = E.P
    P.subtitulo(T.get("p04"))
    P.segmentado(T["p04_modos"], "si" if o.p04 else "no", lambda v: cambio(True, p04=v == "si"))
    if not o.p04:
        return
    pc = obstrucciones.config()["p04"]
    f1 = cargar_ficha01()["p04"]
    el = o.p04_elemento or pc["elemento"].get(o.tipo) or "Muro "
    ops = {x: x.strip() for x in pc["elementos"]}
    ops.setdefault(el, el.strip())
    P.selector(T["p04_elemento"], ops, el, lambda v: cambio(True, p04_elemento=v))
    ais = o.p04_aislacion or pc.get("aislacion") or f1["aislacion_defecto"]
    ops = {x: x for x in f1["aislaciones"]}
    ops.setdefault(ais, ais)
    P.selector(T["p04_aislacion"], ops, ais, lambda v: cambio(True, p04_aislacion=v))
    auto = _largo_auto(E, k, o)
    modo = "manual" if o.p04_largo is not None else "auto"
    P.segmentado(T["p04_largo"], modo,
                 lambda v: cambio(True, p04_largo=None if v == "auto" else round(auto, 2)))
    if modo == "manual":
        P.numero(T["p04_largo_valor"], o.p04_largo, lambda v: cambio(p04_largo=float(v)), 0.0, None, 0.05)
    elif auto > 0:
        P.nota(T["p04_auto"].format(largo=num(auto)))
    else:
        P.nota(T.get("p04_sin_muro"))


def detalle(E, k: int, t: int) -> None:
    st, P = E.st, E.P
    T = textos(E.cfg)
    u = st["u"]
    if k >= len(u.niveles) or t >= len(u.niveles[k].obstaculos):
        return
    o = u.niveles[k].obstaculos[t]
    h, b = o.tipo == "horizontal", o.tipo == "balcon"

    def cambio(paneles=False, **c):
        E.aplicar(editor.cambiar_obstaculo, k, t, _paneles=paneles, **c)

    # ---------------------------------------------------------------- posicion
    P.subtitulo(T.get("titulo_medidas"))
    P.dato(T["area"] if b else (T["ancho"] if h else T["largo"]), _medidas(o, T))
    if len(u.niveles) > 1:
        P.selector(T["nivel_balcon" if b else "nivel"],
                   {str(x): T["nivel_opcion"].format(nivel=x + 1) for x in range(len(u.niveles))},
                   str(k), lambda v: pasar(E, k, t, int(v)))
    e3 = (E.cfg.get("modelo3d") or {})
    if b:
        P.explicacion(T.get("balcon_ayuda"))
        esp = o.alto if o.alto is not None else float((e3.get("obstaculo") or {}).get(
            "balcon_espesor_m", e3.get("espesor_losa", 0.2)))
        P.numero(T["espesor_b"], esp, lambda v: cambio(alto=float(v)), 0.01, None, 0.05)
    else:
        if h:
            z = obstrucciones.z_horizontal(o, u.altura)
            alto = o.alto if o.alto is not None else float((e3.get("obstaculo") or {}).get("espesor_m", 0.15))
        else:
            z, z1 = obstrucciones.z_vertical(o, u.altura)
            alto = z1 - z
        with ui.row().classes("w-full no-wrap gap-2"):
            P.numero(T["z_h" if h else "z_v"], z, lambda v: cambio(z=float(v)), 0.0, None, 0.05)
            P.numero(T["alto_h" if h else "alto_v"], alto, lambda v: cambio(alto=float(v)), 0.01, None, 0.05)
        if o.z is not None or o.alto is not None:
            with ui.element("div").classes("acciones"):
                P.accion(T["automatico"], lambda: cambio(True, z=None, alto=None), ayuda=T.get("automatico_ayuda"))

    _p04(E, k, o, cambio, T)

    # ---------------------------------------------------------------- ventanas
    if not b:
        P.subtitulo(T.get("ventanas"))
        mias = _de(st.get("_obs") or (), k, t, o)
        if not mias:
            P.nota(T.get("sin_ventanas"))
        lc = E.cfg["componentes"]["lista"]
        for x in mias:
            linea = obstrucciones.avisos([x])[0].split(": ", 1)[-1]
            P.nota(f"{lc['ventana'].format(muro=x.muro, n=x.ventana + 1)}: {linea}")
    with ui.element("div").classes("acciones"):
        P.accion(T["eliminar_balcon" if b else "eliminar"], partial(eliminar, E, k, t), peligro=True)
