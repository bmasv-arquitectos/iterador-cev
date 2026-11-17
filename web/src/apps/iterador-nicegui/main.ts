/**
 * Iterador CEV web: la misma interfaz del instalable (NiceGUI) corriendo en el navegador, sin
 * servidor.
 *
 *   1. carga Python (Pyodide) con la herramienta y NiceGUI (py/herramientas.zip y py/nicegui.zip,
 *      npm run python y npm run nicegui), los paquetes que NiceGUI pide a Pyodide (py/nicegui.json)
 *   2. herramientas.web.nicegui_web: iniciar(base) y pagina() -> el HTML de la pagina
 *   3. lo muestra en un iframe que ocupa toda la ventana; dentro, public/puente/socketio_puente.js
 *      conversa con Python por window.__puenteNiceGUI (este archivo) en vez de un websocket
 *   4. cuando la interfaz ya se ve, carga los procesos de calculo (config.json, app.calculo; ?n=2
 *      en la direccion para usar 2). Calcular en la interfaz (herramientas/web/calculo_navegador)
 *      pide el calculo por el canal "calculo": aca se corre repartido (cev/motor.ts) y se avisa
 *      el avance y el resultado a la interfaz.
 */
import config from "../../config.json";
import { calcularRepartido } from "../../cev/motor";
import { Python, type ErrorPython } from "../../python/cliente";
import { GrupoPython } from "../../python/grupo";
import type { ConfigPython } from "../../python/protocolo";
import "./carga.css";

const M = "herramientas.web.nicegui_web";
const C = "herramientas.web.calculo_navegador";

interface InfoNiceGUI {
  pyodide: string[];
  stdlib?: string[];
}
interface Puente {
  emitir(evento: string, datos: unknown): Promise<unknown>;
  subir(cliente: string, elemento: number, archivos: unknown[]): Promise<unknown>;
  escuchar(fn: (texto: string) => void): void;
}
declare global {
  interface Window {
    __puenteNiceGUI?: Puente;
  }
}

const n = Math.max(1, Math.floor(Number(new URLSearchParams(location.search).get("n")) || config.app.calculo));
const $carga = document.getElementById("carga")!;
const $barra = document.getElementById("barra") as HTMLProgressElement;
const $mensaje = document.getElementById("mensaje")!;
const $error = document.getElementById("error")!;

function avance(f: number, m: string): void {
  $barra.value = f;
  $mensaje.textContent = m;
}

/** Procesos de calculo: se crean una vez, cuando la interfaz ya se ve. */
let grupo: GrupoPython | null = null;
function motor(): GrupoPython {
  if (!grupo) {
    const cfg: ConfigPython = {
      pyodide: config.pyodide,
      zip: config.python.zip,
      base: location.href,
      inicio: config.python.inicio,
    };
    grupo = new GrupoPython(n, cfg);
    grupo.listo.then(
      () => console.info(`Motor listo (${n} procesos de calculo)`),
      (ex) => console.error("No se pudo cargar el motor", ex),
    );
  }
  return grupo;
}

function atenderCalculos(py: Python): void {
  py.alAvisar("calculo", async (texto) => {
    const { id, unidad } = JSON.parse(texto) as { id: number; unidad: string };
    const avisar = (f: number, m: string) => {
      void py.llamar(C, "avance", [id, f, m]).catch(() => {});
    };
    try {
      const g = motor();
      avisar(0, `Cargando el motor (${n} procesos; la primera vez tarda unos segundos)`);
      await g.listo;
      const r = await calcularRepartido(g, unidad, avisar);
      await py.llamar(C, "listo", [id, { planilla: r.planilla, segundos: r.segundos }]);
    } catch (ex) {
      const e = ex as ErrorPython;
      console.error(e?.message ?? ex, e?.traza ?? "");
      await py.llamar(C, "fallo", [id, String(e?.message ?? ex)]).catch(() => {});
    }
  });
}

async function principal(): Promise<void> {
  const t0 = performance.now();
  const r = await fetch("py/nicegui.json");
  if (!r.ok) throw new Error("Falta py/nicegui.json: corre npm run nicegui");
  const info = (await r.json()) as InfoNiceGUI;
  const py = new Python(
    {
      pyodide: {
        ...config.pyodide,
        paquetes: [...config.pyodide.paquetes, ...(info.stdlib ?? ["ssl"])],
        opcionales: [...config.pyodide.opcionales, ...info.pyodide],
      },
      zip: config.python.zip,
      zips: ["py/nicegui.zip"],
      base: location.href,
    },
    (f, m) => avance(f * 0.8, m),
  );

  // mensajes de Python al iframe (se guardan hasta que el iframe escucha)
  let oyente: ((texto: string) => void) | null = null;
  const cola: string[] = [];
  py.alAvisar("nicegui", (texto) => (oyente ? oyente(texto) : cola.push(texto)));
  atenderCalculos(py);
  window.__puenteNiceGUI = {
    emitir: (evento, datos) => py.llamar(M, "recibir", [evento, datos ?? null]),
    subir: (cliente, elemento, archivos) => py.llamar(M, "subir", [cliente, elemento, archivos]),
    escuchar: (fn) => {
      oyente = fn;
      for (const t of cola.splice(0)) fn(t);
    },
  };

  await py.listo;
  avance(0.85, "Preparando la interfaz");
  const ini = await py.llamar<{ titulo: string }>(M, "iniciar", [new URL("./", location.href).href]);
  document.title = ini.titulo;
  avance(0.92, "Dibujando la unidad");
  const html = await py.llamar<string>(M, "pagina");
  avance(0.97, "Abriendo");

  const marco = document.createElement("iframe");
  marco.className = "app";
  marco.title = ini.titulo;
  marco.addEventListener(
    "load",
    () => {
      $carga.hidden = true;
      marco.focus();
      console.info(`Iterador CEV web listo en ${((performance.now() - t0) / 1000).toFixed(1)} s`);
      setTimeout(() => motor(), 1500); // los procesos de calculo cargan despues, sin frenar la interfaz
    },
    { once: true },
  );
  marco.srcdoc = html;
  document.body.append(marco);
}

principal().catch((ex) => {
  const e = ex as ErrorPython;
  avance(0, "No se pudo abrir el Iterador CEV");
  $error.textContent = `${e?.message ?? ex}\n\n${e?.traza ?? ""}`;
  $error.hidden = false;
  console.error(ex);
});
