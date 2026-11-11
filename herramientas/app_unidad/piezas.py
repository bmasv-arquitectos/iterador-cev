# -*- coding: utf-8 -*-
"""
Piezas de interfaz del editor: botones con icono, grupos, botones segmentados,
acciones, datos, numeros, listas y textos, con la apariencia de estilo.css. No
tienen logica: las usan app.py y las cajas (paneles.py, calculo_ui.py), y otra
herramienta de la caja puede reutilizarlas tal cual.

Textos (config/editor.yaml):
  - un texto vacio ("" o null) no se muestra: nota(), explicacion(), subtitulo()
    y ayuda() no crean nada. Asi se elimina un texto sin tocar el codigo (conviene
    dejar la clave con "" en vez de borrarla).
  - las explicaciones ("ayudas") se muestran segun interfaz.ayudas:
      tooltip  al dejar el cursor sobre el boton o la fila (por defecto);
      texto    como texto gris en la caja (y la barra de estado abajo);
      ninguna  no se muestran.
    El tooltip aparece tras interfaz.tooltip_ms y mide como maximo
    interfaz.ayuda_ancho_px; un salto de linea (\n) en el texto se respeta.

Descargas (descargar_bytes): en el navegador, una descarga normal; en la ventana propia
(pywebview), el «Guardar como» de Windows: el archivo queda solo donde el usuario elige
(textos en comun/distribucion.yaml, ventana.textos).
"""
from __future__ import annotations

from functools import partial
from pathlib import Path

from nicegui import app, background_tasks, ui

ICONOS = Path(__file__).parent / "iconos"


def num(v, d=2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def icono_url(nombre: str | None) -> str | None:
    """/iconos/<nombre>.png si existe, si no .svg (con la fecha, para no usar uno viejo en cache)."""
    if not nombre:
        return None
    for ext in ("png", "svg"):
        f = ICONOS / f"{nombre}.{ext}"
        if f.exists():
            return f"/iconos/{f.name}?v={int(f.stat().st_mtime)}"
    return None


def nativo() -> bool:
    """La app corre en su ventana propia (pywebview), no en un navegador."""
    return getattr(getattr(app, "native", None), "main_window", None) is not None


def _textos_ventana() -> dict:
    from herramientas.comun import app_config
    return app_config.ventana()["textos"]


async def _guardar_como(cliente, datos: bytes, nombre: str) -> None:
    """«Guardar como» de Windows y el archivo en la ruta elegida (nada si se cancela)."""
    import webview

    tx = _textos_ventana()
    tipo = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
    if tipo is None:
        tipo = webview.SAVE_DIALOG
    ext = Path(nombre).suffix.lstrip(".")
    tipos = (f"{ext.upper()} (*.{ext})", tx["todos"]) if ext else ()
    try:
        r = await app.native.main_window.create_file_dialog(tipo, save_filename=nombre, file_types=tipos)
    except Exception as ex:
        with cliente:
            ui.notify(tx["error_dialogo"].format(error=ex), type="negative")
        return
    if not r:
        return                                   # cancelado
    ruta = Path(r if isinstance(r, str) else r[0])
    try:
        ruta.write_bytes(datos)
    except OSError as ex:
        with cliente:
            ui.notify(tx["error_guardar"].format(error=ex), type="negative")
        return
    with cliente:
        ui.notify(tx["guardado"].format(ruta=ruta), type="positive")


def descargar_bytes(datos: bytes, nombre: str) -> None:
    if nativo():
        background_tasks.create(_guardar_como(ui.context.client, datos, nombre), name="guardar_como")
        return
    f = getattr(ui.download, "content", None)        # NiceGUI 3
    if f is not None:
        f(datos, nombre)
    else:
        ui.download(datos, nombre)


def html(contenido: str, clases: str = ""):
    """ui.html sin sanear (NiceGUI 3 pide sanitize; NiceGUI 2 no lo conoce)."""
    try:
        el = ui.html(contenido, sanitize=False)
    except TypeError:
        el = ui.html(contenido)
    return el.classes(clases) if clases else el


def unir(*textos) -> str:
    """Los textos no vacios, uno por linea."""
    return "\n".join(str(t) for t in textos if t)


class Piezas:
    """cfg: config/editor.yaml (usa debounce_ms e interfaz: tooltip_ms, ayudas, ayuda_ancho_px)."""

    def __init__(self, cfg: dict):
        ic = cfg["interfaz"]
        self.debounce = cfg["debounce_ms"]
        self.tooltip = ic.get("tooltip_ms", 500)
        self.ayudas = ic.get("ayudas") or "tooltip"
        self.ancho_ayuda = int(ic.get("ayuda_ancho_px", 300))

    @property
    def con_tooltip(self) -> bool:
        return self.ayudas == "tooltip"

    @property
    def con_texto(self) -> bool:
        return self.ayudas == "texto"

    # ------------------------------------------------------------ textos
    def ayuda(self, texto):
        """Tooltip del elemento abierto (dentro de un with). Nada si el texto esta vacio."""
        if not texto:
            return None
        return (ui.tooltip(str(texto)).props(f"delay={self.tooltip} max-width={self.ancho_ayuda}px")
                .style("white-space: pre-line"))

    def ayuda_explicativa(self, texto):
        """Tooltip solo con ayudas: tooltip (para explicaciones)."""
        return self.ayuda(texto) if self.con_tooltip else None

    def nota(self, texto, clases: str = "texto-suave"):
        """Texto informativo (siempre visible, salvo que este vacio)."""
        if not texto:
            return None
        return ui.label(str(texto)).classes(clases)

    def explicacion(self, texto, clases: str = "texto-suave"):
        """Texto de ayuda: visible solo con ayudas: texto."""
        return self.nota(texto, clases) if self.con_texto else None

    def subtitulo(self, texto):
        return self.nota(texto, "subtitulo")

    # ------------------------------------------------------------ botones
    def boton(self, nombre, ayuda, al_click, activo=False, etiqueta=None, detalle=None):
        """Boton de la barra: icono (o texto) y, tras interfaz.tooltip_ms, su nombre (ayuda)
        y, con ayudas: tooltip, la explicacion (detalle) debajo."""
        url = None if etiqueta else icono_url(nombre)
        with ui.element("div").classes("boton" + (" activo" if activo else "")) as b:
            if url:
                im = ui.element("img").classes("icono")
                im._props["src"] = url
                im._props["alt"] = ayuda or ""
            else:
                ui.label(etiqueta or ayuda or nombre).classes("boton-texto")
            self.ayuda(unir(ayuda, detalle if self.con_tooltip else None))
        if al_click is not None:
            b.on("click", al_click)
        return b

    def grupo(self):
        return ui.element("div").classes("grupo")

    def segmentado(self, opciones: dict, valor, al_cambiar):
        """Una opcion activa entre varias (al_cambiar(clave) al elegir otra)."""
        with self.grupo():
            for clave, texto in opciones.items():
                self.boton(None, None, None if clave == valor else partial(al_cambiar, clave),
                           activo=clave == valor, etiqueta=texto)

    def accion(self, texto, al_click, peligro=False, principal=False, ayuda=None):
        """Boton de accion; ayuda: explicacion en el tooltip (solo con ayudas: tooltip)."""
        clases = "accion" + (" peligro" if peligro else "") + (" principal" if principal else "")
        a = ui.element("div").classes(clases)
        with a:
            ui.label(texto)
            self.ayuda_explicativa(ayuda)
        a.on("click", al_click)
        return a

    # ------------------------------------------------------------ campos
    def dato(self, etiqueta, valor):
        with ui.element("div").classes("dato"):
            ui.label(etiqueta).classes("dato-etiqueta")
            ui.label(valor)

    def numero(self, etiqueta, valor, al_cambiar, minimo=None, maximo=None, paso=0.01, fmt="%.2f"):
        return (ui.number(etiqueta, value=valor, min=minimo, max=maximo, step=paso, format=fmt,
                          on_change=lambda e: e.value is not None and al_cambiar(e.value))
                .props(f"debounce={self.debounce} dense").classes("w-full"))

    def selector(self, etiqueta, opciones, valor, al_cambiar, ayuda=None):
        s = (ui.select(opciones, value=valor, label=etiqueta,
                       on_change=lambda e: e.value and e.value != valor and al_cambiar(e.value))
             .props("dense").classes("w-full"))
        if ayuda and self.con_tooltip:
            with s:
                self.ayuda(ayuda)
        return s
