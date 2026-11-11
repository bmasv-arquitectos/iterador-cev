# -*- coding: utf-8 -*-
"""
Criterios de Excel que replica el motor Python.

  - Igualdad de BUSCARV / SUMAR.SI.CONJUNTO: texto sin distinguir mayusculas,
    numeros como float (clave, coincide). Una celda con error no coincide.
  - Comparacion (<, >, =): numeros < texto < logicos; una celda vacia vale 0
    frente a un numero y "" frente a un texto (comparar).
  - Errores (#N/A, #DIV/0!, #VALUE!, #NUM!, #REF!): ErrorExcel, subclase de
    str, asi se comparan igual que los textos de la referencia. Se propagan
    por las cuentas (ar), SI, Y, O y las busquedas; SI.ERROR los reemplaza.
  - Celdas vacias: valen 0 al copiarlas (=+celda) o al usarlas en una cuenta.
  - Sumas en orden, sin compensar el redondeo (Excel no usa fsum; sum() de
    Python >= 3.12 si compensa: no usarlo en el motor). a+b+c = (a+b)+c (mas).
  - Funciones sobre rangos (SUMA, PROMEDIO, MIN, MAX) ignoran textos y vacias;
    sobre argumentos sueltos (MIN(BUSCARV(); BUSCARV())) un texto da #VALUE!.
  - Numero -> texto (CONCATENAR): 15 cifras significativas y punto decimal
    (lo confirma la ficha: "LivianoInterior0.18").
  - TRUNCAR(x; n) con n > 0 trabaja sobre las 15 cifras que muestra Excel
    (TRUNCAR(0,29; 2) = 0,29 aunque 0,29 en binario sea 0,28999...).
"""
from __future__ import annotations

import math
import numbers
import operator
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from functools import reduce


class ErrorExcel(str):
    """Valor de error de Excel. Es str para compararlo con la referencia ('#N/A')."""

    __slots__ = ()


NA = ErrorExcel("#N/A")
DIV0 = ErrorExcel("#DIV/0!")
VALOR = ErrorExcel("#VALUE!")
NUM = ErrorExcel("#NUM!")
REF = ErrorExcel("#REF!")


def es_error(v) -> bool:
    return isinstance(v, ErrorExcel)


def es_numero(v) -> bool:
    return isinstance(v, numbers.Real) and not isinstance(v, bool)


# --------------------------------------------------------------------------- igualdad y sumas
def clave(v):
    """Clave de igualdad de Excel: texto sin distinguir mayusculas, numeros como float."""
    if isinstance(v, str):
        return ("t", v.casefold())
    if isinstance(v, bool):
        return ("b", v)
    if es_numero(v):
        return ("n", float(v))
    return ("v", None)


def coincide(celda, criterio) -> bool:
    """Igualdad de SUMAR.SI.CONJUNTO / BUSCARV exacto (sin comodines)."""
    return clave(celda) == clave(criterio)


def suma_secuencial(valores) -> float:
    """Suma en orden, como Excel (no pairwise ni fsum)."""
    total = 0.0
    for v in valores:
        total += v
    return total


def buscar(claves, valor) -> int:
    """Indice de la primera coincidencia exacta (BUSCARV(...;0)); KeyError = #N/A."""
    for i, k in enumerate(claves):
        if coincide(k, valor):
            return i
    raise KeyError(f"#N/A: {valor!r} no esta en la tabla")


def indice(*columnas) -> dict:
    """{claves de la fila: [filas en orden]} para SUMAR.SI.CONJUNTO."""
    idx: dict = {}
    for i, fila in enumerate(zip(*columnas)):
        idx.setdefault(tuple(clave(v) for v in fila), []).append(i)
    return idx


def sumar_si(idx: dict, valores, *criterios) -> float:
    """SUMAR.SI.CONJUNTO: suma, en orden, los numeros de las filas que coinciden (0 si no hay)."""
    total = 0.0
    for i in idx.get(tuple(clave(c) for c in criterios), ()):
        v = valores[i]
        if es_numero(v):
            total += v
    return total


def sumar_si_lista(valores, criterios, criterio):
    """SUMAR.SI.CONJUNTO(valores; criterios; criterio) sobre listas."""
    if es_error(criterio):
        return criterio
    total = 0.0
    for v, k in zip(valores, criterios):
        if k is not None and not es_error(k) and coincide(k, criterio):
            if es_error(v):
                return v
            if es_numero(v):
                total += v
    return total


# --------------------------------------------------------------------------- valores y cuentas
def copia(v):
    """=+celda: una celda vacia vale 0."""
    return 0.0 if v is None else v


def numero(v):
    """Operando de una cuenta: vacia -> 0, logico -> 1/0, texto numerico -> numero, otro texto -> #VALUE!."""
    if es_error(v):
        return v
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if es_numero(v):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return VALOR
    return VALOR


def ar(fn, *args):
    """Cuenta con criterio de Excel: el primer error se propaga; /0 -> #DIV/0!; dominio -> #NUM!."""
    vals = [numero(a) for a in args]
    for v in vals:
        if es_error(v):
            return v
    try:
        r = fn(*vals)
    except ZeroDivisionError:
        return DIV0
    except (ValueError, OverflowError):
        return NUM
    if isinstance(r, float) and not math.isfinite(r):
        return NUM
    return r


def mas(*valores):
    """a + b + c ... en orden: ((a + b) + c)."""
    return ar(lambda *v: reduce(operator.add, v), *valores)


def trunc(v):
    """TRUNCAR(x; 0) y REDONDEAR.MENOS(x; 0): hacia cero."""
    return ar(lambda x: float(math.trunc(x)), v)


def _truncar(x: float, n: float) -> float:
    n = int(n)
    if x == 0:
        return 0.0
    try:
        d = Decimal(f"{x:.15g}")
        return float(d.quantize(Decimal(1).scaleb(-n), rounding=ROUND_DOWN))
    except InvalidOperation:
        f = 10.0 ** n
        return math.trunc(x * f) / f


def truncar(v, decimales=0):
    """TRUNCAR(x; n): hacia cero con n decimales, sobre las 15 cifras significativas."""
    return ar(_truncar, v, decimales)


def _numeros(valores):
    """Numeros de un rango (textos, logicos y vacias se ignoran), o el primer error."""
    nums = []
    for v in valores:
        if es_error(v):
            return v
        if es_numero(v):
            nums.append(float(v))
    return nums


def suma_rango(valores):
    """SUMA de un rango: el primer error se propaga; textos, logicos y vacias no suman."""
    total = 0.0
    for v in valores:
        if es_error(v):
            return v
        if es_numero(v):
            total += v
    return total


def promedio_rango(valores):
    """PROMEDIO de un rango: solo numeros; sin numeros -> #DIV/0!."""
    nums = _numeros(valores)
    if es_error(nums):
        return nums
    if not nums:
        return DIV0
    return suma_secuencial(nums) / len(nums)


def max_rango(valores):
    """MAX de celdas: solo numeros; sin numeros -> 0."""
    nums = _numeros(valores)
    if es_error(nums):
        return nums
    return max(nums) if nums else 0.0


def min_rango(valores):
    """MIN de celdas: solo numeros; sin numeros -> 0."""
    nums = _numeros(valores)
    if es_error(nums):
        return nums
    return min(nums) if nums else 0.0


def _args(valores):
    nums = []
    for v in valores:
        n = numero(v)
        if es_error(n):
            return n
        nums.append(n)
    return nums


def min_args(*valores):
    """MIN(a; b) con valores sueltos: vacio -> 0, texto no numerico -> #VALUE!."""
    nums = _args(valores)
    return nums if es_error(nums) else min(nums)


def max_args(*valores):
    """MAX(a; b) con valores sueltos: vacio -> 0, texto no numerico -> #VALUE!."""
    nums = _args(valores)
    return nums if es_error(nums) else max(nums)


def large(valores, k):
    """K.ESIMO.MAYOR: solo numeros; k fuera de rango -> #NUM!."""
    nums = _numeros(valores)
    if es_error(nums):
        return nums
    k = numero(k)
    if es_error(k):
        return k
    k = int(math.ceil(k))
    if not 1 <= k <= len(nums):
        return NUM
    return sorted(nums, reverse=True)[k - 1]


# --------------------------------------------------------------------------- comparaciones y logica
def _rango(v) -> int:
    if isinstance(v, bool):
        return 2
    if isinstance(v, str):
        return 1
    return 0


def _vacio_como(otro):
    if isinstance(otro, str):
        return ""
    if isinstance(otro, bool):
        return False
    return 0.0


def comparar(a, b):
    """-1, 0 o 1 como Excel (numeros < texto < logicos), o el error."""
    if es_error(a):
        return a
    if es_error(b):
        return b
    if a is None:
        a = _vacio_como(b)
    if b is None:
        b = _vacio_como(a)
    ra, rb = _rango(a), _rango(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 1:
        a, b = a.casefold(), b.casefold()
    elif ra == 0:
        a, b = float(a), float(b)
    return (a > b) - (a < b)


def _cmp(a, b, prueba):
    r = comparar(a, b)
    return r if es_error(r) else prueba(r)


def igual(a, b):
    return _cmp(a, b, lambda r: r == 0)


def distinto(a, b):
    return _cmp(a, b, lambda r: r != 0)


def mayor(a, b):
    return _cmp(a, b, lambda r: r > 0)


def menor(a, b):
    return _cmp(a, b, lambda r: r < 0)


def mayor_igual(a, b):
    return _cmp(a, b, lambda r: r >= 0)


def menor_igual(a, b):
    return _cmp(a, b, lambda r: r <= 0)


def si(condicion, verdadero, falso=False):
    """SI: un error en la condicion se propaga; un texto da #VALUE!."""
    if es_error(condicion):
        return condicion
    if isinstance(condicion, str):
        return VALOR
    return verdadero if condicion else falso


def y_(*condiciones):
    """Y: el primer error se propaga."""
    for c in condiciones:
        if es_error(c):
            return c
    return all(bool(c) for c in condiciones)


def o_(*condiciones):
    """O: el primer error se propaga."""
    for c in condiciones:
        if es_error(c):
            return c
    return any(bool(c) for c in condiciones)


def iferror(v, alternativa):
    """SI.ERROR."""
    return alternativa if es_error(v) else v


# --------------------------------------------------------------------------- texto
def texto_numero(v: float) -> str:
    """Numero -> texto como CONCATENAR: 15 cifras significativas."""
    return f"{float(v):.15g}".replace("e", "E")


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):        # PENDIENTE: en Excel en espanol podria ser VERDADERO/FALSO
        return "TRUE" if v else "FALSE"
    if es_numero(v):
        return texto_numero(v)
    return str(v)


def concatenar(*valores):
    for v in valores:
        if es_error(v):
            return v
    return "".join(texto(v) for v in valores)


# --------------------------------------------------------------------------- formulas (openpyxl)
def texto_formula(v) -> str | None:
    """Texto de la formula de una celda leida con openpyxl, o None si la celda es un valor."""
    if isinstance(v, str) and v.startswith("="):
        return v
    nombre = type(v).__name__
    if nombre == "ArrayFormula":
        return getattr(v, "text", None) or "={matricial}"
    if nombre == "DataTableFormula":
        return (f"=TABLE(r1={getattr(v, 'r1', '')}, "
                f"r2={getattr(v, 'r2', '')})  [tabla de datos]")
    return None


# --------------------------------------------------------------------------- busquedas
@dataclass(frozen=True)
class Tabla:
    """Rango de busqueda: filas con todas sus columnas (la primera es la clave)."""

    filas: tuple
    celda: str = ""

    @property
    def claves(self) -> tuple:
        return tuple(f[0] for f in self.filas)


def posicion(claves, valor):
    """Indice de la primera coincidencia exacta, o None."""
    if valor is None or es_error(valor):
        return None
    for i, k in enumerate(claves):
        if k is not None and not es_error(k) and coincide(k, valor):
            return i
    return None


def posicion_aproximada(claves, valor):
    """BUSCARV(...;VERDADERO) con la tabla ordenada: la ultima clave <= valor, del mismo tipo."""
    if valor is None or es_error(valor):
        return None
    tipo, mejor = _rango(valor), None
    for i, k in enumerate(claves):
        if k is None or es_error(k) or _rango(k) != tipo:
            continue
        if comparar(k, valor) <= 0:
            mejor = i
        else:
            break
    return mejor


def buscarv(valor, tabla: Tabla, columna, exacto: bool = True):
    """BUSCARV: #N/A si no esta, #REF! si la columna no existe, vacia -> 0."""
    if es_error(valor):
        return valor
    col = numero(columna)
    if es_error(col):
        return col
    col = int(col)
    if col < 1:
        return VALOR
    i = posicion(tabla.claves, valor) if exacto else posicion_aproximada(tabla.claves, valor)
    if i is None:
        return NA
    fila = tabla.filas[i]
    if col > len(fila):
        return REF
    v = fila[col - 1]
    return 0.0 if v is None else v


def elegir(indice_, *opciones):
    """ELEGIR: el indice se trunca; fuera de rango -> #VALUE!."""
    n = numero(indice_)
    if es_error(n):
        return n
    n = int(n)
    if not 1 <= n <= len(opciones):
        return VALOR
    return copia(opciones[n - 1])
