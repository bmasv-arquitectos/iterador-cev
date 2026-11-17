# -*- coding: utf-8 -*-
"""
Puente generico entre JavaScript y Python (Pyodide). El worker de web/src/python/worker.ts
llama llamar(modulo, funcion, args_json, kwargs_json, avanzar) y recibe un texto JSON.

Argumentos y resultado viajan en JSON; lo que JSON no tiene se codifica igual que en
web/src/python/json.ts:
    bytes                 {"__bytes__": base64}
    float no finito       {"__float__": "nan" | "inf" | "-inf"}
    numpy (arreglos)      listas
    dataclass             dict
    Path                  texto con / (igual en Windows y en el navegador)
    lo demas              texto
Si la funcion acepta un argumento avanzar, recibe avanzar(fraccion, mensaje), que avisa el
progreso a JavaScript mientras la funcion corre. Un error sale como excepcion de Python (el
worker la devuelve con su traza).
Si la funcion es async (devuelve algo que se espera), llamar devuelve una corrutina que entrega
el texto JSON: el worker la espera (en el navegador, una corrutina de Python se espera como una
promesa). Esas funciones no reciben avanzar (el proxy de JavaScript no vive mas que la llamada).

No sabe de CEV: cualquier herramienta de la familia expone sus funciones asi.
"""
from __future__ import annotations

import base64
import dataclasses
import importlib
import inspect
import json
import math
from pathlib import PurePath


def a_json(v):
    """v en algo que json.dumps acepta sin NaN (ver la tabla del modulo)."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        if math.isfinite(v):
            return v
        return {"__float__": "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(v)).decode("ascii")}
    if isinstance(v, dict):
        return {str(k): a_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [a_json(x) for x in v]
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return a_json(dataclasses.asdict(v))
    if isinstance(v, PurePath):
        return v.as_posix()
    tolist = getattr(v, "tolist", None)          # numpy: arreglos y escalares
    if callable(tolist):
        return a_json(tolist())
    return str(v)


def desde_json(v):
    """Lo inverso de a_json para lo que llega de JavaScript (bytes y floats no finitos)."""
    if isinstance(v, dict):
        if set(v) == {"__bytes__"}:
            return base64.b64decode(v["__bytes__"])
        if set(v) == {"__float__"}:
            return float(v["__float__"])
        return {k: desde_json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [desde_json(x) for x in v]
    return v


def acepta(f, nombre: str) -> bool:
    """f tiene un parametro con ese nombre (o **kwargs)."""
    try:
        p = inspect.signature(f).parameters
    except (TypeError, ValueError):
        return False
    return nombre in p or any(x.kind is inspect.Parameter.VAR_KEYWORD for x in p.values())


def _texto(v) -> str:
    return json.dumps(a_json(v), ensure_ascii=False, allow_nan=False)


async def _esperar(aw) -> str:
    return _texto(await aw)


def llamar(modulo: str, funcion: str, args_json: str = "[]", kwargs_json: str = "{}", avanzar=None):
    """modulo.funcion(*args, **kwargs) y su resultado en JSON (o una corrutina que lo entrega)."""
    f = getattr(importlib.import_module(modulo), funcion)
    args = desde_json(json.loads(args_json or "[]"))
    kwargs = desde_json(json.loads(kwargs_json or "{}"))
    asincrona = inspect.iscoroutinefunction(f)
    if avanzar is not None and not asincrona and "avanzar" not in kwargs and acepta(f, "avanzar"):
        kwargs["avanzar"] = lambda fraccion, mensaje="": avanzar(float(fraccion), str(mensaje))
    res = f(*args, **kwargs)
    if inspect.isawaitable(res):
        return _esperar(res)
    return _texto(res)
