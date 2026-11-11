# Iterador CEV

Herramienta para iterar la envolvente de una vivienda y estimar su **calificación energética
pasiva (CEV)** mientras se diseña. Se dibuja la unidad en planta, alzado y 3D, se definen
soluciones constructivas, ventanas, protecciones solares, obstrucciones y el entorno, y se
obtiene la letra, el ahorro y la demanda con un motor en Python que reproduce la metodología
PBTD v2.2, sin Excel.

> **Uso referencial.** No tiene validez legal ni reemplaza la calificación oficial, que solo
> puede emitir un evaluador acreditado con las herramientas del MINVU.

## Descargar (Windows 10 y 11)

En [Releases](../../releases) está el instalador. No necesita permisos de administrador ni
Python. Como el instalador no está firmado, Windows SmartScreen muestra un aviso: «Más
información» > «Ejecutar de todas formas».

## Qué hace

- Editor de la unidad: muros exteriores y adiabáticos, varios niveles, tabiques, ventanas y
  puertas, techos y pisos, con vista en planta, alzado y 3D.
- Soluciones constructivas por elemento o generales, vidrios y puertas de listado o
  personalizados.
- Protecciones solares (FAV1, FAV2, FAV3), obstrucciones dibujadas, balcones (P04) y
  volúmenes del entorno para las obstrucciones remotas (FAR).
- Cálculo de la calificación: letra, ahorro y demanda de calefacción y refrigeración.
- Exporta la ficha 01 (.xlsm) llenada con la unidad, un reporte PDF, los resultados (.zip)
  y la etiqueta (.png). Todo marcado como referencial.

## Desde el código

Con Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m herramientas.app_unidad
```

Se abre en el navegador (http://127.0.0.1:8082). El instalador de Windows se arma como se
explica en [`distribucion/LEEME.md`](distribucion/LEEME.md).

Este repositorio trae solo lo necesario para usar la herramienta.

| Carpeta | Contenido |
|---|---|
| `herramientas/unidad` | modelo de la unidad, geometría, traducción a la ficha 01, vistas y reporte |
| `herramientas/app_unidad` | la interfaz (NiceGUI); apariencia en `estilo.css` |
| `herramientas/motor_cev/motor_py` | motor de cálculo y planilla 03 en Python |
| `herramientas/far` | obstrucciones remotas dibujadas |
| `herramientas/recinto` | soluciones constructivas, vidrios y zonas térmicas |
| `herramientas/comun` | rutas, tareas y configuración de la distribución |
| `herramientas/fichas_cev` | escritura de la ficha 01 y plantilla oficial |
| `distribucion` | ejecutable e instalador de Windows |

Casi todo lo modificable (textos, colores, medidas y opciones) está en archivos `.yaml` y en
`estilo.css`, no en el código.

## Errores e ideas

Son bienvenidos en [Issues](../../issues). Por ahora el proyecto **no acepta contribuciones de
código** (ver [CONTRIBUTING.md](CONTRIBUTING.md)); los forks están permitidos bajo la licencia.

## Licencia

[GNU AGPL-3.0](LICENSE). La plantilla PBTD y la metodología pertenecen al MINVU: ver
[NOTICE.md](NOTICE.md).

## Créditos

B+V Arquitectos · Lucas Vásquez Gimeno · Eloy Bahamondes Estévez
