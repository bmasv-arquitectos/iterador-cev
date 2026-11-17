# -*- coding: utf-8 -*-
"""
NiceGUI en el navegador (Pyodide), sin servidor: la interfaz web es la misma del instalable
(herramientas/app_unidad: app.pagina con distribucion_ui, como al arrancar el instalable en
modo web). La pagina web/index.html (src/apps/iterador-nicegui) la muestra en un iframe.

Como funciona
  - NiceGUI corre completo en este worker, salvo el servidor. La pagina se arma llamando al
    mismo envoltorio de ui.page que usaria FastAPI (pagina()). Lo que NiceGUI manda por
    socket.io (core.sio.emit) sale por canal_js (web/src/python/worker.ts) hacia la pagina,
    que lo pasa al iframe. En el iframe, web/public/puente/socketio_puente.js reemplaza a
    socket.io: lo que el navegador emite (conexion, eventos, respuestas de JavaScript, ack y
    log) llega a recibir(), que llama a los mismos manejadores del modulo nicegui.nicegui.
  - Las subidas (ui.upload) no van por HTTP: el puente las manda a subir().
  - Los archivos de NiceGUI para el navegador (Vue, Quasar, componentes y librerias) estan
    copiados en web/public/ng/_nicegui/<version>/ (npm run nicegui): static/ y nicegui/.
    Las URL con claves (libraries/<clave>, components/<clave>, esm/, resources/) se reescriben
    a esa copia (reescribir()); /iconos/ va a web/public/iconos/ (npm run python).
  - Calcular: el panel usa la calculadora calculo_navegador (calculo.modulo), que pide el
    calculo a la pagina; la pagina lo corre repartido en los procesos de calculo y la interfaz
    sigue viva, con la barra de progreso.
  - Reporte (PDF): sin PyMuPDF, el reporte se arma en HTML y se abre la impresion del
    navegador («Guardar como PDF»): reporte_web.activar.
  - compat_pyodide.preparar() antes de importar NiceGUI.

  sonda()                             importa NiceGUI y la interfaz y mide cuanto tarda
                                      (pagina de diagnostico, solo en desarrollo)
  iniciar(base)                       configura NiceGUI (lo de ui.run que aplica) y registra la
                                      pagina; base: la direccion de la carpeta del sitio
  pagina()                            el HTML de la pagina, para el iframe
  recibir(evento, datos)              lo que emite el navegador
  subir(cliente, elemento, archivos)  archivos elegidos en un ui.upload
"""
from __future__ import annotations

import base64
import importlib
import os
import sys
import time
import traceback
from pathlib import Path, PurePath

from . import compat_pyodide

MODULOS = ("fastapi", "starlette", "pydantic", "socketio", "engineio", "uvicorn", "httpx", "jinja2",
           "markdown2", "pygments", "docutils", "aiofiles", "itsdangerous", "ifaddr", "orjson", "aiohttp",
           "nicegui", "nicegui.ui", "nicegui.events", "nicegui.run", "nicegui.background_tasks",
           "herramientas.app_unidad.piezas", "herramientas.app_unidad.paneles",
           "herramientas.app_unidad.calculo_ui", "herramientas.app_unidad.vista3d_ui",
           "herramientas.app_unidad.contexto_ui", "herramientas.app_unidad.app",
           "herramientas.app_unidad.distribucion_ui")
SID = "test-navegador"          # con el prefijo test- NiceGUI no pide el entorno del websocket
CANAL = "nicegui"               # canal de canal_js (worker.ts)
CARPETA_NG = "ng"               # web/public/ng/_nicegui/<version>/
ESPEJO = "../nicegui/"          # desde libraries/, components/... hasta la copia de nicegui/
ESTATICOS = {"/iconos/": "iconos/"}   # app.add_static_files del instalable -> carpeta del sitio
RESPUESTA_S = 120.0             # tiempo maximo para armar la pagina (ui.page response_timeout)
SALIDAS = "/tmp/iterador_cev"   # carpetas de calculo (memoria del navegador)
CALCULADORA = "herramientas.web.calculo_navegador"

_e: dict = {"listo": False, "base": "", "decorado": None, "firma": None, "reglas": [], "info": {}}


def _version(m) -> str:
    v = getattr(m, "__version__", None) or getattr(m, "VERSION", None) or ""
    return str(v)


# --------------------------------------------------------------------------- sonda
def sonda() -> dict:
    """{modulo: {ok, version, s, error, traza}} en orden, la plataforma y lo que agrego
    compat_pyodide."""
    compat = compat_pyodide.preparar()
    out = {}
    for nombre in MODULOS:
        t0 = time.perf_counter()
        try:
            m = importlib.import_module(nombre)
            out[nombre] = {"ok": True, "version": _version(m), "s": round(time.perf_counter() - t0, 3)}
        except BaseException as ex:                   # tambien SystemExit y similares
            out[nombre] = {"ok": False, "error": f"{type(ex).__name__}: {ex}",
                           "traza": "".join(traceback.format_exception(ex)[-6:]),
                           "s": round(time.perf_counter() - t0, 3)}
    return {"plataforma": sys.platform, "python": sys.version.split()[0], "compat": compat, "modulos": out}


# --------------------------------------------------------------------------- JSON hacia el navegador
def _convertir(o):
    if isinstance(o, (bytes, bytearray, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(o)).decode("ascii")}
    if isinstance(o, PurePath):
        return o.as_posix()
    tolist = getattr(o, "tolist", None)
    if callable(tolist):
        return tolist()
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)


def a_texto(v) -> str:
    """JSON como el de NiceGUI (orjson, numpy, NaN = null) y los bytes como {"__bytes__": base64}
    (el puente del iframe los vuelve Uint8Array)."""
    import orjson

    op = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS
    return orjson.dumps(v, option=op, default=_convertir).decode("utf-8")


# --------------------------------------------------------------------------- URL hacia la copia de NiceGUI
def reglas() -> list:
    """[(texto, reemplazo)] para las URL de NiceGUI (se rehace si se registran componentes nuevos)."""
    from nicegui import dependencies as dp
    from nicegui.version import __version__ as v

    firma = (_e["base"], len(dp.libraries), len(dp.js_components), len(dp.vue_components),
             len(dp.esm_modules), len(dp.resources))
    if firma == _e["firma"]:
        return _e["reglas"]
    raiz = Path(dp.__file__).parent
    prefijo = f"{_e['base']}{CARPETA_NG}/_nicegui/{v}"

    def espejo(p):
        try:
            return ESPEJO + Path(p).relative_to(raiz).as_posix()
        except ValueError:
            return None

    out = [(f"{prefijo}/static/socket.io.min.js", f"{_e['base']}puente/socketio_puente.js")]
    for k, c in dp.vue_components.items():           # .vue: el script armado por NiceGUI, en linea
        datos = base64.b64encode(c.script.encode("utf-8")).decode("ascii")
        out.append((f"{prefijo}/components/{k}", f"data:text/javascript;base64,{datos}"))
    claves = []
    for tipo, dic in (("libraries", dp.libraries), ("components", dp.js_components), ("resources", dp.resources)):
        for k, x in dic.items():
            r = espejo(x.path)
            if r:
                claves.append((f"/{tipo}/{k}", f"/{tipo}/{r}"))
                if tipo == "components":            # load_js_components arma la URL con la clave
                    claves.append((f'"key":"{k}"', f'"key":"{r}"'))
    for k, x in dp.esm_modules.items():
        r = espejo(x.path)
        if r:
            claves.append((f"/esm/{k}/", f"/esm/{r}/"))
    out += sorted(claves, key=lambda c: -len(c[0]))
    out += [(f'"{a}', f'"{_e["base"]}{b}') for a, b in ESTATICOS.items()]
    _e["firma"], _e["reglas"] = firma, out
    return out


def reescribir(texto: str) -> str:
    claves = "_nicegui" in texto or '"key":"' in texto
    for a, b in reglas():
        if (claves or not a.startswith(("/", '"key"'))) and a in texto:
            texto = texto.replace(a, b)
    return texto


# --------------------------------------------------------------------------- mensajes
async def _emitir(event, data=None, to=None, room=None, skip_sid=None, namespace=None, callback=None,
                  ignore_queue=False):
    """Reemplaza a core.sio.emit: el mensaje sale por canal_js hacia la pagina."""
    import canal_js

    canal_js.enviar(CANAL, reescribir(a_texto([event, data])))


def _servidor():
    return importlib.import_module("nicegui.nicegui")


async def recibir(evento: str, datos=None):
    """Lo que emite el navegador (socketio_puente.js). connect: el saludo inicial (devuelve si se
    acepto)."""
    s = _servidor()
    datos = datos or {}
    if evento in ("connect", "handshake"):
        return bool(await s._on_handshake(SID, datos))
    manejador = {"event": s._on_event, "javascript_response": s._on_javascript_response, "ack": s._on_ack,
                 "log": s._on_log}.get(evento)
    if manejador is not None:
        manejador(SID, datos)
    return True


async def subir(cliente: str, elemento: int, archivos: list) -> bool:
    """Archivos de un ui.upload: [{nombre, tipo, datos (bytes)}]."""
    from nicegui import Client
    from nicegui.elements.upload_files import SmallFileUpload

    c = Client.instances.get(str(cliente))
    el = c.elements.get(int(elemento)) if c is not None else None
    if el is None or not hasattr(el, "handle_uploads"):
        return False
    files = [SmallFileUpload(str(a.get("nombre") or ""), str(a.get("tipo") or ""), bytes(a.get("datos") or b""))
             for a in archivos or ()]
    with c:
        await el.handle_uploads(files)
    return True


# --------------------------------------------------------------------------- pagina
def iniciar(base: str) -> dict:
    """NiceGUI listo para armar la pagina del Iterador CEV (una vez por worker)."""
    if _e["listo"]:
        return _e["info"]
    import asyncio

    compat_pyodide.preparar()
    os.environ["ITERADOR_MODO"] = "web"
    from herramientas.comun import rutas_app

    os.environ.setdefault(rutas_app.ENV_SALIDAS, f"{SALIDAS}/salidas")
    os.environ.setdefault(rutas_app.ENV_DATOS, f"{SALIDAS}/datos")

    from nicegui import app, core, ui
    from nicegui.version import __version__

    _servidor()                                       # registra los manejadores de socket.io
    from herramientas.app_unidad import app as editor_app
    from herramientas.app_unidad import distribucion_ui
    from herramientas.comun import app_config as ac
    from herramientas.comun import icono_app
    from herramientas.unidad import editor

    from . import reporte_web

    reporte_web.activar(editor_app)                   # Reporte (PDF): HTML para imprimir
    _e["base"] = base if base.endswith("/") else base + "/"
    core.loop = asyncio.get_event_loop()
    titulo = f"{ac.nombre()} {ac.version()}"
    app.config.add_run_config(reload=False, title=titulo, viewport="width=device-width, initial-scale=1",
                              favicon=icono_app.svg(), dark=False, language=None, binding_refresh_interval=0.1,
                              reconnect_timeout=3600.0, message_history_length=1000, tailwind=True, unocss=None,
                              prod_js=True, show_welcome_message=False, markdown=False)
    core.sio.emit = _emitir

    async def _inicio():
        cfg = distribucion_ui.preparar(editor.cargar_config())
        cal = cfg.setdefault("calculo", {})
        cal["modulo"] = CALCULADORA                   # el calculo lo hacen los procesos de calculo
        cal["en_procesos"] = False
        cal["mostrar_carpeta"] = False
        distribucion_ui.boton_acerca()
        distribucion_ui.aviso_inicial()
        await editor_app.pagina(cfg)

    pg = ui.page("/", title=titulo, response_timeout=RESPUESTA_S)
    pg(_inicio)
    _e["decorado"] = pg._wrap(_inicio)
    app.start()
    _e["listo"] = True
    _e["info"] = {"nicegui": __version__, "titulo": titulo}
    return _e["info"]


async def pagina() -> str:
    """El HTML de la pagina, con las URL de NiceGUI apuntando a la copia del sitio."""
    if not _e["listo"]:
        raise RuntimeError("llama primero a iniciar(base)")
    from starlette.requests import Request

    prefijo = f"{_e['base']}{CARPETA_NG}"
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
             "scheme": "http", "path": "/", "raw_path": b"/", "root_path": "", "query_string": b"",
             "headers": [(b"host", b"navegador"), (b"accept", b"text/html"),
                         (b"x-forwarded-prefix", prefijo.encode("utf-8"))],
             "client": ("navegador", 0), "server": ("navegador", 80)}
    respuesta = await _e["decorado"](request=Request(scope))
    return reescribir(bytes(respuesta.body).decode("utf-8"))
