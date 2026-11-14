import * as React from "react";
import { Link, useLocation } from "@tanstack/react-router";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing, radii } from "../styles/tokens.stylex";
import { ensureBackendReadinessProbe, useChatSession } from "../lib/chatStore";

const pulse = stylex.keyframes({
  "0%": { opacity: 1 },
  "50%": { opacity: 0.35 },
  "100%": { opacity: 1 },
});

const styles = stylex.create({
  header: {
    position: "sticky",
    top: 0,
    zIndex: 40,
    height: "64px",
    backgroundColor: colors.bgCard,
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingLeft: spacing.lg,
    paddingRight: spacing.lg,
    boxShadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
  },
  brandContainer: {
    display: "flex",
    alignItems: "center",
    gap: spacing.md,
  },
  brandLink: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    textDecoration: "none",
  },
  logoBadge: {
    width: "36px",
    height: "36px",
    borderRadius: radii.md,
    backgroundColor: colors.primary,
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 800,
    fontSize: "1.25rem",
    boxShadow: "0 2px 4px rgba(37, 99, 235, 0.2)",
  },
  brandTextWrapper: {
    display: "flex",
    alignItems: "baseline",
    gap: spacing.sm,
  },
  brandTitle: {
    fontSize: "1.25rem",
    fontWeight: 700,
    color: colors.textMain,
    letterSpacing: "-0.025em",
  },
  brandTag: {
    fontSize: "0.75rem",
    fontWeight: 600,
    color: colors.primaryText,
    backgroundColor: colors.primaryLight,
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.full,
  },
  nav: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
  },
  navLink: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    paddingTop: "8px",
    paddingBottom: "8px",
    paddingLeft: "14px",
    paddingRight: "14px",
    borderRadius: radii.md,
    fontSize: "0.875rem",
    fontWeight: 500,
    color: {
      default: colors.textMuted,
      ":hover": colors.textMain,
    },
    backgroundColor: {
      default: "transparent",
      ":hover": colors.bgSubtle,
    },
    textDecoration: "none",
    transition: "background-color 0.15s ease, color 0.15s ease",
  },
  navLinkActive: {
    backgroundColor: {
      default: colors.primaryLight,
      ":hover": colors.primaryLight,
    },
    color: {
      default: colors.primaryText,
      ":hover": colors.primaryText,
    },
    fontWeight: 600,
  },
  streamingDot: {
    width: "8px",
    height: "8px",
    borderRadius: radii.full,
    backgroundColor: colors.primary,
    animationName: pulse,
    animationDuration: "1s",
    animationIterationCount: "infinite",
  },
});

export function Header() {
  const location = useLocation();
  const pathname = location.pathname;
  const { isStreaming } = useChatSession();

  React.useEffect(() => {
    ensureBackendReadinessProbe();
  }, []);

  const isChatActive = pathname === "/";
  const isDocsActive = pathname === "/documents" || pathname.startsWith("/documents");

  return (
    <header {...stylex.props(styles.header)}>
      <div {...stylex.props(styles.brandContainer)}>
        <Link to="/" {...stylex.props(styles.brandLink)}>
          <div {...stylex.props(styles.logoBadge)}>E</div>
          <div {...stylex.props(styles.brandTextWrapper)}>
            <span {...stylex.props(styles.brandTitle)}>EvidenceOS</span>
            <span {...stylex.props(styles.brandTag)}>Verifiable RAG</span>
          </div>
        </Link>
      </div>

      <nav {...stylex.props(styles.nav)}>
        <Link
          to="/"
          activeOptions={{ exact: true }}
          {...stylex.props(styles.navLink, isChatActive && styles.navLinkActive)}
        >
          <span>💬</span>
          <span>问答检索 (Chat)</span>
          {isStreaming && (
            <span title="后台正在生成回答..." {...stylex.props(styles.streamingDot)} />
          )}
        </Link>

        <Link
          to="/documents"
          {...stylex.props(styles.navLink, isDocsActive && styles.navLinkActive)}
        >
          <span>📄</span>
          <span>文档管理 (Documents)</span>
        </Link>
      </nav>
    </header>
  );
}
