# -*- coding: utf-8 -*-
"""
Borra lo viejo de una carpeta de salidas (modo web: las carpetas de calculo de los
visitantes no se acumulan en el servidor). La llama app_unidad/__main__.py al arrancar y
cada web.limpiar_cada_min minutos (comun/distribucion.yaml).

  limpiar(carpeta, horas)   borra los archivos con mas de `horas` sin cambios y las
                            carpetas que quedan vacias (con un minuto de gracia, para no
                            borrar una recien creada); nunca la carpeta misma. Devuelve
                            cuantos archivos borro.
"""
from __future__ import annotations

import time
from pathlib import Path

GRACIA_S = 60


def limpiar(carpeta, horas: float) -> int:
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return 0
    ahora = time.time()
    limite = ahora - float(horas) * 3600
    borrados = 0
    for p in sorted(carpeta.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        try:
            if p.is_file():
                if p.stat().st_mtime < limite:
                    p.unlink()
                    borrados += 1
            elif p.is_dir() and not any(p.iterdir()) and p.stat().st_mtime < ahora - GRACIA_S:
                p.rmdir()
        except OSError:
            pass                                   # en uso o sin permiso: queda para la proxima
    return borrados
