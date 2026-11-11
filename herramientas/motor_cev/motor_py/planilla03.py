# -*- coding: utf-8 -*-
"""
Planilla 03 en Python: de los 10 bloques de calculo() a la letra.

Traduce las formulas de la plantilla 03 (v2.2) que alimentan lo que lee el macro
oficial al terminar (RESUMEN). Inspeccion de la plantilla: 9.435 formulas, 36 patrones,
sin volatiles.

  'Resultados'  los bloques se pegan en C6:BE3125 (10 casos x 312 filas: 12 meses
                x [25 horas + 1 vacia]); por fila:
                  BF   hora 0-23 (constante en la hora 0, =+BF anterior + 1)
                  BH   HD(-): 1 si T interior (T) < limite inferior de confort
                       del mes (BN7:BZ16; de noche, BF <= BP3 o BF >= BO3, 2 grados menos)
                  BI   HD(+): 1 si T > limite superior (BN20:BZ29)
                BO7:BZ16 = 18.9+0.255*Tm-2.6 y BO20:BZ29 = 18.9+0.255*Tm+2.6 (Tm: BO33:BZ42).
  'Resumen'     O19:Z28  demanda de calefaccion (AI) y refrigeracion (AJ) por mes y caso
                         (SUMAR.SI.CONJUNTO por la etiqueta del caso BG y el mes E) x dias/1000
                O30:Z30, O35:Z35  horas de disconfort del caso propuesto sin clima (BF < 24)
                C7/D7 promedio de los 4 casos base con clima; E7/F7 por m2 ('CEV CEVE'!I15 =
                'CEV-CEVE'!D56); C8/D8 propuesto; I7, I8, J7 = 1 - I8/I7 y la letra K7.
                E15/F15 = horas HD(-)/HD(+) / 288.

Entradas: EntradasPlanilla03 (los bloques de calculo_py y de 'CEV-CEVE' la superficie D56,
la zona E10 y el tipo de vivienda E16). Constantes: DatosPlanilla03 (motor_py/datos/planilla03.yaml).

Particularidades que se replican (no se corrigen):
  - La demanda (AI, AJ) suma las 25 filas del dia, tambien la hora 24; el disconfort
    solo BF < 24.
  - El confort usa la zona escrita en 'CEV-CEVE'!E10, no la zona de clima ('0. Clima'!M2).
  - Una fila vacia de los bloques (la 26 de cada mes) cuenta como T = 0 en BI y BH no la
    cuenta porque BF esta vacio.
  - La clave disconfort_calor (RESUMEN) es E15, pero E15 = HD(-)/288 (horas bajo la banda:
    frio) y F15 = HD(+)/288 (calor). Aca se deja ese nombre: hay que revisarlo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from openpyxl.utils import column_index_from_string, get_column_letter

from .datos import DIR, _yaml
from .excel import (
    NA, Tabla, ar, buscarv, clave, copia, es_error, es_numero, iferror, igual, indice, mayor,
    mayor_igual, menor, menor_igual, o_, posicion_aproximada, promedio_rango, si, suma_rango, texto,
)

YAML_P03 = "planilla03.yaml"
H_RES, H_RESU, H_CEV03, H_CEV = "Resultados", "Resumen", "CEV CEVE", "CEV-CEVE"
FILA0, FILAS_CASO, CASOS, ANCHO = 6, 312, 10, 55
FILA_FIN = FILA0 + FILAS_CASO * CASOS - 1           # 3125
FILA_CONTROL = 3000                                  # Resultados!C3000
MESES = 12
COLS_MES = tuple(get_column_letter(15 + j) for j in range(MESES))                         # O..Z
COLS_ZONA = tuple(get_column_letter(column_index_from_string("BO") + j) for j in range(MESES))  # BO..BZ
I_TIEMPO, I_MES, I_T, I_CALEF, I_REF = 0, 2, 17, 32, 33   # columnas C, E, T, AI, AJ del bloque
FILAS_CALEF, FILAS_REF = range(19, 24), range(24, 29)
FILAS_HD = ((30, "BH"), (35, "BI"))
LETRAS = ((0.85, "A+"), (0.7, "A"), (0.55, "B"), (0.4, "C"), (0.2, "D"), (-0.1, "E"), (-0.35, "F"))
RESUMEN = {"demanda_calefaccion": "C72", "demanda_refrigeracion": "C73", "demanda_total": "C74",
           "ahorro_calefaccion": "G8", "ahorro_refrigeracion": "H8", "ahorro_total": "C92",
           "letra": "K7", "disconfort_calor": "E15", "disconfort_frio": "F15"}
EXTRA = {"caso_base": "B7", "demanda_base_total": "I7", "demanda_prop_total": "I8"}


@dataclass(frozen=True)
class DatosPlanilla03:
    resultados: dict       # constantes de 'Resultados'!BF1:BZ3126 (hora, etiqueta del caso, Tm, BO3, BP3)
    resumen: dict          # constantes de 'Resumen'!N4:AH35 (dias O4:Z4, mes O5, etiquetas N19:N35, AD7:AH15)
    filas_bf: frozenset    # filas de BF con formula =+BF(r-1)+1
    origen: dict = field(default_factory=dict, compare=False)


def cargar_planilla03(carpeta: Path = DIR) -> DatosPlanilla03:
    cfg = _yaml(carpeta, YAML_P03)
    k = cfg.get("constantes") or {}
    return DatosPlanilla03(dict(k.get(H_RES) or {}), dict(k.get(H_RESU) or {}),
                           frozenset(cfg.get("filas_bf") or ()), cfg.get("origen") or {})


def celdas_resumen() -> dict:
    """{clave: celda del Resumen}: las que lee el macro oficial al terminar (RESUMEN) mas B7, I7 e I8."""
    return {**RESUMEN, **EXTRA}


@dataclass(frozen=True)
class EntradasPlanilla03:
    bloques: tuple         # 10 bloques de 312 filas: None (fila vacia) o 55 valores (columnas C..BE)
    superficie: object     # 'CEV-CEVE'!D56 [m2]
    zona: object           # 'CEV-CEVE'!E10
    tipo_vivienda: object  # 'CEV-CEVE'!E16 (Casa / Departamento)


@dataclass(frozen=True)
class ResultadoPlanilla03:
    celdas: dict           # {hoja: {celda: valor}}
    resumen: dict          # {clave: valor} (celdas_resumen)

    def valor(self, hoja, celda):
        return self.celdas.get(hoja, {}).get(celda)


def letra(j):
    """K7: A+ > 0,85 ... F > -0,35, si no G."""
    for limite, l in LETRAS:
        c = mayor(j, limite)
        if es_error(c):
            return c
        if c:
            return l
    return "G"


def _izquierda(v, n: int):
    return v if es_error(v) else texto(v)[:n]


def _buscar(valor, claves, resultados):
    """BUSCAR(valor; claves; resultados): coincidencia aproximada en claves ordenadas."""
    if es_error(valor):
        return valor
    i = posicion_aproximada(claves, valor)
    return NA if i is None else copia(resultados[i])


def calcular(d: DatosPlanilla03, e: EntradasPlanilla03, resumen: dict | None = None) -> ResultadoPlanilla03:
    k, s = d.resultados, d.resumen
    res, rsm = {}, {}

    def bloque(r, i):
        kk, j = divmod(r - FILA0, FILAS_CASO)
        if kk >= len(e.bloques) or e.bloques[kk] is None or j >= len(e.bloques[kk]):
            return None
        fila = e.bloques[kk][j]
        return None if fila is None or i >= len(fila) else fila[i]

    filas = range(FILA0, FILA_FIN + 1)

    # ------------------------------------------------ Resultados: hora 0-23 (BF)
    bf = {}
    for r in filas:
        if r in d.filas_bf:
            v = res[f"BF{r}"] = ar(lambda x: x + 1, bf[r - 1] if r - 1 in bf else k.get(f"BF{r - 1}"))
        else:
            v = k.get(f"BF{r}")
        bf[r] = v

    # ------------------------------------------------ bandas de confort por zona y mes
    for c in COLS_ZONA:
        for i in range(10):
            tm = k.get(f"{c}{33 + i}")
            res[f"{c}{7 + i}"] = ar(lambda t: 18.9 + 0.255 * t - 2.6, tm)
            res[f"{c}{20 + i}"] = ar(lambda t: 18.9 + 0.255 * t + 2.6, tm)
    t_min = Tabla(tuple((k.get(f"BN{r}"),) + tuple(res[f"{c}{r}"] for c in COLS_ZONA) for r in range(7, 17)))
    t_max = Tabla(tuple((k.get(f"BN{r}"),) + tuple(res[f"{c}{r}"] for c in COLS_ZONA) for r in range(20, 30)))
    zona, bo3, bp3 = e.zona, k.get("BO3"), k.get("BP3")

    # ------------------------------------------------ horas de disconfort por fila (BH, BI)
    etiquetas, meses_f, calef, refr, hd_m, hd_p, horas = [], [], [], [], [], [], []
    for r in filas:
        mes, t, h = bloque(r, I_MES), bloque(r, I_T), bf[r]
        col = ar(lambda x: 1 + x, mes)
        inf = buscarv(zona, t_min, col)
        noche = o_(menor_igual(h, bp3), mayor_igual(h, bo3))
        lim = si(noche, ar(lambda x: x - 2, inf), inf)
        bh = res[f"BH{r}"] = iferror(si(igual(h, ""), 0.0, si(menor(t, lim), 1.0, 0.0)), 0.0)
        bi = res[f"BI{r}"] = iferror(si(mayor(t, buscarv(zona, t_max, col)), 1.0, 0.0), 0.0)
        etiquetas.append(k.get(f"BG{r}"))
        meses_f.append(mes)
        calef.append(bloque(r, I_CALEF))
        refr.append(bloque(r, I_REF))
        hd_m.append(bh)
        hd_p.append(bi)
        horas.append(h)
    ix = indice(etiquetas, meses_f)

    def sumar(valores, caso, mes, menor_24: bool):
        """SUMAR.SI.CONJUNTO(valores; BG; caso; E; mes [; BF; "<24"]) en orden de filas."""
        for x in (caso, mes):
            if es_error(x):
                return x
        total = 0.0
        for i in ix.get((clave(caso), clave(mes)), ()):
            if menor_24 and not (es_numero(horas[i]) and horas[i] < 24):
                continue
            v = valores[i]
            if es_error(v):
                return v
            if es_numero(v):
                total += v
        return total

    # ------------------------------------------------ Resumen: por mes y caso
    meses = [s.get("O5")]
    for j in range(1, MESES):
        meses.append(rsm.setdefault(f"{COLS_MES[j]}5", ar(lambda x: x + 1, meses[-1])))
    for filas_r, valores in ((FILAS_CALEF, calef), (FILAS_REF, refr)):
        for r in filas_r:
            for j, c in enumerate(COLS_MES):
                rsm[f"{c}{r}"] = ar(lambda a, dias: a * dias / 1000,
                                    sumar(valores, s.get(f"N{r}"), meses[j], False), s.get(f"{c}4"))
    for r, col in FILAS_HD:
        valores = hd_m if col == "BH" else hd_p
        for j, c in enumerate(COLS_MES):
            rsm[f"{c}{r}"] = sumar(valores, s.get(f"N{r}"), meses[j], True)
    for r in list(FILAS_CALEF) + list(FILAS_REF) + [r for r, _ in FILAS_HD]:
        rsm[f"AA{r}"] = suma_rango([rsm[f"{c}{r}"] for c in COLS_MES])

    def aa(*rs):
        return [rsm[f"AA{r}"] for r in rs]

    # ------------------------------------------------ Resumen: totales, ahorro y letra
    sin_bloques = igual(bloque(FILA_CONTROL, I_TIEMPO), "")
    i15 = copia(e.superficie)
    ad19 = rsm["AD19"] = copia(e.zona)
    ad20 = rsm["AD20"] = _izquierda(e.tipo_vivienda, 4)
    claves = [s.get(f"AD{r}") for r in range(7, 16)]
    casa = igual(ad20, "Casa")
    for celda, c_casa, c_depa in (("AD21", "AE", "AG"), ("AD22", "AF", "AH")):
        rsm[celda] = si(casa, _buscar(ad19, claves, [s.get(f"{c_casa}{r}") for r in range(7, 16)]),
                        _buscar(ad19, claves, [s.get(f"{c_depa}{r}") for r in range(7, 16)]))
    c7 = rsm["C7"] = si(sin_bloques, "Prueba no Oficial", promedio_rango(aa(20, 21, 22, 23)))
    d7 = rsm["D7"] = si(sin_bloques, " Ejecutar 02.PBTD CON Caso Base", promedio_rango(aa(25, 26, 27, 28)))
    e7 = rsm["E7"] = si(sin_bloques, rsm["AD21"], ar(lambda a, b: a / b, c7, i15))
    f7 = rsm["F7"] = si(sin_bloques, rsm["AD22"], ar(lambda a, b: a / b, d7, i15))
    c8 = rsm["C8"] = copia(rsm["AA19"])
    d8 = rsm["D8"] = copia(rsm["AA24"])
    e8 = rsm["E8"] = ar(lambda a, b: a / b, c8, i15)
    f8 = rsm["F8"] = ar(lambda a, b: a / b, d8, i15)
    i7 = rsm["I7"] = ar(lambda a, b: a - b, e7, f7)
    i8 = rsm["I8"] = ar(lambda a, b: a - b, e8, f8)
    j7 = rsm["J7"] = iferror(ar(lambda a, b: 1 - a / b, i8, i7), 0.0)
    rsm["K7"] = letra(j7)
    rsm["G8"] = iferror(ar(lambda a, b: 1 - a / b, e8, e7), 0.0)
    rsm["H8"] = iferror(ar(lambda a, b: 1 - a / b, f8, f7), 0.0)
    rsm["B7"] = si(igual(promedio_rango(aa(20, 21, 22, 23)), 0), "Caso Base de Prueba NO OFICIAL",
                   "Caso Base Oficial")
    c15 = rsm["C15"] = copia(rsm["AA30"])
    d15 = rsm["D15"] = copia(rsm["AA35"])
    rsm["E15"] = ar(lambda a: a / (24 * 12), c15)
    rsm["F15"] = ar(lambda a: a / (24 * 12), d15)
    rsm["C72"] = copia(e8)
    rsm["C73"] = ar(abs, f8)
    rsm["C74"] = copia(i8)
    rsm["C92"] = copia(j7)

    celdas = {H_RES: res, H_RESU: rsm, H_CEV03: {"I15": i15}}
    resumen = resumen or celdas_resumen()
    return ResultadoPlanilla03(celdas, {k_: rsm.get(c) for k_, c in resumen.items()})


def desde_corridas(f, corridas, tipo_vivienda=None) -> EntradasPlanilla03:
    """Entradas desde motor.correr (los 10 casos) y la Ficha."""
    por_caso = {c.caso: c for c in corridas}
    faltan = [n for n in range(1, CASOS + 1) if n not in por_caso]
    if faltan:
        raise ValueError(f"faltan los casos {faltan}: la planilla 03 promedia los casos base")
    renv = por_caso[1].resultado.resultados["envolvente"]
    tipo = getattr(f, "tipo_vivienda", None) if tipo_vivienda is None else tipo_vivienda
    return EntradasPlanilla03(tuple(por_caso[n].filas for n in range(1, CASOS + 1)),
                              renv.valor(H_CEV, "D56"), f.zona, tipo)
