import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Vite plugin that rebuilds the rsstitcher wheel from Python source.
 *
 * - On buildStart (dev server start / production build): builds the wheel.
 * - In dev mode: watches rsstitcher/**\/*.{py,json} and rebuilds on change.
 */
export default function rsstitcherWheel(): Plugin {
  const projectRoot = resolve(__dirname, "..");
  const outDir = resolve(__dirname, "public/wheels");

  function build() {
    execSync(`uv build --wheel --out-dir ${outDir}`, {
      cwd: projectRoot,
      stdio: "inherit",
    });
  }

  return {
    name: "rsstitcher-wheel",

    buildStart() {
      build();
    },

    configureServer(server) {
      const watchDir = resolve(projectRoot, "rsstitcher");
      server.watcher.add(watchDir);
      server.watcher.on("change", (path) => {
        if (
          path.startsWith(watchDir) &&
          (path.endsWith(".py") || path.endsWith(".json"))
        ) {
          console.log(`\n[rsstitcher-wheel] ${path} changed, rebuilding…`);
          build();
          server.ws.send({ type: "full-reload" });
        }
      });
    },
  };
}
