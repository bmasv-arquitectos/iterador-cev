# -*- coding: utf-8 -*-
"""
Barrido del semicírculo y conversión de tramos a obstrucciones (A, B, D).

1. El semicírculo (180° centrados en el azimut del punto) se divide en 5
   divisiones de 36°, numeradas de izquierda a derecha mirando desde adentro.
2. Cada división se recorre en pasos de `paso_grados` (muestras en el centro
   de cada paso). En cada dirección gana el volumen con mayor elevación
   atan((h - z) / r), con r la distancia al primer cruce con su contorno
   (Figura 38: en lo superpuesto manda el de mayor ángulo).
3. Las muestras seguidas con el mismo ganador forman un tramo. Sus bordes se
   afinan por bisección (o son el borde de la división).
4. Por tramo: Pa y Pb son los cruces de los rayos extremos con el volumen.
   B = distancia al punto medio M de la cuerda Pa-Pb (así mide el ejercicio
   MINVU), D = B·(tan(θm - θi) + tan(θf - θm)), A = h - z.
"""
from __future__ import annotations

import math

from .geometria import azimut, contiene, direccion, impacto, relativo
from .modelo import Obstruccion, Omitida, Parametros, ResultadoPunto, a_dict, desde_dict

DIVISIONES = 5
ANCHO_DIVISION = 36.0
BISECCIONES = 40
_TOL_E = 1e-12


class _Escena:
    """Volúmenes que pueden obstruir a un punto."""

    def __init__(self, punto, volumenes):
        self.p = punto
        self.vols = []
        self.avisos = []
        for v in volumenes:
            if len(v.poligono) < 3:
                self.avisos.append(f"{v.id}: el polígono tiene menos de 3 vértices; se ignora.")
            elif contiene(punto.x, punto.y, v.poligono):
                self.avisos.append(f"{v.id}: contiene el punto {punto.id}; se ignora.")
            elif v.h > punto.z:
                self.vols.append(v)

    def _rayo(self, rel):
        return direccion(self.p.azimut + rel)

    def ganador(self, rel):
        """Índice del volumen que manda en la dirección rel, o None."""
        ux, uy = self._rayo(rel)
        mejor = None
        for i, v in enumerate(self.vols):
            imp = impacto(self.p.x, self.p.y, ux, uy, v.poligono)
            if imp is None:
                continue
            t = imp[0]
            e = math.atan2(v.h - self.p.z, t)
            if mejor is None or e > mejor[1] + _TOL_E or (abs(e - mejor[1]) <= _TOL_E and t < mejor[2]):
                mejor = (i, e, t)
        return None if mejor is None else mejor[0]

    def cruce(self, i, rel):
        """Primer cruce del rayo rel con el volumen i: (x, y) o None."""
        ux, uy = self._rayo(rel)
        imp = impacto(self.p.x, self.p.y, ux, uy, self.vols[i].poligono)
        return None if imp is None else (imp[1], imp[2])

    def borde(self, i, fuera, dentro):
        """Ángulo donde i empieza a mandar, entre fuera (no manda) y dentro (manda)."""
        for _ in range(BISECCIONES):
            m = 0.5 * (fuera + dentro)
            if self.ganador(m) == i:
                dentro = m
            else:
                fuera = m
        return dentro


def _tramos(esc, par):
    """[(division, i, theta_i, theta_f, muestra_i, muestra_f)]."""
    n = max(1, round(ANCHO_DIVISION / par.paso_grados))
    s = ANCHO_DIVISION / n
    out = []
    for d in range(DIVISIONES):
        lo = -90.0 + ANCHO_DIVISION * d
        hi = lo + ANCHO_DIVISION
        angs = [lo + (k + 0.5) * s for k in range(n)]
        gan = [esc.ganador(a) for a in angs]
        k = 0
        while k < n:
            g = gan[k]
            if g is None:
                k += 1
                continue
            j = k
            while j + 1 < n and gan[j + 1] == g:
                j += 1
            a = lo if k == 0 else esc.borde(g, angs[k - 1], angs[k])
            b = hi if j == n - 1 else esc.borde(g, angs[j + 1], angs[j])
            out.append((d + 1, g, a, b, angs[k], angs[j]))
            k = j + 1
    return out


def _obstruccion(esc, division, i, a, b, ak, aj):
    p, v = esc.p, esc.vols[i]
    pa = esc.cruce(i, a) or esc.cruce(i, ak)
    pb = esc.cruce(i, b) or esc.cruce(i, aj)
    if pa is None or pb is None:
        return None
    mx, my = 0.5 * (pa[0] + pb[0]), 0.5 * (pa[1] + pb[1])
    dx, dy = mx - p.x, my - p.y
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return None
    tm = min(max(relativo(azimut(dx, dy) - p.azimut), a), b)
    ancho = dist * (math.tan(math.radians(tm - a)) + math.tan(math.radians(b - tm)))
    alto = v.h - p.z
    elev = math.degrees(math.atan(alto / dist))
    abertura = 2 * math.degrees(math.atan(ancho / (2 * dist)))
    return Obstruccion(division=division, volumen=v.id, a=alto, b=dist, d=ancho, theta_i=a, theta_f=b,
                       elevacion=elev, relevancia=(elev / 90.0) * abertura / 180.0, punto_medio=(mx, my))


def _descartar(o, par) -> bool:
    u = par.umbral_descarte
    if par.descarte == "logico":
        return o.d / o.b < u or o.a / o.b < u
    if par.descarte == "literal":
        return (o.d > 0 and o.b / o.d < u) or (o.a > 0 and o.b / o.a < u)
    return False


def calcular_punto(punto, volumenes, parametros: Parametros | None = None) -> ResultadoPunto:
    par = parametros or Parametros()
    par.validar()
    esc = _Escena(punto, volumenes)
    obs, omit = [], []
    for tr in _tramos(esc, par):
        o = _obstruccion(esc, *tr)
        if o is None:
            continue
        if o.theta_f - o.theta_i < par.ancho_min_grados:
            omit.append(Omitida(o, "angosto"))
        elif _descartar(o, par):
            omit.append(Omitida(o, "descarte"))
        else:
            obs.append(o)
    if par.maximo is not None and len(obs) > par.maximo:
        orden = sorted(obs, key=lambda o: (-o.relevancia, -o.elevacion))
        quedan = {id(o) for o in orden[:par.maximo]}
        omit.extend(Omitida(o, "maximo") for o in orden[par.maximo:])
        esc.avisos.append(f"{punto.id}: {len(obs)} obstrucciones; se conservan las {par.maximo} más relevantes.")
        obs = [o for o in obs if id(o) in quedan]
    return ResultadoPunto(punto.id, tuple(obs), tuple(omit), tuple(esc.avisos))


def calcular(puntos, volumenes, parametros: Parametros | None = None) -> tuple:
    return tuple(calcular_punto(p, volumenes, parametros) for p in puntos)


def calcular_json(datos: dict) -> dict:
    """JSON de entrada (dict) -> JSON de salida (dict)."""
    puntos, vols, par = desde_dict(datos)
    return a_dict(calcular(puntos, vols, par))


def tabla(resultado: ResultadoPunto) -> str:
    """Texto legible de un resultado."""
    lin = [f"Punto {resultado.punto}",
           f"  {'Div':>3}  {'Volumen':<16}{'A':>7}{'B':>8}{'D':>8}{'Elev':>7}{'Relev':>9}"]
    for o in resultado.obstrucciones:
        lin.append(f"  {o.division:>3}  {o.volumen:<16}{o.a:>7.1f}{o.b:>8.1f}{o.d:>8.1f}"
                   f"{o.elevacion:>7.1f}{o.relevancia:>9.5f}")
    if not resultado.obstrucciones:
        lin.append("  (sin obstrucciones)")
    for m in resultado.omitidas:
        o = m.obstruccion
        lin.append(f"  omitida ({m.motivo}): división {o.division}, {o.volumen}, "
                   f"A {o.a:.1f} B {o.b:.1f} D {o.d:.1f}")
    lin.extend(f"  aviso: {a}" for a in resultado.avisos)
    return "\n".join(lin)
