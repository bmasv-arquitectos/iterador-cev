# Iterador CEV en el navegador

La misma interfaz del instalable (NiceGUI) corriendo completa en el navegador de quien la usa,
sin servidor: Python con [Pyodide](https://pyodide.org) en workers. La unidad no se envia a
ningun servidor.

- `herramientas/web/`: lo que necesita el navegador (puente con JavaScript, NiceGUI sin
  websocket, motor repartido, calculo y reporte para imprimir).
- `web/`: el sitio (Vite + TypeScript): workers de Python, el bucle de la simulacion en
  JavaScript (`nucleo/nucleo.ts`, mismo resultado que el motor Python) y el puente que
  reemplaza al websocket de NiceGUI (`public/puente/socketio_puente.js`).

## Armar el sitio

Con Python 3.12 y Node 22 (los comandos `npm` van dentro de `web/`):

```powershell
py -3.12 -m venv .venv-web
.\.venv-web\Scripts\Activate.ps1
pip install -r web\requirements-web.txt
cd web
npm ci
npm run python      # public/py/herramientas.zip: el Python de la herramienta (archivos versionados)
npm run nicegui     # public/py/nicegui.zip y public/ng: NiceGUI para el navegador
npm run dev         # prueba: http://localhost:5173
npm run build       # el sitio en web/dist (estatico, rutas relativas)
```

`dist/` se publica tal cual en cualquier carpeta de un sitio. En este repositorio lo publica
GitHub Pages con cada version (`.github/workflows/pages.yml`). La primera visita descarga
Pyodide de su CDN (jsdelivr) y unos 40 MB del sitio; las siguientes usan la cache del
navegador.

No se versionan: `node_modules/`, `dist/`, `public/py/`, `public/ng/` y `public/iconos/`.
