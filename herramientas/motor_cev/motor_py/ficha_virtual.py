# -*- coding: utf-8 -*-
r"""
La ficha 01 escrita en memoria, sin Excel: lo que hace fichas_cev.escritor.generar
(copiar la plantilla y escribir celdas por COM) pero sobre un diccionario.

Se usan las MISMAS funciones del escritor (escribir_catalogo y llenar) con una hoja
virtual que imita lo que esas funciones le piden a Excel:
  - ws.Range(celda).Value = v      escribe una celda; si la hoja esta protegida y la
                                   celda bloqueada, error (como Excel: asi el mapa se
                                   sigue validando);
  - ws.Range(rango).ClearContents() vacia el rango; si tiene una celda bloqueada, error
                                   (el escritor lo ignora, igual que con Excel).
La hoja parte de las constantes de la plantilla ('CEV-CEVE'!A1:Z239 y '3. Tablas
Envolvente'!A10:M92, las que lee leer_ficha) con su proteccion.

No se escribe lo que solo describe la vivienda en el certificado (los paquetes de
'CEV-CEVE' fila 33-40, seleccionar_paquetes): no entra al calculo.

Pendiente de confirmar contra Excel: Excel convierte un texto con forma de numero
("12") en numero al escribirlo; aca queda como texto y se avisa.

PLANTILLA y MAPA_FICHA son rutas absolutas (comun/rutas_app.recurso): se encuentran con el
codigo en el repositorio o empaquetado, sin depender de la carpeta de trabajo.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from openpyxl.utils import get_column_letter, range_boundaries

from herramientas.comun.rutas_app import recurso

from .entradas import RANGO_CEV, RANGO_TE, Ficha, _igual, diferencias, ficha_desde_cev

PLANTILLA = recurso("herramientas/fichas_cev/bases/01.-PBTD-Datos-de-Arquitectura-v2.2.xlsm")
MAPA_FICHA = recurso("herramientas/fichas_cev/mapa.yaml")
H_CEV, H_TE, H_ARQ = "CEV-CEVE", "3. Tablas Envolvente", "0. Datos Arq Motor"
RANGOS = {H_CEV: RANGO_CEV, H_TE: RANGO_TE}
RE_NUMERO = re.compile(r"^\s*[-+]?\d+([.,]\d+)?\s*$")


def _celdas(ref: str):
    c1, f1, c2, f2 = range_boundaries(ref)
    return [f"{get_column_letter(c)}{f}" for f in range(f1, f2 + 1) for c in range(c1, c2 + 1)]


def en_rango(celda: str, rango: str) -> bool:
    c1, f1, c2, f2 = range_boundaries(rango)
    c, f, _, _ = range_boundaries(celda)
    return c1 <= c <= c2 and f1 <= f <= f2


# --------------------------------------------------------------------------- hoja virtual
class HojaVirtual:
    """Lo que el escritor usa de una hoja de Excel (Name, Range().Value, Range().ClearContents())."""

    def __init__(self, nombre: str, valores: dict, bloqueadas=frozenset(), protegida: bool = False):
        self.Name = nombre
        self.valores = dict(valores)
        self.bloqueadas = frozenset(bloqueadas)
        self.protegida = bool(protegida)
        self.escritas: dict = {}
        self.avisos: list = []

    def Range(self, ref: str) -> "RangoVirtual":          # noqa: N802 (nombre de la API de Excel)
        return RangoVirtual(self, str(ref).replace("$", "").upper())

    def bloqueada(self, celda: str) -> bool:
        return self.protegida and celda in self.bloqueadas


class RangoVirtual:
    def __init__(self, hoja: HojaVirtual, ref: str):
        self.hoja, self.ref = hoja, ref

    @property
    def Value(self):                                      # noqa: N802
        cs = _celdas(self.ref)
        if len(cs) == 1:
            return self.hoja.valores.get(cs[0])
        return tuple(self.hoja.valores.get(c) for c in cs)

    @Value.setter
    def Value(self, v):                                   # noqa: N802
        cs = _celdas(self.ref)
        if len(cs) != 1:
            raise ValueError(f"la hoja virtual solo escribe celdas sueltas ({self.ref})")
        c = cs[0]
        if self.hoja.bloqueada(c):
            raise PermissionError(f"celda bloqueada {self.hoja.Name}!{c}")
        if isinstance(v, str) and RE_NUMERO.match(v):
            self.hoja.avisos.append(f"{self.hoja.Name}!{c}: texto con forma de numero {v!r} "
                                    "(Excel lo convertiria en numero)")
        self.hoja.valores[c] = v
        self.hoja.escritas[c] = v

    def ClearContents(self):                              # noqa: N802
        cs = _celdas(self.ref)
        if any(self.hoja.bloqueada(c) for c in cs):
            raise PermissionError(f"rango con celdas bloqueadas {self.hoja.Name}!{self.ref}")
        for c in cs:
            self.hoja.valores.pop(c, None)


class LibroVirtual:
    def __init__(self, hojas: dict):
        self.hojas = hojas

    def Worksheets(self, nombre: str) -> HojaVirtual:     # noqa: N802
        try:
            return self.hojas[nombre]
        except KeyError:
            raise KeyError(f"la ficha virtual no tiene la hoja {nombre!r}") from None


# --------------------------------------------------------------------------- plantilla
@dataclass(frozen=True)
class Base:
    valores: dict          # {hoja: {celda: constante}} de RANGOS
    bloqueadas: dict       # {hoja: frozenset de celdas bloqueadas} de RANGOS
    protegidas: dict       # {hoja: bool}
    caso: object           # '0. Datos Arq Motor'!C33 de la plantilla


def _protegidas(ruta: Path) -> dict:
    from .xlsm import hojas_del_libro

    out = {}
    with zipfile.ZipFile(ruta) as z:
        partes = hojas_del_libro(z)
        for h in RANGOS:
            xml = z.read(partes[h]).decode("utf-8", errors="replace")
            m = re.search(r"<sheetProtection\b([^>]*)/?>", xml)
            out[h] = bool(m and re.search(r'\bsheet="(1|true)"', m.group(1)))
    return out


@lru_cache(maxsize=2)
def base(plantilla: str = str(PLANTILLA)) -> Base:
    """Constantes y proteccion de la plantilla (se leen una vez por proceso)."""
    from openpyxl import load_workbook

    from .excel import texto_formula

    ruta = Path(plantilla)
    wb = load_workbook(ruta, read_only=True, data_only=False, keep_links=False)
    try:
        valores, bloqueadas = {}, {}
        for h, rango in RANGOS.items():
            c1, f1, c2, f2 = range_boundaries(rango)
            vals, bloq = {}, set()
            for i, fila in enumerate(wb[h].iter_rows(min_row=f1, max_row=f2, min_col=c1, max_col=c2)):
                for j, c in enumerate(fila):
                    ref = f"{get_column_letter(c1 + j)}{f1 + i}"
                    prot = getattr(c, "protection", None)
                    if prot is None or prot.locked:
                        bloq.add(ref)
                    v = getattr(c, "value", None)
                    if v is None or texto_formula(v):
                        continue
                    vals[ref] = v if isinstance(v, (int, float, str, bool)) else str(v)
            valores[h], bloqueadas[h] = vals, frozenset(bloq)
        caso = wb[H_ARQ]["C33"].value if H_ARQ in wb.sheetnames else None
    finally:
        wb.close()
    return Base(valores, bloqueadas, _protegidas(ruta), caso)


# --------------------------------------------------------------------------- ficha
@dataclass
class FichaVirtual:
    ficha: Ficha                   # entradas del motor (entradas.Ficha)
    cev: dict                      # 'CEV-CEVE' {celda: valor}: constantes de la plantilla + lo escrito
    tablas: dict                   # '3. Tablas Envolvente'!A10:M92 {celda: valor}
    caso: object = 1               # '0. Datos Arq Motor'!C33 (el de la plantilla)
    avisos: list = field(default_factory=list)
    escritas: int = 0

    def guardar(self, ruta) -> Path:
        """JSON con las celdas (basta para volver a calcular: cargar())."""
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"cev": self.cev, "tablas": self.tablas, "caso": self.caso},
                                   ensure_ascii=False, default=str), encoding="utf-8")
        return ruta


def desde_celdas(cev: dict, tablas: dict, caso=1) -> FichaVirtual:
    te = {k: v for k, v in tablas.items() if en_rango(k, RANGO_TE)}
    return FichaVirtual(ficha_desde_cev(cev.get, te), dict(cev), te, caso)


def cargar(ruta) -> FichaVirtual:
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return desde_celdas(d["cev"], d["tablas"], d.get("caso", 1))


def construir(ficha_cev, proyecto: dict, mapa: dict | None = None, plantilla=PLANTILLA) -> FichaVirtual:
    """ficha_cev, proyecto: los de recinto.a_ficha.construir (los mismos que recibe escritor.generar)."""
    from herramientas.fichas_cev.escritor import escribir_catalogo, llenar
    from herramientas.fichas_cev.modelo import CLAVE_CATALOGO, cargar_mapa

    b = base(str(plantilla))
    mapa = mapa or cargar_mapa(MAPA_FICHA)
    hojas = {h: HojaVirtual(h, b.valores.get(h, {}), b.bloqueadas.get(h, ()), b.protegidas.get(h, False))
             for h in RANGOS}
    escribir_catalogo(LibroVirtual(hojas), proyecto.get(CLAVE_CATALOGO) or [], mapa)
    llenar(hojas[mapa["hoja"]], ficha_cev, proyecto, mapa)
    fv = desde_celdas(hojas[H_CEV].valores, hojas[H_TE].valores, b.caso if b.caso is not None else 1)
    fv.avisos = [a for h in hojas.values() for a in h.avisos]
    fv.escritas = sum(len(h.escritas) for h in hojas.values())
    return fv


# --------------------------------------------------------------------------- comparar con una ficha escrita
def celdas_xlsm(ruta) -> dict:
    """{hoja: {celda: constante}} de RANGOS en una ficha escrita (openpyxl)."""
    from openpyxl import load_workbook

    from .entradas import _constantes

    wb = load_workbook(Path(ruta), read_only=True, data_only=False, keep_links=False)
    try:
        return {h: _constantes(wb[h], r) for h, r in RANGOS.items()}
    finally:
        wb.close()


def comparar_celdas(virtual: dict, real: dict, ignorar=()) -> list:
    out = []
    for c in sorted(set(virtual) | set(real), key=lambda x: range_boundaries(x)[1::-1]):
        if c in ignorar:
            continue
        if not _igual(virtual.get(c), real.get(c)):
            out.append(f"{c}: virtual {virtual.get(c)!r} vs Excel {real.get(c)!r}")
    return out
