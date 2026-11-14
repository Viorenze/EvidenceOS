import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing, radii } from "../styles/tokens.stylex";
import { getChunkDetail, type ChunkDetail } from "../lib/api";

const slideIn = stylex.keyframes({
  "0%": { transform: "translateX(100%)" },
  "100%": { transform: "translateX(0)" },
});

const fadeIn = stylex.keyframes({
  "0%": { opacity: 0 },
  "100%": { opacity: 1 },
});

const pulse = stylex.keyframes({
  "0%": { opacity: 1 },
  "50%": { opacity: 0.4 },
  "100%": { opacity: 1 },
});

const styles = stylex.create({
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 50,
    backgroundColor: "rgba(15, 23, 42, 0.5)",
    backdropFilter: "blur(4px)",
    display: "flex",
    justifyContent: "flex-end",
    animationName: fadeIn,
    animationDuration: "0.2s",
    animationTimingFunction: "ease-out",
  },
  drawer: {
    backgroundColor: colors.bgCard,
    width: "100%",
    maxWidth: "600px",
    height: "100%",
    boxShadow: "-4px 0 24px rgba(0, 0, 0, 0.15)",
    display: "flex",
    flexDirection: "column",
    padding: spacing.lg,
    overflow: "hidden",
    boxSizing: "border-box",
    animationName: slideIn,
    animationDuration: "0.25s",
    animationTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.md,
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
  },
  badge: {
    backgroundColor: colors.primaryLight,
    color: colors.primaryText,
    fontSize: "0.75rem",
    fontWeight: 600,
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.sm,
  },
  chunkId: {
    fontSize: "0.75rem",
    color: colors.textLight,
    fontFamily: "monospace",
  },
  closeIconButton: {
    color: {
      default: colors.textLight,
      ":hover": colors.textMain,
    },
    fontSize: "1.25rem",
    fontWeight: 700,
    padding: spacing.xs,
    borderRadius: radii.sm,
    backgroundColor: "transparent",
    borderWidth: 0,
    cursor: "pointer",
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "color 0.15s ease",
  },
  body: {
    flexGrow: 1,
    overflowY: "auto",
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    display: "flex",
    flexDirection: "column",
    gap: spacing.md,
  },
  loading: {
    paddingTop: "80px",
    paddingBottom: "80px",
    textAlign: "center",
    color: colors.textLight,
    fontSize: "0.875rem",
    animationName: pulse,
    animationDuration: "1.5s",
    animationIterationCount: "infinite",
  },
  error: {
    padding: spacing.md,
    backgroundColor: colors.errorBg,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    borderRadius: radii.md,
    color: colors.errorText,
    fontSize: "0.875rem",
  },
  metaCard: {
    backgroundColor: colors.bgPage,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    borderRadius: radii.md,
    padding: spacing.md,
    fontSize: "0.75rem",
    display: "flex",
    flexDirection: "column",
    gap: spacing.sm,
  },
  metaRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
  },
  metaLabel: {
    color: colors.textMuted,
    fontWeight: 500,
    flexShrink: 0,
  },
  metaDocValue: {
    color: colors.textMain,
    fontWeight: 600,
    textAlign: "right",
    wordBreak: "break-all",
  },
  metaPageValue: {
    color: colors.textMain,
  },
  metaHeadingValue: {
    color: colors.textMuted,
    fontFamily: "monospace",
    fontSize: "0.75rem",
    textAlign: "right",
    maxWidth: "320px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  metaIdxValue: {
    color: colors.textMain,
    fontFamily: "monospace",
    fontWeight: 600,
  },
  sectionHeading: {
    fontSize: "0.75rem",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: colors.textMuted,
    margin: 0,
    marginBottom: spacing.xs,
  },
  contentWrapper: {
    display: "flex",
    flexDirection: "column",
  },
  contentCard: {
    padding: spacing.md,
    backgroundColor: colors.bgPage,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    borderRadius: radii.md,
    color: colors.textMain,
    fontSize: "0.875rem",
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    wordBreak: "break-word",
  },
  footer: {
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: colors.borderSubtle,
    paddingTop: spacing.md,
    display: "flex",
    justifyContent: "flex-end",
  },
  footerButton: {
    paddingTop: "8px",
    paddingBottom: "8px",
    paddingLeft: "16px",
    paddingRight: "16px",
    backgroundColor: {
      default: colors.bgSubtle,
      ":hover": colors.bgMuted,
    },
    color: colors.textMain,
    fontSize: "0.875rem",
    fontWeight: 500,
    borderRadius: radii.md,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderLight,
    cursor: "pointer",
    transition: "background-color 0.15s ease",
  },
});

export interface ChunkModalProps {
  chunkId: string | null;
  onClose: () => void;
}

export function ChunkModal({ chunkId, onClose }: ChunkModalProps) {
  if (!chunkId) return null;
  return <ChunkModalContent key={chunkId} chunkId={chunkId} onClose={onClose} />;
}

function ChunkModalContent({ chunkId, onClose }: { chunkId: string; onClose: () => void }) {
  const [detail, setDetail] = React.useState<ChunkDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getChunkDetail(chunkId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load chunk");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      {...stylex.props(styles.overlay)}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
    >
      <div {...stylex.props(styles.drawer)}>
        <div {...stylex.props(styles.header)}>
          <div {...stylex.props(styles.headerLeft)}>
            <span {...stylex.props(styles.badge)}>引用原文对账</span>
            <span {...stylex.props(styles.chunkId)}>ID: {chunkId.slice(0, 8)}...</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            {...stylex.props(styles.closeIconButton)}
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        <div {...stylex.props(styles.body)}>
          {loading && (
            <div {...stylex.props(styles.loading)}>
              正在从 PostgreSQL + pgvector 获取 Chunk 原文...
            </div>
          )}

          {error && <div {...stylex.props(styles.error)}>获取失败：{error}</div>}

          {detail && (
            <>
              <div {...stylex.props(styles.metaCard)}>
                <div {...stylex.props(styles.metaRow)}>
                  <span {...stylex.props(styles.metaLabel)}>来源文档:</span>
                  <span {...stylex.props(styles.metaDocValue)}>{detail.document}</span>
                </div>
                {detail.page != null && (
                  <div {...stylex.props(styles.metaRow)}>
                    <span {...stylex.props(styles.metaLabel)}>页码:</span>
                    <span {...stylex.props(styles.metaPageValue)}>第 {detail.page} 页</span>
                  </div>
                )}
                {detail.heading && (
                  <div {...stylex.props(styles.metaRow)}>
                    <span {...stylex.props(styles.metaLabel)}>章节面包屑:</span>
                    <span {...stylex.props(styles.metaHeadingValue)} title={detail.heading}>
                      {detail.heading}
                    </span>
                  </div>
                )}
                <div {...stylex.props(styles.metaRow)}>
                  <span {...stylex.props(styles.metaLabel)}>文档切片序号:</span>
                  <span {...stylex.props(styles.metaIdxValue)}>Chunk #{detail.idx}</span>
                </div>
              </div>

              <div {...stylex.props(styles.contentWrapper)}>
                <h4 {...stylex.props(styles.sectionHeading)}>切片完整原文 (Full Chunk Content)</h4>
                <div {...stylex.props(styles.contentCard)}>{detail.content}</div>
              </div>
            </>
          )}
        </div>

        <div {...stylex.props(styles.footer)}>
          <button type="button" onClick={onClose} {...stylex.props(styles.footerButton)}>
            完成查看
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChunkModal;
