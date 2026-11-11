"""
Tablas de transmitancia U máxima [W/m²K] por zona y componente.
- Tabla 1  → uso residencial (norma, Numeral 1)
- Tabla 10 → equipamiento educación/salud y hoteles (norma, Numeral 2)
"""

U_MAX_RESIDENCIAL = {
    "A": {"techumbre": 0.84, "muro": 2.10, "piso_ventilado": 3.60, "puerta": None},
    "B": {"techumbre": 0.47, "muro": 0.80, "piso_ventilado": 0.70, "puerta": 1.70},
    "C": {"techumbre": 0.47, "muro": 0.80, "piso_ventilado": 0.87, "puerta": 1.70},
    "D": {"techumbre": 0.38, "muro": 0.80, "piso_ventilado": 0.60, "puerta": 1.70},
    "E": {"techumbre": 0.33, "muro": 0.60, "piso_ventilado": 0.60, "puerta": 1.70},
    "F": {"techumbre": 0.28, "muro": 0.45, "piso_ventilado": 0.50, "puerta": 1.70},
    "G": {"techumbre": 0.28, "muro": 0.40, "piso_ventilado": 0.39, "puerta": 1.70},
    "H": {"techumbre": 0.25, "muro": 0.30, "piso_ventilado": 0.32, "puerta": 1.70},
    "I": {"techumbre": 0.25, "muro": 0.35, "piso_ventilado": 0.32, "puerta": 1.70},
}

U_MAX_EQUIPAMIENTO = {
    "A": {"techumbre": 0.84, "muro": 2.00, "piso_ventilado": 3.60, "puerta": None},
    "B": {"techumbre": 0.47, "muro": 0.80, "piso_ventilado": 0.70, "puerta": 1.70},
    "C": {"techumbre": 0.47, "muro": 0.80, "piso_ventilado": 0.87, "puerta": 1.70},
    "D": {"techumbre": 0.38, "muro": 0.60, "piso_ventilado": 0.60, "puerta": 1.70},
    "E": {"techumbre": 0.33, "muro": 0.60, "piso_ventilado": 0.60, "puerta": 1.70},
    "F": {"techumbre": 0.28, "muro": 0.45, "piso_ventilado": 0.50, "puerta": 1.70},
    "G": {"techumbre": 0.28, "muro": 0.40, "piso_ventilado": 0.39, "puerta": 1.70},
    "H": {"techumbre": 0.25, "muro": 0.30, "piso_ventilado": 0.32, "puerta": 1.70},
    "I": {"techumbre": 0.25, "muro": 0.35, "piso_ventilado": 0.32, "puerta": 1.70},
}

# Selector por tipo de uso
U_MAX_POR_USO = {
    "residencial":  U_MAX_RESIDENCIAL,
    "equipamiento": U_MAX_EQUIPAMIENTO,
}
