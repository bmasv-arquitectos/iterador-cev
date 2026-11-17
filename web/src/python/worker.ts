/**
 * Worker con Python (Pyodide): carga Pyodide, sus librerias y el paquete herramientas (un zip
 * que arma `npm run python`) y otros zips (config.zips), ofrece a Python los modulos de
 * modulos_js.ts y canal_js, hace las llamadas de inicio de la configuracion y responde llamadas
 * a herramientas.web.puente.llamar (tambien a funciones async: se esperan).
 *
 *   canal_js.enviar(canal, texto)   Python avisa algo a la pagina sin que se lo pidan
 *                                   (Respuesta "aviso"; Python.alAvisar en cliente.ts)
 *
 * Corre aparte de la pagina: un calculo largo no congela la interfaz. Generico.
 */
import { aJson, desdeJson } from "./json";
import { MODULOS_JS } from "./modulos_js";
import type { ConfigPython, InicioPython, Pedido, Respuesta } from "./protocolo";

// tipos minimos del worker (sin la libreria WebWorker de TypeScript, que choca con DOM)
const ctx = self as unknown as {
  postMessage(m: Respuesta): void;
  addEventListener(t: "message", f: (e: MessageEvent<Pedido>) => void): void;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let py: any = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let llamarPy: any = null;

function enviar(r: Respuesta): void {
  ctx.postMessage(r);
}

const CANAL_JS = {
  enviar: (canal: string, datos: string) => enviar({ id: 0, tipo: "aviso", canal: String(canal), datos: String(datos) }),
};

async function descomprimir(ruta: string, base: string, aviso: string): Promise<void> {
  const r = await fetch(new URL(ruta, base));
  if (!r.ok) throw new Error(`No se pudo descargar ${ruta} (${r.status}): ${aviso}`);
  py.unpackArchive(await r.arrayBuffer(), "zip");
}

async function iniciar(id: number, cfg: ConfigPython): Promise<InicioPython> {
  const avanzar = (f: number, m: string) => enviar({ id, tipo: "progreso", fraccion: f, mensaje: m });
  const segundos: Record<string, number> = {};
  let t0 = performance.now();
  const marca = (clave: string) => {
    segundos[clave] = Math.round((performance.now() - t0) / 10) / 100;
    t0 = performance.now();
  };

  avanzar(0.02, "Cargando Python (Pyodide)");
  const { loadPyodide } = await import(/* @vite-ignore */ `${cfg.pyodide.url}pyodide.mjs`);
  py = await loadPyodide({ indexURL: cfg.pyodide.url });
  for (const [nombre, modulo] of Object.entries(MODULOS_JS)) py.registerJsModule(nombre, modulo);
  py.registerJsModule("canal_js", CANAL_JS);
  marca("pyodide");

  avanzar(0.35, "Cargando librerias");
  await py.loadPackage(cfg.pyodide.paquetes);
  marca("paquetes");
  const micropip = py.pyimport("micropip");
  if (cfg.pyodide.pip.length) await micropip.install(cfg.pyodide.pip);
  marca("pip");
  const faltan: string[] = [];
  for (const p of cfg.pyodide.opcionales) {
    try {
      await micropip.install(p);
    } catch {
      faltan.push(p);
    }
  }
  marca("opcionales");

  avanzar(0.75, "Cargando la herramienta");
  await descomprimir(cfg.zip, cfg.base, "corre npm run python");
  for (const z of cfg.zips ?? []) await descomprimir(z, cfg.base, "corre npm run nicegui");
  py.runPython("import importlib; importlib.invalidate_caches()");
  llamarPy = py.pyimport("herramientas.web.puente").llamar;
  marca("herramienta");

  if (cfg.inicio?.length) {
    avanzar(0.9, "Preparando");
    for (const ll of cfg.inicio) {
      llamarPy(ll.modulo, ll.funcion, JSON.stringify(aJson(ll.args ?? [])), "{}", null);
    }
    marca("inicio");
  }

  avanzar(1, "Listo");
  const python = String(py.runPython("import sys; sys.version.split()[0]"));
  return { python, pyodide: String(py.version), faltan, segundos };
}

async function llamar(p: Extract<Pedido, { tipo: "llamar" }>): Promise<unknown> {
  if (!llamarPy) throw new Error("Python todavia no esta listo");
  const avanzar = (f: number, m: string) => enviar({ id: p.id, tipo: "progreso", fraccion: f, mensaje: m });
  let r: unknown = llamarPy(
    p.modulo,
    p.funcion,
    JSON.stringify(aJson(p.args)),
    JSON.stringify(aJson(p.kwargs)),
    avanzar,
  );
  if (typeof r !== "string") {
    // funcion async: Python devolvio una corrutina, que se espera como una promesa
    const proxy = r as { destroy?: () => void };
    r = await (r as Promise<string>);
    proxy.destroy?.();
  }
  return desdeJson(JSON.parse(r as string));
}

ctx.addEventListener("message", async (e) => {
  const p = e.data;
  try {
    const valor = p.tipo === "iniciar" ? await iniciar(p.id, p.config) : await llamar(p);
    enviar({ id: p.id, tipo: "listo", valor });
  } catch (ex) {
    const err = ex as { message?: string; stack?: string };
    enviar({ id: p.id, tipo: "error", error: String(err?.message ?? ex), traza: err?.stack });
  }
});
