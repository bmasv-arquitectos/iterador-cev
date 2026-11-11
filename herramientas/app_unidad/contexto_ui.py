# -*- coding: utf-8 -*-
"""
Vista Contexto del editor (FAR dibujado): dibujo con el raton de los volumenes del
entorno, su grupo en el arbol de la caja Envolvente, su detalle, la tabla FAR de la
caja Detalles modelo y el FAR de una fachada dibujado en la vista.

La vista es una planta donde la unidad es solo referencia (unidad/vista_contexto.py).
Herramientas (HERRAMIENTAS y config/editor.yaml contexto.en_contexto):
  ctx_rect   rectangulo con dos clics en esquinas opuestas;
  ctx_poli   polilinea ortogonal (sin diagonales); se cierra con un clic en el primer
             punto o con doble clic (si falta una esquina, se agrega);
  mover      el volumen elegido muestra asas: esquinas, lados (en paralelo) y cuerpo;
  borrar     un clic en un volumen lo quita;
  seleccionar un clic elige un volumen (en el vacio, ninguno).
El cursor mide, por eje, la distancia a la cara de la unidad perpendicular mas cercana
(vista_contexto.cotas_desde: exterior = cara interior + modelo3d.espesor_muro) y el
primer punto se ajusta a cotas redondas (vista_contexto.snap_m); Shift lo apaga.
Esc cancela lo que se esta dibujando, luego deja de elegir y luego apaga el FAR.

Mostrar FAR (boton de la barra de vistas; alternar_far; boton_far dice si se ve):
  - en la vista Contexto esta siempre (si la unidad tiene fachadas con FAR) y prende o
    apaga el dibujo. Al prenderlo parte con la fachada de arriba (la que mira a +y en la
    pantalla: far_inicial). Con el FAR prendido, un clic en una fachada de la unidad
    (Seleccionar o Mover, fuera de los volumenes) solo cambia la orientacion dibujada
    (fachada_en): la unidad no se elige ni se edita aca;
  - en las otras vistas aparece con un muro elegido que tiene FAR (exterior, o tambien
    adiabatico con el criterio far.orientaciones: unidad de config/cev.yaml) y lleva a
    la vista Contexto con el FAR de ese muro.
El dibujo (st["far_o"]): los muros de esa orientacion, el punto de referencia, el
semicirculo con sus divisiones y las obstrucciones. Una orientacion a la vez.

Arbol (paneles.py): grupo Contexto con una fila por volumen; al elegirlo (en el arbol,
la vista Contexto o el 3D) se despliega panel(). Con un dibujo con problemas no hay
arbol: detalle() muestra entonces el panel suelto. far(): la tabla de obstrucciones
remotas que van a la ficha, por orientacion (las de fachadas adiabaticas, marcadas), en
la caja Detalles modelo.

Estado: st["sel_ctx"] (volumen elegido, tambien en el 3D), st["cx"] (puntos que se
estan dibujando y arrastre), st["far_o"] (orientacion dibujada), st["_far_boton"]
(el boton Mostrar FAR esta visible) y st["_far"] (ultimo FAR de la tabla).
Textos: TX, cambiables en config/editor.yaml (vista_contexto.textos).
E: el contexto del editor (app.py).
"""
from __future__ import annotations

import math
from functools import partial

from nicegui import ui

from herramientas.unidad import contexto as cx
from herramientas.unidad import contexto_far
from herramientas.unidad import edicion_contexto as ec
from herramientas.unidad import editor
from herramientas.unidad import vista_contexto as vc
from herramientas.unidad.contexto_far import orientacion
from herramientas.unidad.modelo import area_firmada

from .piezas import num

HERRAMIENTAS = {"ctx_rect": "rect", "ctx_poli": "poli"}
VISIBLES = ("seleccionar", "mover", "ctx_rect", "ctx_poli", "borrar")
CURSOR_FACHADA = "pointer"        # sobre una fachada con el FAR prendido (vista_contexto.cursor_fachada)
TX = {
    "titulo": "Volumen de contexto",
    "nombre": "Nombre",
    "h": "Altura sobre el terreno [m]",
    "medidas": "Planta",
    "medidas_valor": "{ancho} × {fondo} m",
    "ubicacion": "Ubicación desde la unidad",
    "separacion": "Separación de {cara} ({rumbo}) [m]",
    "desfase": "Desfase del plano {cara} ({rumbo}) [m]",
    "ayuda_ubicacion": "Separación: distancia libre entre la cara exterior de la unidad y el volumen. "
                       "Desfase: cuánto sobresale el volumen del plano de esa cara (negativo: queda por "
                       "dentro). Cambia el número para mover el volumen.",
    "sin_unidad": "Dibuja la unidad para ubicar el volumen desde ella.",
    "editar": "Editar en la vista Contexto",
    "eliminar": "Eliminar volumen",
    # arbol
    "grupo": "Contexto",
    "grupo_ayuda": "Volúmenes del entorno (FAR dibujado). Lo que entra a la ficha está en Detalles modelo; "
                   "en la vista Contexto, «Mostrar FAR» lo dibuja y un clic en una fachada cambia la "
                   "orientación.",
    "fila": "{h} m · {area} m²",
    "vacio": "Sin volúmenes: dibújalos en la vista Contexto.",
    # tabla FAR (caja Detalles modelo)
    "far_titulo": "Obstrucciones remotas (FAR)",
    "far_ayuda": "Lo que se escribe en la ficha: una tabla por orientación con fachada, medida desde su "
                 "punto de referencia. Con el criterio «unidad» también las fachadas adiabáticas: el caso de "
                 "referencia gira la vivienda y sus ventanas leen el FAR de esas orientaciones.",
    "far_sin_puntos": "La unidad no tiene fachadas con FAR: no hay puntos de referencia.",
    "far_punto": "{o} · punto a {z} m sobre el terreno",
    "far_adiabatica": " · fachada adiabática",
    "far_sin": "Ningún volumen obstruye esta orientación.",
    "far_columnas": ["Div.", "Volumen", "A", "B", "D"],
    "far_omitida": "{volumen} (división {division}) no entra: {motivo}",
    "motivos": {"descarte": "obstrucción menor (descarte)", "maximo": "hay más de 8 en esta orientación"},
    "far_error": "No se pudo calcular el FAR del contexto.",
    # Mostrar FAR
    "far_boton": "Mostrar FAR (en la vista Contexto, un clic en una fachada cambia la orientación)",
    "far_elige": "Elige un muro con FAR (exterior, o también adiabático con el criterio «unidad»).",
    "far_sin_punto": "Ese muro no define un punto de referencia (altura libre menor que far.muro_min).",
}


def _vc(E) -> dict:
    return E.cfg.get("vista_contexto") or {}


def textos(cfg: dict) -> dict:
    extra = (cfg.get("vista_contexto") or {}).get("textos") or {}
    t = {**TX, **extra}
    t["motivos"] = {**TX["motivos"], **(extra.get("motivos") or {})}
    return t


def estilo(E) -> dict:
    return vc.estilo(E.cfg["planta"], _vc(E), textos(E.cfg))


def espesor(E) -> float:
    if _vc(E).get("cotas_desde", "exterior") == "interior":
        return 0.0
    return float(E.cfg["modelo3d"]["espesor_muro"])


def paso(E) -> float:
    return float(_vc(E).get("snap_m", 0.5))


def radio(E) -> float:
    return E.metros(E.cfg["captura"]["radio_px"])


def estado(E) -> dict:
    """Puntos que se estan dibujando y arrastre; se limpian al cambiar de herramienta."""
    s = E.st.setdefault("cx", {"pts": [], "arr": None, "herr": None})
    if s["herr"] != E.st["herr"]:
        s.update(pts=[], arr=None, herr=E.st["herr"])
    return s


def activo(E):
    """Indice del volumen elegido (si todavia existe), o None."""
    i = E.st.get("sel_ctx")
    return i if i is not None and 0 <= i < len(E.st["u"].contexto) else None


def elegir(E, i) -> None:
    """Elige el volumen i (None: ninguno) y deja de elegir lo de la unidad."""
    E.st.update(sel=None, sel_vano=None, sel_hz=None, sel_ctx=i)
    E.refrescar_seleccion()


def eliminar(E, i: int) -> None:
    E.st["sel_ctx"] = None
    E.aplicar(cx.eliminar, i)


def _crear(E, f, *args) -> None:
    """Crea un volumen con f (contexto.rectangulo o contexto.polilinea) y lo elige."""
    s = estado(E)
    try:
        nueva = f(E.st["u"], *args, float(_vc(E).get("altura_defecto", 9.0)))
    except ValueError as ex:
        ui.notify(str(ex), type="warning")
        return
    s["pts"].clear()
    E.st["cursor"] = None
    if E.aplicar(lambda _u: nueva):
        elegir(E, len(E.st["u"].contexto) - 1)


# ==================================================================== Mostrar FAR
def _con_far(x) -> bool:
    """El pano lleva FAR: exterior, o cualquiera con el criterio far.orientaciones: unidad."""
    return x.exterior or contexto_far.config()["orientaciones"] == "unidad"


def orientacion_muro(E):
    """Orientacion de la ficha del muro elegido si esa fachada lleva FAR, o None."""
    ma, g = E.muro_activo(), E.st.get("g")
    if ma is None or g is None:
        return None
    x = next((p for p in g.panos if (p.nivel, p.lado, p.tramo) == ma), None)
    return orientacion(x.azimut) if x is not None and _con_far(x) else None


def _puntos(E) -> list:
    g = E.st.get("g")
    if g is None:
        return []
    try:
        return contexto_far.puntos(E.st["u"], g)
    except Exception as ex:                       # el boton no debe romper la barra
        print(f"FAR (puntos): {type(ex).__name__}: {ex}", flush=True)
        return []


def far_inicial(E):
    """Orientacion con que parte el FAR en la vista Contexto: la fachada de arriba (su
    semicirculo mira a +y de la planta, lo mas cerca de 0 grados), o None."""
    ps = _puntos(E)
    if not ps:
        return None
    return min(ps, key=lambda pf: abs(contexto_far.normalizar_azimut(pf.punto.azimut))).orientacion


def boton_far(E) -> bool:
    """El boton Mostrar FAR se ve: en la vista Contexto, si la unidad tiene fachadas con FAR;
    en las otras, con un muro elegido que lleva FAR."""
    if E.st["modo"] == "contexto":
        return bool(_puntos(E))
    return orientacion_muro(E) is not None


def alternar_far(E) -> None:
    """Vista Contexto: prende (desde la fachada de arriba) o apaga el FAR. Otras vistas: va a la
    vista Contexto con el FAR del muro elegido."""
    st = E.st
    T = textos(E.cfg)
    if st["modo"] == "contexto":
        if st.get("far_o"):
            st["far_o"] = None
        else:
            o = far_inicial(E)
            if o is None:
                ui.notify(T["far_sin_puntos"], type="warning")
                return
            st["far_o"] = o
        E.refrescar_vistas()
        E.refrescar_lienzo()
        return
    o = orientacion_muro(E)
    if o is None:
        ui.notify(T["far_elige"], type="warning")
        return
    if not any(p.orientacion == o for p in _puntos(E)):
        ui.notify(T["far_sin_punto"], type="warning")
        return
    st["far_o"] = o
    E.ir_a("contexto")                             # redibuja la vista y la barra (boton prendido)


def _distancia_segmento(p, a, b) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def fachada_en(E, p):
    """Orientacion de la fachada de la unidad bajo p (con FAR y punto de referencia), o None.
    Toma el muro mas cercano, con una tolerancia del radio de captura mas el espesor del muro."""
    g = E.st.get("g")
    if g is None:
        return None
    tol = radio(E) + espesor(E)
    cerca = [(_distancia_segmento(p, x.a, x.b), x) for x in g.panos if _con_far(x) and x.largo > 0]
    cerca = [c for c in cerca if c[0] <= tol]
    if not cerca:
        return None
    o = orientacion(min(cerca, key=lambda c: c[0])[1].azimut)
    return o if any(pf.orientacion == o for pf in _puntos(E)) else None


def _cambiar_fachada(E, tipo: str, p) -> bool:
    """Con el FAR prendido, Seleccionar o Mover fuera de los volumenes: un clic en una fachada
    cambia la orientacion dibujada (y el cursor lo anuncia). True si lo atendio."""
    st = E.st
    if not st.get("far_o") or st["herr"] not in ("seleccionar", "mover") or estado(E)["arr"] is not None:
        return False
    u, r = st["u"], radio(E)
    i = activo(E)
    if cx.tocar(u, p, r) is not None or (i is not None and ec.tocar_asa(u.contexto[i].vertices, p, r)):
        return False
    o = fachada_en(E, p)
    if tipo == "mousemove":
        if o is not None:
            E.poner_cursor(CURSOR_FACHADA)
            return True
        E.poner_cursor(E.cfg["herramientas"][st["herr"]]["cursor"])
        return False
    if tipo == "mousedown" and o is not None:
        if o != st["far_o"]:
            st["far_o"] = o
            E.refrescar_lienzo()
        return True
    return False


def _dibujo_far(E):
    """(PuntoFar, ResultadoPunto, muros) de la orientacion que se muestra, o None."""
    st = E.st
    o, g = st.get("far_o"), st.get("g")
    if not o or g is None:
        return None
    try:
        pf, res = contexto_far.punto(E.actual(), g, o)
    except Exception as ex:                       # el dibujo del FAR no debe romper la vista
        print(f"FAR del muro: {type(ex).__name__}: {ex}", flush=True)
        return None
    if pf is None:
        return None
    return pf, res, [(p.a, p.b) for p in g.panos if p.id in pf.muros]


# ==================================================================== raton
def _dibujar(E, modo: str, tipo: str, p, libre: bool) -> None:
    st, s = E.st, estado(E)
    pts = s["pts"]
    cierre = E.metros(E.cfg["captura"]["cierre_px"])
    if modo == "poli" and len(pts) >= 3 and editor.distancia(p, pts[0]) <= cierre:
        q = pts[0]
    else:
        q = ec.ajustar(st["u"], p, pts[-1] if pts else None, modo, libre, paso(E), espesor(E))
    st["cursor"] = q
    if tipo == "mousedown":
        if modo == "rect":
            if not pts:
                pts.append(q)
            elif editor.distancia(q, pts[0]) > 1e-9:
                _crear(E, cx.rectangulo, pts[0], q)
                return
        elif len(pts) >= 3 and q == pts[0]:
            _crear(E, cx.polilinea, list(pts))
            return
        elif not pts or editor.distancia(q, pts[-1]) > 1e-9:
            pts.append(q)
    E.refrescar_lienzo()


def _mover(E, tipo: str, p, libre: bool) -> None:
    st, s = E.st, estado(E)
    u = st["u"]
    r = radio(E)
    i = activo(E)
    if tipo == "mousedown":
        asa = ec.tocar_asa(u.contexto[i].vertices, p, r) if i is not None else None
        if asa is None:
            j = cx.tocar(u, p, r)
            if j != i:
                elegir(E, j)
            i, asa = j, (("cuerpo", 0) if j is not None else None)
        s["arr"] = (i, asa, p) if asa is not None else None
        st["previa"] = None
        E.refrescar_lienzo()
    elif tipo == "mousemove" and s["arr"] is not None:
        j, asa, p0 = s["arr"]
        try:
            st["previa"] = ec.arrastrar(u, j, asa, p0, p, libre, paso(E))
        except ValueError:
            pass
        E.refrescar_lienzo()
    elif tipo == "mouseup" and s["arr"] is not None:
        s["arr"] = None
        previa, st["previa"] = st["previa"], None
        if previa is not None and previa != u:
            E.aplicar(lambda _u: previa)
        else:
            E.refrescar_lienzo()
    elif tipo == "mousemove" and i is not None:
        vs = u.contexto[i].vertices
        E.poner_cursor(ec.cursor(ec.tocar_asa(vs, p, r), vs) or E.cfg["herramientas"]["mover"]["cursor"])


def raton(E, tipo: str, p, libre: bool) -> None:
    st = E.st
    h = st["herr"]
    modo = HERRAMIENTAS.get(h)
    if tipo == "dblclick":
        s = estado(E)
        if modo == "poli" and len(s["pts"]) >= 3:
            _crear(E, cx.polilinea, list(s["pts"]))
        return
    if modo:
        _dibujar(E, modo, tipo, p, libre)
        return
    if _cambiar_fachada(E, tipo, p):              # FAR prendido: un clic en una fachada la muestra
        return
    if h == "mover":
        _mover(E, tipo, p, libre)
        return
    if tipo != "mousedown":
        return
    i = cx.tocar(st["u"], p, radio(E))
    if h == "borrar":
        if i is not None:
            eliminar(E, i)
        return
    elegir(E, i)


def escape(E) -> bool:
    """Cancela lo que se dibuja o arrastra; si no hay nada, deja de elegir el volumen; si no,
    apaga el FAR. True si hizo algo."""
    st, s = E.st, estado(E)
    if s["pts"] or s["arr"] is not None:
        s["pts"].clear()
        s["arr"] = None
        st["previa"], st["cursor"] = None, None
        E.refrescar_lienzo()
        return True
    if activo(E) is not None:
        elegir(E, None)
        return True
    if st.get("far_o"):
        st["far_o"] = None
        E.refrescar_vistas()
        E.refrescar_lienzo()
        return True
    return False


def suprimir(E) -> None:
    i = activo(E)
    if i is not None:
        eliminar(E, i)


def svg(E) -> str:
    st = E.st
    v = st.get("vista_ctx")
    if v is None:
        return ""
    h = st["herr"]
    modo = HERRAMIENTAS.get(h)
    s = estado(E)
    return vc.contenido(E.actual(), v, estilo(E), espesor(E), sel=activo(E), borrador=s["pts"] if modo else (),
                        cursor=st["cursor"] if modo else None, modo=modo, asas=h == "mover", far=_dibujo_far(E))


# ==================================================================== detalle del volumen
def _nombre(E, i: int, valor) -> None:
    nuevo = str(valor or "").strip()
    if nuevo and nuevo != E.st["u"].contexto[i].nombre:
        E.aplicar(cx.editar, i, nombre=nuevo, _paneles=False)


def panel(E, titulo: bool = True) -> None:
    """Datos del volumen elegido: nombre, altura, planta, ubicacion desde la unidad y eliminar."""
    i = activo(E)
    if i is None:
        return
    st, P = E.st, E.P
    T = textos(E.cfg)
    u = st["u"]
    c = u.contexto[i]
    esp = espesor(E)
    if titulo:
        ui.label(T["titulo"]).classes("titulo-componente")
    (ui.input(T["nombre"], value=c.nombre, on_change=lambda e: _nombre(E, i, e.value))
     .props(f"dense debounce={E.cfg['debounce_ms']}").classes("w-full"))
    P.numero(T["h"], c.h, lambda v: E.aplicar(cx.editar, i, h=float(v), _paneles=False), 0.1, None, 0.5)
    xs, ys = [p[0] for p in c.vertices], [p[1] for p in c.vertices]
    P.dato(T["medidas"], T["medidas_valor"].format(ancho=num(max(xs) - min(xs)), fondo=num(max(ys) - min(ys))))
    P.subtitulo(T.get("ubicacion"))
    cs = cx.cotas(u, c.vertices, esp)
    if not any(cs.values()):
        P.nota(T.get("sin_unidad"))
    for eje in ("y", "x"):
        k = cs[eje]
        if k is None:
            continue
        etiqueta = T[k.tipo].format(cara=k.cara.id, rumbo=orientacion(k.cara.azimut))
        P.numero(etiqueta, round(k.distancia, 2),
                 lambda v, eje=eje: E.aplicar(cx.separar, i, eje, float(v), esp), None, None, paso(E))
    P.explicacion(T.get("ayuda_ubicacion"))
    with ui.element("div").classes("acciones"):
        if st["modo"] != "contexto":
            P.accion(T["editar"], lambda: E.ir_a("contexto"))
        P.accion(T["eliminar"], partial(eliminar, E, i), peligro=True)


def detalle(E) -> None:
    """Panel suelto del volumen elegido, arriba del arbol (lo llama app.py). Solo cuando no hay
    arbol (dibujo con problemas); si no, el panel se despliega en su fila del grupo Contexto."""
    if E.st.get("g") is not None or activo(E) is None:
        return
    with ui.element("div").classes("detalle-suelto"):
        panel(E, titulo=True)


# ==================================================================== arbol
def resumen(E) -> str:
    """Texto de la cabecera del grupo: cuantos volumenes hay."""
    n = len(E.st["u"].contexto)
    return str(n) if n else ""


def filas(E, fila, desplegar) -> None:
    """Una fila por volumen (fila y desplegar: los del arbol de paneles.py)."""
    T = textos(E.cfg)
    u = E.st["u"]
    act_i = activo(E)
    if not u.contexto:
        E.P.nota(T.get("vacio"), "subnivel")
    for i, c in enumerate(u.contexto):
        act = i == act_i
        fila(c.nombre, T["fila"].format(h=num(c.h, 1), area=num(abs(area_firmada(c.vertices)), 1)),
             partial(elegir, E, None if act else i), activa=act)
        if act:
            desplegar(lambda: panel(E, titulo=False))


# ==================================================================== tabla FAR (Detalles modelo)
def _far(E):
    """contexto_far.ResultadoFar de la unidad (se recalcula solo si la unidad cambio)."""
    st = E.st
    c = st.get("_far")
    if c is not None and c[0] is st["u"] and c[1] is st["g"]:
        return c[2]
    r = contexto_far.calcular(st["u"], st["g"])
    st["_far"] = (st["u"], st["g"], r)
    return r


def far(E) -> None:
    """Obstrucciones remotas que van a la ficha, una tabla por orientacion con punto de
    referencia (nada si la unidad no tiene volumenes de contexto)."""
    st, P = E.st, E.P
    T = textos(E.cfg)
    u, g = st["u"], st["g"]
    if not u.contexto or g is None:
        return
    P.subtitulo(T.get("far_titulo"))
    P.explicacion(T.get("far_ayuda"))
    try:
        tabla = contexto_far.tabla(_far(E))
        dec = int(contexto_far.config()["decimales"])
    except Exception as ex:                       # el FAR no debe impedir ver las tablas
        print(f"FAR del contexto: {type(ex).__name__}: {ex}", flush=True)
        P.nota(T.get("far_error"))
        return
    if not tabla:
        P.nota(T.get("far_sin_puntos"))
        return
    cab = T["far_columnas"]
    cols = [{"name": f"c{i}", "label": c, "field": f"c{i}", "align": "left" if i == 1 else "right"}
            for i, c in enumerate(cab)]
    for x in tabla:
        rotulo = T["far_punto"].format(o=x["orientacion"], z=num(x["z"], 1))
        if not x.get("exterior", True):
            rotulo += T.get("far_adiabatica") or ""
        P.nota(rotulo)
        if x["filas"]:
            rows = [{"_k": r, "c0": d, "c1": v, "c2": num(a, dec), "c3": num(b, dec), "c4": num(w, dec)}
                    for r, (d, v, a, b, w) in enumerate(x["filas"])]
            (ui.table(columns=cols, rows=rows, row_key="_k", pagination=0)
             .props("dense flat hide-bottom").classes("w-full tabla"))
        else:
            P.nota(T.get("far_sin"))
        for d, v, motivo in x["omitidas"]:
            P.nota(T["far_omitida"].format(volumen=v, division=d, motivo=T["motivos"].get(motivo, motivo)))
