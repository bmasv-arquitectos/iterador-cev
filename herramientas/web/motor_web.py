# -*- coding: utf-8 -*-
"""
F2: el motor Python repartido por casos, para el cliente web (web/src/cev/motor.ts). Se prueba
igual en escritorio, con la linea de comandos de abajo.

unidad: el texto JSON de una unidad (lo que guarda unidad/modelo.guardar).

  unidad_prueba_json()          la unidad de prueba de api.py, como texto
  preparar(unidad)              traduce la unidad (ficha 01 virtual), carga los datos del motor y
                                calcula lo comun a los casos; queda en memoria de este proceso
  casos(unidad, casos)          los casos pedidos (1..10): bloques (filas) y tiempos y, en el
                                caso 1, la superficie D56 que usa la planilla 03
  planilla(unidad, resultados)  la planilla 03 con los 10 casos: resumen, demandas del caso base,
                                texto y huella del resumen
  calcular(unidad)              todo en este proceso, como motor_py.calcular (para comparar)
  repartido(unidad, partes)     casos() en partes + planilla(), pasando por JSON como en el
                                navegador (para comparar)
  ficha01(unidad)               la ficha 01 (.xlsm) llenada: nombre, datos (bytes) y avisos
  usar_nucleo_js(activar)       en el navegador, calculo_py._nucleo pasa a ser el de JavaScript
                                (modulo nucleo_js que registra web/src/python/modulos_js.ts)

Repartir los casos da lo mismo que calcularlos juntos: planilla() arma las entradas de la
planilla 03 igual que planilla03.desde_corridas, con los bloques de cada caso.

Huella: los primeros 12 caracteres del sha256 del texto del resumen (una linea "clave = valor"
por celda, mas las demandas del caso base). La calcula Python en los dos lados, asi que es
comparable. El navegador no conserva el signo de un cero (-0.0 llega como 0.0): el texto
escribe los dos igual.

    python -m herramientas.web.motor_web                    unidad de prueba
    python -m herramientas.web.motor_web unidad.json        otra unidad (o carpeta con unidad.json)
imprime el resumen y su huella, juntos y repartidos; el navegador debe dar la misma.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

H_CEV = "CEV-CEVE"
MAX_CACHE = 2
_cache: dict = {}
_original: dict = {"nucleo": None}
_nucleo_js: dict = {"s": 0.0, "llamadas": 0}


@dataclass
class Preparado:
    unidad: object
    traduccion: object               # unidad/cev.Traduccion
    virtual: object                  # motor_py/ficha_virtual.FichaVirtual
    comun: object = None             # motor.Comun
    tiempos: dict = field(default_factory=dict)

    @property
    def ficha(self):
        return self.virtual.ficha


# --------------------------------------------------------------------------- unidad
def a_texto(u) -> str:
    from herramientas.unidad import modelo

    with tempfile.TemporaryDirectory(prefix="unidad_") as tmp:
        ruta = Path(tmp) / "unidad.json"
        modelo.guardar(u, ruta)
        return ruta.read_text(encoding="utf-8")


def de_texto(texto: str):
    from herramientas.unidad import modelo

    with tempfile.TemporaryDirectory(prefix="unidad_") as tmp:
        ruta = Path(tmp) / "unidad.json"
        ruta.write_text(texto, encoding="utf-8")
        return modelo.cargar(ruta)


def unidad_prueba_json() -> str:
    from .api import unidad_prueba

    return a_texto(unidad_prueba())


def _datos():
    from herramientas.motor_cev.motor_py.calcular import datos

    return datos()


def _preparado(unidad: str, comun: bool = True) -> Preparado:
    clave = hashlib.sha256(unidad.encode("utf-8")).hexdigest()
    p = _cache.get(clave)
    if p is None:
        from herramientas.motor_cev.motor_py import ficha_virtual
        from herramientas.unidad import cev

        t0 = time.perf_counter()
        u = de_texto(unidad)
        t = cev.construir(u)                         # ValueError: mensaje para el usuario
        fv = ficha_virtual.construir(t.ficha, t.proyecto)
        p = Preparado(u, t, fv, tiempos={"ficha": time.perf_counter() - t0})
        while len(_cache) >= MAX_CACHE:
            _cache.pop(next(iter(_cache)))
        _cache[clave] = p
    if comun and p.comun is None:
        from herramientas.motor_cev.motor_py import motor as mt

        t0 = time.perf_counter()
        d, _ = _datos()
        p.tiempos["datos"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        p.comun = mt.comun(d, p.ficha)
        p.tiempos["comun"] = time.perf_counter() - t0
    return p


# --------------------------------------------------------------------------- resumen
def _normal(x):
    item = getattr(x, "item", None)                  # numpy
    if callable(item) and not isinstance(x, (str, bytes)):
        x = item()
    if isinstance(x, float):
        x = x + 0.0                                  # -0.0 -> 0.0
    return x


def texto_resumen(resumen: dict, base_cal=None, base_ref=None) -> tuple:
    """(texto, huella) del resumen de la planilla 03 y las demandas del caso base."""
    v = dict(resumen)
    v["base_cal"], v["base_ref"] = base_cal, base_ref
    texto = "\n".join(f"{k} = {_normal(v[k])!r}" for k in sorted(v))
    return texto, hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def _salida(resumen: dict, res03) -> dict:
    base_cal = res03.valor("Resumen", "E7") if res03 is not None else None
    base_ref = res03.valor("Resumen", "F7") if res03 is not None else None
    texto, huella = texto_resumen(resumen, base_cal, base_ref)
    return {"resumen": dict(resumen), "base_cal": base_cal, "base_ref": base_ref, "texto": texto, "huella": huella}


# --------------------------------------------------------------------------- motor repartido
def preparar(unidad: str) -> dict:
    p = _preparado(unidad)
    f = p.ficha
    return {"comuna": f.comuna, "zona": f.zona, "tipo_vivienda": getattr(f, "tipo_vivienda", None),
            "avisos": list(p.traduccion.avisos) + list(p.virtual.avisos),
            "tiempos": {k: round(v, 3) for k, v in p.tiempos.items()}}


def casos(unidad: str, casos: list, avanzar=None) -> dict:
    """{caso: {filas, dpm, t, t_modulos, t_calculo, t_nucleo, sin_calcular[, d56]}}."""
    from herramientas.motor_cev.motor_py import motor as mt

    avanzar = avanzar or (lambda f, m="": None)
    p = _preparado(unidad)
    d, _ = _datos()
    lista = [int(c) for c in casos]
    out = {}
    for k, caso in enumerate(lista):
        avanzar(k / max(len(lista), 1), f"Caso {caso}")
        t0, n0 = time.perf_counter(), _nucleo_js["s"]
        rc = mt.calcular_caso(d, p.ficha, caso, p.comun)
        filas, dpm, t = mt.simular(rc)
        r = {"filas": filas, "dpm": dpm, "t": time.perf_counter() - t0, "t_modulos": rc.tiempo, "t_calculo": t,
             "t_nucleo": _nucleo_js["s"] - n0, "sin_calcular": list(rc.sin_calcular)}
        if caso == 1:
            r["d56"] = rc.resultados["envolvente"].valor(H_CEV, "D56")
        out[str(caso)] = r
    avanzar(1.0, "Listo")
    return out


def _float(x):
    """Lo que llega por JSON: 3.0 vuelve como 3; en los bloques todo es float."""
    return float(x) if isinstance(x, int) and not isinstance(x, bool) else x


def planilla(unidad: str, resultados: dict) -> dict:
    """La planilla 03 con los bloques de los 10 casos (como planilla03.desde_corridas)."""
    from herramientas.motor_cev.motor_py import motor as mt
    from herramientas.motor_cev.motor_py import planilla03 as p3

    t0 = time.perf_counter()
    p = _preparado(unidad, comun=False)
    _, d03 = _datos()
    por = {int(k): v for k, v in resultados.items()}
    faltan = [n for n in mt.CASOS if n not in por]
    if faltan:
        raise ValueError(f"faltan los casos {faltan}: la planilla 03 promedia los casos base")
    filas = tuple([None if fila is None else [_float(x) for x in fila] for fila in por[n]["filas"]]
                  for n in mt.CASOS)
    e = p3.EntradasPlanilla03(filas, _float(por[1]["d56"]), p.ficha.zona, getattr(p.ficha, "tipo_vivienda", None))
    res = p3.calcular(d03, e)
    out = _salida(dict(res.resumen), res)
    out["t"] = time.perf_counter() - t0
    out["sin_calcular"] = sorted({x for n in mt.CASOS for x in por[n].get("sin_calcular") or []})
    return out


def calcular(unidad: str, avanzar=None) -> dict:
    """Los 10 casos y la planilla 03 en este proceso (motor_py.calcular)."""
    from herramientas.motor_cev.motor_py.calcular import calcular as calc

    avanzar = avanzar or (lambda f, m="": None)
    p = _preparado(unidad, comun=False)

    def antes(k, total, caso):
        avanzar(k / max(total, 1), f"Caso {k + 1} de {total}")

    cal = calc(p.ficha, antes_de_caso=antes)
    out = _salida(dict(cal.resumen), cal.planilla)
    out["tiempos"] = dict(cal.tiempos)
    out["sin_calcular"] = list(cal.sin_calcular)
    return out


def repartido(unidad: str, partes: int = 3, por_json: bool = True) -> dict:
    """casos() en partes y planilla(), pasando los bloques por JSON como en el navegador."""
    from herramientas.motor_cev.motor_py import motor as mt

    from . import puente

    resultados = {}
    for i in range(max(1, partes)):
        grupo = list(mt.CASOS[i::max(1, partes)])
        if grupo:
            resultados.update(casos(unidad, grupo))
    if por_json:
        resultados = puente.desde_json(json.loads(json.dumps(puente.a_json(resultados), allow_nan=False)))
    return planilla(unidad, resultados)


# --------------------------------------------------------------------------- ficha 01
def ficha01(unidad: str) -> dict:
    from herramientas.unidad import ficha01 as f01

    p = _preparado(unidad, comun=False)
    x = f01.exportar(p.unidad)
    return {"nombre": x.nombre, "datos": x.datos, "avisos": list(x.avisos)}


# --------------------------------------------------------------------------- nucleo en JavaScript
def usar_nucleo_js(activar: bool = True) -> dict:
    """En el navegador, calculo_py._nucleo pasa a llamar al de JavaScript (nucleo_js.calcular).
    activar=False vuelve al de Python. Fuera del navegador solo se puede desactivar."""
    from herramientas.motor_cev import calculo_py as cp

    if _original["nucleo"] is None:
        _original["nucleo"] = cp._nucleo
    original = _original["nucleo"]
    if not activar:
        cp._nucleo = original
        return {"nucleo": "python", "numba": bool(cp.HAY_NUMBA)}
    if sys.platform != "emscripten":
        raise RuntimeError("el nucleo en JavaScript solo se usa en el navegador")

    import js
    import nucleo_js
    import numpy as np
    from pyodide.ffi import to_js

    nombres = list(inspect.signature(getattr(original, "py_func", original)).parameters)

    def envoltura(*args):
        t0 = time.perf_counter()
        d = {}
        for nombre, v in zip(nombres, args):
            if isinstance(v, np.ndarray):
                d[nombre] = np.ascontiguousarray(v, dtype=np.float64).reshape(-1)
            elif isinstance(v, (bool, np.bool_)):
                d[nombre] = bool(v)
            else:
                d[nombre] = float(v)
        r = nucleo_js.calcular(to_js(d, dict_converter=js.Object.fromEntries))
        filas = int(args[0]) + 1
        M = np.empty((filas, int(r.length) // filas))
        try:
            r.assign_to(M)
        except Exception:
            M = np.frombuffer(r.to_bytes(), dtype="<f8").reshape(filas, -1).copy()
        _nucleo_js["s"] += time.perf_counter() - t0
        _nucleo_js["llamadas"] += 1
        return M

    cp._nucleo = envoltura
    return {"nucleo": "javascript"}


# --------------------------------------------------------------------------- linea de comandos
def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Resumen y huella de una unidad: casos juntos y repartidos")
    ap.add_argument("unidad", nargs="?", help="unidad .json o carpeta con unidad.json (sin nada: la de prueba)")
    ap.add_argument("--partes", type=int, default=3, help="en cuantas partes se reparten los casos")
    a = ap.parse_args(argv)
    if a.unidad:
        ruta = Path(a.unidad)
        if ruta.is_dir():
            ruta = ruta / "unidad.json"
        texto = ruta.read_text(encoding="utf-8")
    else:
        texto = unidad_prueba_json()
    t0 = time.perf_counter()
    juntos = calcular(texto)
    t1 = time.perf_counter()
    rep = repartido(texto, a.partes)
    t2 = time.perf_counter()
    print(juntos["texto"])
    print(f"\nhuella juntos:     {juntos['huella']}  ({t1 - t0:.1f} s)")
    print(f"huella repartidos: {rep['huella']}  ({t2 - t1:.1f} s, {a.partes} partes)")
    if juntos["huella"] != rep["huella"]:
        print("!! distintas:\n" + rep["texto"])
        return 1
    print("Iguales. El navegador debe dar esta misma huella para esta unidad.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
