# -*- coding: utf-8 -*-
"""
Escribe las fichas oficiales a partir de las Ficha que armo modelo.py.

Por que COM y no openpyxl
-------------------------
La PBTD son 5 MB con ~30.000 formulas, formato condicional extendido e
imagenes WMF. openpyxl no preserva nada de eso al guardar: devolveria una
ficha degradada. Asi que la plantilla se copia BINARIA con shutil.copy y
Excel solo escribe las celdas variables.

Ventaja inesperada de que la hoja este protegida: si el mapa apunta a una
celda bloqueada, Excel lanza error y el mapa queda validado gratis.

P04: una fila por cada muro que lo declare (Muro.p04) y, despues, las filas
propias que traiga ficha.p04_extra (opcional; objetos con muro, azimut,
elemento, aislacion y longitud: las obstrucciones del iterador de unidad). Sin
p04_extra se escribe exactamente lo mismo que antes.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from herramientas.comun.excel_io import app_excel
from herramientas.fichas_cev.modelo import (
    CLAVE_AZIMUT_FAR, CLAVE_CATALOGO, Ficha, valor_proyecto,
)

XL_MANUAL, XL_AUTOMATICO = -4135, -4105


MAX_OBSTRUCCIONES = 8      # alto del bloque de cada orientacion en la ficha

from openpyxl.utils import get_column_letter as _letra


def _txt_valor(v) -> str:
    return "" if v is None else str(v).strip()

class ErrorEscritura(Exception):
    pass


def _poner(ws, celda: str, valor) -> None:
    """Escribe una celda y explica donde fallo si Excel la rechaza."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return
    try:
        ws.Range(celda).Value = valor
    except Exception as e:
        raise ErrorEscritura(
            f"No se pudo escribir {valor!r} en {ws.Name}!{celda}. "
            "Puede ser una celda bloqueada o un valor que la lista "
            f"desplegable no acepta. Detalle: {e}"
        ) from e


def _limpiar(ws, columnas: list[str], fila_ini: int, fila_fin: int) -> None:
    """Borra las celdas editables de un bloque antes de llenarlo."""
    for col in columnas:
        try:
            ws.Range(f"{col}{fila_ini}:{col}{fila_fin}").ClearContents()
        except Exception:
            pass          # si esta bloqueada, no era nuestra para empezar


def _validar(ficha: Ficha, mapa: dict) -> None:
    """Chequeos que evitan escribir fuera de los bloques de la ficha."""
    limites = [
        ("muros", ficha.muros, mapa["muros"]["filas"]),
        ("ventanas", ficha.ventanas, mapa["ventanas"]["filas"]),
    ]
    for nombre, items, (ini, fin) in limites:
        cupo = fin - ini + 1
        if len(items) > cupo:
            raise ErrorEscritura(
                f"La unidad {ficha.unidad} tiene {len(items)} {nombre} y la "
                f"ficha solo admite {cupo}.")

    for destino, clave in (("techo", "techos"), ("piso", "pisos")):
        ini, fin = mapa[clave]["filas"]
        n = sum(1 for h in ficha.horizontales if h.destino == destino)
        if n > fin - ini + 1:
            raise ErrorEscritura(
                f"La unidad {ficha.unidad} tiene {n} filas de {destino} y la "
                f"ficha admite {fin - ini + 1}.")

    por_orientacion: dict[str, int] = {}
    for o in ficha.obstrucciones:
        por_orientacion[o.orientacion] = por_orientacion.get(o.orientacion, 0) + 1
    excedidas = {k: v for k, v in por_orientacion.items() if v > MAX_OBSTRUCCIONES}
    if excedidas:
        detalle = ", ".join(f"{k}={v}" for k, v in sorted(excedidas.items()))
        raise ErrorEscritura(
            f"La unidad {ficha.unidad} excede las {MAX_OBSTRUCCIONES} "
            f"obstrucciones por orientacion ({detalle}).")


def llenar(ws, ficha: Ficha, proyecto: dict, mapa: dict) -> None:
    """Escribe una ficha completa en la hoja ya abierta."""
    _validar(ficha, mapa)

    # --- Portada: constantes del proyecto e identificacion de la unidad ---
    for clave, celda in (mapa.get("proyecto_a_ficha") or {}).items():
        if not celda:
            continue
        _poner(ws, celda, valor_proyecto(proyecto, clave))

    ident = mapa["identificacion"]
    _poner(ws, ident["unidad"], str(ficha.unidad))
    _poner(ws, ident["dormitorios"], ficha.dormitorios)

    # --- Seccion 2: dimensiones, una fila por nivel ---
    dim = mapa["dimensiones"]
    filas = dim["filas"]
    if len(ficha.niveles) > len(filas):
        raise ErrorEscritura(
            f"La unidad {ficha.unidad} tiene {len(ficha.niveles)} niveles y "
            f"la ficha admite {len(filas)}.")
    _limpiar(ws, list(dim["columnas"].values()), filas[0], filas[-1])
    for nivel, fila in zip(ficha.niveles, filas):
        _poner(ws, f"{dim['columnas']['area']}{fila}", nivel.area)
        _poner(ws, f"{dim['columnas']['altura']}{fila}", nivel.altura)

    # --- Muros ---
    cfg = mapa["muros"]
    c = cfg["columnas"]
    ini, fin = cfg["filas"]
    _limpiar(ws, list(c.values()), ini, fin)
    for i, m in enumerate(ficha.muros):
        f = ini + i
        _poner(ws, f"{c['tipo']}{f}", m.tipo)
        _poner(ws, f"{c['azimut']}{f}", m.azimut)
        _poner(ws, f"{c['area']}{f}", m.area)
        _poner(ws, f"{c['p01']}{f}", m.p01)
        _poner(ws, f"{c['p02']}{f}", m.p02)
        _poner(ws, f"{c['p03']}{f}", m.p03)

    # --- Puentes termicos P04 -------------------------------------------
    # A diferencia de P01-P03, que son columnas de la propia fila del muro,
    # P04 tiene tabla propia: una fila por cada muro que lo declare. El
    # material y el azimut se heredan del muro, y la orientacion (columna F)
    # la calcula la ficha a partir del azimut. Despues van las filas propias
    # de ficha.p04_extra (si las hay).

    cfg = mapa["puentes_p04"]
    c = cfg["columnas"]
    ini, fin = cfg["filas"]
    _limpiar(ws, list(c.values()), ini, fin)
    con_p04 = [m for m in ficha.muros if m.p04 and m.p04 > 0]
    extra = [x for x in (getattr(ficha, "p04_extra", None) or ()) if x.longitud and x.longitud > 0]
    if len(con_p04) + len(extra) > fin - ini + 1:
        raise ErrorEscritura(
            f"La unidad {ficha.unidad} tiene {len(con_p04) + len(extra)} filas de P04 y "
            f"la ficha admite {fin - ini + 1}.")
    for i, m in enumerate(con_p04):
        f = ini + i
        _poner(ws, f"{c['muro']}{f}", m.tipo)
        _poner(ws, f"{c['azimut']}{f}", m.azimut)
        _poner(ws, f"{c['elemento_perpendicular']}{f}", m.p04_elemento)
        _poner(ws, f"{c['aislacion']}{f}", m.p04_aislacion)
        _poner(ws, f"{c['longitud']}{f}", m.p04)
    for i, x in enumerate(extra, len(con_p04)):
        f = ini + i
        _poner(ws, f"{c['muro']}{f}", x.muro)
        _poner(ws, f"{c['azimut']}{f}", x.azimut)
        _poner(ws, f"{c['elemento_perpendicular']}{f}", x.elemento)
        _poner(ws, f"{c['aislacion']}{f}", x.aislacion)
        _poner(ws, f"{c['longitud']}{f}", x.longitud)

    # --- Ventanas ---
    cfg = mapa["ventanas"]
    c = cfg["columnas"]
    ini, fin = cfg["filas"]
    _limpiar(ws, list(c.values()), ini, fin)
    const = {
        "aislacion_retorno": valor_proyecto(
            proyecto, "Ventana: Aislación con/sin retorno"),
        "categoria_marco": valor_proyecto(
            proyecto, "Ventana: Categoría para PT y Infilt"),
        # La variante puede pisar el marco del proyecto
        "tipo_marco": (ficha.marco
                       or valor_proyecto(proyecto, "Ventana: Tipo marco")),
    }
    # FAV 3: b (X) para lamas horizontales y a (Y) para verticales. Las fav de
    # 9 valores (MASTER, recinto) terminan en b: zip no llega a la Y.
    orden_fav = ["fav1_d", "fav1_l", "fav2i_p", "fav2i_s",
                 "fav2d_p", "fav2d_s", "fav3_e", "fav3_t", "fav3_b", "fav3_a"]
    for i, v in enumerate(ficha.ventanas):
        f = ini + i
        _poner(ws, f"{c['tipo']}{f}", v.tipo)
        _poner(ws, f"{c['azimut']}{f}", v.azimut)
        _poner(ws, f"{c['elemento']}{f}", v.elemento)
        _poner(ws, f"{c['cierre']}{f}", v.cierre)
        _poner(ws, f"{c['posicion']}{f}", v.posicion)
        _poner(ws, f"{c['alto']}{f}", v.alto)
        _poner(ws, f"{c['ancho']}{f}", v.ancho)
        _poner(ws, f"{c['aislacion_retorno']}{f}", const["aislacion_retorno"])
        _poner(ws, f"{c['categoria_marco']}{f}", const["categoria_marco"])
        _poner(ws, f"{c['tipo_marco']}{f}", const["tipo_marco"])
        for clave, valor in zip(orden_fav, v.fav):
            _poner(ws, f"{c[clave]}{f}", valor)

    # --- Puertas ---
    cfg = mapa["puertas"]
    c = cfg["columnas"]
    ini, fin = cfg["filas"]
    _limpiar(ws, list(c.values()), ini, fin)
    if len(ficha.puertas) > fin - ini + 1:
        raise ErrorEscritura(
            f"La unidad {ficha.unidad} tiene {len(ficha.puertas)} puertas y "
            f"la ficha admite {fin - ini + 1}.")
    for i, p in enumerate(ficha.puertas):
        f = ini + i
        _poner(ws, f"{c['tipo']}{f}", p.tipo)
        _poner(ws, f"{c['azimut']}{f}", p.azimut)
        _poner(ws, f"{c['categoria_infiltraciones']}{f}", p.categoria)
        _poner(ws, f"{c['alto']}{f}", p.alto)
        _poner(ws, f"{c['ancho']}{f}", p.ancho)

    # --- Obstrucciones del entorno ---
    cfg = mapa["obstrucciones"]
    alto = int(cfg["filas_por_grupo"])
    azimuts = proyecto.get(CLAVE_AZIMUT_FAR) or {}
    for g in cfg["grupos"]:
        ini = int(g["fila_inicio"])
        _limpiar(ws, [g["division"], g["a"], g["b"], g["d"]], ini, ini + alto - 1)
        # El azimut define la orientacion del bloque, no una obstruccion: se
        # escribe aunque la unidad haya quedado sin obstrucciones.
        celda_az = g.get("azimut")
        if celda_az and azimuts.get(g["orientacion"]):
            _poner(ws, celda_az, azimuts[g["orientacion"]])
    grupos = {g["orientacion"]: g for g in cfg["grupos"]}
    for o in ficha.obstrucciones:
        g = grupos.get(o.orientacion)
        if g is None:
            raise ErrorEscritura(
                f"Orientacion '{o.orientacion}' desconocida en la unidad "
                f"{ficha.unidad}.")
        f = int(g["fila_inicio"]) + o.fila
        _poner(ws, f"{g['division']}{f}", o.division)
        _poner(ws, f"{g['a']}{f}", o.a)
        _poner(ws, f"{g['b']}{f}", o.b)
        _poner(ws, f"{g['d']}{f}", o.d)

    # --- Techos y pisos ---
    for destino, clave in (("techo", "techos"), ("piso", "pisos")):
        cfg = mapa[clave]
        c = cfg["columnas"]
        ini, fin = cfg["filas"]
        _limpiar(ws, list(c.values()), ini, fin)
        propias = [h for h in ficha.horizontales if h.destino == destino]
        for i, h in enumerate(propias):
            f = ini + i
            _poner(ws, f"{c['tipo']}{f}", h.material)
            _poner(ws, f"{c['densidad']}{f}", h.densidad)
            _poner(ws, f"{c['area']}{f}", h.area)
            if destino == "techo":
                _poner(ws, f"{c['camaras_aire']}{f}", h.extra)
                _poner(ws, f"{c['tipo_cubierta']}{f}", h.tipo)
            else:
                # El perimetro de la unidad manda sobre el de la tabla: la
                # tabla es el valor comun del proyecto y el indice permite
                # excepciones (tipicamente, solo el primer piso toca terreno).
                perimetro = ficha.perimetro_terreno
                if perimetro is None:
                    perimetro = h.extra
                _poner(ws, f"{c['perimetro_terreno']}{f}", perimetro)
                _poner(ws, f"{c['ventilado']}{f}", h.tipo)

def escribir_catalogo(wb, catalogo, mapa: dict) -> None:
    """Vuelca el catalogo del MASTER en la hoja de tablas de la ficha."""
    cfg = mapa.get("catalogo")
    if not cfg or not catalogo:
        return
    ws = wb.Worksheets(cfg["hoja_ficha"])
    for fila in catalogo:
        for col, valor in fila.valores.items():
            _poner(ws, f"{_letra(col)}{fila.fila}", valor)

def leer_nombres(wb, mapa: dict) -> dict[str, dict[str, str]]:
    """
    bloque -> {abreviatura: nombre largo}, leido de la propia ficha.

    La traduccion se saca de la ficha y no del MASTER porque ahi conviven las
    filas de fabrica (puertas, vidrios, marcos, adiabaticos) con las del
    proyecto. El MASTER solo tiene las del proyecto, asi que no alcanzaria.

    Hace falta porque el MASTER referencia los materiales por ABREVIATURA,
    mientras que las opciones de los desplegables de 1.2 se arman con el
    NOMBRE LARGO.
    """
    cfg = mapa.get("catalogo") or {}
    cols = cfg.get("columnas_ficha") or {}
    if not cfg.get("bloques") or not cols:
        return {}

    ws = wb.Worksheets(cfg["hoja_ficha"])
    c_nombre = str(cols["nombre"]).upper()
    c_abrev = str(cols["abreviatura"]).upper()

    nombres: dict[str, dict[str, str]] = {}
    for b in cfg["bloques"]:
        rango = b.get("ficha_todas")
        if not rango:
            continue
        ini, fin = int(rango[0]), int(rango[1])
        mapa_bloque: dict[str, str] = {}
        for f in range(ini, fin + 1):
            nombre = _txt_valor(ws.Range(f"{c_nombre}{f}").Value)
            abrev = _txt_valor(ws.Range(f"{c_abrev}{f}").Value)
            if abrev and nombre:
                mapa_bloque[abrev] = nombre
        nombres[b["nombre"]] = mapa_bloque
    return nombres

def seleccionar_paquetes(wb, ws, ficha: Ficha, mapa: dict,
                         nombres: dict[str, dict[str, str]]) -> None:
    """
    Elige en 1.2 el paquete que corresponde a cada elemento principal.

    La opcion del desplegable es un texto compuesto que la ficha arma por
    formula ("Muro Hormigon Aislado con aislacion por Exterior, ... U= 0.56"),
    asi que no se puede escribir a mano: hay que traducir la abreviatura a su
    nombre largo, buscar la opcion que lo contiene y copiarla literal.
    """
    for etiqueta, cfg in (mapa.get("paquetes") or {}).items():
        abrev = _txt_valor(ficha.paquetes.get(etiqueta))
        if not abrev:
            continue

        buscado = (nombres.get(cfg.get("bloque"), {}) or {}).get(abrev, abrev)

        try:
            rango = wb.Names(cfg["lista"]).RefersToRange
        except Exception as e:
            raise ErrorEscritura(
                f"No se encontro la lista '{cfg['lista']}' para "
                f"'{etiqueta}'. Detalle: {e}") from e

        opciones = [str(c.Value).strip() for c in rango
                    if c.Value not in (None, "")]
        calzan = [o for o in opciones if buscado and buscado in o]
        if not calzan:
            resumen = "; ".join(o[:60] for o in opciones[:6]) or "(ninguna)"
            raise ErrorEscritura(
                f"'{etiqueta}': no hay opcion para '{abrev}' "
                f"(nombre largo: '{buscado}'). Primeras opciones: {resumen}. "
                "Revisar que el material este en la hoja 'Materiales'.")
        if len(calzan) > 1:
            raise ErrorEscritura(
                f"'{etiqueta}': '{buscado}' calza con {len(calzan)} opciones. "
                "Usar nombres que no sean prefijo unos de otros.")
        _poner(ws, cfg["celda"], calzan[0])

def generar(fichas: list[Ficha], proyecto: dict, mapa: dict,
            plantilla: Path, destino: Path) -> tuple[list[Path], list[str]]:
    """Copia la plantilla por unidad, la llena y la guarda en carpeta por piso."""
    plantilla = Path(plantilla).resolve()
    if not plantilla.exists():
        raise FileNotFoundError(f"No existe la plantilla: {plantilla}")

    destino = Path(destino).resolve()
    catalogo = proyecto.get(CLAVE_CATALOGO) or []
    generadas: list[Path] = []
    errores: list[str] = []
    hoja = mapa["hoja"]

    with app_excel() as excel:
        calculo_original = None
        for ficha in fichas:
            carpeta = destino / f"Piso_{ficha.piso:02d}"
            carpeta.mkdir(parents=True, exist_ok=True)
            salida = carpeta / f"{ficha.unidad}{plantilla.suffix}"
            shutil.copy(plantilla, salida)   # copia binaria: nada se degrada

            wb = None
            fallo = False
            try:
                wb = excel.Workbooks.Open(str(salida), UpdateLinks=0)
                if wb is None:
                    raise ErrorEscritura(f"Excel no pudo abrir {salida}")

                # Calculation solo existe cuando hay un libro abierto: Excel
                # arranca sin libros y la propiedad no esta disponible todavia.
                if calculo_original is None:
                    try:
                        calculo_original = excel.Calculation
                        excel.Calculation = XL_MANUAL
                    except Exception:
                        calculo_original = False   # no se pudo: seguir igual

                # 1. Catalogo primero: los combos de CEV-CEVE leen de aca, asi
                #    que si se escribe al reves todavia no conocen los
                #    materiales del proyecto.
                escribir_catalogo(wb, catalogo, mapa)
                excel.CalculateFull()

                ws = wb.Worksheets(hoja)

                esperada = str(mapa.get("version_plantilla", "")).strip()
                celda_v = mapa.get("celda_version")
                if esperada and celda_v:
                    actual = str(ws.Range(celda_v).Value or "").strip()
                    if actual and not actual.startswith(esperada):
                        raise ErrorEscritura(
                            f"La plantilla dice version '{actual}' y el mapa "
                            f"espera '{esperada}'. Revisar mapa.yaml.")

                # 2. Datos de la unidad
                llenar(ws, ficha, proyecto, mapa)

                # 3. Recalculo antes de elegir los paquetes: las opciones de
                #    1.2 son formulas que concatenan nombre y transmitancia, y
                #    hasta que Excel no recalcula todavia no existen.
                excel.CalculateFull()
                nombres = leer_nombres(wb, mapa)
                seleccionar_paquetes(wb, ws, ficha, mapa, nombres)

                excel.CalculateFull()
                wb.Save()
                generadas.append(salida)
                print(f"  ok  {ficha.unidad} -> {salida.parent.name}/{salida.name}")
            except Exception as e:
                fallo = True
                detalle = f"{type(e).__name__}: {e}"
                if isinstance(e, KeyError):
                    detalle = f"falta la clave {e} en mapa.yaml"
                errores.append(f"{ficha.unidad}: {detalle}")
            finally:
                if wb is not None:
                    try:
                        wb.Close(SaveChanges=False)
                    except Exception:
                        pass
                if fallo:
                    salida.unlink(missing_ok=True)   # no dejar fichas a medias

        if calculo_original not in (None, False):
            try:
                excel.Calculation = calculo_original
            except Exception:
                pass

    return generadas, errores
