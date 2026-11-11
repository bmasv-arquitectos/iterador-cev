# Avisos

## Uso referencial

Iterador CEV es una herramienta de diseño y docencia. Sus resultados no tienen validez legal
ni reemplazan la Calificación Energética de Viviendas oficial, que solo puede emitir un
evaluador acreditado con las herramientas del Ministerio de Vivienda y Urbanismo (MINVU).
Los archivos que exporta (ficha 01, reporte, resultados) están marcados como referenciales.

El proyecto no está afiliado al MINVU ni cuenta con su respaldo.

## Plantillas y metodología del MINVU

La herramienta PBTD v2.2, sus planillas, sus tablas y la metodología de cálculo pertenecen al
MINVU y **no están cubiertas por la licencia AGPL-3.0** de este repositorio. En particular:

- la planilla «01. Datos de Arquitectura» (`herramientas/fichas_cev/bases/`) se incluye sin
  modificar, solo para que la herramienta pueda entregar la ficha 01 llenada con la unidad;
- los datos de `herramientas/motor_cev/motor_py/datos/` (clima, perfiles de uso y demás
  constantes) están tomados de las planillas PBTD, para que el motor pueda calcular sin ellas.

## Software de terceros

El instalador incluye, entre otras, estas bibliotecas, cada una con su propia licencia:
Python (PSF), NiceGUI (MIT), pywebview (BSD), pythonnet (MIT), numba y llvmlite (BSD),
NumPy (BSD), Shapely (BSD), PyMuPDF (AGPL-3.0), openpyxl (MIT), ReportLab (BSD), pypdf (BSD)
y PyYAML (MIT).

## Nombre

«Iterador CEV» y la identidad gráfica del programa son de B+V Arquitectos. Un fork puede usar
el código según la licencia, pero debe distribuirse con otro nombre para no confundirse con
la versión original.
