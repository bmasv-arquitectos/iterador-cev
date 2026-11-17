# -*- coding: utf-8 -*-
"""
El reporte de la unidad (como reporte.pdf) en HTML para imprimir, sin PyMuPDF: lo usa la version
web, donde PyMuPDF no existe (herramientas/web/reporte_web.py). El navegador lo imprime en A4
horizontal y el usuario elige «Guardar como PDF».

  pagina 1   encabezado (titulo, fecha y las lineas de resumen), el modelo 3D (la captura de la
             vista 3D o, si no hay, axonometria.svg), las plantas de cada nivel y la etiqueta;
  despues    el detalle de la envolvente (las tablas de exportar.html);
  todas      pie con el aviso de uso referencial y el nombre y la version del programa (la
             tabla .pagina repite un espacio al final de cada hoja para que el texto no quede
             debajo del pie).

Textos, colores y medidas: config/editor.yaml (reporte:), los mismos del PDF. El navegador no
numera las paginas de forma pareja, asi que aca no van numeros de pagina.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from xml.sax.saxutils import escape

from . import exportar
from .calculo_cev import vista as vista_etiqueta
from .reporte import aviso_pie, plantas_svg, vista_3d_svg

CSS = """
@page { size: A4 landscape; margin: 10mm 11mm 8mm 11mm; }
* { box-sizing: border-box; }
html, body { margin: 0; font-family: "Avenir Next", "Segoe UI", Arial, sans-serif; color: __TEXTO__;
             font-size: 8pt; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
table.pagina { width: 100%; border-collapse: collapse; }
table.pagina > tfoot td, table.pagina > tbody > tr > td { padding: 0; border: 0; }
.espacio-pie { height: 13mm; }
.hoja1 { height: 172mm; display: flex; flex-direction: column; break-after: page; }
header { border-bottom: 0.8pt solid __LINEA__; padding-bottom: 4pt; margin-bottom: 8pt; }
header .fila { display: flex; justify-content: space-between; align-items: baseline; }
header h1 { font-size: 17pt; margin: 0; }
header .fecha, header p { color: __SUAVE__; font-size: 9pt; margin: 2pt 0 0; }
.cuerpo { flex: 1; display: flex; gap: 14pt; min-height: 0; }
.izq { flex: 1; display: flex; flex-direction: column; gap: 10pt; min-width: 0; min-height: 0; }
.plantas { display: flex; gap: 8pt; min-height: 0; }
figure { margin: 0; display: flex; flex-direction: column; min-height: 0; min-width: 0; flex: 1 1 0; }
figcaption { font-size: 7pt; font-weight: 700; color: __SUAVE__; text-transform: uppercase;
             letter-spacing: 0.04em; margin-bottom: 3pt; }
.marco { flex: 1; min-height: 0; border: 0.6pt solid __LINEA__; padding: 3pt; display: flex; }
.marco img { width: 100%; height: 100%; object-fit: contain; }
figure.etiqueta { flex: 0 0 __ANCHO__pt; }
.etq svg { display: block; width: 100%; height: auto; }
.nota { color: __SUAVE__; font-size: 7.5pt; text-align: center; margin-top: 4pt; }
.pie { position: fixed; left: 0; right: 0; bottom: 0; background: __FONDO_ADV__; color: __ADV__; font-size: 7pt;
       padding: 3pt 6pt; display: flex; justify-content: space-between; gap: 12pt; }
.pie .programa { color: __SUAVE__; white-space: nowrap; }
.detalle h1 { font-size: 13pt; margin: 0 0 2pt; }
.detalle h2 { font-size: 9.5pt; margin: 10pt 0 3pt; }
.detalle p { margin: 0 0 1pt; color: __SUAVE__; }
.detalle table { border-collapse: collapse; width: 100%; }
.detalle th { text-align: left; color: __SUAVE__; font-weight: bold; border-bottom: 0.8pt solid #9aa4ad; padding: 2pt 4pt; }
.detalle td { border-bottom: 0.4pt solid __LINEA__; padding: 2pt 4pt; }
.detalle tr { break-inside: avoid; }
.detalle .n { text-align: right; }
"""


def con_viewbox(svg: str) -> str:
    """El SVG con viewBox (con su ancho y alto) para que escale dentro de una imagen."""
    i = svg.find("<svg")
    j = svg.find(">", i)
    if i < 0 or j < 0:
        return svg
    tag = svg[i:j]
    if "viewBox" in tag:
        return svg
    w = re.search(r'\bwidth="([\d.]+)', tag)
    h = re.search(r'\bheight="([\d.]+)', tag)
    if not (w and h):
        return svg
    return svg[:j] + f' viewBox="0 0 {w.group(1)} {h.group(1)}"' + svg[j:]


def imagen_svg(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(con_viewbox(svg).encode("utf-8")).decode("ascii")


def imagen(datos: bytes) -> str:
    tipo = "jpeg" if datos[:2] == b"\xff\xd8" else "png"
    return f"data:image/{tipo};base64," + base64.b64encode(datos).decode("ascii")


def css(rc: dict) -> str:
    c = rc["colores"]
    out = CSS
    for clave, valor in (("__TEXTO__", c["texto"]), ("__SUAVE__", c["suave"]), ("__LINEA__", c["linea"]),
                         ("__ADV__", c["advertencia"]), ("__FONDO_ADV__", c["fondo_advertencia"]),
                         ("__ANCHO__", str(float(rc.get("ancho_etiqueta_pt", 230))))):
        out = out.replace(clave, str(valor))
    return out


def _figura(titulo: str, src: str) -> str:
    return (f'<figure><figcaption>{escape(titulo)}</figcaption>'
            f'<div class="marco"><img src="{src}" alt="{escape(titulo)}"></div></figure>')


def html(u, g, tablas: dict, cfg: dict, res: dict | None = None, vista_3d: bytes | None = None,
         lineas=()) -> str:
    """El reporte en HTML. Mismos argumentos que reporte.pdf."""
    from herramientas.comun import app_config

    rc = cfg["reporte"]
    tt = rc["titulos"]
    p3 = float(rc.get("proporcion_3d", 0.62))
    src3d = imagen(vista_3d) if vista_3d else imagen_svg(vista_3d_svg(u, g, cfg["modelo3d"], rc))
    plantas = "".join(_figura(tt["plantas"].format(nivel=k + 1), imagen_svg(s))
                      for k, s in enumerate(plantas_svg(u, cfg["planta"], rc)))
    etiqueta = vista_etiqueta(res, cfg.get("calculo") or {})
    nota = f'<p class="nota">{escape(rc["sin_calculo"])}</p>' if res is None and rc.get("sin_calculo") else ""
    detalle = exportar.html(tablas, cfg["envolvente"], tt["envolvente"], lineas)
    detalle = detalle.removeprefix("<body>").removesuffix("</body>")
    try:
        programa = app_config.pie_reporte()
    except (OSError, KeyError, TypeError):
        programa = ""
    cabeza = "".join(f"<p>{escape(x)}</p>" for x in list(lineas)[:2])
    modelo = _figura(tt["modelo"], src3d).replace("<figure>", f'<figure style="flex: {p3} 1 0">', 1)
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        f'<title>{escape(rc.get("archivo") or "reporte")}</title><style>{css(rc)}</style></head><body>'
        f'<div class="pie"><span class="aviso">{escape(aviso_pie(rc))}</span>'
        f'<span class="programa">{escape(programa)}</span></div>'
        '<table class="pagina"><tfoot><tr><td><div class="espacio-pie"></div></td></tr></tfoot><tbody><tr><td>'
        '<section class="hoja1"><header><div class="fila">'
        f'<h1>{escape(rc["titulo"])}</h1><span class="fecha">{datetime.now():%d-%m-%Y %H:%M}</span></div>'
        f'{cabeza}</header><div class="cuerpo"><div class="izq">{modelo}'
        f'<div class="plantas" style="flex: {max(1 - p3, 0.1)} 1 0">{plantas}</div></div>'
        f'<figure class="etiqueta"><figcaption>{escape(tt["etiqueta"])}</figcaption>'
        f'<div class="etq">{etiqueta}</div>{nota}</figure></div></section>'
        f'<section class="detalle">{detalle}</section>'
        '</td></tr></tbody></table></body></html>'
    )
