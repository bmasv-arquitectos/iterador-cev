# -*- coding: utf-8 -*-
"""
Entradas del motor Python: lo que se escribe en la ficha 01 ('CEV-CEVE' y
'3. Tablas Envolvente'), con nombre, en un solo objeto (Ficha).

Las entradas no cambian entre los 10 casos: cada modulo recibe su parte con
Ficha.envolvente(caso), Ficha.uso(...) y Ficha.far. Lo que el perfil de uso lee
de 'CEV-CEVE' y es formula (superficie D56, volumen F52:F56, densidad de muros
G66:G81 y BW65, U y area de ventanas AB/AH, area de puertas AB) sale de
envolvente.py (ResultadoEnvolvente), no de la ficha.

De donde sale una Ficha:
  ficha_desde_cev(cev, tablas)   cev: funcion celda -> valor de 'CEV-CEVE'
  leer_ficha(ruta)               una ficha .xlsm (openpyxl, sin Excel; solo constantes)
La interfaz (iterador) la armara directamente.

Celdas de 'CEV-CEVE' (filas en envolvente.py):
  E9 comuna, E10 zona, E11 dormitorios, E16 tipo de vivienda (solo planilla 03),
  D52:E54 pisos (area, altura),
  muros D/E/H/K/L/M 66-81, P04 D/E/G/H/I 87-91, puertas D/E/K/L + FAV P:Y 96-98
  y H (categoria para infiltraciones), ventanas D/E/G/H/I/J/K/L/M/N + FAV 103-122,
  techos D/F/G/K/L 150-154, pisos D/F/G/K/L 158-161, obstrucciones E125:W146,
  F217 infiltracion variable, F219 ensayo, F221 ductos, F223 celosias,
  E227 recuperador, F229 eficiencia [%], F232 control, F234 ventilacion propuesta.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl.utils import range_boundaries

from . import envolvente as ev
from . import obstrucciones_far as of
from . import perfil_uso as pu
from .excel import es_numero

H_CEV, H_TE = ev.H_CEV, ev.H_TE
RANGO_CEV = "A1:Z239"          # lo que el motor oficial lee de 'CEV-CEVE'
RANGO_TE = "A10:M92"           # y de '3. Tablas Envolvente'


@dataclass(frozen=True)
class Ficha:
    comuna: object                  # E9
    zona: object                    # E10
    dormitorios: object             # E11
    pisos: tuple                    # D52:E54: (area, altura) x 3
    muros: tuple                    # 16 envolvente.Muro
    p04: tuple                      # 5 envolvente.P04
    puertas: tuple                  # 3 envolvente.Puerta
    puertas_infiltracion: tuple     # H96:H98 (categoria para infiltraciones)
    ventanas: tuple                 # 20 envolvente.Ventana
    techos: tuple                   # 5 envolvente.Techo
    pisos_env: tuple                # 4 envolvente.Piso
    infiltracion_variable: object   # F217
    infiltracion_ensayo: object     # F219 [1/h a 50 Pa]
    ductos: object                  # F221 [un]
    celosias: object                # F223 [un]
    recuperador: object             # E227
    eficiencia_recuperador: object  # F229 [%]
    control_ventilacion: object     # F232
    ventilacion_propuesta: object   # F234 [1/h]
    far: of.EntradasFar             # E125:W146
    tablas: dict = field(default_factory=dict, compare=False)   # '3. Tablas Envolvente' {celda: valor}
    # E16 (Casa / Departamento): solo lo usa la planilla 03 (demanda de referencia sin casos base).
    # Las referencias de Excel no lo guardan: diferencias() no lo compara.
    tipo_vivienda: object = field(default=None, metadata={"comparar": False})

    def envolvente(self, caso: int) -> ev.EntradasEnvolvente:
        return ev.EntradasEnvolvente(
            caso=caso, comuna=self.comuna, zona=self.zona, pisos=self.pisos, muros=self.muros,
            p04=self.p04, puertas=self.puertas, ventanas=self.ventanas, techos=self.techos,
            pisos_env=self.pisos_env, recuperador=self.recuperador,
            eficiencia_recuperador=self.eficiencia_recuperador, tablas=dict(self.tablas))

    def uso(self, caso: int, renv, zona, temporada, iluminancia) -> pu.EntradasUso:
        """renv: ResultadoEnvolvente del caso; temporada: inercia; iluminancia: radiacion_fav."""
        def c(celda):
            return renv.valor(H_CEV, celda)

        return pu.EntradasUso(
            caso=caso, dormitorios=self.dormitorios, superficie=c("D56"), volumen=c("F56"),
            infiltracion_variable=self.infiltracion_variable, recuperador=self.recuperador,
            control_ventilacion=self.control_ventilacion,
            ventilacion_propuesta=self.ventilacion_propuesta,
            area_pisos=tuple(a for a, _ in self.pisos),
            volumen_pisos=tuple(c(f"F{f}") for f in ev.FILAS_DIM),
            categoria_muros=renv.categoria_muros,
            muros=tuple(pu.Muro(c(f"G{f}"), m.area) for m, f in zip(self.muros, ev.FILAS_MURO)),
            ventanas=tuple(pu.Ventana(v.categoria, v.cierre, c(f"AB{f}"), c(f"AH{f}"))
                           for v, f in zip(self.ventanas, ev.FILAS_VENTANA)),
            puertas=tuple(pu.Puerta(h, c(f"AB{f}"))
                          for h, f in zip(self.puertas_infiltracion, ev.FILAS_PUERTA)),
            infiltracion_ensayo=self.infiltracion_ensayo, ductos=self.ductos, celosias=self.celosias,
            zona_clima=zona, temporada=tuple(temporada), iluminancia=tuple(iluminancia),
            base=renv.base_uso())


def ficha_desde_cev(cev, tablas: dict | None = None) -> Ficha:
    """cev: funcion celda -> valor de 'CEV-CEVE'; tablas: '3. Tablas Envolvente' (sin formulas)."""
    def fav(f):
        return tuple(cev(f"{c}{f}") for c in ev.FAV)

    return Ficha(
        comuna=cev("E9"), zona=cev("E10"), dormitorios=cev("E11"),
        pisos=tuple((cev(f"D{f}"), cev(f"E{f}")) for f in ev.FILAS_DIM),
        muros=tuple(ev.Muro(*(cev(f"{c}{f}") for c in "DEHKLM")) for f in ev.FILAS_MURO),
        p04=tuple(ev.P04(*(cev(f"{c}{f}") for c in "DEGHI")) for f in ev.FILAS_P04),
        puertas=tuple(ev.Puerta(*(cev(f"{c}{f}") for c in "DEKL"), fav(f)) for f in ev.FILAS_PUERTA),
        puertas_infiltracion=tuple(cev(f"H{f}") for f in ev.FILAS_PUERTA),
        ventanas=tuple(ev.Ventana(*(cev(f"{c}{f}") for c in "DEGHIJKLMN"), fav(f))
                       for f in ev.FILAS_VENTANA),
        techos=tuple(ev.Techo(*(cev(f"{c}{f}") for c in "DFGKL")) for f in ev.FILAS_TECHO),
        pisos_env=tuple(ev.Piso(*(cev(f"{c}{f}") for c in "DFGKL")) for f in ev.FILAS_PISO),
        infiltracion_variable=cev("F217"), infiltracion_ensayo=cev("F219"), ductos=cev("F221"),
        celosias=cev("F223"), recuperador=cev("E227"), eficiencia_recuperador=cev("F229"),
        control_ventilacion=cev("F232"), ventilacion_propuesta=cev("F234"),
        far=of.entradas_desde_cev(cev), tablas=dict(tablas or {}), tipo_vivienda=cev("E16"))


# --------------------------------------------------------------------------- desde un .xlsm
def _constantes(ws, rango: str) -> dict:
    """{celda: valor} de las celdas sin formula del rango (las formulas no son entradas)."""
    from .excel import texto_formula

    c1, f1, c2, f2 = range_boundaries(rango)
    out = {}
    for fila in ws.iter_rows(min_row=f1, max_row=f2, min_col=c1, max_col=c2):
        for c in fila:
            v = getattr(c, "value", None)
            if v is None or texto_formula(v):
                continue
            out[c.coordinate] = v if isinstance(v, (int, float, str, bool)) else str(v)
    return out


def leer_ficha(ruta) -> Ficha:
    """Ficha desde un .xlsm con openpyxl (solo lectura, sin Excel). Una celda de entrada con
    formula queda vacia: las entradas de la ficha son constantes."""
    from openpyxl import load_workbook

    wb = load_workbook(Path(ruta), read_only=True, data_only=False, keep_links=False)
    try:
        cev = _constantes(wb[H_CEV], RANGO_CEV)
        te = _constantes(wb[H_TE], RANGO_TE)
    finally:
        wb.close()
    return ficha_desde_cev(cev.get, te)


# --------------------------------------------------------------------------- comparar dos fichas
def _igual(a, b) -> bool:
    if es_numero(a) and es_numero(b):
        return float(a) == float(b)
    if a in (None, "") and b in (None, ""):
        return True
    return a == b


def diferencias(a, b, ruta: str = "ficha") -> list:
    """Donde difieren dos fichas (o partes). En dicts se revisan las claves de b. Los campos con
    metadata comparar=False (tipo_vivienda) no se comparan."""
    if dataclasses.is_dataclass(a) and dataclasses.is_dataclass(b):
        out = []
        for fl in dataclasses.fields(a):
            if not fl.metadata.get("comparar", True):
                continue
            out += diferencias(getattr(a, fl.name), getattr(b, fl.name), f"{ruta}.{fl.name}")
        return out
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        if len(a) != len(b):
            return [f"{ruta}: largo {len(a)} vs {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diferencias(x, y, f"{ruta}[{i}]")
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in b:
            out += diferencias(a.get(k), b.get(k), f"{ruta}[{k}]")
        return out
    return [] if _igual(a, b) else [f"{ruta}: {a!r} vs {b!r}"]
