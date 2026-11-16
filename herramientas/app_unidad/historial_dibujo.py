# -*- coding: utf-8 -*-
"""
Historial del perimetro que se esta dibujando (herramienta Dibujar muro del editor, app.py).

Cada punto que se agrega es un paso del historial (Ctrl+Z quita el ultimo punto). Al cerrar el
perimetro, o al cancelarlo con Esc, esos pasos se juntan en uno: el estado de antes del primer
punto. Asi:
  - Ctrl+Z despues de cerrar quita el perimetro nuevo entero y vuelve lo que habia (por
    ejemplo, el edificio que el dibujo nuevo reemplazo), sin dejar las lineas del dibujo;
  - Esc dibujando borra todo lo dibujado, como si no se hubiera empezado.

pila: {"atras": [...], "adelante": [...]} del editor; cada estado es (unidad, abiertos).
Los pasos se juntan solo si desde el primer punto la unidad no cambio (la misma Unidad en cada
estado y ahora): si entre medio se edito otra cosa, el historial no se toca.
No usa NiceGUI: se prueba sin interfaz.
"""
from __future__ import annotations


class DibujoEnCurso:
    def __init__(self):
        self.marca = None            # posicion en pila["atras"] del estado de antes del primer punto

    def empezar(self, pila: dict, puntos) -> None:
        """Antes de agregar un punto: si es el primero, recuerda donde empieza el dibujo."""
        if not puntos:
            self.marca = len(pila["atras"])

    def revisar(self, pila: dict) -> None:
        """Despues de deshacer: si se volvio a antes del primer punto, ya no hay dibujo en curso."""
        if self.marca is not None and self.marca >= len(pila["atras"]):
            self.marca = None

    def _juntar(self, pila: dict, u_actual):
        m, self.marca = self.marca, None
        atras = pila["atras"]
        if m is None or m >= len(atras):
            return None
        base = atras[m][0]
        if u_actual is not base or any(e[0] is not base for e in atras[m:]):
            return None
        estado = atras[m]
        del atras[m:]
        return estado

    def cerrar(self, pila: dict, u_actual):
        """Al cerrar: quita del historial los pasos de cada punto y devuelve el estado de antes del
        primero (el que se guarda como el paso de cerrar), o None si no corresponde."""
        return self._juntar(pila, u_actual)

    def cancelar(self, pila: dict, u_actual):
        """Esc: igual que cerrar; el estado devuelto es el que hay que restaurar (None: no se pudo)."""
        return self._juntar(pila, u_actual)
