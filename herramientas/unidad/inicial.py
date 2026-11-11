# -*- coding: utf-8 -*-
"""
Unidad con la que abre el editor (y Cargar > Recinto): el rectangulo de
config/editor.yaml (inicial:) con sus vanos (inicial.vanos: tipo, lado, x, z,
ancho, alto). El vidrio de las ventanas es alzado.vidrio_defecto.
"""
from __future__ import annotations

from . import editor
from .modelo import Unidad


def unidad(cfg: dict | None = None) -> Unidad:
    cfg = cfg or editor.config()
    u = editor.unidad_inicial(cfg)
    vidrio = (cfg.get("alzado") or {}).get("vidrio_defecto", "")
    for v in cfg["inicial"].get("vanos") or ():
        tipo, lado = v["tipo"], int(v.get("lado", 0))
        x, z = float(v["x"]), float(v.get("z", 0.0))
        try:
            largo = editor.largo_tramo(u.niveles[0], lado, 0)
            w = editor.vano_desde_esquinas(tipo, (x, z), (x + float(v["ancho"]), z + float(v["alto"])),
                                           largo, u.altura, vidrio)
            u = editor.agregar_vano(u, 0, lado, 0, tipo, w)
        except (ValueError, IndexError) as ex:
            print(f"editor.yaml inicial.vanos: se omite {v} ({ex})", flush=True)
    return u
