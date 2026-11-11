# -*- coding: utf-8 -*-
"""
Campos editables de un componente personalizado (muro, techo, piso, vidrio,
puerta). Se dibujan desde recinto/config/personalizado.yaml: agregar o quitar un
dato de la ficha no requiere tocar este archivo. Debajo se muestra el primer
problema de los datos (personalizado.validar), si lo hay.
"""
from __future__ import annotations

from nicegui import ui

from herramientas.recinto import personalizado as pz


def campos(elemento: str, datos: dict, al_cambiar, piso: str | None = None, debounce: int = 500,
           excluir=()) -> None:
    """al_cambiar(clave, valor) tras cada cambio."""
    for c in pz.campos(elemento, piso):
        k = c["clave"]
        if k in excluir:
            continue
        v = datos.get(k)
        if c["tipo"] == "texto":
            (ui.input(c["etiqueta"], value=v or "", on_change=lambda e, k=k: al_cambiar(k, e.value))
             .props(f"debounce={debounce} dense").classes("w-full"))
        elif c["tipo"] == "lista":
            (ui.select(pz.opciones(c), value=v, label=c["etiqueta"],
                       on_change=lambda e, k=k: e.value and al_cambiar(k, e.value))
             .props("dense").classes("w-full"))
        else:
            opcional = bool(c.get("opcional"))
            (ui.number(c["etiqueta"], value=v, min=c["min"], max=c["max"], step=c.get("paso", 0.01),
                       on_change=lambda e, k=k, o=opcional: (e.value is not None or o) and al_cambiar(k, e.value))
             .props(f"debounce={debounce} dense" + (" clearable" if opcional else "")).classes("w-full"))
    try:
        pz.validar(elemento, datos, piso)
    except ValueError as ex:
        ui.label(str(ex)).classes("errores")
