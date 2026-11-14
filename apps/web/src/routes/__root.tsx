import { createRootRoute, HeadContent, Outlet, Scripts } from "@tanstack/react-router";
import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing } from "../styles/tokens.stylex";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import "../styles/reset.css";

const TanStackRouterDevtools = import.meta.env.PROD
  ? () => null
  : React.lazy(() =>
      import("@tanstack/react-router-devtools").then((res) => ({
        default: res.TanStackRouterDevtools,
      })),
    );

const styles = stylex.create({
  root: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    backgroundColor: colors.bgPage,
    color: colors.textMain,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    margin: 0,
    padding: 0,
  },
  main: {
    flexGrow: 1,
    display: "flex",
    flexDirection: "column",
    maxWidth: "1152px",
    width: "100%",
    marginLeft: "auto",
    marginRight: "auto",
    paddingTop: spacing.lg,
    paddingBottom: spacing.xl,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
    boxSizing: "border-box",
  },
  notFoundContainer: {
    textAlign: "center",
    paddingTop: spacing.xl,
    paddingBottom: spacing.xl,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
  },
  notFoundTitle: {
    fontSize: "1.25rem",
    fontWeight: 600,
    color: colors.textMain,
    marginBottom: spacing.xs,
  },
  notFoundDesc: {
    fontSize: "0.875rem",
    color: colors.textMuted,
  },
});

const CRITICAL_LAYER_RESET_CSS = `
@layer reset, priority1, priority2, priority3, priority4, priority5;
@layer reset {
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  html, body {
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #0f172a;
    background-color: #f8fafc;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  button {
    font: inherit;
    border: none;
    background: none;
    cursor: pointer;
  }
  input, textarea, select {
    font: inherit;
  }
  a {
    color: inherit;
    text-decoration: none;
  }
  dialog:modal {
    overscroll-behavior: contain;
    margin: auto;
    border: none;
    background: transparent;
    max-width: min(920px, 94vw);
    max-height: 90vh;
    width: 100%;
  }
  dialog::backdrop {
    overflow: hidden;
    overscroll-behavior: contain;
    background-color: rgba(15, 23, 42, 0.55);
    backdrop-filter: blur(4px);
  }
}
`;

export const Route = createRootRoute({
  head: () => ({
    meta: [
      {
        charSet: "utf-8",
      },
      {
        name: "viewport",
        content: "width=device-width, initial-scale=1",
      },
      {
        title: "EvidenceOS - 可信技术文档检索与问答系统",
      },
    ],
    links: import.meta.env.DEV
      ? [
          {
            rel: "stylesheet",
            href: "/virtual:stylex.css",
          },
        ]
      : [],
  }),
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});

function NotFoundComponent() {
  return (
    <div {...stylex.props(styles.notFoundContainer)}>
      <h2 {...stylex.props(styles.notFoundTitle)}>404 - 页面未找到</h2>
      <p {...stylex.props(styles.notFoundDesc)}>您访问的页面不存在或已被移除。</p>
    </div>
  );
}

function RootComponent() {
  return (
    <html lang="zh-CN">
      <head>
        <style dangerouslySetInnerHTML={{ __html: CRITICAL_LAYER_RESET_CSS }} />
        <HeadContent />
      </head>
      <body {...stylex.props(styles.root)}>
        <Header />
        <main {...stylex.props(styles.main)}>
          <Outlet />
        </main>
        <Footer />
        <React.Suspense fallback={null}>
          <TanStackRouterDevtools position="bottom-right" />
        </React.Suspense>
        <Scripts />
      </body>
    </html>
  );
}
