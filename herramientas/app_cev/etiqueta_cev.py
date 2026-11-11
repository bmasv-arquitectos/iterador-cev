# -*- coding: utf-8 -*-
"""
Etiqueta de la calificacion CEV: escala de flechas (A+ ... G) con la letra
obtenida destacada, y los datos de demanda y ahorro (calefaccion,
refrigeracion, total).

Dos disposiciones (config/etiqueta.yaml, disposicion):
  horizontal  la escala y a su derecha una tabla (la de app_cev);
  vertical    como las etiquetas de eficiencia energetica: la escala arriba,
              debajo la demanda total en grande (con la del caso base en gris)
              y luego calefaccion y refrigeracion; en cada columna, la demanda,
              la del caso base y el ahorro, en el orden de vertical.columnas.orden
              (la del editor de unidad).

Sin NiceGUI (testeable): svg(resultado, cfg) arma el SVG; png(svg) lo
rasteriza con PyMuPDF (ya esta en requirements); guardar() deja
etiqueta_cev.svg y etiqueta_cev.png en la carpeta de la iteracion.

La letra NO se calcula aca: se destaca la que entrega la planilla 03 (el
resultado de ejecucion.py). Todo lo visual (colores, medidas, textos,
formatos, orden, rotulos 'Mas/Menos eficiente') esta en config/etiqueta.yaml.

Los anchos de texto se miden con las metricas de Helvetica de PyMuPDF y las
posiciones se escriben explicitas (sin text-anchor), para que el navegador y
el PNG ubiquen los textos igual.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import yaml

try:
    import pymupdf as _mu
except ImportError:
    try:
        import fitz as _mu
    except ImportError:
        _mu = None

CONFIG = Path(__file__).parent / "config" / "etiqueta.yaml"
ORDEN_COLUMNAS = ("valor", "base", "ahorro")


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- formatos
def numero(v, decimales: int, fmt: dict) -> str:
    """Redondeo como Excel (mitad hacia afuera), coma decimal y sin '-0'."""
    if v is None:
        return fmt["sin_dato"]
    paso = Decimal(1).scaleb(-decimales)
    r = float(Decimal(repr(float(v))).quantize(paso, rounding=ROUND_HALF_UP))
    if r == 0:
        r = 0.0
    s = f"{abs(r):.{decimales}f}".replace(".", fmt["separador_decimal"])
    return (fmt["signo_menos"] if r < 0 else "") + s


def porcentaje(v, fmt: dict, sufijo: str) -> str:
    return fmt["sin_dato"] if v is None else numero(v, fmt["decimales_ahorro"], fmt) + sufijo


def normalizar_letra(v, letras) -> str | None:
    if v is None:
        return None
    s = str(v).strip().upper().replace(" ", "")
    return s if s in letras else None


def valores(res: dict | None, cfg: dict) -> dict:
    """Textos ya formateados de la flecha destacada y de los datos.
    base: demanda del caso base [calefaccion, refrigeracion, total] o None si no hay."""
    res = res or {}
    fmt = cfg["formato"]
    d = fmt["decimales_demanda"]
    positiva = fmt.get("refrigeracion_positiva", True)
    ref = res.get("demanda_ref")
    if ref is not None and positiva:
        ref = abs(ref)

    def base(clave, absoluto=False):
        v = res.get(clave)
        if v is None:
            return None
        return numero(abs(v) if absoluto else v, d, fmt)

    return {
        "letra": normalizar_letra(res.get("letra"), cfg["letras"]),
        "demanda": [numero(res.get("demanda_cal"), d, fmt), numero(ref, d, fmt),
                    numero(res.get("demanda"), d, fmt)],
        "ahorro": [porcentaje(res.get(k), fmt, fmt["sufijo_tabla"])
                   for k in ("ahorro_cal_pct", "ahorro_ref_pct", "ahorro_pct")],
        "flecha": (None if res.get("ahorro_pct") is None
                   else porcentaje(res["ahorro_pct"], fmt, fmt["sufijo_flecha"])),
        "base": [base("demanda_base_cal"), base("demanda_base_ref", positiva), base("demanda_base")],
    }


# --------------------------------------------------------------------------- dibujo
def ancho_texto(texto: str, tam: float, negrita: bool = False) -> float:
    if _mu is not None:
        try:
            return float(_mu.get_text_length(texto, fontname="hebo" if negrita else "helv",
                                             fontsize=tam))
        except Exception:
            pass
    return 0.56 * tam * len(texto)


class _Lienzo:
    def __init__(self, fuente: str):
        self.fuente = quoteattr(fuente)
        self.partes: list[str] = []

    def poligono(self, pts, relleno, borde=None, grosor=1.0):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        b = f' stroke="{borde}" stroke-width="{grosor}"' if borde else ""
        self.partes.append(f'<polygon points="{p}" fill="{relleno}"{b}/>')

    def linea(self, x1, y1, x2, y2, color, grosor):
        self.partes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                           f'stroke="{color}" stroke-width="{grosor}"/>')

    def texto(self, x, y_centro, t, tam, color, negrita=False, ancla="start"):
        """y_centro: centro vertical de las mayusculas; ancla start/middle/end."""
        w = ancho_texto(t, tam, negrita)
        if ancla == "middle":
            x -= w / 2
        elif ancla == "end":
            x -= w
        y = y_centro + 0.36 * tam
        peso = ' font-weight="bold"' if negrita else ""
        self.partes.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family={self.fuente} '
                           f'font-size="{tam}"{peso} fill="{color}">{escape(t)}</text>')

    def valor_unidad(self, xc, y_centro, valor, tam, unidad, tam_u, color, color_u, sep=4):
        """Un numero y su unidad (mas chica, en la misma linea base), centrados en xc."""
        w1 = ancho_texto(valor, tam)
        w2 = ancho_texto(unidad, tam_u) if unidad else 0.0
        x = xc - (w1 + (sep + w2 if unidad else 0.0)) / 2
        self.texto(x, y_centro, valor, tam, color)
        if unidad:
            base = y_centro + 0.36 * tam
            self.texto(x + w1 + sep, base - 0.36 * tam_u, unidad, tam_u, color_u)


def _flecha(L: _Lienzo, x, y, w, h, punta, color):
    L.poligono([(x, y), (x + w - punta, y), (x + w, y + h / 2),
                (x + w - punta, y + h), (x, y + h)], color)


def _rotulo(L: _Lienzo, x, y, w, h, punta, c: dict, fondo: str):
    """'Mas eficiente' / 'Menos eficiente': contorno con el borde derecho inclinado."""
    L.poligono([(x, y), (x + w - punta, y), (x + w, y + h), (x, y + h)], fondo, c["borde"], 1.2)
    L.texto(x + 6, y + h / 2, c["texto"], c["tamano"], c["color_texto"])


def _escala(L: _Lienzo, v: dict, cfg: dict, x0: float, y: float) -> tuple:
    """Flechas A+ ... G desde (x0, y). Devuelve (ancho, y del borde inferior)."""
    e = cfg["escala"]
    dest = e["destacada"]
    blanco = cfg["texto_flecha"]
    letras = cfg["letras"]
    alto, sep, punta = e["alto"], e["separacion"], e["punta"]
    rotulos = e.get("rotulos", True)
    ancho = float(e["ancho_inicial"])
    if rotulos:
        _rotulo(L, x0, y, e["ancho_inicial"], alto, punta, e["encabezado"], cfg["fondo"])
        y += alto + sep
    for i, letra in enumerate(letras):
        w = e["ancho_inicial"] + i * e["incremento"]
        color = cfg["colores"][letra]
        if letra == v["letra"]:
            h, w = dest["alto"], w + dest["ancho_extra"]
            _flecha(L, x0, y, w, h, dest["punta"], color)
            L.texto(x0 + dest["margen_letra"], y + h / 2, letra, dest["tamano_letra"], blanco,
                    dest["letra_negrita"])
            if v["flecha"] is not None:
                derecha = x0 + w - dest["punta"] - dest["margen_valor"]
                ancho_v = max(ancho_texto(v["flecha"], dest["tamano_valor"]),
                              ancho_texto(cfg["texto_ahorro"], dest["tamano_ahorro"]))
                cx = derecha - ancho_v / 2
                L.texto(cx, y + h * 0.40, v["flecha"], dest["tamano_valor"], blanco, ancla="middle")
                L.texto(cx, y + h * 0.76, cfg["texto_ahorro"], dest["tamano_ahorro"], blanco,
                        ancla="middle")
        else:
            h = alto
            _flecha(L, x0, y, w, h, punta, color)
            L.texto(x0 + e["margen_letra"], y + h / 2, letra, e["tamano_letra"], blanco, True)
        ancho = max(ancho, w)
        y += h + sep
    if rotulos:
        _rotulo(L, x0, y, e["ancho_inicial"] + (len(letras) - 1) * e["incremento"], alto, punta,
                e["pie"], cfg["fondo"])
        return ancho, y + alto
    return ancho, y - sep


def _tabla(L: _Lienzo, v: dict, cfg: dict, x_izq: float, m: float, fin_escala: float) -> tuple:
    """Tabla a la derecha de la escala. Devuelve (x derecha, y inferior)."""
    t = cfg["tabla"]
    anchos = [t["ancho_rotulo"]] + [t["ancho_columna"]] * 3
    altos = [t["alto_encabezado"], t["alto_fila"], t["alto_fila"]]
    xs = [x_izq]
    for a in anchos:
        xs.append(xs[-1] + a)
    ys = [max(m, m + (fin_escala - m - sum(altos)) / 2)]
    for a in altos:
        ys.append(ys[-1] + a)
    for yy in ys:
        L.linea(xs[0], yy, xs[-1], yy, t["color_linea"], t["grosor_linea"])
    for xx in xs:
        L.linea(xx, ys[0], xx, ys[-1], t["color_linea"], t["grosor_linea"])
    tc, pad, f = t["color_texto"], t["relleno"], t["filas"]
    for j, titulo in enumerate(t["columnas"]):
        L.texto((xs[j + 1] + xs[j + 2]) / 2, (ys[0] + ys[1]) / 2, titulo,
                t["tamano_encabezado"], tc, True, "middle")
    c_dem, c_aho = (ys[1] + ys[2]) / 2, (ys[2] + ys[3]) / 2
    L.texto(xs[0] + pad, c_dem - 0.6 * t["tamano_unidad"], f["demanda"], t["tamano"], tc)
    L.texto(xs[0] + pad, c_dem + 0.6 * t["tamano"], f["unidad"], t["tamano_unidad"], tc)
    L.texto(xs[0] + pad, c_aho, f["ahorro"], t["tamano"], tc)
    centrar = t.get("alineacion", "centro") == "centro"
    for j in range(3):
        if centrar:
            x, ancla = (xs[j + 1] + xs[j + 2]) / 2, "middle"
        else:
            x, ancla = xs[j + 2] - pad, "end"
        L.texto(x, c_dem, v["demanda"][j], t["tamano"], tc, ancla=ancla)
        L.texto(x, c_aho, v["ahorro"][j], t["tamano"], tc, ancla=ancla)
    return xs[-1], ys[-1]


def _datos_vertical(L: _Lienzo, v: dict, cfg: dict, x0: float, x1: float, y: float) -> float:
    """Debajo de la escala: la demanda total en grande con la del caso base en gris, y
    las columnas de calefaccion y refrigeracion (demanda, demanda base y ahorro en el
    orden de vertical.columnas.orden). Devuelve la y inferior."""
    vc, tc = cfg["vertical"], cfg["tabla"]["color_texto"]
    suave, sep = vc["color_suave"], vc["separacion"]
    lc, lg = vc["linea"]["color"], vc["linea"]["grosor"]
    cx = (x0 + x1) / 2
    y += sep
    L.linea(x0, y, x1, y, lc, lg)
    t = vc["total"]
    y += sep + t["tamano_rotulo"] / 2
    L.texto(cx, y, t["rotulo"], t["tamano_rotulo"], suave, ancla="middle")
    yv = y + t["tamano_rotulo"] / 2 + t.get("separacion", 8) + t["tamano"] * 0.36
    L.valor_unidad(cx, yv, v["demanda"][2], t["tamano"], t["unidad"], t["tamano_unidad"], tc, suave, 6)
    y = yv + 0.36 * t["tamano"]
    if v["base"][2] is not None:
        tb = t.get("tamano_base", 11)
        y += 7 + tb / 2
        L.texto(cx, y, f"{t['base']} {v['base'][2]} {t['unidad']}", tb, suave, ancla="middle")
        y += tb / 2
    y += sep
    L.linea(x0, y, x1, y, lc, lg)

    c = vc["columnas"]
    n = len(c["titulos"])
    cw = (x1 - x0) / n
    tt = c["tamano_titulo"]
    altos = {"valor": c["tamano_valor"], "ahorro": c["tamano_ahorro"], "base": c.get("tamano_base", 10)}
    gap = c.get("separacion", 6)
    con_base = any(b is not None for b in v["base"][:n])
    orden = [x for x in (c.get("orden") or ORDEN_COLUMNAS) if x in altos and (x != "base" or con_base)]
    alto = sep + tt + sum(gap + altos[x] for x in orden) + 2 + sep
    unidad = c.get("unidad", "")
    for j, titulo in enumerate(c["titulos"]):
        xc = x0 + cw * (j + 0.5)
        yy = y + sep + tt / 2
        L.texto(xc, yy, titulo, tt, suave, True, "middle")
        previo = tt
        for x in orden:
            yy += previo / 2 + gap + altos[x] / 2
            previo = altos[x]
            if x == "valor":
                L.valor_unidad(xc, yy, v["demanda"][j], altos[x], unidad, c.get("tamano_unidad", 10), tc, suave, 3)
            elif x == "ahorro":
                L.texto(xc, yy, f"{c['ahorro']} {v['ahorro'][j]}", altos[x], suave, ancla="middle")
            elif v["base"][j] is not None:
                L.texto(xc, yy, f"{c['base']} {v['base'][j]} {unidad}".strip(), altos[x], suave, ancla="middle")
    for j in range(1, n):
        x = x0 + cw * j
        L.linea(x, y + sep * 0.6, x, y + alto - sep * 0.6, lc, lg)
    y += alto
    L.linea(x0, y, x1, y, lc, lg)
    return y


def svg(res: dict | None, cfg: dict, responsivo: bool = False, fuente: str | None = None) -> str:
    """
    res: resultado de ejecucion.py (letra, ahorro_*_pct, demanda_*), o None para
    la escala vacia. responsivo=True: ancho 100 % del contenedor (navegador).
    """
    v = valores(res, cfg)
    m = cfg["margen"]
    L = _Lienzo(fuente or cfg["fuente"])
    ancho_escala, fin_escala = _escala(L, v, cfg, m, m)
    if cfg.get("disposicion") == "vertical":
        ancho = max(ancho_escala, float(cfg["vertical"].get("ancho_min", 0)))
        fin = _datos_vertical(L, v, cfg, m, m + ancho, fin_escala)
        W, H = math.ceil(ancho + 2 * m), math.ceil(fin + m)
    else:
        x_fin, y_fin = _tabla(L, v, cfg, m + ancho_escala + cfg["tabla"]["separacion"], m, fin_escala)
        W, H = math.ceil(x_fin + m), math.ceil(max(fin_escala, y_fin) + m)
    if responsivo:
        tam = f'viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px;height:auto"'
        if cfg.get("disposicion") == "vertical":
            tam = f'viewBox="0 0 {W} {H}" style="width:100%;height:auto"'
    else:
        tam = f'width="{W}" height="{H}" viewBox="0 0 {W} {H}"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" {tam}>'
            f'<rect x="0" y="0" width="{W}" height="{H}" fill="{cfg["fondo"]}"/>'
            + "".join(L.partes) + "</svg>")


# --------------------------------------------------------------------------- archivos
def png(svg_txt: str, escala: float = 3.0) -> bytes:
    if _mu is None:
        raise RuntimeError("falta PyMuPDF (pip install pymupdf)")
    doc = _mu.open(stream=svg_txt.encode("utf-8"), filetype="svg")
    try:
        pix = doc[0].get_pixmap(matrix=_mu.Matrix(escala, escala), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def carpeta_resultado(res: dict | None) -> Path | None:
    """Carpeta de la iteracion (la que tiene la ficha, los bloques y la 03)."""
    if not res:
        return None
    if res.get("carpeta"):
        return Path(res["carpeta"])
    if res.get("archivo"):
        return Path(res["archivo"]).parent
    return None


def guardar(res: dict, carpeta: Path, cfg: dict) -> Path:
    """Escribe <nombre>.svg y <nombre>.png en la carpeta. Devuelve la ruta del PNG."""
    p = cfg["png"]
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    txt = svg(res, cfg, fuente=p.get("fuente"))
    (carpeta / f"{p['nombre']}.svg").write_text(txt, encoding="utf-8")
    ruta = carpeta / f"{p['nombre']}.png"
    ruta.write_bytes(png(txt, p["escala"]))
    return ruta
