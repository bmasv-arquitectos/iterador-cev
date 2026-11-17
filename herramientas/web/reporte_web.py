# -*- coding: utf-8 -*-
"""
El boton «Reporte (PDF)» de la interfaz del instalable, corriendo en el navegador
(nicegui_web.py). PyMuPDF no existe en el navegador, asi que:

  pdf(...)          reemplaza a unidad/reporte.pdf: arma el reporte en HTML (unidad/reporte_html.py)
                    y lo devuelve como Imprimible (bytes con el HTML adentro);
  descargar(...)    reemplaza a la descarga del editor (app.descargar_bytes): un Imprimible se
                    imprime (ventana de impresion del navegador: «Guardar como PDF») y lo
                    demas se descarga como siempre (piezas.descargar_bytes);
  activar(modulo)   pone los dos en app_unidad/app.py (lo llama nicegui_web.iniciar). En
                    escritorio no se usa: el instalable sigue haciendo el PDF con PyMuPDF.

El aviso que aparece al imprimir: config/editor.yaml, reporte.aviso_imprimir (si falta, AVISO).
"""
from __future__ import annotations

import json

AVISO = "Se abrió la ventana de impresión: elige «Guardar como PDF» como destino."
# imprime el HTML desde un marco oculto con el tamano de una hoja A4 horizontal (96 dpi)
IMPRIMIR_JS = ("(function(h){const f=document.createElement('iframe');"
               "f.style.cssText='position:fixed;left:-20000px;top:0;width:1123px;height:794px;border:0';"
               "f.onload=()=>setTimeout(()=>{f.contentWindow.focus();f.contentWindow.print();"
               "setTimeout(()=>f.remove(),120000);},400);"
               "f.srcdoc=h;document.body.appendChild(f);})(%s)")


class Imprimible(bytes):
    """Lo que devuelve pdf(): pasa por el codigo del editor como si fueran los bytes del PDF."""
    html: str = ""
    aviso: str = AVISO


def pdf(u, g, tablas: dict, cfg: dict, res=None, vista_3d=None, lineas=()) -> Imprimible:
    from herramientas.unidad import reporte_html

    out = Imprimible(b"%PDF-imprimir")
    out.html = reporte_html.html(u, g, tablas, cfg, res, vista_3d, lineas)
    out.aviso = (cfg.get("reporte") or {}).get("aviso_imprimir") or AVISO
    return out


def imprimir(html: str, aviso: str = AVISO) -> None:
    from nicegui import ui

    ui.run_javascript(IMPRIMIR_JS % json.dumps(html))
    if aviso:
        ui.notify(aviso, timeout=6000)


def descargar(datos, nombre: str) -> None:
    if isinstance(datos, Imprimible):
        imprimir(datos.html, datos.aviso)
        return
    from herramientas.app_unidad import piezas

    piezas.descargar_bytes(datos, nombre)


def activar(modulo_app) -> None:
    from herramientas.unidad import reporte

    reporte.pdf = pdf
    modulo_app.descargar_bytes = descargar
