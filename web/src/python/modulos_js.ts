/**
 * Modulos de JavaScript que Python puede importar dentro del worker (py.registerJsModule, en
 * worker.ts). Es el unico lugar donde se agregan: cada herramienta de la familia suma los suyos.
 *
 *   nucleo_js.calcular(entradas)   el bucle de la simulacion del motor CEV (nucleo/nucleo.ts);
 *                                  lo usa herramientas/web/motor_web.usar_nucleo_js
 */
import { calcularNucleo, revisarEntradas, type EntradasNucleo } from "../../nucleo/nucleo";

export const MODULOS_JS: Record<string, Record<string, unknown>> = {
  nucleo_js: {
    calcular: (e: EntradasNucleo): Float64Array => calcularNucleo(revisarEntradas(e)),
  },
};
