import { defineConfig } from 'vite';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Absolute path to the directory containing this vite.config.js (= app/)
// so that all relative paths resolve correctly regardless of where vite
// is invoked from (`tauri build` runs from a different cwd than `vite`).
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const host = process.env.TAURI_DEV_HOST;

/**
 * Vite plugin: copy multi-window HTML entries into dist/ after the main
 * build. The Tauri config registers extra windows ('dashboard',
 * 'aquarium') that load HTML from the frontendDist directory; vite only
 * bundles the root entry, so we need to manually copy the additional
 * trees into dist/.
 *
 * Without this, the release binary opens those windows blank (because
 * dashboard/index.html doesn't exist in dist/) while dev mode works
 * fine (vite serves src/ directly). That's the root cause of "Agent
 * Monitor appears to do nothing" in the packaged build through alpha.7.
 */
function copyExtraWindows() {
  async function copyDir(src, dest) {
    await fs.mkdir(dest, { recursive: true });
    const entries = await fs.readdir(src, { withFileTypes: true });
    for (const ent of entries) {
      const s = path.join(src, ent.name);
      const d = path.join(dest, ent.name);
      if (ent.isDirectory()) await copyDir(s, d);
      else await fs.copyFile(s, d);
    }
  }
  return {
    name: 'gmux-copy-extra-windows',
    apply: 'build',
    enforce: 'post',                  // run after other plugins
    // Use closeBundle (final hook) instead of writeBundle so we run
    // AFTER any emptyOutDir cleanup that vite does between stages.
    async closeBundle() {
      // IMPORTANT: resolve relative to vite.config.js's directory (app/)
      // — when invoked via `tauri build` the cwd is the project root, not app/.
      // Using path.resolve() alone resolves against cwd which gave us
      // /home/.../gmux_v4/dist instead of /home/.../gmux_v4/app/dist.
      const srcRoot  = path.join(__dirname, 'src');
      const distRoot = path.join(__dirname, 'dist');
      // Multi-window entries other than index.html, plus any vendored
      // third-party scripts that the bundler isn't supposed to touch
      // (e.g. the QR generator for phone pairing — see commands/pairing.rs).
      const extras = ['dashboard', 'aquarium.html', 'vendor'];
      for (const name of extras) {
        const from = path.join(srcRoot, name);
        const to   = path.join(distRoot, name);
        try {
          const stat = await fs.stat(from);
          if (stat.isDirectory()) {
            await copyDir(from, to);
            console.log(`[gmux-vite] copied dir  src/${name} → dist/${name}`);
          } else {
            await fs.copyFile(from, to);
            console.log(`[gmux-vite] copied file src/${name} → dist/${name}`);
          }
        } catch (e) {
          if (e.code === 'ENOENT') {
            console.warn(`[gmux-vite] skipped src/${name} (not found)`);
          } else {
            throw e;
          }
        }
      }
      // Sanity check: the dashboard file must exist in dist after we're
      // done; if not, the release binary will silently open a blank window.
      try {
        await fs.access(path.join(distRoot, 'dashboard', 'index.html'));
        console.log('[gmux-vite] ✓ dist/dashboard/index.html present');
      } catch {
        console.error('[gmux-vite] ✗ dist/dashboard/index.html MISSING — Agent Monitor window will be blank');
      }
    },
  };
}

export default defineConfig({
  clearScreen: false,
  root: 'src',          // serve src/index.html as the entry point
  plugins: [copyExtraWindows()],
  server: {
    port:         1421,          // different from gmux-app (1420) so both can run at once
    strictPort:   true,
    host:         host || false,
    hmr: host
      ? { protocol: 'ws', host, port: 1422 }
      : undefined,
    watch: { ignored: ['**/src-tauri/**'] },
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    // safari13 can't lower modern destructuring in some xterm addons; bump
    // to safari15 (still supports WKWebView on macOS 10.15+).
    target:    process.env.TAURI_ENV_PLATFORM === 'windows' ? 'chrome105' : 'safari15',
    minify:    !process.env.TAURI_ENV_DEBUG ? 'esbuild' : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
    // Output to app/dist (root of the app folder) so it matches
    // src-tauri/tauri.conf.json `frontendDist: "../dist"`.
    outDir:      '../dist',
    emptyOutDir: true,
  },
});
