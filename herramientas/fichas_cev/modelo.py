# -*- coding: utf-8 -*-
"""
Lee el Excel MASTER del edificio y arma la lista de fichas a generar.

Este modulo NO escribe nada: solo lee, valida y expande. La idea es poder
revisar en un CSV que las N unidades quedaron bien antes de gastar minutos de
Excel generando fichas.

Reglas de negocio implementadas
-------------------------------
1. Cada unidad del indice (hoja "Area") declara de que hoja-plantilla del
   MASTER se copian sus muros y ventanas (columna "Plantilla").
2. Las obstrucciones del entorno (FAR) se leen para la unidad plantilla y se
   ajustan por altura: A_piso = A_base - (piso - piso_base) * altura_piso_a_piso.
   Cuando A <= 0 la obstruccion se elimina: el departamento quedo mas arriba
   que el obstaculo.
3. Piso y techumbre se declaran como area adiabatica y, cuando existe, area de
   techumbre real (ultimo piso).
4. El area de cada muro se declara BRUTA y se le restan los vanos de sus
   ventanas y puertas: el motor no descuenta nada.
5. En las unidades que lo declaran ('Cielo a P01' = Si), el P03 del cielo se
   traspasa a P01: bajo la techumbre el encuentro es un borde exterior.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from herramientas.comun.xlsx_inspeccion import (
    es_vacio, mapa_merges, normalizar, valor_efectivo,
)

# El azimut del FAR es un dato de proyecto (una fila para toda la hoja), no de
# cada unidad, asi que viaja dentro del dict de proyecto con esta clave.
CLAVE_AZIMUT_FAR = "__azimut_far__"
CLAVE_CATALOGO = "__catalogo__"

# Filas que la ficha oficial trae de fabrica y estan protegidas: no se
# escriben, pero si se usan como valor valido en las hojas de unidad.
ADIABATICOS = {
    "muros": "Muro Adiabatico",
    "techos": "Techo Adiabatico",
    "pisos": "Piso Adiabatico",
}

# Valores que activan un interruptor declarado en el MASTER
VERDADEROS = ("si", "s", "x", "1", "true")

# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------

@dataclass
class Muro:
    tipo: str
    azimut: str
    area: float | None
    p01: float | None
    p02: float | None
    p03: float | None
    p04: float | None = None
    p04_elemento: str = ""
    p04_aislacion: str = ""
    etiqueta: str = ""            # "Muro 1": lo que referencian las ventanas
    area_bruta: float | None = None
    area_vanos: float = 0.0
    p03_cielo: float | None = None  # parte del P03 que corresponde al cielo

@dataclass
class Ventana:
    tipo: str
    azimut: str
    elemento: str
    cierre: str
    posicion: str
    alto: float | None
    ancho: float | None
    fav: list = field(default_factory=list)   # 9 valores: D,L,P,S,P,S,E,T,b
    muro: str = ""                # etiqueta del muro que la aloja

@dataclass
class Puerta:
    etiqueta: str
    tipo: str
    azimut: str
    categoria: str
    alto: float | None
    ancho: float | None
    muro: str = ""

@dataclass
class Obstruccion:
    orientacion: str
    fila: int                 # 0..7, posicion dentro del bloque de 8 filas
    division: str
    a: float
    b: float | None
    d: float | None

@dataclass
class Horizontal:
    """Una fila de techo o piso de la ficha, ya resuelta para una unidad."""
    destino: str              # "techo" | "piso"
    nombre: str               # "Techo 1", "Piso 1"
    material: str
    densidad: str
    tipo: str                 # tipo de cubierta / piso ventilado
    area: float
    extra: object = None      # camaras de aire (techo) / perimetro (piso)

@dataclass
class Nivel:
    """Un piso de la vivienda: una fila de la seccion 2 de la ficha."""
    area: float
    altura: float | None = None

@dataclass
class Ficha:
    unidad: str
    piso: int
    plantilla: str
    carpeta: str = ""
    dormitorios: float | None = None
    perimetro_terreno: float | None = None
    niveles: list[Nivel] = field(default_factory=list)
    horizontales: list[Horizontal] = field(default_factory=list)
    muros: list[Muro] = field(default_factory=list)
    ventanas: list[Ventana] = field(default_factory=list)
    puertas: list[Puerta] = field(default_factory=list)
    obstrucciones: list[Obstruccion] = field(default_factory=list)
    obstrucciones_eliminadas: int = 0
    paquetes: dict = field(default_factory=dict)
    marco: str = ""        # override de la variante sobre el de Proyecto
    cielo_p01: bool = False  # el P03 del cielo se traspaso a P01

    @property
    def area(self) -> float:
        """Superficie total, sumando los niveles."""
        return sum(n.area for n in self.niveles)


# ---------------------------------------------------------------------------
# Utilidades de lectura
# ---------------------------------------------------------------------------

def cargar_mapa(ruta: str | Path) -> dict:
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el mapa de celdas: {ruta}")
    with open(ruta, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hoja(wb, nombre: str):
    """Busca la hoja tolerando tildes y mayusculas ('Área' vs 'Area')."""
    objetivo = normalizar(nombre)
    for h in wb.sheetnames:
        if normalizar(h) == objetivo:
            return wb[h]
    raise KeyError(
        f"El MASTER no tiene la hoja '{nombre}'. Hojas: {', '.join(wb.sheetnames)}")


def _indice_columnas(ws, fila: int) -> dict[str, list[int]]:
    """
    Encabezado normalizado -> lista de columnas donde aparece.

    Se guarda una lista y no un solo numero porque en la tabla de ventanas hay
    encabezados repetidos ('Material' aparece dos veces).
    """
    mapa: dict[str, list[int]] = {}
    for c in range(1, (ws.max_column or 1) + 1):
        v = ws.cell(row=fila, column=c).value
        if es_vacio(v):
            continue
        mapa.setdefault(normalizar(v), []).append(c)
    return mapa


def _col(cols: dict, nombre: str, hoja: str, ocurrencia: int = 1,
         obligatoria: bool = True) -> int | None:
    """Columna de un encabezado, por coincidencia EXACTA del texto normalizado."""
    encontradas = cols.get(normalizar(nombre), [])
    if len(encontradas) >= ocurrencia:
        return encontradas[ocurrencia - 1]
    if obligatoria:
        raise ValueError(
            f"En la hoja '{hoja}' no se encontro la columna '{nombre}'"
            + (f" (ocurrencia {ocurrencia})" if ocurrencia > 1 else "")
            + ". Revisar el encabezado en el MASTER o el mapa.yaml."
        )
    return None


def _num(v) -> float | None:
    if es_vacio(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _txt(v) -> str:
    return "" if es_vacio(v) else str(v).strip()


# ---------------------------------------------------------------------------
# Hoja Proyecto
# ---------------------------------------------------------------------------

def leer_proyecto(wb, mapa: dict) -> dict[str, object]:
    """Clave-valor de la hoja Proyecto: columna A = clave, columna B = valor."""
    cfg = mapa["master"]
    ws = _hoja(wb, cfg["hoja_proyecto"])

    datos: dict[str, object] = {}
    for f in range(1, (ws.max_row or 1) + 1):
        clave = ws.cell(row=f, column=1).value
        valor = ws.cell(row=f, column=2).value
        if es_vacio(clave) or es_vacio(valor):
            continue          # las filas de titulo no tienen valor en B
        datos[normalizar(clave)] = valor

    faltantes = [
        k for k in cfg.get("proyecto", {}).get("claves_obligatorias", [])
        if normalizar(k) not in datos
    ]
    if faltantes:
        raise ValueError(
            "Faltan estas claves en la hoja 'Proyecto': " + ", ".join(faltantes))
    return datos


def valor_proyecto(proyecto: dict, clave: str, defecto=None):
    return proyecto.get(normalizar(clave), defecto)

def _leer_niveles(ws_idx, fila: int, cols: dict, cfg: dict,
                  altura_defecto) -> list[Nivel]:
    """
    Niveles declarados para una unidad.

    En departamentos hay una sola fila y basta la columna 'Área'. En viviendas
    aisladas hay una por piso, y cada una puede tener su propia altura libre
    (un segundo piso bajo cubierta no mide lo mismo que el primero).
    """
    niveles: list[Nivel] = []
    for i, ref in enumerate(cfg.get("niveles") or [], start=1):
        c_area = cols.get(f"nivel_area_{i}")
        if not c_area:
            continue
        area = _num(ws_idx.cell(row=fila, column=c_area).value)
        if area is None or area <= 0:
            continue
        c_alt = cols.get(f"nivel_altura_{i}")
        altura = _num(ws_idx.cell(row=fila, column=c_alt).value) if c_alt else None
        niveles.append(Nivel(area=area, altura=altura or altura_defecto))

    if not niveles and cols.get("area_simple"):
        area = _num(ws_idx.cell(row=fila, column=cols["area_simple"]).value)
        if area is not None and area > 0:
            niveles.append(Nivel(area=area, altura=altura_defecto))
    return niveles

# ---------------------------------------------------------------------------
# Tablas de una hoja de unidad
# ---------------------------------------------------------------------------
def leer_plantillas_horizontales(wb, mapa: dict) -> list[dict]:
    """
    Lee la tabla de envolventes horizontales de la hoja Proyecto.

    Cada fila declara una fila de la ficha (Techo 1, Techo 2, Piso 1...) con su
    material, densidad, tipo y de que columna de la hoja indice sale el area.
    El destino se deduce del nombre: lo que empieza con "techo" va al bloque de
    techos y lo que empieza con "piso" al de pisos, en el orden declarado.
    """
    cfg = mapa["master"]["horizontales"]
    ws = _hoja(wb, mapa["master"]["hoja_proyecto"])
    merges = mapa_merges(ws)

    def celda(fila: int, letra: str):
        return valor_efectivo(
            ws, fila, column_index_from_string(str(letra).upper()), merges)

    filas: list[dict] = []
    f = int(cfg["fila_encabezado"]) + 1
    while f <= (ws.max_row or 1):
        nombre = _txt(celda(f, cfg["nombre"]))
        if not nombre:
            break                      # la tabla termina en la primera fila vacia

        clave = normalizar(nombre)
        if clave.startswith("techo") or clave.startswith("techumbre"):
            destino = "techo"
        elif clave.startswith("piso"):
            destino = "piso"
        else:
            raise ValueError(
                f"La fila {f} de la tabla de envolventes dice '{nombre}'. "
                "Debe empezar con 'Techo' o 'Piso'.")

        filas.append({
            "destino": destino,
            "nombre": nombre,
            "columna_area": _txt(celda(f, cfg["columna_area"])),
            "material": _txt(celda(f, cfg["material"])),
            "densidad": _txt(celda(f, cfg["densidad"])),
            "tipo": _txt(celda(f, cfg["tipo"])),
            "extra": celda(f, cfg["extra"]) if cfg.get("extra") else None,
        })
        f += 1

    if not filas:
        raise ValueError(
            "La tabla de envolventes horizontales de la hoja 'Proyecto' esta "
            f"vacia (se busco bajo la fila {cfg['fila_encabezado']}).")
    return filas

def leer_muros(ws, mapa: dict) -> list[Muro]:
    cfg = mapa["master"]["muros"]
    fila_enc = int(cfg["fila_encabezado"])
    cols = _indice_columnas(ws, fila_enc)
    claves = ("tipo", "azimut", "area", "p01", "p02", "p03",
              "p04", "p04_elemento", "p04_aislacion", "p03_cielo")
    c = {k: _col(cols, cfg[k], ws.title,
                 obligatoria=k in ("tipo", "azimut", "area"))
         for k in claves if k in cfg}

    def num(fila, clave):
        return _num(ws.cell(row=fila, column=c[clave]).value) \
            if c.get(clave) else None

    def txt(fila, clave):
        return _txt(ws.cell(row=fila, column=c[clave]).value) \
            if c.get(clave) else ""

    muros: list[Muro] = []
    f = fila_enc + 1
    while f <= (ws.max_row or 1):
        etiqueta = ws.cell(row=f, column=1).value     # "Muro 1", "Muro 2", ...
        if es_vacio(etiqueta):
            break                                     # la tabla termina en blanco
        muros.append(Muro(
            tipo=txt(f, "tipo"),
            azimut=txt(f, "azimut"),
            area=num(f, "area"),
            p01=num(f, "p01"),
            p02=num(f, "p02"),
            p03=num(f, "p03"),
            p04=num(f, "p04"),
            p04_elemento=txt(f, "p04_elemento"),
            p04_aislacion=txt(f, "p04_aislacion"),
            etiqueta=_txt(etiqueta),
            p03_cielo=num(f, "p03_cielo"),
        ))
        f += 1
    if not muros:
        raise ValueError(f"La hoja '{ws.title}' no tiene muros bajo la fila "
                         f"{fila_enc}.")
    return muros


def leer_ventanas(ws, mapa: dict) -> list[Ventana]:
    cfg = mapa["master"]["ventanas"]
    fila_enc = int(cfg["fila_encabezado"])
    cols = _indice_columnas(ws, fila_enc)

    c_tipo = _col(cols, cfg["tipo"], ws.title, cfg.get("tipo_ocurrencia", 1))
    c_elem = _col(cols, cfg["elemento"], ws.title, cfg.get("elemento_ocurrencia", 2))
    c_az = _col(cols, cfg["azimut"], ws.title)
    c_cierre = _col(cols, cfg["cierre"], ws.title, obligatoria=False)
    c_pos = _col(cols, cfg["posicion"], ws.title, obligatoria=False)
    c_muro = (_col(cols, cfg["muro"], ws.title,
                   obligatoria=bool(mapa["master"].get("restar_ventanas")))
              if cfg.get("muro") else None)
    c_alto = _col(cols, cfg["alto"], ws.title)
    c_ancho = _col(cols, cfg["ancho"], ws.title)
    # El bloque FAV se lee por posicion: 9 columnas contiguas (D,L,P,S,P,S,E,T,b)
    c_fav = column_index_from_string(str(cfg["fav_col_inicio"]).upper())

    ventanas: list[Ventana] = []
    f = fila_enc + 1
    while f <= (ws.max_row or 1):
        if es_vacio(ws.cell(row=f, column=1).value):
            break
        ventanas.append(Ventana(
            tipo=_txt(ws.cell(row=f, column=c_tipo).value),
            azimut=_txt(ws.cell(row=f, column=c_az).value),
            elemento=_txt(ws.cell(row=f, column=c_elem).value),
            cierre=_txt(ws.cell(row=f, column=c_cierre).value) if c_cierre else "",
            posicion=_txt(ws.cell(row=f, column=c_pos).value) if c_pos else "",
            alto=_num(ws.cell(row=f, column=c_alto).value),
            ancho=_num(ws.cell(row=f, column=c_ancho).value),
            fav=[_num(ws.cell(row=f, column=c_fav + i).value) for i in range(9)],
            muro=_txt(ws.cell(row=f, column=c_muro).value) if c_muro else "",
        ))
        f += 1
    return ventanas

def _buscar_fila(ws, texto: str, desde: int = 1) -> int | None:
    """Primera fila que tenga una celda con ese texto (sin tildes ni mayusculas)."""
    objetivo = normalizar(texto)
    for f in range(desde, (ws.max_row or 1) + 1):
        for c in range(1, (ws.max_column or 1) + 1):
            if normalizar(ws.cell(row=f, column=c).value) == objetivo:
                return f
    return None


def leer_puertas(ws, mapa: dict) -> list[Puerta]:
    """
    Puertas de una hoja de unidad.

    La tabla no tiene fila fija: queda debajo de las ventanas, asi que se
    ubica por su encabezado. Una hoja sin tabla de puertas no es un error.
    """
    cfg = mapa["master"].get("puertas")
    if not cfg:
        return []
    fila_enc = _buscar_fila(ws, cfg["ancla"])
    if fila_enc is None:
        return []

    cols = _indice_columnas(ws, fila_enc)
    c = {k: _col(cols, cfg[k], ws.title,
                 obligatoria=k in ("tipo", "alto", "ancho"))
         for k in ("tipo", "azimut", "alto", "ancho", "muro", "categoria")}

    def leer(fila, clave, numero=False):
        if not c[clave]:
            return None if numero else ""
        v = ws.cell(row=fila, column=c[clave]).value
        return _num(v) if numero else _txt(v)

    puertas: list[Puerta] = []
    f = fila_enc + 1
    while f <= (ws.max_row or 1):
        etiqueta = ws.cell(row=f, column=1).value
        if es_vacio(etiqueta):
            break
        puertas.append(Puerta(
            etiqueta=_txt(etiqueta), tipo=leer(f, "tipo"),
            azimut=leer(f, "azimut"), categoria=leer(f, "categoria"),
            alto=leer(f, "alto", True), ancho=leer(f, "ancho", True),
            muro=leer(f, "muro"),
        ))
        f += 1
    return puertas

def restar_vanos(muros: list[Muro], ventanas: list[Ventana],
                 puertas: list[Puerta], hoja: str,
                 tolerancia: float = 0.0) -> list[Muro]:
    """
    Area neta de cada muro: la bruta menos los vanos de sus ventanas y puertas.

    El motor suma muros, ventanas y puertas como superficies separadas y no
    descuenta nada, asi que un area bruta cuenta dos veces cada abertura. Se
    resta el vano completo (alto x ancho, con marco).

    Tambien verifica que cada abertura tenga el mismo azimut que su muro: si
    esta asignada a un muro de otra orientacion, el vano se descontaria de la
    fachada equivocada.
    """
    por_etiqueta: dict[str, Muro] = {}
    for m in muros:
        clave = normalizar(m.etiqueta)
        if clave in por_etiqueta:
            raise ValueError(f"En '{hoja}' hay dos muros llamados "
                             f"'{m.etiqueta}'.")
        por_etiqueta[clave] = m

    aberturas = [(f"ventana {i}", v.muro, v.azimut,
                  (v.alto or 0.0) * (v.ancho or 0.0))
                 for i, v in enumerate(ventanas, start=1)]
    aberturas += [(p.etiqueta.lower(), p.muro, p.azimut,
                   (p.alto or 0.0) * (p.ancho or 0.0)) for p in puertas]

    vanos: dict[str, float] = defaultdict(float)
    detalle: dict[str, list[str]] = defaultdict(list)
    errores: list[str] = []
    for nombre, muro, azimut, area in aberturas:
        clave = normalizar(muro)
        m = por_etiqueta.get(clave)
        if not clave:
            errores.append(f"{nombre} no indica en que muro esta")
        elif m is None:
            errores.append(f"{nombre} apunta a '{muro}', que no existe")
        elif m.tipo == ADIABATICOS["muros"]:
            errores.append(f"{nombre} esta en '{muro}', que es adiabatico")
        elif azimut and m.azimut and normalizar(azimut) != normalizar(m.azimut):
            errores.append(f"{nombre} tiene azimut '{azimut}' pero {m.etiqueta} "
                           f"tiene '{m.azimut}'")
        else:
            vanos[clave] += area
            detalle[clave].append(f"{nombre} {area:.3f}")

    if errores:
        raise ValueError(f"Problemas con las aberturas de '{hoja}':\n  "
                         + "\n  ".join(errores))

    netos: list[Muro] = []
    negativos: list[str] = []
    for m in muros:
        clave = normalizar(m.etiqueta)
        va = vanos.get(clave, 0.0)
        bruta = m.area or 0.0
        neta = round(bruta - va, 4)
        if neta < -1e-6:
            exceso = -neta / bruta if bruta else float("inf")
            texto = ", ".join(detalle[clave])
            if exceso <= tolerancia:
                print(f"[aviso] '{hoja}' {m.etiqueta}: las aberturas exceden "
                      f"el muro en {exceso:.1%}; se deja en 0 ({texto})")
                neta = 0.0
            else:
                negativos.append(f"{m.etiqueta}: muro {bruta:g} m2, aberturas "
                                 f"{va:g} m2 (exceso {exceso:.1%}) -> {texto}")
        netos.append(replace(m, area=max(neta, 0.0), area_bruta=bruta,
                             area_vanos=va))

    if negativos:
        raise ValueError(f"En '{hoja}' hay muros con menos area que sus "
                         "aberturas:\n  " + "\n  ".join(negativos))
    return netos


def mover_cielo_a_p01(muros: list[Muro], unidad: str) -> list[Muro]:
    """
    Pasa los metros de P03 cielo a P01, muro por muro.

    Bajo la techumbre, el encuentro del cielo con el muro deja de ser un
    elemento interior (P03) y pasa a ser un borde exterior (P01).

    Devuelve objetos NUEVOS con replace: los muros vienen del cache por
    plantilla y los comparten todas las unidades de esa plantilla. Mutarlos
    moveria el cielo tambien en los pisos de abajo, sin ningun error.
    """
    nuevos: list[Muro] = []
    movidos = 0.0
    for m in muros:
        cielo = m.p03_cielo or 0.0
        if cielo <= 0:
            nuevos.append(m)
            continue
        p03 = (m.p03 or 0.0) - cielo
        if p03 < -1e-6:
            raise ValueError(
                f"{unidad}, {m.etiqueta}: 'P03 cielo' ({cielo:g}) es mayor que "
                f"el P03 total ({m.p03 or 0:g}). El P03 debe incluir el cielo.")
        movidos += cielo
        nuevos.append(replace(m, p03=round(max(p03, 0.0), 4),
                              p01=round((m.p01 or 0.0) + cielo, 4),
                              p03_cielo=0.0))
    if movidos == 0:
        print(f"[aviso] {unidad}: declara 'Cielo a P01' pero ningun muro "
              "tiene metros en 'P03 cielo'. No se movio nada.")
    return nuevos


def auditar_areas(fichas: list[Ficha]) -> None:
    """Tabla bruta / vanos / neta por plantilla, mas puertas y traspaso de cielo."""
    vistas: set[str] = set()
    for fi in fichas:
        if fi.plantilla in vistas:
            continue
        vistas.add(fi.plantilla)
        print(f"\n{fi.plantilla}")
        if any(m.area_bruta for m in fi.muros):
            print(f"  {'MURO':<10}{'BRUTA':>9}{'VANOS':>9}{'NETA':>9}")
            for m in fi.muros:
                print(f"  {m.etiqueta:<10}{(m.area_bruta or 0):>9.2f}"
                      f"{m.area_vanos:>9.2f}{(m.area or 0):>9.2f}")
        if fi.puertas:
            print("  PUERTAS:")
            for p in fi.puertas:
                print(f"    {p.etiqueta:<10} {p.tipo:<6} {p.alto} x {p.ancho}"
                      f"  en {p.muro}  [{p.categoria}]")
        else:
            print("  PUERTAS: (ninguna leida)")

    # El traspaso es por unidad, no por plantilla: se lista aparte
    con_cielo = [fi for fi in fichas if fi.cielo_p01]
    if con_cielo:
        print("\nCIELO A P01 (P03 cielo traspasado a P01):")
        for fi in con_cielo:
            p01 = sum(m.p01 or 0 for m in fi.muros)
            p03 = sum(m.p03 or 0 for m in fi.muros)
            print(f"  {fi.unidad:<10} P01 total {p01:>8.2f}   P03 total {p03:>8.2f}")

# ---------------------------------------------------------------------------
# FAR
# ---------------------------------------------------------------------------

def leer_far(wb, mapa: dict) -> dict[str, list[Obstruccion]]:
    """
    unidad -> obstrucciones tal como estan declaradas en el MASTER.

    La hoja se recorre en BLOQUES de alto fijo (8 filas por unidad, igual que
    el bloque de obstrucciones de la ficha oficial). Es mas confiable que
    buscar la etiqueta fila por fila: la columna de unidad viene combinada por
    bloque, y basta que una fila quede corrida para desalinear todo.

    Se descartan las filas sin division y las que tienen A <= 0: son relleno
    (ceros) o etiquetas sueltas, no obstrucciones reales.
    """
    cfg = mapa["master"]["far"]
    ws = _hoja(wb, cfg["hoja"])
    merges = mapa_merges(ws)
    alto = int(cfg.get("filas_por_unidad", 8))
    c_unidad = column_index_from_string(str(cfg["unidad"]).upper())

    por_unidad: dict[str, list[Obstruccion]] = {}
    f = int(cfg["fila_inicio"])
    while f <= (ws.max_row or 1):
        crudo = valor_efectivo(ws, f, c_unidad, merges)
        if es_vacio(crudo):
            break                      # primer bloque sin etiqueta: fin de la tabla
        clave = str(int(crudo)) if isinstance(crudo, float) and crudo.is_integer() \
            else _txt(crudo)
        if clave in por_unidad:
            raise ValueError(
                f"La hoja '{ws.title}' declara dos veces la unidad {clave}. "
                f"Revisar que cada bloque tenga exactamente {alto} filas.")

        obst: list[Obstruccion] = []
        for i in range(alto):
            fila = f + i
            for g in cfg["grupos"]:
                div = _txt(valor_efectivo(
                    ws, fila, column_index_from_string(g["division"]), merges))
                a = _num(valor_efectivo(
                    ws, fila, column_index_from_string(g["a"]), merges))
                b = _num(valor_efectivo(
                    ws, fila, column_index_from_string(g["b"]), merges))
                d = _num(valor_efectivo(
                    ws, fila, column_index_from_string(g["d"]), merges))
                if not div or a is None or a <= 0:
                    continue
                obst.append(Obstruccion(g["orientacion"], i, div, a, b, d))
        por_unidad[clave] = obst
        f += alto

    if not por_unidad:
        raise ValueError(f"No se leyo ninguna unidad en la hoja '{ws.title}'.")
    return por_unidad

def leer_azimut_far(wb, mapa: dict) -> dict[str, str]:
    """
    Azimut declarado por orientacion en el encabezado de la hoja FAR.

    Es uno por orientacion para todo el proyecto (fila 1), no por unidad: el
    edificio no gira segun el piso.
    """
    cfg = mapa["master"]["far"]
    ws = _hoja(wb, cfg["hoja"])
    merges = mapa_merges(ws)
    fila = int(cfg.get("fila_azimut", 1))

    azimuts: dict[str, str] = {}
    for g in cfg["grupos"]:
        letra = g.get("azimut")
        if not letra:
            continue
        valor = _txt(valor_efectivo(
            ws, fila, column_index_from_string(str(letra).upper()), merges))
        if valor:
            azimuts[g["orientacion"]] = valor
    return azimuts

def ajustar_far(obstrucciones: list[Obstruccion], piso: int, piso_base: int,
                altura: float) -> tuple[list[Obstruccion], int]:
    """
    Baja la altura A segun cuantos pisos se subio, descarta lo que quedo por
    debajo del nivel de la ventana y COMPACTA cada orientacion hacia arriba.

    La compactacion es por grupo de orientacion, no global: cada orientacion
    ocupa su propio bloque de filas en la ficha, asi que si el norte pierde dos
    obstrucciones, solo el norte sube dos lugares.

    Se compacta y no se dejan huecos para no depender de como la planilla
    oficial interpreta una fila en blanco en medio de la tabla.
    """
    delta = (piso - piso_base) * altura
    vivas: list[Obstruccion] = []
    eliminadas = 0
    siguiente: dict[str, int] = {}     # orientacion -> proxima fila libre

    for o in sorted(obstrucciones, key=lambda x: (x.orientacion, x.fila)):
        nueva = round(o.a - delta, 4)
        if nueva <= 0:
            eliminadas += 1
            continue
        fila = siguiente.get(o.orientacion, 0)
        siguiente[o.orientacion] = fila + 1
        vivas.append(Obstruccion(o.orientacion, fila, o.division, nueva, o.b, o.d))

    return vivas, eliminadas

@dataclass
class FilaCatalogo:
    """Una fila del catalogo, ya traducida a coordenadas de la ficha."""
    bloque: str
    fila: int                        # fila absoluta en "3. Tablas Envolvente"
    valores: dict[int, object]       # columna de la ficha -> valor


def leer_catalogo(wb, mapa: dict) -> tuple[list[FilaCatalogo], dict[str, set[str]]]:
    """
    Lee la hoja 'Materiales' del MASTER y la traduce a celdas de la ficha.

    No se interpreta el significado de cada columna: los bloques son espejo de
    la tabla oficial, asi que basta copiarlos desplazados. Devuelve las filas a
    escribir y las abreviaturas por familia, para validar referencias.
    """
    cfg = mapa.get("catalogo")
    if not cfg:
        return [], {}
    try:
        ws = _hoja(wb, cfg["hoja_master"])
    except KeyError:
        return [], {}          # sin catalogo: las tablas se llenan a mano

    merges = mapa_merges(ws)
    desplazamiento = int(cfg.get("desplazamiento_columnas", 1))
    por_bloque: dict[str, list[FilaCatalogo]] = {}
    filas: list[FilaCatalogo] = []

    for b in cfg["bloques"]:
        ini, fin = (column_index_from_string(x.strip().upper())
                    for x in str(b["cols"]).split(":"))
        for i in range(int(b["filas"])):
            f_master = int(b["master"]) + i
            valores: dict[int, object] = {}
            for c in range(ini, fin + 1):
                v = valor_efectivo(ws, f_master, c, merges)
                if es_vacio(v):
                    continue
                valores[c + desplazamiento] = v
            if not valores:
                continue       # fila vacia: no se escribe nada
            fila = FilaCatalogo(b["nombre"], int(b["ficha"]) + i, valores)
            filas.append(fila)
            por_bloque.setdefault(b["nombre"], []).append(fila)

    # Abreviaturas por familia, para la validacion cruzada y para expandir
    # el '*' de la hoja Iteraciones. Una familia sin filas en el MASTER es
    # normal: los vidrios y marcos suelen ser todos de fabrica.
    abreviaturas: dict[str, set[str]] = {
        familia: set() for familia in (cfg.get("familias") or {})
    }
    for familia, ref in (cfg.get("familias") or {}).items():
        col = column_index_from_string(str(ref["columna"]).upper()) \
            + desplazamiento
        vistas: list[str] = []
        for fila in por_bloque.get(ref["bloque"], []):
            v = _txt(fila.valores.get(col))
            if v:
                vistas.append(v)
        repes = sorted({a for a in vistas if vistas.count(a) > 1})
        if repes:
            raise ValueError(
                f"Abreviaturas repetidas en el bloque {ref['bloque']} de la "
                f"hoja 'Materiales': {', '.join(repes)}")
        abreviaturas[familia] = set(vistas)

    return filas, abreviaturas

# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------

def _piso_de(unidad: str) -> int:
    """'301' -> 3, '1502' -> 15. Las dos ultimas cifras son el numero de unidad."""
    digitos = "".join(ch for ch in unidad if ch.isdigit())
    if len(digitos) < 3:
        raise ValueError(
            f"No se puede deducir el piso de la unidad '{unidad}'. "
            "Agregar una columna 'Piso' al indice.")
    return int(digitos[:-2])

def _piso_base_de(plantilla: str, defecto: int | None = None,
                  piso_unidad: int | None = None) -> int:
    """
    Piso en que se midieron las obstrucciones de una plantilla.

    Se deduce del nombre ('D201' -> 2), que es el dato mas confiable en un
    edificio. En proyectos de viviendas aisladas los nombres no codifican
    piso, asi que se cae al piso de la propia unidad: sin diferencia de
    altura, el decremento es cero y el FAR queda tal como se declaro.
    """
    digitos = "".join(ch for ch in str(plantilla) if ch.isdigit())
    if len(digitos) >= 3:
        return int(digitos[:-2])
    if defecto is not None:
        return int(defecto)
    if piso_unidad is not None:
        return int(piso_unidad)
    raise ValueError(
        f"No se puede deducir el piso base de la plantilla '{plantilla}'. "
        "Declarar 'Piso base FAR' en la hoja Proyecto.")

def validar_referencias(fichas: list[Ficha],
                        abreviaturas: dict[str, set[str]]) -> None:
    """
    Verifica que todo material usado exista en el catalogo.

    Es la validacion que mas vale la pena: las escrituras por COM IGNORAN las
    listas desplegables de Excel, asi que un nombre mal escrito no se rechaza,
    se escribe igual y la ficha calcula con basura.
    """
    if not any(abreviaturas.values()):
        return

    # No todas las familias tienen adiabatico: vidrios y marcos no lo tienen.
    conocidos = {
        fam: set(vals) | ({ADIABATICOS[fam]} if fam in ADIABATICOS else set())
        for fam, vals in abreviaturas.items()
    }

    faltan: dict[tuple[str, str], set[str]] = {}

    def anotar(familia: str, valor: str, unidad: str):
        if valor and familia in conocidos and valor not in conocidos[familia]:
            faltan.setdefault((familia, valor), set()).add(unidad)

    for fi in fichas:
        for m in fi.muros:
            anotar("muros", m.tipo, fi.unidad)
        for v in fi.ventanas:
            anotar("muros", v.elemento, fi.unidad)
        for h in fi.horizontales:
            anotar("techos" if h.destino == "techo" else "pisos",
                   h.material, fi.unidad)

    if faltan:
        lineas = []
        for (fam, valor), unidades in sorted(faltan.items()):
            disponibles = ", ".join(sorted(conocidos[fam])) or "(vacio)"
            u = ", ".join(sorted(unidades)[:5])
            lineas.append(
                f"  - {fam}: '{valor}' (en {u}). Disponibles: {disponibles}")
        raise ValueError(
            "Hay materiales usados que no estan en la hoja 'Materiales':\n"
            + "\n".join(lineas))

    incompletos = []
    for fi in fichas:
        for i, m in enumerate(fi.muros, start=1):
            if m.p04 and m.p04 > 0 and not (m.p04_elemento and m.p04_aislacion):
                incompletos.append(f"{fi.unidad} muro {i} ({m.tipo})")
    if incompletos:
        raise ValueError(
            "Hay muros con P04 declarado pero sin 'P04 elemento' o "
            "'P04 aislación':\n  " + "\n  ".join(incompletos[:10]))

def _ranking(items, adiabatico: str | None = None) -> list[str]:
    """
    Ordena materiales por area total, de mayor a menor.

    Los adiabaticos se dejan al final: no son envolvente real, asi que solo se
    eligen si la unidad no tiene ninguna otra cosa (el caso de los pisos y
    techos de las unidades intermedias, donde todo es adiabatico).

    A igualdad de area se ordena por nombre, para que el resultado sea estable
    entre corridas y no dependa del orden de lectura.
    """
    totales: dict[str, float] = {}
    for nombre, area in items:
        if not nombre:
            continue
        totales[nombre] = totales.get(nombre, 0.0) + float(area or 0.0)
    if not totales:
        return []
    reales = {k: v for k, v in totales.items() if k != adiabatico}
    elegidos = reales or totales
    return [k for k, _ in sorted(elegidos.items(), key=lambda kv: (-kv[1], kv[0]))]


def calcular_paquetes(ficha: Ficha, proyecto: dict) -> dict[str, str]:
    """
    Elige el elemento principal y el secundario de cada familia, por unidad.

    El predominante se define por AREA acumulada, no por cantidad: dos muros
    chicos no le ganan a uno grande. Se calcula por unidad porque cambia entre
    ellas (una unidad de esquina no tiene la misma proporcion que una central).

    Cualquiera de estos valores se puede fijar a mano en la hoja Proyecto con
    la clave 'Paquete: <etiqueta>', que tiene prioridad sobre el calculo.
    """
    muros = _ranking(((m.tipo, m.area) for m in ficha.muros),
                     ADIABATICOS["muros"])
    techos = _ranking(((h.material, h.area) for h in ficha.horizontales
                       if h.destino == "techo"), ADIABATICOS["techos"])
    pisos = _ranking(((h.material, h.area) for h in ficha.horizontales
                      if h.destino == "piso"), ADIABATICOS["pisos"])
    ventanas = _ranking((v.tipo, (v.alto or 0) * (v.ancho or 0))
                        for v in ficha.ventanas)
    puertas = _ranking(((p.tipo, (p.alto or 0) * (p.ancho or 0))
                        for p in ficha.puertas))

    def n(lista: list[str], i: int) -> str:
        return lista[i] if len(lista) > i else ""

    paquetes = {
        "Muro principal": n(muros, 0),
        "Muro secundario": n(muros, 1),
        "Piso principal": n(pisos, 0),
        "Techo principal": n(techos, 0),
        "Techo secundario": n(techos, 1),
        "Ventana principal": n(ventanas, 0),
        "Ventana secundaria": n(ventanas, 1),
        "Marco principal": _txt(valor_proyecto(proyecto, "Ventana: Tipo marco")),
        "Marco secundario": "",
        "Puerta principal": (n(puertas, 0)
                             or _txt(valor_proyecto(proyecto, "Puerta: Tipo"))),
    }

    for etiqueta in list(paquetes):
        manual = _txt(valor_proyecto(proyecto, f"Paquete: {etiqueta}"))
        if manual:
            paquetes[etiqueta] = manual

    return {k: v for k, v in paquetes.items() if v}

def construir(ruta_master: str | Path, mapa: dict) -> tuple[list[Ficha], dict]:
    """Lee el MASTER completo y devuelve (fichas, parametros de proyecto)."""
    wb = load_workbook(Path(ruta_master), data_only=True)
    cfg = mapa["master"]

    # --- Parametros del proyecto ------------------------------------------
    proyecto = leer_proyecto(wb, mapa)
    altura = _num(valor_proyecto(proyecto, "Altura piso a piso [m]"))
    if not altura or altura <= 0:
        raise ValueError(
            "'Altura piso a piso [m]' debe ser un numero mayor a 0 en la hoja "
            "'Proyecto'. Es la distancia losa a losa, no la altura libre.")

    altura_defecto = _num(valor_proyecto(
        proyecto, "Altura libre cielo a piso [m]"))

    # Respaldo: solo se usa si el nombre de la plantilla no permite deducir
    # el piso en que se midieron sus obstrucciones.
    piso_base_global = _num(valor_proyecto(proyecto, "Piso base FAR"))
    piso_base_global = int(piso_base_global) if piso_base_global else None

    # --- Indice de unidades (hoja "Area") ---------------------------------
    ws_idx = _hoja(wb, cfg["hoja_indice"])
    icfg = cfg["indice"]
    cols = _indice_columnas(ws_idx, 1)
    c_unidad = _col(cols, icfg["unidad"], ws_idx.title)
    c_plantilla = _col(cols, icfg["plantilla"], ws_idx.title)

    opcionales: dict[str, int | None] = {
        k: _col(cols, icfg[k], ws_idx.title, obligatoria=False)
        for k in ("piso", "dormitorios", "perimetro_terreno", "carpeta",
                  "cielo_p01")
        if k in icfg
    }
    # Las columnas opcionales que no se encuentran se ignoran en silencio, y
    # un typo en el encabezado hace desaparecer el dato sin ninguna senal.
    # Mejor decirlo: casi siempre es un error de tipeo, no una omision.
    faltantes = [icfg[k] for k, c in opcionales.items()
                 if c is None and k in icfg]
    if faltantes:
        print(f"[aviso] Columnas no encontradas en la hoja "
              f"'{ws_idx.title}': {', '.join(faltantes)}")
        print(f"        Disponibles: "
              f"{', '.join(sorted(_txt(ws_idx.cell(row=1, column=c).value) for c in range(1, (ws_idx.max_column or 1) + 1) if not es_vacio(ws_idx.cell(row=1, column=c).value)))}")
    # Superficie por nivel: en departamentos hay una sola fila, en viviendas
    # aisladas una por piso. Se busca cada columna y se usa la que exista.
    for i, ref in enumerate(cfg.get("niveles") or [], start=1):
        opcionales[f"nivel_area_{i}"] = _col(
            cols, ref["area"], ws_idx.title, obligatoria=False)
        if ref.get("altura"):
            opcionales[f"nivel_altura_{i}"] = _col(
                cols, ref["altura"], ws_idx.title, obligatoria=False)
    if cfg.get("area_simple"):
        opcionales["area_simple"] = _col(
            cols, cfg["area_simple"], ws_idx.title, obligatoria=False)

    # Las columnas de area de techos y pisos no estan fijas en el mapa: las
    # declara la tabla de envolventes de la hoja Proyecto.
    plantillas_h = leer_plantillas_horizontales(wb, mapa)
    for p in plantillas_h:
        p["col"] = _col(cols, p["columna_area"], ws_idx.title, obligatoria=False)
        if p["col"] is None:
            raise ValueError(
                f"La envolvente '{p['nombre']}' apunta a la columna "
                f"'{p['columna_area']}', que no existe en la hoja "
                f"'{ws_idx.title}'.")

    far = leer_far(wb, mapa)
    cache: dict[str, tuple[list[Muro], list[Ventana], list[Puerta]]] = {}
    fichas: list[Ficha] = []

    # --- Una ficha por fila del indice ------------------------------------
    for f in range(2, (ws_idx.max_row or 1) + 1):
        crudo = ws_idx.cell(row=f, column=c_unidad).value
        if es_vacio(crudo):
            continue
        unidad = str(int(crudo)) if isinstance(crudo, float) and crudo.is_integer() \
            else _txt(crudo)

        plantilla = _txt(ws_idx.cell(row=f, column=c_plantilla).value)
        if not plantilla:
            raise ValueError(f"La unidad {unidad} no declara 'Plantilla'.")

        def opt(nombre: str):
            c = opcionales.get(nombre)
            return _num(ws_idx.cell(row=f, column=c).value) if c else None

        # El piso se declara o se deduce del numero. En viviendas aisladas hay
        # que declararlo: los nombres no codifican piso.
        piso_declarado = opt("piso")
        piso = int(piso_declarado) if piso_declarado is not None else _piso_de(unidad)

        carpeta = ""
        if opcionales.get("carpeta"):
            carpeta = _txt(ws_idx.cell(row=f, column=opcionales["carpeta"]).value)

        # Muros y ventanas se leen una vez por plantilla y se reutilizan
        if plantilla not in cache:
            ws_p = _hoja(wb, plantilla)
            muros_p = leer_muros(ws_p, mapa)
            ventanas_p = leer_ventanas(ws_p, mapa)
            puertas_p = leer_puertas(ws_p, mapa)
            if cfg.get("restar_ventanas"):
                muros_p = restar_vanos(
                    muros_p, ventanas_p, puertas_p, plantilla,
                    float(cfg.get("tolerancia_vanos", 0.0)))
            cache[plantilla] = (muros_p, ventanas_p, puertas_p)
        muros, ventanas, puertas = cache[plantilla]

        # Si la unidad trae su propio bloque de FAR, se usa tal cual: son datos
        # medidos, no derivados. Solo las unidades no declaradas se calculan
        # bajando la altura desde el piso base de su plantilla.
        declarada = unidad in far
        base = far.get(unidad) or far.get(plantilla.lstrip("Dd")) \
            or far.get(plantilla) or []
        base_piso = piso if declarada else _piso_base_de(
            plantilla, piso_base_global, piso)
        obst, eliminadas = ajustar_far(base, piso, base_piso, altura)

        # Una envolvente sin area en esta unidad simplemente no existe aca
        # (ej. la techumbre real solo esta en el ultimo piso).
        horizontales: list[Horizontal] = []
        for p in plantillas_h:
            area_h = _num(ws_idx.cell(row=f, column=p["col"]).value)
            if area_h is None or area_h <= 0:
                continue
            horizontales.append(Horizontal(
                destino=p["destino"], nombre=p["nombre"],
                material=p["material"], densidad=p["densidad"],
                tipo=p["tipo"], area=area_h, extra=p["extra"]))

        # Cielo contra la techumbre: el encuentro deja de ser P03 y pasa a
        # P01. Solo se hace si la unidad lo declara explicitamente en la
        # columna 'Cielo a P01': deducirlo daria traspasos falsos en casas,
        # donde el P01/P03 ya viene resuelto en el MASTER.
        mover = False
        if opcionales.get("cielo_p01"):
            v = normalizar(ws_idx.cell(row=f, column=opcionales["cielo_p01"]).value)
            mover = v in VERDADEROS
        if mover:
            muros = mover_cielo_a_p01(muros, unidad)

        niveles = _leer_niveles(ws_idx, f, opcionales, cfg, altura_defecto)
        if not niveles:
            raise ValueError(
                f"La unidad {unidad} no tiene superficie declarada. Revisar "
                f"las columnas de area en la hoja '{ws_idx.title}'.")

        ficha = Ficha(
            unidad=unidad, piso=piso, plantilla=plantilla, carpeta=carpeta,
            dormitorios=opt("dormitorios"),
            perimetro_terreno=opt("perimetro_terreno"),
            niveles=niveles, horizontales=horizontales,
            muros=muros, ventanas=ventanas, puertas=puertas,
            obstrucciones=obst, obstrucciones_eliminadas=eliminadas,
            cielo_p01=mover,
        )
        ficha.paquetes = calcular_paquetes(ficha, proyecto)
        fichas.append(ficha)

    if not fichas:
        raise ValueError("El indice no tiene unidades.")

    repetidas = [u for u in {fi.unidad for fi in fichas}
                 if sum(1 for fi in fichas if fi.unidad == u) > 1]
    if repetidas:
        raise ValueError(f"Unidades repetidas en el indice: {', '.join(repetidas)}")

    catalogo, abreviaturas = leer_catalogo(wb, mapa)
    validar_referencias(fichas, abreviaturas)
    proyecto[CLAVE_CATALOGO] = catalogo
    proyecto[CLAVE_AZIMUT_FAR] = leer_azimut_far(wb, mapa)

    return fichas, proyecto


def exportar_csv(fichas: list[Ficha], ruta: str | Path) -> Path:
    """Resumen para revisar la expansion en una planilla antes de generar."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["UNIDAD", "PISO", "PLANTILLA", "AREA", "DORM", "MUROS",
                    "VENTANAS", "OBSTRUCCIONES", "OBST_ELIMINADAS",
                    "TECHOS", "PISOS", "A_MAX", "CIELO_P01", "P01_TOTAL",
                    "P03_TOTAL", "PAQUETES", "HORIZONTALES"])
        for fi in fichas:
            a_max = max((o.a for o in fi.obstrucciones), default=0)
            # Paquetes elegidos por area: es lo que hay que auditar cuando la
            # ficha sale con un muro principal que no era el esperado.
            paquetes = " | ".join(f"{k}: {v}" for k, v in fi.paquetes.items())
            # Detalle de techos y pisos, util sobre todo en el ultimo piso.
            detalle = " | ".join(
                f"{h.nombre}: {h.material} ({h.area:g} m2)"
                for h in fi.horizontales)
            w.writerow([
                fi.unidad, fi.piso, fi.plantilla, fi.area, fi.dormitorios,
                len(fi.muros), len(fi.ventanas), len(fi.obstrucciones),
                fi.obstrucciones_eliminadas,
                sum(1 for h in fi.horizontales if h.destino == "techo"),
                sum(1 for h in fi.horizontales if h.destino == "piso"),
                round(a_max, 2),
                "Si" if fi.cielo_p01 else "",
                round(sum(m.p01 or 0 for m in fi.muros), 2),
                round(sum(m.p03 or 0 for m in fi.muros), 2),
                paquetes, detalle,
            ])
    return ruta


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Uso: python -m herramientas.fichas_cev.modelo MASTER.xlsx "
              "[mapa.yaml]")
        raise SystemExit(1)

    ruta_mapa = sys.argv[2] if len(sys.argv) > 2 else \
        "herramientas/fichas_cev/mapa.yaml"
    fichas, proyecto = construir(sys.argv[1], cargar_mapa(ruta_mapa))

    print(f"Proyecto        : {valor_proyecto(proyecto, 'Proyecto', '(sin nombre)')}")
    print(f"Altura piso/piso: {valor_proyecto(proyecto, 'Altura piso a piso [m]')} m")
    print(f"Fichas a generar: {len(fichas)}\n")
    print(f"{'UNIDAD':<8}{'PISO':>5}{'PLANT':>8}{'MUR':>5}{'VEN':>5}"
          f"{'OBST':>6}{'ELIM':>6}{'TEC':>5}{'PIS':>5}{'A_MAX':>8}")
    for fi in fichas:
        a_max = max((o.a for o in fi.obstrucciones), default=0)
        techos = sum(1 for h in fi.horizontales if h.destino == "techo")
        pisos = sum(1 for h in fi.horizontales if h.destino == "piso")
        print(f"{fi.unidad:<8}{fi.piso:>5}{fi.plantilla:>8}{len(fi.muros):>5}"
              f"{len(fi.ventanas):>5}{len(fi.obstrucciones):>6}"
              f"{fi.obstrucciones_eliminadas:>6}{techos:>5}{pisos:>5}"
              f"{a_max:>8.2f}")

    salida = exportar_csv(fichas, "salidas/fichas_cev/expansion.csv")
    print(f"\nCSV: {salida}")
