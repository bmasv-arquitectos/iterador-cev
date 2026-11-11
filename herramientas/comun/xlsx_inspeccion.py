# -*- coding: utf-8 -*-
"""
Utilidades compartidas por los inspectores de libros Excel.

Se abre el libro con openpyxl en modo normal (NO read_only) a proposito: el
modo de solo lectura no expone proteccion de celdas, validaciones de datos ni
formato condicional, que es justamente lo que interesa para mapear un
formulario oficial.

Los libros se abren y nunca se guardan, asi que el archivo original no se
modifica en ningun caso.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterator

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries

EXTENSIONES = (".xlsx", ".xlsm")

# Tope para expandir el sqref de una validacion: hay formularios con
# validaciones declaradas sobre columnas enteras.
TOPE_SQREF = 20000

col = get_column_letter


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def validar_archivo(ruta: str | Path) -> Path:
    ruta = Path(ruta).expanduser()
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    if ruta.suffix.lower() not in EXTENSIONES:
        raise ValueError(
            f"Extension no soportada: '{ruta.suffix}'. openpyxl lee solo "
            f"{', '.join(EXTENSIONES)}. Si el archivo es .xls o .xlsb, abrirlo en "
            "Excel y guardarlo como .xlsx (o usar el motor COM)."
        )
    return ruta.resolve()

def tiene_macros(ruta: Path) -> bool:
    """
    Un .xlsx/.xlsm es un zip. Si trae 'xl/vbaProject.bin', tiene macros.
    Es el unico chequeo confiable: wb.vba_archive solo se rellena si el libro
    se cargo con keep_vba=True, asi que da falso negativo por omision.
    """
    import zipfile
    try:
        with zipfile.ZipFile(ruta) as z:
            return "xl/vbaProject.bin" in z.namelist()
    except Exception:
        return False

def cargar(ruta: Path):
    """
    Devuelve (wb_formulas, wb_valores).

    wb_formulas trae el texto de las formulas; wb_valores trae el ultimo
    resultado calculado que Excel dejo en cache. Hacen falta los dos: sin el
    primero no se ve que celdas son calculadas, y sin el segundo no se ve que
    valor muestran en pantalla.
    """
    wb_f = load_workbook(ruta, data_only=False)
    try:
        wb_v = load_workbook(ruta, data_only=True)
    except Exception:
        wb_v = None
    return wb_f, wb_v


# ---------------------------------------------------------------------------
# Valores
# ---------------------------------------------------------------------------

def es_vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def tipo_de(v: Any) -> str:
    if es_vacio(v):
        return "vacio"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return "fecha"
    if isinstance(v, (int, float)):
        return "numero"
    if isinstance(v, str):
        return "formula" if v.startswith("=") else "texto"
    return type(v).__name__


def texto_corto(v: Any, n: int = 38) -> str:
    if es_vacio(v):
        return ""
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
    elif isinstance(v, (dt.datetime, dt.date)):
        s = v.strftime("%d/%m/%Y")
    else:
        s = str(v)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def sin_tildes(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalizar(s: Any) -> str:
    """Minusculas, sin tildes, espacios colapsados. Para comparar etiquetas."""
    if s is None:
        return ""
    return " ".join(sin_tildes(str(s)).lower().split())


# ---------------------------------------------------------------------------
# Celdas combinadas
# ---------------------------------------------------------------------------

def mapa_merges(ws) -> dict[tuple[int, int], tuple[int, int]]:
    """
    (fila, col) -> (fila, col) de la celda ancla.

    Importa porque openpyxl devuelve None al leer cualquier celda de un rango
    combinado que no sea la de arriba a la izquierda, y en los formularios
    oficiales casi todas las etiquetas estan combinadas.
    """
    mapa: dict[tuple[int, int], tuple[int, int]] = {}
    for r in ws.merged_cells.ranges:
        ancla = (r.min_row, r.min_col)
        for f in range(r.min_row, r.max_row + 1):
            for c in range(r.min_col, r.max_col + 1):
                mapa[(f, c)] = ancla
    return mapa


def valor_efectivo(ws, fila: int, columna: int, merges: dict) -> Any:
    """Valor de la celda, resolviendo el ancla si forma parte de un merge."""
    f, c = merges.get((fila, columna), (fila, columna))
    try:
        return ws.cell(row=f, column=c).value
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extension de la hoja
# ---------------------------------------------------------------------------

def extremos(ws, tope_filas: int, tope_cols: int) -> tuple[int, int, bool]:
    """Limites declarados por la hoja, recortados a los topes del CLI."""
    mf = ws.max_row or 1
    mc = ws.max_column or 1
    truncado = mf > tope_filas or mc > tope_cols
    return min(mf, tope_filas), min(mc, tope_cols), truncado


def extremos_contenido(ws, max_f: int, max_c: int, merges: dict) -> dict:
    """
    Limites reales del contenido. ws.max_row suele venir inflado por celdas
    que solo tienen formato, asi que se recorre y se mide.
    """
    f_min = c_min = None
    f_max = c_max = 0
    n = 0
    for f in range(1, max_f + 1):
        for c in range(1, max_c + 1):
            if es_vacio(valor_efectivo(ws, f, c, merges)):
                continue
            n += 1
            f_min = f if f_min is None else min(f_min, f)
            c_min = c if c_min is None else min(c_min, c)
            f_max = max(f_max, f)
            c_max = max(c_max, c)
    return {
        "celdas_con_contenido": n,
        "fila_min": f_min, "fila_max": f_max or None,
        "col_min": c_min, "col_max": c_max or None,
        "rango": (
            f"{col(c_min)}{f_min}:{col(c_max)}{f_max}" if f_min else "(vacia)"
        ),
    }


# ---------------------------------------------------------------------------
# Proteccion
# ---------------------------------------------------------------------------

def esta_bloqueada(celda) -> bool:
    """
    True si la celda esta bloqueada. El valor por omision en Excel es
    bloqueada, asi que 'desbloqueada' es siempre una decision explicita de
    quien armo el formulario: es la senal que interesa.
    """
    try:
        return bool(celda.protection.locked)
    except Exception:
        return True


def proteccion_columna(ws, columna: int):
    """Algunos formularios desbloquean columnas completas sin tocar celdas."""
    try:
        dim = ws.column_dimensions.get(col(columna))
        if dim is None:
            return None
        return bool(dim.protection.locked)
    except Exception:
        return None


def info_proteccion_hoja(ws) -> dict:
    p = ws.protection
    campos = (
        "sheet", "selectLockedCells", "selectUnlockedCells", "formatCells",
        "formatColumns", "formatRows", "insertColumns", "insertRows",
        "deleteColumns", "deleteRows", "sort", "autoFilter", "objects",
        "scenarios",
    )
    d = {k: getattr(p, k, None) for k in campos}
    d["tiene_password"] = bool(getattr(p, "password", None))
    return d


# ---------------------------------------------------------------------------
# Etiquetas vecinas
# ---------------------------------------------------------------------------

def etiqueta_izquierda(ws, fila: int, columna: int, merges: dict,
                       pasos: int = 12) -> str:
    """Primer texto no vacio hacia la izquierda, en la misma fila."""
    for c in range(columna - 1, max(0, columna - pasos - 1), -1):
        v = valor_efectivo(ws, fila, c, merges)
        if not es_vacio(v) and tipo_de(v) in ("texto", "formula"):
            return texto_corto(v, 46)
    return ""


def etiqueta_arriba(ws, fila: int, columna: int, merges: dict,
                    pasos: int = 8) -> str:
    """Primer texto no vacio hacia arriba, en la misma columna."""
    for f in range(fila - 1, max(0, fila - pasos - 1), -1):
        v = valor_efectivo(ws, f, columna, merges)
        if not es_vacio(v) and tipo_de(v) in ("texto", "formula"):
            return texto_corto(v, 46)
    return ""


# ---------------------------------------------------------------------------
# Validaciones de datos (listas desplegables)
# ---------------------------------------------------------------------------

def _valores_de_rango(wb, ws, ref: str, tope: int = 80) -> list[str] | None:
    ref = ref.lstrip("=").replace("$", "").strip()
    hoja = ws
    if "!" in ref:
        nombre, ref = ref.split("!", 1)
        nombre = nombre.strip().strip("'")
        if nombre not in wb.sheetnames:
            return None
        hoja = wb[nombre]
    try:
        c1, f1, c2, f2 = range_boundaries(ref)
    except Exception:
        return None
    f1 = f1 or 1
    f2 = f2 or min(hoja.max_row or 1, f1 + tope)
    c1 = c1 or 1
    c2 = c2 or c1
    vals: list[str] = []
    for f in range(f1, min(f2, f1 + tope) + 1):
        for c in range(c1, c2 + 1):
            v = hoja.cell(row=f, column=c).value
            if not es_vacio(v):
                vals.append(texto_corto(v, 40))
    return vals


def opciones_validacion(wb, ws, dv) -> list[str] | None:
    """
    Resuelve las opciones de una lista desplegable, vengan escritas en la
    propia validacion o en un rango/nombre definido.
    """
    f1 = getattr(dv, "formula1", None)
    if not f1:
        return None
    f1 = str(f1).strip()
    if f1.startswith('"') and f1.endswith('"'):
        return [x.strip() for x in f1[1:-1].split(",")]

    ref = f1.lstrip("=").strip()
    try:
        nombres = dict(wb.defined_names.items())
    except Exception:
        nombres = {}
    if ref in nombres:
        destino = getattr(nombres[ref], "attr_text", None) or getattr(
            nombres[ref], "value", "")
        return _valores_de_rango(wb, ws, str(destino))
    return _valores_de_rango(wb, ws, ref)


def validaciones(wb, ws) -> tuple[list[dict], dict[tuple[int, int], int]]:
    """Devuelve (lista de validaciones, indice (fila, col) -> posicion)."""
    lista: list[dict] = []
    indice: dict[tuple[int, int], int] = {}
    try:
        dvs = list(ws.data_validations.dataValidation)
    except Exception:
        dvs = []

    for i, dv in enumerate(dvs):
        opciones = opciones_validacion(wb, ws, dv) if dv.type == "list" else None
        lista.append({
            "id": i,
            "tipo": dv.type,
            "operador": getattr(dv, "operator", None),
            "sqref": str(dv.sqref),
            "formula1": getattr(dv, "formula1", None),
            "formula2": getattr(dv, "formula2", None),
            "permite_blanco": getattr(dv, "allow_blank", None),
            "opciones": opciones,
            "n_opciones": len(opciones) if opciones else 0,
            "mensaje": getattr(dv, "prompt", None),
            "titulo_mensaje": getattr(dv, "promptTitle", None),
        })
        n = 0
        try:
            for rango_dv in dv.sqref.ranges:
                for f, c in rango_dv.cells:
                    indice[(f, c)] = i
                    n += 1
                    if n > TOPE_SQREF:
                        raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass
    return lista, indice


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------

RE_REF = re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+)")


def patron_formula(f: str) -> str:
    """'=B12*C12' -> '=B#*C#'. Permite agrupar una columna entera de formulas."""
    return RE_REF.sub(lambda m: f"{m.group(1)}#", str(f))


def hojas_referidas(f: str) -> list[str]:
    """Nombres de hoja citados en una formula (dependencias entre pestanias)."""
    encontrados = re.findall(r"'([^']+)'!|([A-Za-z_][A-Za-z0-9_.]*)!", str(f))
    salida = []
    for a, b in encontrados:
        nombre = a or b
        if nombre and nombre not in salida:
            salida.append(nombre)
    return salida


# ---------------------------------------------------------------------------
# Varios
# ---------------------------------------------------------------------------

def comprimir(nums) -> list[tuple[int, int]]:
    """[1,2,3,7,8] -> [(1,3), (7,8)]"""
    res: list[list[int]] = []
    for n in sorted(set(nums)):
        if res and n == res[-1][1] + 1:
            res[-1][1] = n
        else:
            res.append([n, n])
    return [(a, b) for a, b in res]


def texto_rangos(nums) -> str:
    partes = [f"{a}" if a == b else f"{a}-{b}" for a, b in comprimir(nums)]
    return ", ".join(partes)


def texto_columnas(cols) -> str:
    partes = []
    for a, b in comprimir(cols):
        partes.append(col(a) if a == b else f"{col(a)}-{col(b)}")
    return ",".join(partes)


class Salida:
    """Acumula el reporte para imprimirlo y guardarlo de una sola vez."""

    def __init__(self, eco: bool = True):
        self.lineas: list[str] = []
        self.eco = eco

    def p(self, texto: str = "") -> None:
        self.lineas.append(texto)
        if self.eco:
            print(texto)

    def titulo(self, texto: str, caracter: str = "=") -> None:
        self.p()
        self.p(caracter * 78)
        self.p(texto)
        self.p(caracter * 78)

    def guardar(self, ruta: Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("\n".join(self.lineas) + "\n", encoding="utf-8")
        return ruta


def guardar_json(obj, ruta: Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return ruta
