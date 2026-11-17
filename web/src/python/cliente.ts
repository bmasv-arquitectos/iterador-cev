/**
 * Python en un worker, visto desde la pagina:
 *
 *   const py = new Python(config, (f, m) => ...);      // carga en segundo plano
 *   await py.listo;                                     // InicioPython
 *   const r = await py.llamar("herramientas.web.api", "info");
 *   py.alAvisar("canal", (texto) => ...);               // lo que Python manda con canal_js.enviar
 *
 * Cada llamada puede recibir su propio avance (fraccion, mensaje). Generico.
 */
import type { ConfigPython, InicioPython, Pedido, Respuesta, SinId } from "./protocolo";

export type Avance = (fraccion: number, mensaje: string) => void;

export class ErrorPython extends Error {
  constructor(
    mensaje: string,
    public traza?: string,
  ) {
    super(mensaje);
    this.name = "ErrorPython";
  }
}

interface Pendiente {
  ok: (v: unknown) => void;
  mal: (e: Error) => void;
  avanzar?: Avance;
}

export class Python {
  readonly listo: Promise<InicioPython>;
  private trabajador: Worker;
  private siguiente = 1;
  private pendientes = new Map<number, Pendiente>();
  private oyentes = new Map<string, (datos: string) => void>();

  constructor(config: ConfigPython, alAvanzar?: Avance) {
    this.trabajador = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    this.trabajador.addEventListener("message", (e: MessageEvent<Respuesta>) => this.recibir(e.data));
    this.trabajador.addEventListener("error", (e) =>
      this.fallarTodo(new ErrorPython(e.message || "el worker de Python fallo")),
    );
    this.listo = this.pedir<InicioPython>({ tipo: "iniciar", config }, alAvanzar);
  }

  async llamar<T = unknown>(
    modulo: string,
    funcion: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {},
    alAvanzar?: Avance,
  ): Promise<T> {
    await this.listo;
    return this.pedir<T>({ tipo: "llamar", modulo, funcion, args, kwargs }, alAvanzar);
  }

  /** Lo que Python manda por ese canal (canal_js.enviar), en orden. */
  alAvisar(canal: string, fn: (datos: string) => void): void {
    this.oyentes.set(canal, fn);
  }

  cerrar(): void {
    this.trabajador.terminate();
    this.fallarTodo(new ErrorPython("Python cerrado"));
  }

  private pedir<T>(p: SinId<Pedido>, avanzar?: Avance): Promise<T> {
    const id = this.siguiente++;
    return new Promise<T>((ok, mal) => {
      this.pendientes.set(id, { ok: ok as (v: unknown) => void, mal, avanzar });
      this.trabajador.postMessage({ ...p, id } as Pedido);
    });
  }

  private recibir(r: Respuesta): void {
    if (r.tipo === "aviso") {
      this.oyentes.get(r.canal)?.(r.datos);
      return;
    }
    const p = this.pendientes.get(r.id);
    if (!p) return;
    if (r.tipo === "progreso") {
      p.avanzar?.(r.fraccion, r.mensaje);
      return;
    }
    this.pendientes.delete(r.id);
    if (r.tipo === "listo") p.ok(r.valor);
    else p.mal(new ErrorPython(r.error, r.traza));
  }

  private fallarTodo(e: Error): void {
    for (const p of this.pendientes.values()) p.mal(e);
    this.pendientes.clear();
  }
}
