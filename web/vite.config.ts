import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// Sitio estatico con rutas relativas: se publica en cualquier carpeta (por ejemplo /iterador/).
// El build arma solo la herramienta (index.html); las demas paginas (basica.html, sonda.html,
// nicegui.html) se abren con npm run dev, para desarrollo y diagnostico.
export default defineConfig({
  base: "./",
  worker: { format: "es" },
  build: {
    target: "es2022",
    outDir: "dist",
    rollupOptions: {
      input: { main: fileURLToPath(new URL("./index.html", import.meta.url)) },
    },
  },
  server: { port: 5173 },
});
