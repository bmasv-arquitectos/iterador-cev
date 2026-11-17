/**
 * F1: calculo_py._nucleo (el bucle de la simulacion del motor) en JavaScript.
 *
 * Traduccion linea a linea de herramientas/motor_cev/calculo_py.py (_nucleo), con el mismo
 * orden de operaciones (mismos parentesis, sumas de izquierda a derecha), para dar el mismo
 * resultado que el motor Python dentro de la tolerancia de los tests (1e-9). Lo comprueba
 * comparar.ts con lo que grabo exportar_casos.py.
 *
 * Sin dependencias de Node: se usa igual en el navegador (F2, src/python/modulos_js.ts).
 *
 *   calcularNucleo(entradas)   -> Float64Array de (n_filas + 1) x 56, fila a fila
 *   revisarEntradas(entradas)  -> las mismas, o un error que dice que argumento llego mal
 *   nucleo(...args)            -> lo mismo con los 43 argumentos en el orden de Python
 *                                 (para comparar.ts); devuelve {tipo, forma, datos}
 *
 * La matriz es la de Python: filas y columnas desde 1 (la fila 0 y la columna 0 quedan en 0).
 */

const RO = 1.2;
const CP = 1000.0;
const HINT = 8.3;
const PMAX = 100000.0;
const COLUMNAS = 56;

type Numeros = ArrayLike<number>;

export interface EntradasNucleo {
  n_filas: number;
  ib: number;
  dt: number;
  mes: Numeros;
  text: Numeros;
  rad: Numeros;
  pers: Numeros;
  ilum: Numeros;
  equip: Numeros;
  tsol: Numeros; // n_filas x 9, fila a fila
  clima: Numeros;
  nvent: Numeros;
  tmax1: Numeros;
  tmin1: Numeros;
  tmax2: Numeros;
  tmin2: Numeros;
  tsuelo: Numeros;
  infilt: Numeros;
  verano: Numeros; // 0 / 1
  invierno: Numeros; // 0 / 1
  c8: Numeros;
  sa: Numeros; // 2 x 24 x 11, en ese orden
  ini18: Numeros;
  ini31: Numeros;
  aplanta: number;
  vaire: number;
  ut_v: number;
  at_v: number;
  ut: number;
  at: number;
  a_v: Numeros; // 8
  a: Numeros;
  fil: Numeros;
  u_v: Numeros;
  u: Numeros;
  apv: number;
  upv: number;
  filpt: number;
  part: Numeros; // 5
  area_hor: number;
  cap_hor: number;
  recup: boolean;
  ef_recup: number;
}

/** Los argumentos de _nucleo en el orden de Python. */
export const NOMBRES = [
  "n_filas", "ib", "dt", "mes", "text", "rad", "pers", "ilum", "equip", "tsol", "clima", "nvent",
  "tmax1", "tmin1", "tmax2", "tmin2", "tsuelo", "infilt", "verano", "invierno", "c8",
  "sa", "ini18", "ini31", "aplanta", "vaire", "ut_v", "at_v", "ut", "at",
  "a_v", "a", "fil", "u_v", "u", "apv", "upv", "filpt", "part", "area_hor", "cap_hor",
  "recup", "ef_recup",
] as const;

const ESCALARES = new Set<string>([
  "n_filas", "ib", "dt", "aplanta", "vaire", "ut_v", "at_v", "ut", "at", "apv", "upv", "filpt",
  "area_hor", "cap_hor", "recup", "ef_recup",
]);
const SERIES = [
  "mes", "text", "rad", "pers", "ilum", "equip", "clima", "nvent", "tmax1", "tmin1", "tmax2", "tmin2",
  "tsuelo", "infilt", "verano", "invierno", "c8",
];

function describir(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (ArrayBuffer.isView(v) || Array.isArray(v)) {
    return `${(v as object).constructor?.name ?? "arreglo"} de ${(v as ArrayLike<unknown>).length}`;
  }
  return `${typeof v} ${(v as object).constructor?.name ?? ""}`.trim();
}

/** Revisa que lleguen todos los argumentos con su largo (por ejemplo desde Python). */
export function revisarEntradas(e: EntradasNucleo): EntradasNucleo {
  const o = e as unknown as Record<string, unknown>;
  for (const n of NOMBRES) {
    if (!ESCALARES.has(n)) continue;
    const v = o[n];
    const ok = n === "recup" ? typeof v === "boolean" || typeof v === "number" : typeof v === "number";
    if (!ok) throw new Error(`_nucleo: ${n} deberia ser un numero y llego ${describir(v)}`);
  }
  const largo = (n: string, min: number) => {
    const v = o[n];
    const ok = (ArrayBuffer.isView(v) || Array.isArray(v)) && (v as ArrayLike<number>).length >= min;
    if (!ok) throw new Error(`_nucleo: ${n} deberia ser un arreglo de ${min} numeros o mas y llego ${describir(v)}`);
  };
  for (const n of SERIES) largo(n, e.n_filas);
  largo("tsol", e.n_filas * 9);
  largo("sa", 2 * 24 * 11);
  largo("ini18", e.ib);
  largo("ini31", e.ib);
  for (const n of ["a_v", "a", "fil", "u_v", "u"]) largo(n, 8);
  largo("part", 5);
  return e;
}

export function calcularNucleo(e: EntradasNucleo): Float64Array {
  const C = COLUMNAS;
  const nf = e.n_filas;
  const ib = e.ib;
  const dt = e.dt;
  const R = nf + 1;
  const M = new Float64Array(R * C);
  const paso = Math.trunc(3600 / dt);
  const vrc = e.vaire * RO * CP;
  const { mes, text, rad, pers, ilum, equip, tsol, clima, nvent, tmax1, tmin1, tmax2, tmin2 } = e;
  const { tsuelo, infilt, verano, invierno, c8, sa, ini18, ini31, a_v, a, fil, u_v, u, part } = e;
  const { aplanta, vaire, ut_v, at_v, ut, at, apv, upv, filpt, area_hor, cap_hor, recup, ef_recup } = e;

  for (let f = 1; f <= ib; f++) {
    const j = f - 1;
    const o = f * C;
    M[o + 1] = (j * dt) / 60;
    M[o + 2] = j * dt;
    M[o + 3] = mes[j];
    M[o + 4] = text[j];
    M[o + 18] = ini18[j];
    M[o + 31] = ini31[j];
  }

  let n = 0.0;
  const qv = new Float64Array(8);
  const qs = new Float64Array(8);
  for (let f = ib + 1; f <= nf; f++) {
    const j = f - 1;
    const o = f * C;
    const p = (f - 1) * C;
    const s = verano[j - 1] ? 1 : 0; // SA con el tiempo de la fila anterior
    M[o + 2] = M[p + 2] + dt;
    M[o + 1] = M[o + 2] / 3600;
    M[o + 3] = mes[j];
    M[o + 4] = text[j];
    M[o + 5] = rad[j];
    const qsol = M[p + 5];
    M[o + 6] = pers[j] * aplanta;
    M[o + 7] = ilum[j] * aplanta;
    M[o + 8] = equip[j] * aplanta;
    const qint = M[p + 6] + M[p + 7] + M[p + 8];
    for (let k = 0; k < 9; k++) M[o + 9 + k] = tsol[j * 9 + k];
    let qTecho = 0.0;
    for (let k = 0; k < 8; k++) qs[k] = 0.0;
    let qPv = 0.0;
    let qPt = 0.0;
    for (let i = 1; i <= 24; i++) {
      let idx = f - 1 - paso * (i - 1);
      if (idx < 0) idx += R; // numpy: indice negativo cuenta desde el final
      const q = idx * C;
      const ti = M[q + 18];
      const sb = (s * 24 + (i - 1)) * 11;
      qTecho = qTecho + (ut * at * (M[q + 9] - ti) * sa[sb]) / 100;
      for (let k = 0; k < 8; k++) {
        qs[k] = qs[k] + ((u[k] * a[k] + fil[k]) * (M[q + 10 + k] - ti) * sa[sb + 1 + k]) / 100;
      }
      qPv = qPv + (upv * apv * (M[q + 4] - ti) * sa[sb + 9]) / 100;
      qPt = qPt + (filpt * (tsuelo[j] - ti) * sa[sb + 10]) / 100;
    }
    const dtv = M[p + 4] - M[p + 18];
    const qTechoV = ut_v * at_v * dtv;
    M[o + 36] = qTechoV;
    M[o + 37] = qTecho;
    for (let k = 0; k < 8; k++) {
      qv[k] = u_v[k] * a_v[k] * dtv;
      M[o + 38 + 2 * k] = qv[k];
      M[o + 39 + 2 * k] = qs[k];
    }
    M[o + 54] = qPv;
    M[o + 55] = qPt;
    const qHor = HINT * area_hor * (M[p + 18] + (qsol * 0.85) / (HINT * area_hor) - M[p + 31]);
    M[o + 31] = M[p + 31] + (qHor * dt) / cap_hor;
    const qmasa = HINT * area_hor * (M[p + 31] - M[p + 18]);
    const qventanas = qv[0] + qv[1] + qv[2] + qv[3] + qv[4] + qv[5] + qv[6] + qv[7] + qTechoV;
    const qtecho = qTecho + qmasa * part[0];
    const qmuros = qs[0] + qs[1] + qs[2] + qs[3] + qs[4] + qs[5] + qs[6] + qs[7] + qmasa * part[1];
    const qpv = qPv + qmasa * part[2];
    const qpt = qPt + qmasa * part[3];
    const qenv = qventanas + qtecho + qmuros + (qpv + qpt);
    const qmasaAd = qmasa * part[4];
    M[o + 32] = qmasaAd;
    M[o + 19] = qenv;
    M[o + 21] = qventanas;
    M[o + 22] = qtecho;
    M[o + 23] = qmuros;
    M[o + 20] = qpv;
    M[o + 24] = qpt;
    const qinfilt = (vaire * ((infilt[j] / 3600) * dt) * RO * CP * dtv) / dt;
    M[o + 27] = qinfilt;
    const qpot = (vaire * ((n / 3600) * dt) * RO * CP * dtv) / dt;
    let qrecup = 0.0;
    if (recup && invierno[j]) qrecup = -0.5 * ef_recup * qpot;
    n = nvent[j];
    M[o + 25] = qpot;
    M[o + 26] = qrecup;
    const tprev = M[p + 18];
    const S = qsol * 0.15 + qint + qenv + qpot + qmasaAd + qrecup + qinfilt;
    let qclima = 0.0;
    for (const modo of [1, 2]) {
      if (clima[j] !== modo) continue;
      const tmax = modo === 1 ? tmax1[j] : tmax2[j];
      const tmin = modo === 1 ? tmin1[j] : tmin2[j];
      if (tprev >= tmax) {
        if (S > 0) qclima = -S + (vrc * (tmax - tprev)) / dt;
        else if (S < 0) qclima = S + (vrc * (tmax - tprev)) / dt;
        if (qclima < -PMAX) qclima = -PMAX;
      }
      if (tprev <= tmin) {
        if (S < 0) qclima = -S + (vrc * (tmin - tprev)) / dt;
        else if (S > 0) qclima = S + (vrc * (tmin - tprev)) / dt;
        if (qclima > PMAX) qclima = PMAX;
      }
    }
    M[o + 28] = qclima;
    const q = (qsol * 0.15 + qint + qenv + qpot + qmasaAd + qclima + qrecup + qinfilt) * dt;
    M[o + 18] = tprev + q / vrc;
    M[o + 35] = q / dt;
    if (c8[j] === dt) {
      M[o + 33] = 0.0;
      M[o + 34] = 0.0;
    } else if (qclima >= 0) {
      M[o + 33] = M[p + 33] + (qclima * dt) / 3600;
      M[o + 34] = M[p + 34] + 0;
    } else {
      M[o + 33] = M[p + 33] + 0;
      M[o + 34] = M[p + 34] + (qclima * dt) / 3600;
    }
  }
  return M;
}

function arreglo(x: unknown, nombre: string): Numeros {
  if (x && typeof x === "object" && "datos" in x) return (x as { datos: Numeros }).datos;
  if (ArrayBuffer.isView(x) || Array.isArray(x)) return x as Numeros;
  throw new Error(`${nombre}: se esperaba un arreglo`);
}

function escalar(x: unknown, nombre: string): number {
  if (typeof x === "number") return x;
  if (typeof x === "boolean") return x ? 1 : 0;
  throw new Error(`${nombre}: se esperaba un numero`);
}

/** _nucleo con los argumentos en el orden de Python; devuelve {tipo, forma, datos}. */
export function nucleo(...args: unknown[]): { tipo: string; forma: number[]; datos: Float64Array } {
  if (args.length !== NOMBRES.length) {
    throw new Error(`_nucleo recibe ${NOMBRES.length} argumentos y llegaron ${args.length}`);
  }
  const e: Record<string, unknown> = {};
  NOMBRES.forEach((nombre, i) => {
    e[nombre] = ESCALARES.has(nombre) ? escalar(args[i], nombre) : arreglo(args[i], nombre);
  });
  e.recup = Boolean(e.recup);
  const datos = calcularNucleo(e as unknown as EntradasNucleo);
  return { tipo: "float64", forma: [(e.n_filas as number) + 1, COLUMNAS], datos };
}
