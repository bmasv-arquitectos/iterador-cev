/**
 * El motor CEV en el navegador, repartido en varios workers de Python (F2). Usa
 * herramientas/web/motor_web.py:
 *   1. preparar(unidad) en todos los workers (ficha 01 virtual, datos del motor, lo comun);
 *   2. casos(unidad, [caso]) una llamada por caso: el grupo las reparte entre los workers;
 *   3. planilla(unidad, bloques) en uno: letra, ahorros, demandas y huella del resumen.
 * El bucle de la simulacion corre en JavaScript si los workers lo activaron
 * (motor_web.usar_nucleo_js, en las llamadas de inicio de config.json).
 */
import type { Avance } from "../python/cliente";
import type { GrupoPython } from "../python/grupo";

export const MODULO = "herramientas.web.motor_web";
export const CASOS = Array.from({ length: 10 }, (_, i) => i + 1);

export interface Preparado {
  comuna: string;
  zona: string;
  tipo_vivienda: string | null;
  avisos: string[];
  tiempos: Record<string, number>;
}

export interface Caso {
  filas: unknown[];
  dpm: number;
  t: number;
  t_modulos: number;
  t_calculo: number;
  t_nucleo: number;
  sin_calcular: string[];
  d56?: number;
}

export interface Planilla {
  resumen: Record<string, unknown>;
  base_cal: unknown;
  base_ref: unknown;
  texto: string;
  huella: string;
  t: number;
  sin_calcular: string[];
}

export interface Calculo {
  planilla: Planilla;
  preparados: Preparado[];
  casos: Record<string, Caso>;
  segundos: { preparar: number; casos: number; planilla: number; total: number };
}

export interface Ficha01 {
  nombre: string;
  datos: Uint8Array;
  avisos: string[];
}

export async function calcularRepartido(
  grupo: GrupoPython,
  unidad: string,
  avanzar: Avance = () => {},
): Promise<Calculo> {
  const t0 = performance.now();
  avanzar(0.02, `Preparando la unidad en ${grupo.tamano} procesos`);
  const preparados = await grupo.enTodos<Preparado>(MODULO, "preparar", [unidad]);
  const t1 = performance.now();
  let hechos = 0;
  avanzar(0.1, `Calculando ${CASOS.length} casos en ${grupo.tamano} procesos`);
  const partes = await Promise.all(
    CASOS.map(async (caso) => {
      const r = await grupo.llamar<Record<string, Caso>>(MODULO, "casos", [unidad, [caso]]);
      hechos++;
      avanzar(0.1 + (0.8 * hechos) / CASOS.length, `Casos listos: ${hechos} de ${CASOS.length}`);
      return r;
    }),
  );
  const casos: Record<string, Caso> = Object.assign({}, ...partes);
  const t2 = performance.now();
  avanzar(0.92, "Planilla 03");
  const planilla = await grupo.llamar<Planilla>(MODULO, "planilla", [unidad, casos]);
  const t3 = performance.now();
  avanzar(1, "Listo");
  const s = (a: number, b: number) => Math.round(b - a) / 1000;
  return {
    planilla,
    preparados,
    casos,
    segundos: { preparar: s(t0, t1), casos: s(t1, t2), planilla: s(t2, t3), total: s(t0, t3) },
  };
}

/** La ficha 01 (.xlsm) de la unidad, hecha en el navegador. */
export function ficha01(grupo: GrupoPython, unidad: string): Promise<Ficha01> {
  return grupo.llamar<Ficha01>(MODULO, "ficha01", [unidad]);
}

/** Descarga bytes como archivo. */
export function descargar(datos: Uint8Array, nombre: string, tipo = "application/octet-stream"): void {
  const url = URL.createObjectURL(new Blob([datos as BlobPart], { type: tipo }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
