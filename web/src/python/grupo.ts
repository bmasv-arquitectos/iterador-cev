/**
 * Varios workers de Python para repartir trabajo en paralelo (por ejemplo los 10 casos del
 * motor). Cada worker carga su propio Pyodide (100-200 MB de memoria): conviene 2 a 4.
 *
 *   const g = new GrupoPython(4, config);
 *   await g.listo;
 *   await g.enTodos("modulo", "preparar", [x]);                 // la misma llamada en cada uno
 *   const r = await Promise.all(casos.map((c) => g.llamar("modulo", "funcion", [c])));
 *
 * llamar() espera un worker libre, en orden de llegada. enTodos() espera que esten todos
 * libres y los ocupa mientras tanto (no llamar dos enTodos a la vez). Generico.
 */
import { Python, type Avance } from "./cliente";
import type { ConfigPython, InicioPython } from "./protocolo";

export class GrupoPython {
  readonly listo: Promise<InicioPython[]>;
  private trabajadores: Python[];
  private libres: Python[];
  private fila: Array<(p: Python) => void> = [];

  constructor(n: number, config: ConfigPython, alAvanzar?: Avance) {
    this.trabajadores = Array.from({ length: Math.max(1, n) }, (_, i) =>
      new Python(config, i === 0 ? alAvanzar : undefined),
    );
    this.libres = [...this.trabajadores];
    this.listo = Promise.all(this.trabajadores.map((p) => p.listo));
  }

  get tamano(): number {
    return this.trabajadores.length;
  }

  async llamar<T = unknown>(
    modulo: string,
    funcion: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {},
    alAvanzar?: Avance,
  ): Promise<T> {
    const p = await this.tomar();
    try {
      return await p.llamar<T>(modulo, funcion, args, kwargs, alAvanzar);
    } finally {
      this.soltar(p);
    }
  }

  async enTodos<T = unknown>(
    modulo: string,
    funcion: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {},
  ): Promise<T[]> {
    await this.listo;
    const tomados: Python[] = [];
    for (let i = 0; i < this.trabajadores.length; i++) tomados.push(await this.tomar());
    try {
      return await Promise.all(tomados.map((p) => p.llamar<T>(modulo, funcion, args, kwargs)));
    } finally {
      for (const p of tomados) this.soltar(p);
    }
  }

  cerrar(): void {
    for (const p of this.trabajadores) p.cerrar();
  }

  private tomar(): Promise<Python> {
    const p = this.libres.pop();
    return p ? Promise.resolve(p) : new Promise((ok) => this.fila.push(ok));
  }

  private soltar(p: Python): void {
    const siguiente = this.fila.shift();
    if (siguiente) siguiente(p);
    else this.libres.push(p);
  }
}
