import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import rsstitcherWheel from "./vite-plugin-rsstitcher-wheel";

export default defineConfig({
  plugins: [rsstitcherWheel(), react(), tailwindcss()],
  base: "/RSstitcher/",
  server: {
    fs: {
      allow: [".."],
    },
  },
  worker: {
    format: "es",
  },
});
