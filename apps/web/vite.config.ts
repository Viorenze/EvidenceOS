import fs from "node:fs/promises";
import type { ServerResponse } from "node:http";
import path from "node:path";
import {
  defineConfig,
  normalizePath,
  type ConfigEnv,
  type ProxyOptions,
  type UserConfig,
} from "vite-plus";
import type { Plugin as VitePlugin } from "vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import stylex from "@stylexjs/unplugin";
import inspect from "vite-plugin-inspect";

const LAYER_ORDER_PREAMBLE =
  "@layer reset, priority1, priority2, priority3, priority4, priority5;\n";

const STYLEX_ENTRY_FILES = [
  "src/styles/tokens.stylex.ts",
  "src/routes/__root.tsx",
  "src/components/Header.tsx",
  "src/components/Footer.tsx",
  "src/components/ChunkModal.tsx",
  "src/components/DocumentModal.tsx",
  "src/routes/index.tsx",
  "src/routes/documents.tsx",
];

type StylexVitePlugin = VitePlugin & {
  __stylexCollectCss?: () => string;
  __stylexGetSharedStore?: () => { rulesById: Map<string, unknown> };
};

function createEvidenceOSDevPlugin(apiTarget: string, stylexPlugin: StylexVitePlugin): VitePlugin {
  return {
    name: "evidenceos-dev-readiness-and-stylex-prewarm",
    apply: "serve",
    enforce: "pre",
    configureServer(server) {
      let activeWarmup: Promise<void> | null = null;
      let warmupCompleted = false;

      const ensureStylexWarm = async () => {
        const rootDir = server.config.root || process.cwd();
        const rulesById = stylexPlugin.__stylexGetSharedStore?.().rulesById;
        const expectedPaths = STYLEX_ENTRY_FILES.map((relPath) =>
          normalizePath(path.resolve(rootDir, relPath)),
        );
        if (warmupCompleted && rulesById && expectedPaths.every((p) => rulesById.has(p))) {
          return;
        }
        if (!activeWarmup) {
          activeWarmup = (async () => {
            const transformFn =
              typeof stylexPlugin.transform === "function"
                ? stylexPlugin.transform
                : stylexPlugin.transform?.handler;
            if (!transformFn) return;

            for (const relPath of STYLEX_ENTRY_FILES) {
              try {
                const absPath = path.resolve(rootDir, relPath);
                const normPath = normalizePath(absPath);
                const code = await fs.readFile(absPath, "utf8");
                await transformFn.call({} as never, code, normPath);
              } catch {
                // Ignore missing or transient read errors during warmup
              }
            }
            warmupCompleted = true;
          })().finally(() => {
            activeWarmup = null;
          });
        }
        await activeWarmup;
      };

      server.httpServer?.once("listening", () => {
        void ensureStylexWarm();
      });

      server.middlewares.use(async (req, res, next) => {
        if (!req.url) return next();

        // 1. Guarantee /virtual:stylex.css always includes all pre-warmed rules and explicit @layer order
        if (req.url.startsWith("/virtual:stylex.css")) {
          await ensureStylexWarm();
          const collectFn = stylexPlugin.__stylexCollectCss;
          const rawCss = collectFn ? collectFn() : "";
          res.statusCode = 200;
          res.setHeader("Content-Type", "text/css; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end(LAYER_ORDER_PREAMBLE + (rawCss || ""));
          return;
        }

        // 2. Gracefully handle /api/health readiness probes while FastAPI backend is booting
        // so Vite's http-proxy never spams ECONNREFUSED stack traces in the terminal.
        if (req.url.startsWith("/api/health")) {
          try {
            const upstream = await fetch(`${apiTarget}${req.url}`, {
              method: req.method || "GET",
              signal: AbortSignal.timeout(2000),
            });
            const body = await upstream.text();
            res.statusCode = upstream.status;
            res.setHeader(
              "Content-Type",
              upstream.headers.get("content-type") || "application/json",
            );
            res.setHeader("Cache-Control", "no-store");
            res.end(body);
          } catch {
            res.statusCode = 200;
            res.setHeader("Content-Type", "application/json");
            res.setHeader("Cache-Control", "no-store");
            res.end(JSON.stringify({ status: "starting", ready: false }));
          }
          return;
        }

        next();
      });
    },
  };
}

export default defineConfig(({ command }: ConfigEnv): UserConfig => {
  const isDev = command === "serve";
  const apiTarget = process.env.API_URL || "http://127.0.0.1:8000";
  const stylexPlugin = stylex.vite({
    useCSSLayers: true,
    dev: isDev,
    devPersistToDisk: true,
  }) as StylexVitePlugin;

  const createApiProxyConfig = (): Record<string, ProxyOptions> => ({
    "/api": {
      target: apiTarget,
      changeOrigin: true,
      configure: (proxy) => {
        const handleProxyError = (_err: unknown, _req: unknown, res: unknown) => {
          if (res && typeof res === "object" && "writeHead" in res) {
            const httpRes = res as ServerResponse;
            if (!httpRes.headersSent) {
              httpRes.writeHead(503, {
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
              });
              httpRes.end(
                JSON.stringify({
                  detail: "AI 引擎正在启动中，请稍候...",
                  status: "starting",
                  ready: false,
                }),
              );
            }
          }
        };
        proxy.on("error", handleProxyError);
        process.nextTick(() => {
          proxy.removeAllListeners("error");
          proxy.on("error", handleProxyError);
        });
      },
    },
  });

  const vitePlugins: unknown[] = [
    ...(isDev ? [createEvidenceOSDevPlugin(apiTarget, stylexPlugin)] : []),
    {
      ...stylexPlugin,
      enforce: "pre" as const,
    },
    tanstackStart(),
    viteReact(),
    ...(isDev ? [inspect()] : []),
  ];

  return {
    resolve: {
      tsconfigPaths: true,
    },
    lint: {
      plugins: ["typescript", "react", "oxc", "unicorn"],
      jsPlugins: [{ name: "stylex", specifier: "@stylexjs/eslint-plugin" }],
      options: {
        typeAware: true,
        typeCheck: true,
      },
      ignorePatterns: ["dist/**", ".tanstack/**", "src/routeTree.gen.ts"],
      rules: {
        "stylex/valid-styles": "error",
        "stylex/no-unused": "error",
        "stylex/enforce-extension": "error",
        "stylex/no-nonstandard-styles": "error",
      },
    },
    fmt: {
      ignorePatterns: ["dist/**", ".tanstack/**", "src/routeTree.gen.ts"],
    },
    plugins: vitePlugins as UserConfig["plugins"],
    server: {
      port: 3000,
      proxy: createApiProxyConfig(),
    },
    preview: {
      port: 3000,
      proxy: createApiProxyConfig(),
    },
    build: {
      target: "esnext",
      cssCodeSplit: true,
    },
  };
});
