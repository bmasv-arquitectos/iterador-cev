# -*- coding: utf-8 -*-
"""
Edicion de un .xlsm sin Excel. Un .xlsm es un zip y cada hoja es un XML: escribir_libro copia
una planilla cambiando solo las celdas pedidas de algunas hojas (Cambios: valores, valores
guardados de formulas, rangos que se vacian y celdas combinadas que se separan). Lo demas
(macros, graficos, formatos, validaciones, protecciones) se copia tal cual; workbook.xml queda
con fullCalcOnLoad="1" (Excel recalcula todo al abrirla) y se borra calcChain.xml (Excel lo
rehace). Lo usan la ficha 01 (ficha_xlsm.py) y la planilla 03.
"""
from __future__ import annotations

import html
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

from .excel import es_error, es_numero

RE_ATTR = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')
RE_SHEETDATA = re.compile(r"<sheetData\b[^>]*?(?:/>|>(.*?)</sheetData>)", re.S)
RE_ROW = re.compile(r"<row\b([^>]*?)(?:/>|>(.*?)</row>)", re.S)
RE_CELL = re.compile(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.S)
RE_F = re.compile(r"<f\b[^>]*?(?:/>|>.*?</f>)", re.S)
RE_V = re.compile(r"<v>(.*?)</v>", re.S)
RE_SPANS = re.compile(r'\s+spans="[^"]*"')
RE_REF = re.compile(r"([A-Z]+)(\d+)")
RE_MERGES = re.compile(r"<mergeCells\b[^>]*>(.*?)</mergeCells>", re.S)
RE_MERGE = re.compile(r'<mergeCell\b[^>]*?ref="([^"]+)"[^>]*/>')
RE_SHEET = re.compile(r"<sheet\b([^>]*?)/?>")
RE_REL = re.compile(r"<Relationship\b([^>]*?)/?>")
DESPUES_CALCPR = ("<oleSize", "<customWorkbookViews", "<pivotCaches", "<smartTagPr", "<smartTagTypes",
                  "<webPublishing", "<fileRecoveryPr", "<webPublishObjects", "<extLst", "</workbook>")


# --------------------------------------------------------------------------- XML de una hoja
def atributos(texto: str) -> dict:
    return dict(RE_ATTR.findall(texto or ""))


def _col(ref: str) -> int:
    return column_index_from_string(RE_REF.match(ref).group(1))


def _fila(ref: str) -> int:
    return int(RE_REF.match(ref).group(2))


def _sin(attrs: dict, *claves) -> dict:
    return {k: v for k, v in attrs.items() if k not in claves}


def _num(v) -> str:
    return str(v) if isinstance(v, int) else repr(float(v))


def _texto_xml(s) -> str:
    return escape("".join(ch for ch in str(s) if ch in "\t\n\r" or ord(ch) >= 32))


def contenido_valor(v):
    """(t, xml interno) de una celda con valor constante; (None, '') = celda vacia."""
    if v is None:
        return None, ""
    if isinstance(v, bool):
        return "b", f"<v>{int(v)}</v>"
    if isinstance(v, (datetime, date)):
        from openpyxl.utils.datetime import to_excel
        v = to_excel(v)
    if es_error(v):
        return "e", f"<v>{_texto_xml(v)}</v>"
    if es_numero(v):
        return (None, f"<v>{_num(v)}</v>") if math.isfinite(float(v)) else ("e", "<v>#NUM!</v>")
    return "inlineStr", f'<is><t xml:space="preserve">{_texto_xml(v)}</t></is>'


def contenido_cache(v):
    """(t, <v>) del valor guardado de una formula."""
    if v is None:
        return None, ""
    if isinstance(v, bool):
        return "b", f"<v>{int(v)}</v>"
    if es_error(v):
        return "e", f"<v>{_texto_xml(v)}</v>"
    if es_numero(v):
        return (None, f"<v>{_num(v)}</v>") if math.isfinite(float(v)) else ("e", "<v>#NUM!</v>")
    return "str", f"<v>{_texto_xml(v)}</v>"


def _celda(ref: str, attrs: dict, t, interno: str) -> str:
    partes = [f'r="{ref}"'] + [f'{k}="{v}"' for k, v in _sin(attrs, "r", "t").items()]
    if t:
        partes.append(f't="{t}"')
    return "<c " + " ".join(partes) + (f">{interno}</c>" if interno else "/>")


@dataclass
class Cambios:
    valores: dict = field(default_factory=dict)   # {celda: valor}: quedan como constantes
    caches: dict = field(default_factory=dict)    # {celda: valor} guardado de celdas con formula
    limpiar: tuple = ()                           # rangos que se vacian (ClearContents)
    desunir: tuple = ()                           # rangos cuyas celdas combinadas se separan (UnMerge)


def _choca(ref: str, cajas) -> bool:
    c1, f1, c2, f2 = range_boundaries(ref)
    return any(not (c2 < a1 or c1 > a2 or f2 < b1 or f1 > b2) for a1, b1, a2, b2 in cajas)


def editar_hoja(xml: str, c: Cambios) -> tuple[str, Counter]:
    st: Counter = Counter()
    m = RE_SHEETDATA.search(xml)
    if m is None:
        raise ValueError("la hoja no tiene sheetData")
    filas = {}         # n -> [texto original o None, atributos (texto), {ref: [texto, atributos, contenido]}]
    for rm in RE_ROW.finditer(m.group(1) or ""):
        celdas = {}
        for cm in RE_CELL.finditer(rm.group(2) or ""):
            celdas[atributos(cm.group(1))["r"]] = [cm.group(0), cm.group(1), cm.group(2)]
        filas[int(atributos(rm.group(1))["r"])] = [rm.group(0), rm.group(1), celdas]
    tocadas = set()

    cajas = [range_boundaries(r) for r in c.limpiar]
    if cajas:
        for n, fila in filas.items():
            if not any(f1 <= n <= f2 for _, f1, _, f2 in cajas):
                continue
            for ref, celda in fila[2].items():
                col = _col(ref)
                if celda[2] and any(c1 <= col <= c2 and f1 <= n <= f2 for c1, f1, c2, f2 in cajas):
                    fila[2][ref] = [_celda(ref, _sin(atributos(celda[1]), "cm", "vm"), None, ""), celda[1], None]
                    tocadas.add(n)
                    st["vaciadas"] += 1

    for ref, v in c.valores.items():
        n = _fila(ref)
        fila = filas.get(n)
        if fila is None:
            fila = filas[n] = [None, f' r="{n}"', {}]
        vieja = fila[2].get(ref)
        attrs = _sin(atributos(vieja[1]) if vieja else {}, "cm", "vm")
        t, interno = contenido_valor(v)
        fila[2][ref] = [_celda(ref, attrs, t, interno), _celda(ref, attrs, None, "")[2:-2], None]
        tocadas.add(n)
        st["valores"] += 1

    for ref, v in c.caches.items():
        fila = filas.get(_fila(ref))
        vieja = fila[2].get(ref) if fila else None
        f = RE_F.search(vieja[2] or "") if vieja else None
        if f is None:
            st["caches_sin_formula"] += 1
            continue
        t, vtxt = contenido_cache(v)
        fila[2][ref] = [_celda(ref, atributos(vieja[1]), t, f.group(0) + vtxt), vieja[1], vieja[2]]
        tocadas.add(_fila(ref))
        st["caches"] += 1

    partes = []
    for n in sorted(filas):
        texto, a_raw, celdas = filas[n]
        if n not in tocadas and texto is not None:
            partes.append(texto)
            continue
        a_raw = RE_SPANS.sub("", a_raw)
        cs = "".join(x[0] for _, x in sorted(celdas.items(), key=lambda kv: _col(kv[0])))
        partes.append(f"<row{a_raw}>{cs}</row>" if cs else f"<row{a_raw}/>")
    xml = xml[:m.start()] + "<sheetData>" + "".join(partes) + "</sheetData>" + xml[m.end():]

    if c.desunir:
        cajas_d = [range_boundaries(r) for r in c.desunir]
        mm = RE_MERGES.search(xml)
        if mm:
            todas = [x for x in RE_MERGE.finditer(mm.group(1))]
            quedan = [x.group(0) for x in todas if not _choca(x.group(1), cajas_d)]
            st["desunidas"] = len(todas) - len(quedan)
            nuevo = f'<mergeCells count="{len(quedan)}">{"".join(quedan)}</mergeCells>' if quedan else ""
            xml = xml[:mm.start()] + nuevo + xml[mm.end():]
    return xml, st


def valor_xml(xml: str, ref: str):
    """Texto de <v> de una celda (o None)."""
    m = re.search(r'<c\b[^>]*?\br="%s"[^>]*?(?:/>|>(.*?)</c>)' % re.escape(ref), xml, re.S)
    if not m or not m.group(1):
        return None
    v = RE_V.search(m.group(1))
    return v.group(1) if v else None


# --------------------------------------------------------------------------- libro
def hojas_del_libro(z: zipfile.ZipFile) -> dict:
    """{nombre de la hoja: parte del zip}."""
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    destinos = {}
    for m in RE_REL.finditer(rels):
        a = atributos(m.group(1))
        destinos[a.get("Id")] = a.get("Target")
    out = {}
    for m in RE_SHEET.finditer(wb):
        a = atributos(m.group(1))
        rid = next((v for k, v in a.items() if k.endswith(":id")), None)
        t = destinos.get(rid)
        if t is None or "name" not in a:
            continue
        t = t.lstrip("/")
        out[html.unescape(a["name"])] = t if t.startswith("xl/") else f"xl/{t}"
    return out


def editar_workbook(xml: str) -> str:
    """calcPr con fullCalcOnLoad="1": Excel recalcula todo al abrir."""
    m = re.search(r"<calcPr\b([^>]*?)/>", xml)
    if m:
        a = re.sub(r'\s+fullCalcOnLoad="[^"]*"', "", m.group(1))
        return xml[:m.start()] + f'<calcPr{a} fullCalcOnLoad="1"/>' + xml[m.end():]
    for etiqueta in DESPUES_CALCPR:
        i = xml.find(etiqueta)
        if i >= 0:
            return xml[:i] + '<calcPr fullCalcOnLoad="1"/>' + xml[i:]
    return xml


def escribir_libro(origen, destino, cambios: dict) -> dict:
    """Copia origen en destino aplicando {hoja: Cambios}. Devuelve estadisticas por hoja."""
    origen, destino = Path(origen), Path(destino)
    stats = {}
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    with zipfile.ZipFile(origen) as z:
        hojas = hojas_del_libro(z)
        faltan = [h for h in cambios if h not in hojas]
        if faltan:
            raise KeyError(f"la planilla no tiene las hojas {faltan} (tiene {sorted(hojas)})")
        reemplazos = {}
        for h, c in cambios.items():
            xml, st = editar_hoja(z.read(hojas[h]).decode("utf-8"), c)
            reemplazos[hojas[h]] = xml.encode("utf-8")
            stats[h] = dict(st)
        reemplazos["xl/workbook.xml"] = editar_workbook(z.read("xl/workbook.xml").decode("utf-8")).encode("utf-8")
        nombres = set(z.namelist())
        if "xl/calcChain.xml" in nombres:
            ct = z.read("[Content_Types].xml").decode("utf-8")
            reemplazos["[Content_Types].xml"] = re.sub(
                r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "", ct).encode("utf-8")
            rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            reemplazos["xl/_rels/workbook.xml.rels"] = re.sub(
                r'<Relationship\b[^>]*Target="[^"]*calcChain\.xml"[^>]*/>', "", rels).encode("utf-8")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():
                if info.filename == "xl/calcChain.xml":
                    continue
                datos = reemplazos.get(info.filename)
                out.writestr(info, z.read(info.filename) if datos is None else datos,
                             compress_type=zipfile.ZIP_DEFLATED)
    tmp.replace(destino)
    return stats


# --------------------------------------------------------------------------- leer
def leer_valores(ruta, pedidos: dict) -> dict:
    """{clave: {celda: valor}} de los rangos pedidos {clave: (hoja, rango)} (valores guardados)."""
    from openpyxl import load_workbook

    wb = load_workbook(Path(ruta), read_only=True, data_only=True, keep_links=False)
    try:
        out = {}
        for clave, (hoja, rango) in pedidos.items():
            d = out[clave] = {}
            if hoja not in wb.sheetnames:
                continue
            c1, f1, c2, f2 = range_boundaries(rango)
            for i, fila in enumerate(wb[hoja].iter_rows(min_row=f1, max_row=f2, min_col=c1, max_col=c2)):
                for j, x in enumerate(fila):
                    v = getattr(x, "value", None)
                    if v is not None:
                        d[f"{get_column_letter(c1 + j)}{f1 + i}"] = v
        return out
    finally:
        wb.close()


def superponer(base: dict, calculadas: dict, rango: str) -> dict:
    """base con las celdas calculadas que caen en el rango."""
    c1, f1, c2, f2 = range_boundaries(rango)
    out = dict(base)
    for ref, v in calculadas.items():
        if RE_REF.fullmatch(ref) and c1 <= _col(ref) <= c2 and f1 <= _fila(ref) <= f2:
            out[ref] = v
    return out
