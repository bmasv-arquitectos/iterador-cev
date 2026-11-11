# -*- coding: utf-8 -*-
"""
Iterador CEV distribuido: python -m herramientas.app_unidad (y el programa empaquetado,
distribucion/iterador_cev.py).

Prepara el entorno (cache de numba y carpetas, comun/rutas_app.py) antes de importar la
app, y arma la pagina del editor (app.pagina) con lo de la distribucion
(distribucion_ui.py): rotulo con la version, solo el motor Python, el aviso legal al
abrir y el boton Acerca de. El modo (escritorio | web) sale de comun/distribucion.yaml
o de la variable ITERADOR_MODO. Icono de la pestana o ventana: comun/icono_app.py.

En escritorio empaquetado (o con ITERADOR_VENTANA=nativa) abre una ventana propia
(pywebview sobre WebView2) en un puerto libre, en vez del navegador; las descargas abren
el «Guardar como» de Windows (piezas.descargar_bytes).

    python -m herramientas.app_unidad --desarrollo

abre el editor sin nada de esto (app.main): en el navegador, con config/editor.yaml tal cual
y todos los motores que esten registrados.
"""
import sys

from herramientas.comun.rutas_app import preparar_entorno

preparar_entorno()

from nicegui import app, ui  # noqa: E402

from herramientas.app_unidad import app as editor_app  # noqa: E402
from herramientas.app_unidad import distribucion_ui  # noqa: E402
from herramientas.app_unidad.piezas import ICONOS  # noqa: E402
from herramientas.comun import app_config, icono_app  # noqa: E402
from herramientas.unidad import editor  # noqa: E402

DESARROLLO = "--desarrollo"


def _preparar_ventana(v: dict) -> None:
    """Opciones de pywebview (solo las que la version instalada conoce)."""
    import inspect

    import webview

    if v.get("maximizada") and "maximized" in inspect.signature(webview.create_window).parameters:
        app.native.window_args["maximized"] = True
    app.native.settings["ALLOW_DOWNLOADS"] = True          # respaldo si el «Guardar como» falla
    if v.get("depurar"):
        app.native.start_args["debug"] = True


def main() -> None:
    if DESARROLLO in sys.argv[1:]:
        editor_app.main()
        return
    cfg0 = editor.config()
    app.add_static_files("/iconos", str(ICONOS))
    titulo = f"{app_config.nombre()} {app_config.version()}"
    favicon = icono_app.svg()

    @ui.page("/", title=titulo)
    async def _inicio():
        cfg = distribucion_ui.preparar(editor.cargar_config())   # se relee con F5
        distribucion_ui.boton_acerca()
        distribucion_ui.aviso_inicial()
        await editor_app.pagina(cfg)

    v = app_config.ventana()
    if v["nativa"]:
        _preparar_ventana(v)
        ui.run(title=titulo, native=True, window_size=(int(v["ancho"]), int(v["alto"])), favicon=favicon,
               reload=False)
    else:
        ui.run(title=titulo, host=cfg0.get("host", "127.0.0.1"), port=cfg0["puerto"], favicon=favicon,
               show=cfg0["abrir_navegador"], reload=False)


if __name__ in ("__main__", "__mp_main__"):
    main()
