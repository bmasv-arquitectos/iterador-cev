# -*- coding: utf-8 -*-
"""
Icono del Iterador CEV: tres flechas escalonadas con colores de la escala de
calificacion (como las de la etiqueta). Todo lo modificable (colores, largos, alto,
separacion, punta, margen y tamanos del .ico) esta en comun/distribucion.yaml (icono:).

  svg()            el icono en SVG (favicon de la ventana; NiceGUI acepta el texto SVG)
  png(tamano)      PNG con fondo transparente (necesita PyMuPDF)
  ico(destino)     .ico de Windows con todos los tamanos (PNG dentro), para el ejecutable
                   y el instalador (distribucion/preparar.py)
"""
from __future__ import annotations

import struct
from pathlib import Path

from .app_config import config

LADO = 256.0
DEFECTO = {
    "colores": ["#4C8A3F", "#ECD32C", "#A2282D"],   # A, D y G de app_cev/config/etiqueta.yaml
    "largos": [0.62, 0.81, 1.0],                     # fraccion del ancho util
    "alto_barra": 0.24,
    "separacion": 0.08,
    "punta": 0.13,
    "margen": 0.04,
    "tamanos": [16, 20, 24, 32, 40, 48, 64, 128, 256],
}


def opciones() -> dict:
    return {**DEFECTO, **(config().get("icono") or {})}


def svg(op: dict | None = None) -> str:
    o = op or opciones()
    m, h = o["margen"] * LADO, o["alto_barra"] * LADO
    sep, p = o["separacion"] * LADO, o["punta"] * LADO
    n = len(o["colores"])
    y = (LADO - (n * h + (n - 1) * sep)) / 2
    partes = []
    for color, largo in zip(o["colores"], o["largos"]):
        x0, x1 = m, m + float(largo) * (LADO - 2 * m)
        pts = ((x0, y), (x1 - p, y), (x1, y + h / 2), (x1 - p, y + h), (x0, y + h))
        partes.append(f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in pts)}" fill="{color}"/>')
        y += h + sep
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
            + "".join(partes) + "</svg>")


def _mupdf():
    try:
        import pymupdf as mu
    except ImportError:
        import fitz as mu
    return mu


def png(tamano: int, op: dict | None = None) -> bytes:
    mu = _mupdf()
    doc = mu.open(stream=svg(op).encode("utf-8"), filetype="svg")
    try:
        f = tamano / LADO
        return doc[0].get_pixmap(matrix=mu.Matrix(f, f), alpha=True).tobytes("png")
    finally:
        doc.close()


def ico(destino, op: dict | None = None) -> Path:
    """.ico con un PNG por tamano (Windows Vista en adelante los lee)."""
    o = op or opciones()
    tamanos = sorted({int(t) for t in o["tamanos"]})
    imagenes = [png(t, o) for t in tamanos]
    cab = struct.pack("<HHH", 0, 1, len(imagenes))
    pos = len(cab) + 16 * len(imagenes)
    entradas, datos = b"", b""
    for t, im in zip(tamanos, imagenes):
        entradas += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(im), pos + len(datos))
        datos += im
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cab + entradas + datos)
    return destino
