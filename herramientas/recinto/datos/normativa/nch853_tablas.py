"""
Tablas de la NCh 853:2021 (valores que cambian con la norma).
Fuente: NCh853 Tabla 7 (resistencias superficiales), Tabla 8 (cámaras de aire),
Anexo F Tabla F.1 (corrección por huecos).
"""

# Tabla 7 NCh853 — Resistencias superficiales [m²K/W]
# Indexado por dirección del flujo de calor.
RES_SUPERFICIAL = {
    "ascendente":  {"Rsi": 0.10, "Rse": 0.04},
    "horizontal":  {"Rsi": 0.13, "Rse": 0.04},
    "descendente": {"Rsi": 0.17, "Rse": 0.04},
}

# Mapeo: tipo de elemento → dirección de flujo de calor
FLUJO_POR_TIPO = {
    "muro":           "horizontal",
    "techumbre":      "ascendente",
    "piso_ventilado": "descendente",
    "puerta":         "horizontal",
}

# Tabla 8 NCh853 — R de cámara de aire NO ventilada (alta emisividad) [m²K/W]
# {espesor_mm: {dirección: R}}
CAMARA_AIRE_NV = {
    0:   {"ascendente": 0.00, "horizontal": 0.00, "descendente": 0.00},
    5:   {"ascendente": 0.11, "horizontal": 0.11, "descendente": 0.11},
    7:   {"ascendente": 0.13, "horizontal": 0.13, "descendente": 0.13},
    10:  {"ascendente": 0.15, "horizontal": 0.15, "descendente": 0.15},
    15:  {"ascendente": 0.16, "horizontal": 0.17, "descendente": 0.17},
    25:  {"ascendente": 0.16, "horizontal": 0.18, "descendente": 0.19},
    50:  {"ascendente": 0.16, "horizontal": 0.18, "descendente": 0.21},
    100: {"ascendente": 0.16, "horizontal": 0.18, "descendente": 0.22},
    300: {"ascendente": 0.16, "horizontal": 0.18, "descendente": 0.23},
}

# Tabla F.1 NCh853 — Corrección por huecos ΔU'' [W/m²K]
DELTA_U_NIVEL = {0: 0.00, 1: 0.01, 2: 0.04}


def R_camara_aire(espesor_mm: float, flujo: str) -> float:
    """R de una cámara de aire no ventilada, con interpolación lineal (NOTA Tabla 8)."""
    esp = sorted(CAMARA_AIRE_NV.keys())
    if espesor_mm <= esp[0]:
        return CAMARA_AIRE_NV[esp[0]][flujo]
    if espesor_mm >= esp[-1]:
        return CAMARA_AIRE_NV[esp[-1]][flujo]
    for i in range(len(esp) - 1):
        e0, e1 = esp[i], esp[i + 1]
        if e0 <= espesor_mm <= e1:
            r0 = CAMARA_AIRE_NV[e0][flujo]
            r1 = CAMARA_AIRE_NV[e1][flujo]
            return r0 + (r1 - r0) * (espesor_mm - e0) / (e1 - e0)
    return 0.0
