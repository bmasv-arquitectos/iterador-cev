# -*- coding: utf-8 -*-
"""
Tablas de la envolvente (resumen.tablas) a CSV y a PDF, sin interfaz.

Las columnas, sus titulos y decimales son los de la caja Envolvente
(config/editor.yaml, envolvente.tablas): columna [campo, titulo] es texto y
[campo, titulo, decimales] es numero.

  csv_bytes   un CSV con una seccion por tabla (titulo, encabezados, filas, linea en
              blanco), separador ';' y coma decimal (Excel en Chile), utf-8 con BOM.
  pdf_bytes   A4 horizontal con titulo, lineas de encabezado y una tabla por grupo
              (PyMuPDF: Story + DocumentWriter). Estilo en CSS_PDF.
"""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

CSS_PDF = """
body { font-family: sans-serif; font-size: 8pt; color: #2b3440; }
h1 { font-size: 13pt; margin: 0 0 2pt 0; }
h2 { font-size: 9.5pt; margin: 10pt 0 3pt 0; color: #2b3440; }
p { margin: 0 0 1pt 0; color: #7b8692; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; color: #7b8692; font-weight: bold; border-bottom: 0.8pt solid #9aa4ad; padding: 2pt 4pt; }
td { border-bottom: 0.4pt solid #d6dce2; padding: 2pt 4pt; }
.n { text-align: right; }
"""


def num(v, d: int) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def celda(v, decimales=None, sin_dato: str = "—") -> str:
    if v is None or v == "":
        return sin_dato
    if decimales is not None and isinstance(v, (int, float)) and not isinstance(v, bool):
        return num(v, decimales)
    return str(v)


def secciones(tablas: dict, ecfg: dict, sin_dato: str | None = None) -> list:
    """[(titulo, encabezados, filas de texto, es_numero por columna)] de las tablas con datos."""
    sin = ecfg["textos"].get("sin_dato", "—") if sin_dato is None else sin_dato
    out = []
    for clave, spec in ecfg["tablas"].items():
        filas = tablas.get(clave) or []
        if not filas:
            continue
        cs = spec["columnas"]
        out.append((spec["titulo"], [c[1] for c in cs],
                    [[celda(f.get(c[0]), c[2] if len(c) > 2 else None, sin) for c in cs] for f in filas],
                    [len(c) > 2 for c in cs]))
    return out


def csv_bytes(tablas: dict, ecfg: dict, encabezado=()) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    for linea in encabezado:
        w.writerow([linea])
    if encabezado:
        w.writerow([])
    for titulo, cab, filas, _ in secciones(tablas, ecfg, ""):
        w.writerow([titulo])
        w.writerow(cab)
        w.writerows(filas)
        w.writerow([])
    return buf.getvalue().encode("utf-8-sig")


def _celda_html(etiqueta: str, texto: str, es_num: bool) -> str:
    clase = ' class="n"' if es_num else ""
    return f"<{etiqueta}{clase}>{escape(texto)}</{etiqueta}>"


def html(tablas: dict, ecfg: dict, titulo: str, lineas=()) -> str:
    partes = [f"<h1>{escape(titulo)}</h1>"] + [f"<p>{escape(x)}</p>" for x in lineas]
    for t, cab, filas, nums in secciones(tablas, ecfg):
        partes.append(f"<h2>{escape(t)}</h2><table>")
        partes.append("<tr>" + "".join(_celda_html("th", c, n) for c, n in zip(cab, nums)) + "</tr>")
        for f in filas:
            partes.append("<tr>" + "".join(_celda_html("td", c, n) for c, n in zip(f, nums)) + "</tr>")
        partes.append("</table>")
    return "<body>" + "".join(partes) + "</body>"


def _mupdf():
    try:
        import pymupdf as mu
    except ImportError:
        try:
            import fitz as mu
        except ImportError:
            raise RuntimeError("falta PyMuPDF (pip install pymupdf)") from None
    if not hasattr(mu, "Story"):
        raise RuntimeError("esta version de PyMuPDF no puede escribir el PDF: actualizala (pip install -U pymupdf)")
    return mu


def pdf_bytes(tablas: dict, ecfg: dict, titulo: str, lineas=(), margen: float = 36) -> bytes:
    mu = _mupdf()
    story = mu.Story(html=html(tablas, ecfg, titulo, lineas), user_css=CSS_PDF)
    buf = io.BytesIO()
    w = mu.DocumentWriter(buf)
    pagina = mu.paper_rect("a4-l")
    zona = pagina + (margen, margen, -margen, -margen)
    mas = True
    while mas:
        dev = w.begin_page(pagina)
        mas, _ = story.place(zona)
        story.draw(dev)
        w.end_page()
    w.close()
    return buf.getvalue()
