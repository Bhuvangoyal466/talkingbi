import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      // In development, forward /chat /data /charts /insights /session → FastAPI on :8000
      "/chat":     { target: "http://localhost:8000", changeOrigin: true },
      "/data":     { target: "http://localhost:8000", changeOrigin: true },
      "/charts":   { target: "http://localhost:8000", changeOrigin: true },
      "/insights": { target: "http://localhost:8000", changeOrigin: true },
      "/voice":    { target: "http://localhost:8000", changeOrigin: true, ws: true },
      "/sessions": { target: "http://localhost:8000", changeOrigin: true },
      "/session":  { target: "http://localhost:8000", changeOrigin: true },
      "/health":   { target: "http://localhost:8000", changeOrigin: true },
      "/llm":      { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  plugins: [
    react(),
    mode === "development" && componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: [
      "react",
      "react-dom",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "@tanstack/react-query",
      "@tanstack/query-core",
    ],
  },
}));
