/**
 * Mensajes entre la pagina y el worker de Python (worker.ts). Generico: no sabe de CEV.
 */

export interface ConfigPyodide {
  url: string; // carpeta de Pyodide (termina en /)
  paquetes: string[]; // de la distribucion de Pyodide (loadPackage)
  pip: string[]; // con micropip (obligatorios)
  opcionales: string[]; // con micropip; si fallan se avisa y se sigue
}

/** Una llamada a Python que el worker hace al terminar de cargar (por ejemplo, activar el
 * nucleo en JavaScript). */
export interface LlamadaInicio {
  modulo: string;
  funcion: string;
  args?: unknown[];
}

export interface ConfigPython {
  pyodide: ConfigPyodide;
  zip: string; // paquete herramientas (npm run python), relativo a base
  zips?: string[]; // otros zips que se descomprimen despues (por ejemplo NiceGUI y sus dependencias)
  base: string; // direccion de la pagina
  inicio?: LlamadaInicio[];
}

export interface InicioPython {
  python: string;
  pyodide: string;
  faltan: string[]; // opcionales que no se pudieron instalar
  segundos: Record<string, number>; // tiempo de cada paso de la carga
}

export type Pedido =
  | { id: number; tipo: "iniciar"; config: ConfigPython }
  | {
      id: number;
      tipo: "llamar";
      modulo: string;
      funcion: string;
      args: unknown[];
      kwargs: Record<string, unknown>;
    };

/** aviso: Python avisa algo sin que se lo pidan (canal_js.enviar(canal, texto)); id 0. */
export type Respuesta =
  | { id: number; tipo: "progreso"; fraccion: number; mensaje: string }
  | { id: number; tipo: "listo"; valor: unknown }
  | { id: number; tipo: "error"; error: string; traza?: string }
  | { id: number; tipo: "aviso"; canal: string; datos: string };

export type SinId<T> = T extends unknown ? Omit<T, "id"> : never;
