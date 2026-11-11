# -*- coding: utf-8 -*-
"""Entrada del estudiante: un departamento de un piso, planta rectangular."""
from __future__ import annotations

from dataclasses import dataclass, field

PISOS = ("adiabatico", "terreno", "ventilado")
TECHOS = ("adiabatico", "exterior")
# Componentes personalizables UNA vez por recinto. El vidrio se personaliza
# por fachada (Fachada.vidrio_personalizado).
PERSONALIZABLES = ("muro", "techo", "piso")


@dataclass(frozen=True)
class Proteccion:
    """Protecciones solares de la ventana (Manual CEV 6.7.3)."""
    alero_l: float = 0.0            # FAV1 L: largo desde el plomo del muro
    alero_d: float | None = None    # FAV1 D: None -> config
    aleta_izq_p: float = 0.0        # FAV2 P izquierda (vista desde el interior)
    aleta_der_p: float = 0.0        # FAV2 P derecha
    aleta_s: float | None = None    # FAV2 S: None -> config
    celosia_e: float = 0.0          # FAV3 E: largo de lama en corte
    celosia_t: float = 0.0          # FAV3 T: separacion entre lamas
    celosia_beta: float = 0.0       # FAV3 beta (0 perpendicular, 90 paralela)
    # Aislacion del encuentro alero/aletas-muro (P04), texto de la lista
    # Aislacion_Terraza de la ficha. None -> config/ficha01.yaml
    p04_aislacion: str | None = None

    def __post_init__(self):
        for n in ("alero_l", "aleta_izq_p", "aleta_der_p", "celosia_e", "celosia_t"):
            if getattr(self, n) < 0:
                raise ValueError(f"{n} no puede ser negativo")
        if not 0 <= self.celosia_beta <= 90:
            raise ValueError("celosia_beta debe estar entre 0 y 90")


@dataclass(frozen=True)
class Fachada:
    exterior: bool = True
    vidrio_pct: float = 0.0         # % del area bruta del muro (0-100)
    proteccion: Proteccion = field(default_factory=Proteccion)
    vidrio: str = ""                # codigo de datos/vidrios.yaml
    # Vidrio propio ya validado (recinto/personalizado.py); reemplaza a 'vidrio'
    vidrio_personalizado: dict | None = None

    def __post_init__(self):
        if not 0 <= self.vidrio_pct <= 100:
            raise ValueError("vidrio_pct debe estar entre 0 y 100")
        if not self.exterior and self.vidrio_pct > 0:
            raise ValueError("una fachada adiabatica no puede tener ventana")


@dataclass(frozen=True)
class Recinto:
    comuna: str
    largo: float                    # interior, frente y atras [m]
    ancho: float                    # interior, izquierda y derecha [m]
    altura: float                   # libre, piso a cielo [m]
    azimut: float                   # azimut del frente [grados]
    fachadas: tuple                 # 4 x Fachada, orden f1..f4
    piso: str = "adiabatico"
    techo: str = "adiabatico"
    dormitorios: int = 2
    zona: str | None = None         # None -> unica opcion de la comuna
    # Muro, techo y piso personalizados ya validados (recinto/personalizado.py),
    # solo los que aplican: {elemento: {clave: valor}}
    personalizados: dict = field(default_factory=dict)

    def __post_init__(self):
        if len(self.fachadas) != 4:
            raise ValueError("se necesitan 4 fachadas")
        if self.piso not in PISOS:
            raise ValueError(f"piso debe ser uno de {PISOS}")
        if self.techo not in TECHOS:
            raise ValueError(f"techo debe ser uno de {TECHOS}")
        if min(self.largo, self.ancho, self.altura) <= 0:
            raise ValueError("dimensiones deben ser positivas")
        if self.dormitorios < 0:
            raise ValueError("dormitorios no puede ser negativo")
        extra = set(self.personalizados) - set(PERSONALIZABLES)
        if extra:
            raise ValueError(f"componentes personalizables desconocidos: {sorted(extra)}")
