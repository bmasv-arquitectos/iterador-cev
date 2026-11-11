# -*- coding: utf-8 -*-
"""Utilidades comunes para trabajar con libros de Excel."""
from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path

EXTENSIONES = (".xlsx", ".xlsm", ".xlsb", ".xls")


def clave_orden(p: Path):
    """Ordena por el primer numero del nombre (casa2 antes que casa10)."""
    m = re.search(r"(\d+)", p.stem)
    if m:
        return (0, int(m.group(1)), p.stem.lower())
    return (1, 0, p.stem.lower())


def listar_excels(carpeta: Path) -> list[Path]:
    """Devuelve los Excel de la carpeta, ordenados y sin archivos temporales."""
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No existe la carpeta: {carpeta}")
    archivos = [
        p for p in carpeta.iterdir()
        if p.is_file()
        and p.suffix.lower() in EXTENSIONES
        and not p.name.startswith("~$")
    ]
    return sorted(archivos, key=clave_orden)


@contextmanager
def app_excel(visible: bool = False):
    """Abre una instancia de Excel via COM y garantiza que se cierre."""
    import win32com.client as win32

    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = visible
    excel.DisplayAlerts = False
    excel.AskToUpdateLinks = False
    excel.EnableEvents = False
    try:
        yield excel
    finally:
        try:
            excel.Quit()
        except Exception:
            pass


@contextmanager
def libro_solo_lectura(excel, ruta: Path):
    """Abre un libro en solo lectura y lo cierra sin guardar cambios."""
    wb = excel.Workbooks.Open(
        str(ruta.resolve()), UpdateLinks=0, ReadOnly=True, IgnoreReadOnlyRecommended=True
    )
    try:
        yield wb
    finally:
        try:
            wb.Close(SaveChanges=False)
        except Exception:
            pass


def tiene_hoja(wb, nombre: str) -> bool:
    return nombre.strip().lower() in {
        str(ws.Name).strip().lower() for ws in wb.Worksheets
    }


def obtener_hoja(wb, nombre: str):
    """Busca la hoja ignorando mayusculas y espacios sobrantes."""
    objetivo = nombre.strip().lower()
    for ws in wb.Worksheets:
        if str(ws.Name).strip().lower() == objetivo:
            return ws
    raise KeyError(nombre)
