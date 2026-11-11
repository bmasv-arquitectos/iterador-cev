# -*- coding: utf-8 -*-
"""
Punto de entrada del ejecutable de Windows (distribucion/iterador_cev.spec).

- multiprocessing.freeze_support(): la ventana propia de NiceGUI corre en un proceso
  aparte; sin esto, el .exe se abriria a si mismo una y otra vez.
- Sin consola (programa de ventana), sys.stdout y sys.stderr no existen y uvicorn falla al
  escribir: se mandan a <carpeta del usuario>/registro.txt (se rehace en cada arranque;
  sirve para diagnosticar).
"""
import multiprocessing
import sys


def _registro() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    from herramientas.comun.rutas_app import carpeta_usuario

    carpeta = carpeta_usuario()
    carpeta.mkdir(parents=True, exist_ok=True)
    f = open(carpeta / "registro.txt", "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or f
    sys.stderr = sys.stderr or f


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _registro()
    from herramientas.app_unidad.__main__ import main

    main()
