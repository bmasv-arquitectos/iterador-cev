/**
 * Lo que JSON no tiene, igual que herramientas/web/puente.py:
 *   Uint8Array          {"__bytes__": base64}
 *   numero no finito    {"__float__": "nan" | "inf" | "-inf"}
 */

export function aJson(v: unknown): unknown {
  if (v instanceof Uint8Array) return { __bytes__: aBase64(v) };
  if (typeof v === "number" && !Number.isFinite(v)) {
    return { __float__: Number.isNaN(v) ? "nan" : v > 0 ? "inf" : "-inf" };
  }
  if (Array.isArray(v)) return v.map(aJson);
  if (v && typeof v === "object") {
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, aJson(x)]));
  }
  return v;
}

export function desdeJson(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(desdeJson);
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    const claves = Object.keys(o);
    if (claves.length === 1 && claves[0] === "__bytes__") return deBase64(String(o.__bytes__));
    if (claves.length === 1 && claves[0] === "__float__") {
      return o.__float__ === "nan" ? NaN : o.__float__ === "inf" ? Infinity : -Infinity;
    }
    return Object.fromEntries(claves.map((k) => [k, desdeJson(o[k])]));
  }
  return v;
}

export function aBase64(b: Uint8Array): string {
  let s = "";
  const paso = 0x8000;
  for (let i = 0; i < b.length; i += paso) s += String.fromCharCode(...b.subarray(i, i + paso));
  return btoa(s);
}

export function deBase64(t: string): Uint8Array {
  const s = atob(t);
  const b = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
  return b;
}
