import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, proxy API + calendar calls to the FastAPI server so the
// frontend and backend feel like one origin. In production FastAPI serves the
// built files in web/dist, so no proxy is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/calendar": "http://127.0.0.1:8000",
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
