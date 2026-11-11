# -*- coding: utf-8 -*-
"""
Reporte PDF de una unidad (A4 horizontal), sin interfaz:

  pagina 1   encabezado (titulo, resumen de la unidad, resultado y fecha), el modelo
             3D (la captura de la vista 3D del editor o, si no hay, axonometria.svg),
             las plantas de cada nivel (vista_planta) y la etiqueta de calificacion;
  pagina 2+  el detalle de la envolvente (las tablas de exportar.html en un Story);
  todas      pie con el aviso legal de uso referencial (comun/distribucion.yaml,
             aviso.texto; si falta, reporte.advertencia de config/editor.yaml), el
             nombre y la version del programa y el numero de pagina; desde la 2, el
             titulo arriba.

Las imagenes se recortan al contenido (recortar: se quita el fondo uniforme de los
bordes) para que el dibujo use todo el recuadro; las plantas y la axonometria se
dibujan ademas con la proporcion de lo dibujado.
Textos, colores, medidas y lo que se dibuja: config/editor.yaml (reporte:).
Necesita PyMuPDF con Story (exportar._mupdf); el recorte usa numpy (si falta, no recorta).
"""
from __future__ import annotations

import io
from datetime import datetime

from herramientas.comun import app_config

from . import axonometria, exportar, modelo3d, vista_planta
from .calculo_cev import _etiqueta, mezclar


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def svg_a_png(svg: str, escala: float = 2.0) -> bytes:
    mu = exportar._mupdf()
    doc = mu.open(stream=svg.encode("utf-8"), filetype="svg")
    try:
        return doc[0].get_pixmap(matrix=mu.Matrix(escala, escala), alpha=False).tobytes("png")
    finally:
        doc.close()


def recortar(datos: bytes, tol: int = 14, margen: float = 0.03) -> bytes:
    """La imagen (PNG o JPEG) sin el fondo de los bordes: todo lo que se parece al color de la
    esquina superior izquierda (tolerancia tol, 0..255), dejando un margen (fraccion del lado mayor)."""
    try:
        import numpy as np
    except ImportError:
        return datos
    mu = exportar._mupdf()
    try:
        pix = mu.Pixmap(datos)
        if pix.alpha:
            pix = mu.Pixmap(pix, 0)
        if pix.n < 3:
            pix = mu.Pixmap(mu.csRGB, pix)
    except Exception:
        return datos
    w, h, n = pix.width, pix.height, pix.n
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(h, w, n)[:, :, :3]
    rgb = a.astype(np.int16)
    mascara = np.abs(rgb - rgb[0, 0]).max(axis=2) > tol
    filas, cols = np.where(mascara.any(axis=1))[0], np.where(mascara.any(axis=0))[0]
    if not len(filas):
        return datos
    m = int(round(margen * max(w, h)))
    y0, y1 = max(0, int(filas[0]) - m), min(h, int(filas[-1]) + 1 + m)
    x0, x1 = max(0, int(cols[0]) - m), min(w, int(cols[-1]) + 1 + m)
    if (y1 - y0) * (x1 - x0) >= 0.98 * w * h:
        return datos
    sub = np.ascontiguousarray(a[y0:y1, x0:x1])
    return mu.Pixmap(mu.csRGB, x1 - x0, y1 - y0, sub.tobytes(), 0).tobytes("png")


def plantas_svg(u, est_planta: dict, rc: dict) -> list:
    """Una planta por nivel, todas con el mismo encuadre y la proporcion de la unidad (reporte.planta)."""
    pts = [p for n in u.niveles for p in n.vertices]
    if not pts:
        return []
    pc = rc.get("planta") or {}
    est = mezclar(est_planta, pc.get("cambios"))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(max(xs) - min(xs), 0.5), max(max(ys) - min(ys), 0.5)
    ancho, m = float(pc.get("ancho_px", 900)), float(pc.get("margen_px", 70))
    alto = h * (ancho - 2 * m) / w + 2 * m
    v = vista_planta.encuadrar_unidad(u, {"ancho_px": ancho, "alto_px": alto, "margen_px": m,
                                          "extension_min_m": 0.0})
    return [vista_planta.svg_completo(u, k, v, est) for k in range(len(u.niveles))]


def vista_3d_svg(u, g, est3d: dict, rc: dict) -> str:
    return axonometria.svg(modelo3d.construir(u, g, est3d), est3d, rc.get("axonometria") or {})


def etiqueta_png(res: dict | None, calc_cfg: dict) -> bytes:
    ec, ecfg = _etiqueta(calc_cfg)
    p = ecfg["png"]
    return ec.png(ec.svg(res, ecfg, fuente=p.get("fuente")), p["escala"])


def _imagen(mu, p, rect, datos: bytes, titulo: str, col: dict, marco: bool = True) -> None:
    """Rotulo en mayusculas y la imagen debajo, centrada en el rectangulo."""
    p.insert_text((rect.x0, rect.y0 + 7), titulo.upper(), fontname="hebo", fontsize=7, color=col["suave"])
    r = mu.Rect(rect.x0, rect.y0 + 12, rect.x1, rect.y1)
    if marco:
        p.draw_rect(r, color=col["linea"], width=0.6)
        r = r + (3, 3, -3, -3)
    p.insert_image(r, stream=datos, keep_proportion=True)


def _encabezado(mu, p, titulo: str, lineas, W: float, M: float, col: dict) -> float:
    p.insert_text((M, M + 16), titulo, fontname="hebo", fontsize=17, color=col["texto"])
    fecha = datetime.now().strftime("%d-%m-%Y %H:%M")
    w = mu.get_text_length(fecha, fontname="helv", fontsize=9)
    p.insert_text((W - M - w, M + 16), fecha, fontname="helv", fontsize=9, color=col["suave"])
    y = M + 31
    for linea in list(lineas)[:2]:
        p.insert_text((M, y), linea, fontname="helv", fontsize=9, color=col["suave"])
        y += 12
    y += 1
    p.draw_line((M, y), (W - M, y), color=col["linea"], width=0.8)
    return y + 8


def aviso_pie(rc: dict) -> str:
    """El aviso de uso referencial del pie (el de distribucion.yaml; si falta, reporte.advertencia)."""
    try:
        return app_config.texto_aviso()
    except (OSError, KeyError, TypeError):
        return rc.get("advertencia") or ""


def _pies(mu, doc, rc: dict, W: float, H: float, M: float, col: dict) -> None:
    total = doc.page_count
    aviso = aviso_pie(rc)
    try:
        programa = app_config.pie_reporte()
    except (OSError, KeyError, TypeError):
        programa = ""
    for i, p in enumerate(doc):
        caja = mu.Rect(M, H - 30, W - M, H - 12)
        p.draw_rect(caja, color=None, fill=col["fondo_advertencia"])
        n = rc["pagina"].format(n=i + 1, total=total)
        if programa:
            n = f"{programa} · {n}"
        w = mu.get_text_length(n, fontname="helv", fontsize=7.5)
        p.insert_textbox(mu.Rect(M + 6, H - 28, W - M - 18 - w, H - 12), aviso, fontname="helv",
                         fontsize=7, color=col["advertencia"])
        p.insert_text((W - M - 6 - w, H - 18), n, fontname="helv", fontsize=7.5, color=col["suave"])
        if i > 0:
            p.insert_text((M, M - 10), rc["titulo"], fontname="helv", fontsize=7.5, color=col["suave"])


def pdf(u, g, tablas: dict, cfg: dict, res: dict | None = None, vista_3d: bytes | None = None,
        lineas=()) -> bytes:
    """cfg: config/editor.yaml completo (reporte, envolvente, modelo3d, planta, calculo).
    vista_3d: imagen (PNG o JPEG) de la vista 3D; sin ella, la axonometria.
    res: resultado del calculo (None: la etiqueta sale vacia con la nota reporte.sin_calculo)."""
    mu = exportar._mupdf()
    rc = cfg["reporte"]
    col = {k: _rgb(v) for k, v in rc["colores"].items()}
    tt = rc["titulos"]
    W, H = mu.paper_size("a4-l")
    M = float(rc.get("margen_pt", 32))
    escala = float(rc.get("escala_imagen", 2))
    rec = rc.get("recortar") or {}

    def ajustar(datos):
        if not rec.get("activo", True):
            return datos
        return recortar(datos, int(rec.get("tolerancia", 14)), float(rec.get("margen", 0.03)))

    doc = mu.open()
    p = doc.new_page(width=W, height=H)
    top = _encabezado(mu, p, rc["titulo"], lineas, W, M, col)
    bottom = H - 40
    ae = float(rc.get("ancho_etiqueta_pt", 230))
    xd = W - M - ae
    wi = xd - 18 - M
    h3 = (bottom - top) * float(rc.get("proporcion_3d", 0.62))
    img3d = ajustar(vista_3d or svg_a_png(vista_3d_svg(u, g, cfg["modelo3d"], rc), escala))
    _imagen(mu, p, mu.Rect(M, top, M + wi, top + h3), img3d, tt["modelo"], col)
    plantas = plantas_svg(u, cfg["planta"], rc)
    if plantas:
        sep = 10
        w1 = (wi - sep * (len(plantas) - 1)) / len(plantas)
        y0 = top + h3 + 12
        for k, s in enumerate(plantas):
            x0 = M + k * (w1 + sep)
            _imagen(mu, p, mu.Rect(x0, y0, x0 + w1, bottom), ajustar(svg_a_png(s, escala)),
                    tt["plantas"].format(nivel=k + 1), col)
    _imagen(mu, p, mu.Rect(xd, top, W - M, bottom - (26 if res is None else 0)), etiqueta_png(res, cfg["calculo"]),
            tt["etiqueta"], col, marco=False)
    if res is None:
        p.insert_textbox(mu.Rect(xd, bottom - 24, W - M, bottom), rc["sin_calculo"], fontname="helv", fontsize=7.5,
                         color=col["suave"], align=1)

    story = mu.Story(html=exportar.html(tablas, cfg["envolvente"], tt["envolvente"], lineas),
                     user_css=exportar.CSS_PDF)
    buf = io.BytesIO()
    w = mu.DocumentWriter(buf)
    pagina, zona = mu.Rect(0, 0, W, H), mu.Rect(M, M + 6, W - M, H - 40)
    mas = True
    while mas:
        dev = w.begin_page(pagina)
        mas, _ = story.place(zona)
        story.draw(dev)
        w.end_page()
    w.close()
    tabla = mu.open(stream=buf.getvalue(), filetype="pdf")
    doc.insert_pdf(tabla)
    tabla.close()
    _pies(mu, doc, rc, W, H, M, col)
    datos = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return datos
