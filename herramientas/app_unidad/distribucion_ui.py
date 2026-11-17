# -*- coding: utf-8 -*-
"""
Piezas de interfaz de la distribucion (comun/app_config.py y comun/distribucion.yaml):

  preparar(cfg)   ajusta la configuracion del editor antes de armar la pagina: rotulo con la
                  version, solo los motores del modo (sin Excel), el aviso bajo el resultado y,
                  en la web, sin la carpeta del servidor en el detalle del calculo y con el
                  motor en procesos aparte con fila de espera (unidad/cola_calculo.py:
                  web.calculo_en_procesos, calculos_simultaneos, cola_max y textos);
  aviso_inicial() el aviso legal al abrir (una vez en escritorio, cada vez en la web);
  boton_acerca()  boton fijo "Acerca de" (version, creditos, codigo fuente, licencia, nota
                  de la plantilla y, en la web, creditos.web).
Estilo: estilo.css (.aviso-legal, .acerca-de, .boton-acerca).
"""
from __future__ import annotations

from nicegui import ui

from herramientas.comun import app_config as ac


def preparar(cfg: dict) -> dict:
    cfg.setdefault("interfaz", {})["titulo_corto"] = ac.titulo_barra()
    cal = cfg.setdefault("calculo", {})
    pedidos = cal.get("motores") or {"python": "Motor Python"}
    cal["motores"] = {k: t for k, t in pedidos.items() if k in ac.motores()} or {"python": "Motor Python"}
    if ac.aviso().get("en_resultados", True):
        cal["aviso_legal"] = ac.texto_aviso()
    if ac.es_web():
        w = ac.opciones_web()
        cal["mostrar_carpeta"] = bool(w.get("mostrar_carpeta", False))
        cal["en_procesos"] = bool(w.get("calculo_en_procesos", True))
        cal["simultaneos"] = int(w.get("calculos_simultaneos", 2))
        cal["cola_max"] = int(w.get("cola_max", 20))
        cal["textos_cola"] = dict(w.get("textos") or {})
    return cfg


def aviso_inicial():
    """El dialogo del aviso legal, si corresponde (no se cierra sin aceptar)."""
    if not ac.debe_mostrar_aviso():
        return None
    a = ac.aviso()
    with ui.dialog().props("persistent") as d, ui.card().classes("aviso-legal"):
        ui.label(a.get("titulo") or "").classes("aviso-legal-titulo")
        ui.label(ac.texto_aviso())

        def aceptar():
            ac.marcar_aviso_aceptado()
            d.close()

        with ui.row().classes("w-full justify-end"):
            ui.button(a.get("boton") or "Entiendo", on_click=aceptar).props("no-caps")
    d.open()
    return d


def acerca_de() -> None:
    c = ac.creditos()
    with ui.dialog() as d, ui.card().classes("acerca-de"):
        ui.label(f"{ac.nombre()} {ac.version()}").classes("acerca-de-titulo")
        ui.label(c.get("autores") or "")
        if c.get("url"):
            ui.link(c["url"], c["url"], new_tab=True)
        if c.get("licencia"):
            ui.label(c["licencia"])
        if c.get("codigo"):
            with ui.row().classes("items-center gap-1"):
                ui.label(c.get("codigo_texto") or "Código fuente:")
                ui.link(c["codigo"], c["codigo"], new_tab=True)
        if ac.es_web() and c.get("web"):
            ui.label(" ".join(str(c["web"]).split())).classes("acerca-de-nota")
        if c.get("plantilla"):
            ui.label(" ".join(str(c["plantilla"]).split())).classes("acerca-de-nota")
        ui.separator()
        ui.label(ac.texto_aviso()).classes("aviso-legal-texto")
        with ui.row().classes("w-full justify-end"):
            ui.button(c.get("cerrar") or "Cerrar", on_click=d.close).props("flat no-caps")
    d.open()


def boton_acerca():
    return (ui.button(ac.creditos().get("boton") or "Acerca de", on_click=acerca_de)
            .props("flat dense no-caps").classes("boton-acerca"))
