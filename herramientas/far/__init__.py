# -*- coding: utf-8 -*-
"""
Motor geométrico del FAR (obstrucciones remotas), capa B.

Traduce un contexto dibujado (volúmenes con planta poligonal y altura desde el
terreno natural) a obstrucciones por división (A, B, D).

No depende del resto del proyecto: solo la biblioteca estándar. Se puede copiar
tal cual a otro programa (Rhino 8, Grasshopper, un servidor) o usar por JSON:

    python -m herramientas.far calcular entrada.json --tabla
    python -m herramientas.far ejemplo

Convención: x hacia el este, y hacia el norte, metros. Azimut en grados desde
el norte en sentido horario. Ángulos relativos (theta): grados respecto de la
normal de la fachada, negativos a la izquierda de quien mira desde adentro.
"""
from .modelo import (
    DESCARTES, Obstruccion, Omitida, Parametros, Punto, ResultadoPunto, Volumen, a_dict, desde_dict,
)
from .motor import calcular, calcular_json, calcular_punto, tabla

__all__ = [
    "DESCARTES", "Obstruccion", "Omitida", "Parametros", "Punto", "ResultadoPunto", "Volumen",
    "a_dict", "desde_dict", "calcular", "calcular_json", "calcular_punto", "tabla",
]
