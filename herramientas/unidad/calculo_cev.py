# -*- coding: utf-8 -*-
"""
Calculo CEV de una unidad. Motores (config/editor.yaml, calculo.motores):
  python   clon Python del motor y de la planilla 03, sin Excel (~20 s);
  hibrido  ficha 01 con Excel + casos en Python + 03 con Excel (~1 min, Windows);
  oficial  ficha 01 + motor oficial PBTD en Excel (~25 min, Windows).
Python e hibrido son solo para iteracion: no validos para entrega (la
calificacion oficial la emite un evaluador acreditado con las planillas
oficiales). El motor python se calcula aca; los demas son los registrados en
app_cev/ejecucion.py (BACKENDS), con la traduccion de cev.py (opcion armar), y solo
aparecen si estan registrados y se pueden usar en este computador. La copia publica
trae solo el motor Python. En la version distribuida (app_unidad/__main__.py y
comun/distribucion.yaml) solo se ofrece python, y entonces no se consulta nada mas.

Es una "calculadora" del editor (app_unidad): el editor no sabe de CEV, solo
usa estas funciones del modulo que indique config/editor.yaml (calculo.modulo).
Otra herramienta de la caja puede entregar las mismas y reutilizar la interfaz:

    motores(cfg) -> {clave: texto}                 opcional: motores para elegir
    calcular(u, avanzar, cancelar, cfg, motor) -> dict   (en un hilo: comun/tarea.py)
    vista(res, cfg) -> str                         SVG del resultado (o "")
    detalle(res, cfg) -> list[str]                 lineas en markdown
    paquete(res) -> (bytes, nombre)                archivo para descargar
    imagen(res, cfg) -> (bytes, nombre)            opcional: la vista como imagen

cfg: la seccion calculo de config/editor.yaml (salida, motores, etiqueta, textos...).
mostrar_carpeta (false en la web): detalle() no muestra la carpeta del calculo.
La salida relativa ("salidas/iterador_unidad") se resuelve con comun/rutas_app.salida:
en el repositorio al desarrollar, en la carpeta del usuario empaquetado.

Demandas del caso base por uso (demanda_base_cal, demanda_base_ref; la etiqueta
las muestra bajo cada ahorro): con el motor python, 'Resumen'!E7 y F7 de la
planilla 03; con los otros, se despejan del ahorro (G8 = 1 - E8/E7,
H8 = 1 - F8/F7), que es como la planilla los calcula.

Obstrucciones remotas (FAR dibujado, contexto_far.py): res["far"] = {orientacion:
filas en la ficha} de las orientaciones con punto de referencia (vacio sin
volumenes de contexto); detalle() lo muestra en una linea (calculo.textos.far).

Cada calculo deja una carpeta numerada con: unidad.json (la unidad calculada,
se puede volver a abrir), resumen.json, resultado.csv (una fila, para Excel en
Chile) y la etiqueta (etiqueta_cev.png y .svg); el motor python agrega
entradas.json (la ficha 01 virtual, basta para recalcular) y los otros lo suyo.
paquete() la entrega como .zip.
La etiqueta usa app_cev/config/etiqueta.yaml con los cambios de calculo.etiqueta.
"""
from __future__ import annotations

import csv
import io
import json
import threading
import time
import zipfile
from pathlib import Path

from herramientas.comun.rutas_app import salida as ruta_salida
from herramientas.comun.tarea import Cancelado, revisar

from . import cev, modelo

SALIDA = "salidas/iterador_unidad"
TEXTO_FAR = "Obstrucciones remotas (FAR): {detalle}"
COLUMNAS_CSV = (
    ("letra", "Letra", None), ("ahorro_pct", "Ahorro total [%]", 1),
    ("ahorro_cal_pct", "Ahorro calefacción [%]", 1), ("ahorro_ref_pct", "Ahorro refrigeración [%]", 1),
    ("demanda", "Demanda total [kWh/m2año]", 2), ("demanda_cal", "Demanda calefacción [kWh/m2año]", 2),
    ("demanda_ref", "Demanda refrigeración [kWh/m2año]", 2),
    ("demanda_base", "Demanda caso base [kWh/m2año]", 2),
    ("demanda_base_cal", "Demanda base calefacción [kWh/m2año]", 2),
    ("demanda_base_ref", "Demanda base refrigeración [kWh/m2año]", 2),
    ("zona", "Zona térmica", None), ("area", "Superficie [m2]", 2), ("volumen", "Volumen [m3]", 2),
    ("backend", "Motor", None), ("minutos", "Tiempo [min]", 2), ("nota", "Nota", None),
)


def _num(v, d: int) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def _numero(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _salida(cfg: dict) -> Path:
    return ruta_salida(cfg.get("salida") or SALIDA)


def mezclar(base: dict, extra: dict | None) -> dict:
    """Copia de base con las claves de extra (los dicts se mezclan por dentro)."""
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = mezclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _etiqueta(cfg: dict | None = None):
    from herramientas.app_cev import etiqueta_cev as ec
    return ec, mezclar(ec.cargar_config(), (cfg or {}).get("etiqueta"))


def motores(cfg: dict | None = None) -> dict:
    """{clave: texto} de los motores pedidos en cfg que se pueden usar en este PC (python siempre)."""
    pedidos = (cfg or {}).get("motores") or {"python": "Motor Python"}
    if set(pedidos) <= {"python"}:
        return dict(pedidos)                   # solo Python: no se consulta nada mas
    from herramientas.app_cev.ejecucion import disponible

    return {k: t for k, t in pedidos.items() if k == "python" or disponible(k)} or {"python": "Motor Python"}


def completar_bases(res: dict) -> dict:
    """demanda_base_cal y demanda_base_ref desde la demanda y el ahorro, si faltan
    (ahorro = 1 - propuesta / base; sin solucion si el ahorro es 100 %)."""
    for clave, dem, aho in (("demanda_base_cal", "demanda_cal", "ahorro_cal_pct"),
                            ("demanda_base_ref", "demanda_ref", "ahorro_ref_pct")):
        d, a = _numero(res.get(dem)), _numero(res.get(aho))
        if res.get(clave) is None and d is not None and a is not None and abs(1 - a / 100) > 1e-9:
            res[clave] = abs(d / (1 - a / 100))
    return res


def resumen_far(t) -> dict:
    """{orientacion: filas de obstrucciones remotas en la ficha} de las orientaciones con punto
    de referencia (t: cev.Traduccion; vacio sin volumenes de contexto)."""
    far = getattr(t, "far", None)
    if far is None:
        return {}
    return {pf.orientacion: sum(1 for o in t.ficha.obstrucciones if o.orientacion == pf.orientacion)
            for pf in far.puntos}


def escribir_csv(res: dict, ruta: Path) -> Path:
    """Una fila con el resultado (separador ';' y coma decimal)."""
    fila = []
    for clave, _, d in COLUMNAS_CSV:
        v = res.get(clave)
        fila.append("" if v is None else (_num(v, d) if d is not None and isinstance(v, (int, float)) else str(v)))
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([t for _, t, _ in COLUMNAS_CSV])
        w.writerow(fila)
    return ruta


def _python(t, avanzar, cancelar, cfg) -> dict:
    """Traduccion -> ficha 01 virtual -> clon Python (10 casos + planilla 03)."""
    from herramientas.app_cev.ejecucion import carpeta_nueva, resultado_python
    from herramientas.motor_cev.motor_py import ficha_virtual
    from herramientas.motor_cev.motor_py.calcular import calcular as motor

    carpeta = carpeta_nueva(_salida(cfg))
    avanzar(0.04, "Escribiendo las entradas del motor (en memoria, sin Excel)")
    fv = ficha_virtual.construir(t.ficha, t.proyecto)
    fv.guardar(carpeta / "entradas.json")
    revisar(cancelar)

    def antes_de_caso(k, total, caso):
        revisar(cancelar)
        extra = " (la primera vez carga datos y compila)" if k == 0 else ""
        avanzar(0.08 + 0.84 * k / max(total, 1), f"Calculando: caso {k + 1} de {total}{extra}")

    cal = motor(fv.ficha, antes_de_caso=antes_de_caso)
    if not cal.resumen:
        raise RuntimeError("el motor no entregó el resumen de la planilla 03")
    r = dict(cal.resumen)
    r["carpeta"] = str(carpeta)
    res = resultado_python(r)
    res["tiempos"] = cal.tiempos
    if cal.planilla is not None:
        res["demanda_base_cal"] = _numero(cal.planilla.valor("Resumen", "E7"))
        res["demanda_base_ref"] = _numero(cal.planilla.valor("Resumen", "F7"))
    return res


def _otro(u, t, avanzar, cancelar, cfg, motor) -> dict:
    """Un motor registrado en app_cev/ejecucion.py (BACKENDS), con la ficha de la unidad."""
    from herramientas.app_cev import ejecucion as ej

    if not ej.disponible(motor):
        raise ValueError(f"El motor {motor} no está disponible en este computador.")
    try:
        res = ej.BACKENDS[motor].fn(u, avanzar, cancelar, armar=lambda _u: (t.ficha, t.proyecto),
                                   salida=str(_salida(cfg)), workers=int(cfg.get("workers", 4)),
                                   verificar_ficha=bool(cfg.get("verificar_ficha", True)))
    except ej.Cancelado:
        raise Cancelado from None
    res.setdefault("valido_entrega", ej.BACKENDS[motor].valido_entrega)
    return res


def calcular(u: modelo.Unidad, avanzar=None, cancelar=None, cfg: dict | None = None,
             motor: str = "python") -> dict:
    """Unidad -> ficha 01 -> motor elegido -> resultado (y la carpeta del calculo)."""
    from herramientas.app_cev.ejecucion import carpeta_nueva

    cfg = cfg or {}
    avanzar = avanzar or (lambda f, m="": None)
    cancelar = cancelar or threading.Event()
    inicio = time.perf_counter()
    avanzar(0.01, "Traduciendo la unidad a la ficha 01")
    t = cev.construir(u)                                   # ValueError: mensaje para el usuario
    res = _python(t, avanzar, cancelar, cfg) if motor == "python" else _otro(u, t, avanzar, cancelar, cfg, motor)
    completar_bases(res)
    ec, ecfg = _etiqueta(cfg)
    carpeta = ec.carpeta_resultado(res) or carpeta_nueva(_salida(cfg))
    res.update(carpeta=str(carpeta), backend=motor, avisos=list(t.avisos), zona=t.zona,
               area=sum(t.geometria.areas), volumen=t.geometria.volumen, far=resumen_far(t),
               minutos=(time.perf_counter() - inicio) / 60)
    avanzar(0.96, "Guardando la etiqueta y el resumen")
    modelo.guardar(u, carpeta / "unidad.json")
    (carpeta / "resumen.json").write_text(
        json.dumps({"nota": res.get("nota"), "resultado": res}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    escribir_csv(res, carpeta / "resultado.csv")
    try:
        res["etiqueta_png"] = str(ec.guardar(res, carpeta, ecfg))
    except RuntimeError:                                   # sin PyMuPDF: solo el SVG
        (carpeta / f"{ecfg['png']['nombre']}.svg").write_text(ec.svg(res, ecfg), encoding="utf-8")
    avanzar(1.0, "Listo")
    return res


def vista(res: dict | None, cfg: dict | None = None) -> str:
    """Etiqueta CEV (SVG que se ajusta al ancho de la caja). Sin resultado: la escala vacia."""
    if res is None and not (cfg or {}).get("etiqueta_vacia", True):
        return ""
    ec, ecfg = _etiqueta(cfg)
    return ec.svg(res, ecfg, responsivo=True)


def imagen(res: dict, cfg: dict | None = None) -> tuple:
    """(bytes, nombre) de la etiqueta en PNG (en SVG si falta PyMuPDF)."""
    ec, ecfg = _etiqueta(cfg)
    p = ecfg["png"]
    txt = ec.svg(res, ecfg, fuente=p.get("fuente"))
    base = f"{p['nombre']}_{Path(res['carpeta']).name}" if res.get("carpeta") else p["nombre"]
    try:
        return ec.png(txt, p["escala"]), f"{base}.png"
    except RuntimeError:
        return txt.encode("utf-8"), f"{base}.svg"


def detalle(res: dict | None, cfg: dict | None = None) -> list:
    """Obstrucciones remotas, avisos, tiempo, carpeta y nota (las demandas base estan en la etiqueta)."""
    if not res:
        return []
    cfg = cfg or {}
    out = []
    if res.get("far"):
        texto = (cfg.get("textos") or {}).get("far") or TEXTO_FAR
        out.append(texto.format(detalle=" · ".join(f"{o} {n}" for o, n in res["far"].items())))
    if res.get("aviso"):
        out.append(f"Aviso: {res['aviso']}")
    out += [f"Aviso: {a}" for a in res.get("avisos") or []]
    m = res.get("minutos")
    if m is not None:
        out.append(f"Tiempo de cálculo: {_num(m * 60, 0)} s" if m < 1 else f"Tiempo de cálculo: {_num(m, 1)} min")
    if res.get("carpeta") and cfg.get("mostrar_carpeta", True):
        out.append(f"Carpeta: `{res['carpeta']}`")
    if res.get("nota"):
        out.append(f"_{res['nota']}_")
    return out


def paquete(res: dict) -> tuple:
    """(bytes de un .zip con la carpeta del calculo, nombre del archivo)."""
    carpeta = Path(res["carpeta"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(carpeta.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(carpeta).as_posix())
    return buf.getvalue(), f"resultado_cev_{carpeta.name}.zip"
