# -*- coding: utf-8 -*-
"""
Soluciones constructivas de cada elemento de la unidad, sin interfaz. Cada uno
sigue la solucion general de su tipo ("general", la de partida; generales.py) o
tiene una propia: muros, techos y pisos "norma" (solucion de la zona,
recinto/envolvente.py) o "personalizado" (datos escritos a mano,
recinto/config/personalizado.yaml); vidrios y puertas "listado" o "personalizado".
Una solucion propia nueva parte de la que el elemento usaba (la general si la
seguia), asi no cambia nada hasta que se edita.

  - Muros: el tramo usa GENERAL, DEFECTO (norma) o la clave de un muro
    personalizado de Unidad.muros_personalizados (M1, M2...). Varios tramos pueden
    compartir uno; el nombre que va a la ficha es datos["nombre"].
  - Techos y pisos: cada superficie (destino techo | piso, nivel k) tiene su
    solucion (superficie / editar_superficie). Las principales (piso del nivel 1,
    techo del ultimo) usan Unidad.piso_personalizado y techo_personalizado
    (horizontal / editar_horizontal); las del descalce entre niveles,
    Unidad.superficies_personalizadas. None = general, NORMA, o los datos.
  - Vidrio: Ventana.vidrio (GENERAL o codigo) o Ventana.vidrio_personalizado.
  - Puerta: Puerta.tipo (GENERAL o abreviatura de la ficha) o Puerta.personalizada.
Todas las funciones devuelven una Unidad nueva. Los datos no se validan al
editarlos (la interfaz muestra el error); cev.construir los valida al calcular.
"""
from __future__ import annotations

from dataclasses import replace

from herramientas.recinto import catalogo, personalizado

from . import editor, generales
from .modelo import (DEFECTO, DESTINOS, GENERAL, NORMA, Unidad, clave_superficie, es_principal,
                     personalizado_horizontal)

MODOS_SOLUCION = ("general", "norma", "personalizado")
MODOS_LISTA = ("general", "listado", "personalizado")


def nueva_clave(existentes, prefijo: str = "M") -> str:
    n = 1
    while f"{prefijo}{n}" in existentes:
        n += 1
    return f"{prefijo}{n}"


def _modo(modo: str, validos: tuple) -> None:
    if modo not in validos:
        raise ValueError(f"modo debe ser uno de {validos}")


# --------------------------------------------------------------------------- muros
def solucion_muro(u: Unidad, k: int, i: int, j: int, modo: str, sols: dict | None = None) -> Unidad:
    """general: el tramo sigue al muro general. norma: DEFECTO. personalizado: si no lo es,
    se crea un muro personalizado nuevo (con los datos del general si era personalizado y
    el tramo lo seguia; si no, la solucion de la zona) y se le asigna."""
    _modo(modo, MODOS_SOLUCION)
    t = u.niveles[k].lados[i].tramos[j]
    if modo == "general":
        return editor.cambiar_tramo(u, k, i, j, solucion=GENERAL)
    if modo == "norma":
        return editor.cambiar_tramo(u, k, i, j, solucion=DEFECTO)
    if t.solucion not in (DEFECTO, GENERAL):
        return u
    pers = dict(u.muros_personalizados)
    clave = nueva_clave(pers)
    base = personalizado.inicial("muro", sols)
    gm = generales.valor(u, "muro") if t.solucion == GENERAL else None
    d = dict(gm) if isinstance(gm, dict) else base
    d["nombre"] = f"{base.get('nombre') or 'Muro personalizado'} {clave[1:]}"
    pers[clave] = d
    return editor.cambiar_tramo(replace(u, muros_personalizados=pers), k, i, j, solucion=clave)


def asignar_muro(u: Unidad, k: int, i: int, j: int, clave: str) -> Unidad:
    return editor.cambiar_tramo(u, k, i, j, solucion=clave)


def editar_muro(u: Unidad, clave: str, campo: str, valor) -> Unidad:
    pers = dict(u.muros_personalizados)
    if clave not in pers:
        raise ValueError(f"No existe el muro personalizado {clave!r}")
    pers[clave] = dict(pers[clave], **{campo: valor})
    return replace(u, muros_personalizados=pers)


# --------------------------------------------------------------------------- techos y pisos
def _revisar(destino: str, modo: str | None = None) -> None:
    if destino not in DESTINOS:
        raise ValueError(f"destino debe ser uno de {DESTINOS}")
    if modo is not None:
        _modo(modo, MODOS_SOLUCION)


def _nuevo_horizontal(u: Unidad, destino: str, nivel: int, sols: dict | None) -> dict:
    """Datos de un techo o piso que pasa a personalizado: los que usaba (la general, si
    estaba personalizada) o la solucion de la zona, con el nombre de personalizado.yaml."""
    base = personalizado.inicial(destino, sols)
    efectivo = personalizado_horizontal(u, destino, nivel)
    if not efectivo:
        return base
    return dict(efectivo, nombre=base.get("nombre") or f"{destino.capitalize()} personalizado")


def horizontal(u: Unidad, destino: str, modo: str, sols: dict | None = None) -> Unidad:
    """Solucion del piso del nivel 1 o del techo del ultimo nivel."""
    _revisar(destino, modo)
    campo = f"{destino}_personalizado"
    if modo == "general":
        return replace(u, **{campo: None})
    if modo == "norma":
        return replace(u, **{campo: NORMA})
    if isinstance(getattr(u, campo), dict):
        return u
    nivel = 0 if destino == "piso" else len(u.niveles) - 1
    return replace(u, **{campo: _nuevo_horizontal(u, destino, nivel, sols)})


def editar_horizontal(u: Unidad, destino: str, campo: str, valor) -> Unidad:
    _revisar(destino)
    clave = f"{destino}_personalizado"
    d = getattr(u, clave)
    if not isinstance(d, dict):
        raise ValueError(f"El {destino} no está personalizado")
    return replace(u, **{clave: dict(d, **{campo: valor})})


def superficie(u: Unidad, destino: str, nivel: int, modo: str, sols: dict | None = None) -> Unidad:
    """Solucion del techo o piso del nivel `nivel` (tambien los del descalce entre niveles).
    Uno personalizado nuevo se llama como el de personalizado.yaml mas el nivel (N2),
    para no confundirlo con el principal."""
    _revisar(destino, modo)
    if es_principal(u, destino, nivel):
        return horizontal(u, destino, modo, sols)
    clave = clave_superficie(destino, nivel)
    pers = dict(u.superficies_personalizadas)
    if modo == "general":
        if clave not in pers:
            return u
        del pers[clave]
    elif modo == "norma":
        if pers.get(clave) == NORMA:
            return u
        pers[clave] = NORMA
    elif isinstance(pers.get(clave), dict):
        return u
    else:
        d = _nuevo_horizontal(u, destino, nivel, sols)
        d["nombre"] = f"{d.get('nombre') or destino.capitalize()} N{nivel + 1}"
        pers[clave] = d
    return replace(u, superficies_personalizadas=pers)


def editar_superficie(u: Unidad, destino: str, nivel: int, campo: str, valor) -> Unidad:
    _revisar(destino)
    if es_principal(u, destino, nivel):
        return editar_horizontal(u, destino, campo, valor)
    clave = clave_superficie(destino, nivel)
    pers = dict(u.superficies_personalizadas)
    if not isinstance(pers.get(clave), dict):
        raise ValueError(f"El {destino} del nivel {nivel + 1} no está personalizado")
    pers[clave] = dict(pers[clave], **{campo: valor})
    return replace(u, superficies_personalizadas=pers)


# --------------------------------------------------------------------------- vanos
def _vano(u: Unidad, k, i, j, campo, m):
    t = u.niveles[k].lados[i].tramos[j]
    lista = getattr(t, campo)
    if not 0 <= m < len(lista):
        raise ValueError("No existe ese vano")
    return t, lista[m]


def _con_vano(u: Unidad, k, i, j, campo, m, nuevo) -> Unidad:
    t = u.niveles[k].lados[i].tramos[j]
    lista = list(getattr(t, campo))
    lista[m] = nuevo
    return editor._con_tramo(u, k, i, j, replace(t, **{campo: tuple(lista)}))


def _codigo_general(u: Unidad, cat: str) -> str:
    v = generales.valor(u, cat)
    return v if isinstance(v, str) else generales.config()[cat]


def vidrio(u: Unidad, k: int, i: int, j: int, m: int, modo: str, codigo: str | None = None) -> Unidad:
    """general: sigue al vidrio general. listado: vidrio de catalogo (codigo; None conserva
    el actual o toma el general). personalizado: parte del que usaba."""
    _modo(modo, MODOS_LISTA)
    _, w = _vano(u, k, i, j, "ventanas", m)
    if modo == "general":
        return _con_vano(u, k, i, j, "ventanas", m, replace(w, vidrio=GENERAL, vidrio_personalizado=None))
    if modo == "listado":
        cod = codigo or (w.vidrio if w.vidrio in catalogo.vidrios() else _codigo_general(u, "vidrio"))
        if cod not in catalogo.vidrios():
            raise ValueError(f"vidrio desconocido: {cod!r}")
        return _con_vano(u, k, i, j, "ventanas", m, replace(w, vidrio=cod, vidrio_personalizado=None))
    if w.vidrio_personalizado:
        return u
    actual = generales.valor(u, "vidrio") if w.vidrio == GENERAL else w.vidrio
    if isinstance(actual, dict):
        d = dict(actual, nombre=personalizado.inicial("vidrio").get("nombre") or "Vidrio personalizado")
    else:
        base = catalogo.vidrio(actual) if actual in catalogo.vidrios() else None
        d = personalizado.inicial("vidrio", vidrio=base)
    return _con_vano(u, k, i, j, "ventanas", m, replace(w, vidrio_personalizado=d))


def editar_vidrio(u: Unidad, k: int, i: int, j: int, m: int, campo: str, valor) -> Unidad:
    _, w = _vano(u, k, i, j, "ventanas", m)
    if not w.vidrio_personalizado:
        raise ValueError("El vidrio no está personalizado")
    return _con_vano(u, k, i, j, "ventanas", m, replace(w, vidrio_personalizado=dict(w.vidrio_personalizado, **{campo: valor})))


def puerta(u: Unidad, k: int, i: int, j: int, m: int, modo: str, tipo: str | None = None) -> Unidad:
    """general: sigue a la puerta general. listado: tipo de la ficha (None conserva el
    actual o toma el general). personalizado: parte de la general si estaba
    personalizada; si no, de los valores de personalizado.yaml."""
    _modo(modo, MODOS_LISTA)
    _, p = _vano(u, k, i, j, "puertas", m)
    if modo == "general":
        return _con_vano(u, k, i, j, "puertas", m, replace(p, tipo=GENERAL, personalizada=None))
    if modo == "listado":
        if tipo is None:
            tipo = p.tipo if p.tipo not in ("", GENERAL) else _codigo_general(u, "puerta")
        return _con_vano(u, k, i, j, "puertas", m, replace(p, tipo=tipo, personalizada=None))
    if p.personalizada:
        return u
    base = personalizado.defectos("puerta")
    gp = generales.valor(u, "puerta") if p.tipo == GENERAL else None
    d = dict(gp, nombre=base.get("nombre") or "Puerta personalizada") if isinstance(gp, dict) else base
    return _con_vano(u, k, i, j, "puertas", m, replace(p, personalizada=d))


def editar_puerta(u: Unidad, k: int, i: int, j: int, m: int, campo: str, valor) -> Unidad:
    _, p = _vano(u, k, i, j, "puertas", m)
    if not p.personalizada:
        raise ValueError("La puerta no está personalizada")
    return _con_vano(u, k, i, j, "puertas", m, replace(p, personalizada=dict(p.personalizada, **{campo: valor})))
