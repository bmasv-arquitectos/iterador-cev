# -*- coding: utf-8 -*-
"""
Los rangos de la ficha 01 que lee calculo() del motor oficial en cada caso, y la celda del
caso. importar_datos() fija '0. Datos Arq Motor'!C33 = caso y copia estos cinco rangos;
datos_caso() los pega en el motor (entre parentesis, donde). El motor Python arma los mismos
rangos (motor.py) y calculo_py los lee.
"""
HOJA_ARQ = "0. Datos Arq Motor"
HOJA_CLIMA = "0. Datos Clima Motor"
CELDA_CASO = "C33"

# clave -> (hoja de la ficha, rango) ; destino en el motor entre parentesis
RANGOS = {
    "clima": (HOJA_CLIMA, "E9:Y386"),        # (Datos!E9:Y386, bloques de 26 filas cada 32)
    "arq": (HOJA_ARQ, "B2:O29"),             # (Calculo!B2:O29)
    "masa": (HOJA_ARQ, "AH7:AJ18"),          # (SA!P34:R45)
    "sa_libre": (HOJA_ARQ, "X9:AF32"),       # (SA!F36:N59)
    "sa_clima": (HOJA_ARQ, "X36:AF59"),      # (SA!F64:N87)
}
