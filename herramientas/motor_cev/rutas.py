# -*- coding: utf-8 -*-
"""
Organizacion de las carpetas de salida.

    salidas/motor_cev/<proyecto>/<iteracion>/bloques/
                                            /resultados/

La ITERACION es la unidad de aislamiento y envuelve tambien a los bloques, no
solo a los resultados. Si se cambia la envolvente de un proyecto y se vuelve a
correr, los bloques anteriores ya no describen esa vivienda: reutilizarlos
daria un resultado de la iteracion pasada sin ninguna senal de que algo esta
mal. Cada corrida nueva parte de una carpeta limpia; para retomar una que
quedo a medias esta --continuar.
"""
from __future__ import annotations

import re
from pathlib import Path

PROHIBIDOS = '\\/|?*<>":'


def limpiar(nombre: str, defecto: str = "proyecto") -> str:
    texto = (nombre or "").strip()
    if not texto:
        return defecto
    for ch in PROHIBIDOS:
        texto = texto.replace(ch, "_")
    return texto


def iteraciones(carpeta_proyecto: Path) -> list[Path]:
    """Las iteraciones existentes, de la mas vieja a la mas nueva."""
    if not carpeta_proyecto.is_dir():
        return []
    return sorted(p for p in carpeta_proyecto.iterdir() if p.is_dir())


def ultima(carpeta_proyecto: Path) -> Path | None:
    existentes = iteraciones(carpeta_proyecto)
    return existentes[-1] if existentes else None


def siguiente_numero(carpeta_proyecto: Path) -> str:
    """001, 002... El numero es mas facil de seguir que una marca de tiempo."""
    usados = [
        int(m.group(1))
        for p in iteraciones(carpeta_proyecto)
        if (m := re.fullmatch(r"(\d{3})", p.name))
    ]
    return f"{max(usados, default=0) + 1:03d}"


def resolver(base: Path, proyecto: str, iteracion: str | None,
             continuar: bool) -> Path:
    """
    Devuelve la carpeta de trabajo de esta corrida.

    - Con nombre explicito: se usa esa, exista o no.
    - Con --continuar: la ultima que haya, para retomarla.
    - Sin nada: una nueva numerada.
    """
    carpeta_proyecto = Path(base) / limpiar(proyecto)

    if iteracion:
        destino = carpeta_proyecto / limpiar(iteracion, "001")
    elif continuar:
        destino = ultima(carpeta_proyecto)
        if destino is None:
            destino = carpeta_proyecto / "001"
    else:
        destino = carpeta_proyecto / siguiente_numero(carpeta_proyecto)

    (destino / "bloques").mkdir(parents=True, exist_ok=True)
    (destino / "resultados").mkdir(parents=True, exist_ok=True)
    return destino