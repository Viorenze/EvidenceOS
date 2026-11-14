import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing, radii } from "../styles/tokens.stylex";
import { getDocumentDetail, type DocumentDetail } from "../lib/api";

const fadeInScale = stylex.keyframes({
  "0%": { opacity: 0, transform: "scale(0.97) translateY(6px)" },
  "100%": { opacity: 1, transform: "scale(1) translateY(0)" },
});

const pulse = stylex.keyframes({
  "0%": { opacity: 1 },
  "50%": { opacity: 0.45 },
  "100%": { opacity: 1 },
});

const styles = stylex.create({
  dialogElement: {
    padding: 0,
    borderWidth: 0,
    backgroundColor: "transparent",
    outline: "none",
    margin: "auto",
    maxWidth: "min(920px, 94vw)",
    maxHeight: "90vh",
    width: "100%",
    overscrollBehavior: "contain",
  },
  panel: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    boxShadow: "0 20px 40px -12px rgba(15, 23, 42, 0.28)",
    display: "flex",
    flexDirection: "column",
    maxHeight: "88vh",
    width: "100%",
    overflow: "hidden",
    animationName: fadeInScale,
    animationDuration: "0.2s",
    animationTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    paddingLeft: spacing.lg,
    paddingRight: spacing.lg,
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    backgroundColor: colors.bgSubtle,
    flexWrap: "wrap",
  },
  headerTitleArea: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    minWidth: 0,
  },
  fileIcon: {
    fontSize: "1.35rem",
    flexShrink: 0,
  },
  titleTextGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    minWidth: 0,
  },
  dialogTitle: {
    fontSize: "1.05rem",
    fontWeight: 700,
    color: colors.textMain,
    margin: 0,
    wordBreak: "break-all",
  },
  metaSubtitle: {
    fontSize: "0.75rem",
    color: colors.textMuted,
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: spacing.xs,
    flexWrap: "wrap",
  },
  actionBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    paddingTop: "6px",
    paddingBottom: "6px",
    paddingLeft: "12px",
    paddingRight: "12px",
    borderRadius: radii.md,
    fontSize: "0.75rem",
    fontWeight: 600,
    backgroundColor: {
      default: colors.bgCard,
      ":hover": colors.primaryLight,
    },
    color: {
      default: colors.textMain,
      ":hover": colors.primaryText,
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: colors.borderLight,
      ":hover": colors.primary,
    },
    cursor: "pointer",
    transition: "background-color 0.15s ease, border-color 0.15s ease",
  },
  actionBtnSuccess: {
    backgroundColor: colors.successBg,
    color: colors.successText,
    borderColor: colors.successBorder,
  },
  closeIconButton: {
    color: {
      default: colors.textMuted,
      ":hover": colors.textMain,
    },
    fontSize: "1.15rem",
    fontWeight: 700,
    width: "32px",
    height: "32px",
    borderRadius: radii.md,
    backgroundColor: {
      default: "transparent",
      ":hover": colors.bgMuted,
    },
    borderWidth: 0,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background-color 0.15s ease, color 0.15s ease",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingLeft: spacing.lg,
    paddingRight: spacing.lg,
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    backgroundColor: colors.bgCard,
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  tabGroup: {
    display: "inline-flex",
    alignItems: "center",
    backgroundColor: colors.bgSubtle,
    padding: "3px",
    borderRadius: radii.md,
    gap: "4px",
  },
  tabButton: {
    paddingTop: "5px",
    paddingBottom: "5px",
    paddingLeft: "12px",
    paddingRight: "12px",
    borderRadius: radii.sm,
    fontSize: "0.8125rem",
    fontWeight: 600,
    color: {
      default: colors.textMuted,
      ":hover": colors.textMain,
    },
    backgroundColor: "transparent",
    borderWidth: 0,
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  tabButtonActive: {
    backgroundColor: colors.bgCard,
    color: colors.primaryText,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.06)",
  },
  statsInfo: {
    fontSize: "0.75rem",
    color: colors.textMuted,
    fontFamily: "monospace",
  },
  body: {
    flexGrow: 1,
    overflowY: "auto",
    padding: spacing.lg,
    backgroundColor: colors.bgPage,
    display: "flex",
    flexDirection: "column",
    gap: spacing.md,
  },
  loadingBox: {
    paddingTop: "72px",
    paddingBottom: "72px",
    textAlign: "center",
    color: colors.textMuted,
    fontSize: "0.875rem",
    animationName: pulse,
    animationDuration: "1.5s",
    animationIterationCount: "infinite",
  },
  errorBox: {
    padding: spacing.md,
    backgroundColor: colors.errorBg,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    borderRadius: radii.md,
    color: colors.errorText,
    fontSize: "0.875rem",
  },
  fullContentCard: {
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    borderRadius: radii.lg,
    padding: spacing.lg,
    color: colors.textMain,
    fontSize: "0.875rem",
    lineHeight: 1.75,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.03)",
  },
  chunkList: {
    display: "flex",
    flexDirection: "column",
    gap: spacing.md,
  },
  chunkItemCard: {
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    borderRadius: radii.lg,
    padding: spacing.md,
    display: "flex",
    flexDirection: "column",
    gap: spacing.sm,
  },
  chunkItemHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    flexWrap: "wrap",
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.xs,
  },
  chunkIdxBadge: {
    backgroundColor: colors.primaryLight,
    color: colors.primaryText,
    fontSize: "0.75rem",
    fontWeight: 700,
    fontFamily: "monospace",
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.sm,
  },
  chunkBreadcrumb: {
    fontSize: "0.75rem",
    color: colors.textMuted,
    fontFamily: "monospace",
    wordBreak: "break-all",
  },
  chunkContentText: {
    fontSize: "0.875rem",
    lineHeight: 1.65,
    color: colors.textMain,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingLeft: spacing.lg,
    paddingRight: spacing.lg,
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: colors.borderSubtle,
    backgroundColor: colors.bgCard,
  },
  footerHint: {
    fontSize: "0.75rem",
    color: colors.textLight,
  },
  closeButton: {
    paddingTop: "7px",
    paddingBottom: "7px",
    paddingLeft: "16px",
    paddingRight: "16px",
    backgroundColor: {
      default: colors.bgSubtle,
      ":hover": colors.bgMuted,
    },
    color: colors.textMain,
    fontSize: "0.8125rem",
    fontWeight: 600,
    borderRadius: radii.md,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderLight,
    cursor: "pointer",
    transition: "background-color 0.15s ease",
  },
});

export interface DocumentModalProps {
  documentId: string | null;
  initialFilename?: string;
  onClose: () => void;
}

export function DocumentModal({ documentId, initialFilename, onClose }: DocumentModalProps) {
  const dialogRef = React.useRef<HTMLDialogElement | null>(null);
  const pressedOutsideRef = React.useRef(false);
  const onCloseRef = React.useRef(onClose);
  const titleId = React.useId();

  React.useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const handleCloseModal = React.useCallback(() => {
    const dialog = dialogRef.current;
    if (dialog && dialog.open) {
      dialog.close();
    }
    onCloseRef.current();
  }, []);

  // Sync native <dialog> modal open/close state with documentId prop
  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (documentId) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [documentId]);

  // Native close listener + fallback for browsers lacking <dialog closedby="any">
  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleNativeClose = () => {
      dialog.returnValue = "";
      onCloseRef.current();
    };
    dialog.addEventListener("close", handleNativeClose);

    let cleanupFallback: (() => void) | undefined;
    if (typeof HTMLDialogElement !== "undefined" && !("closedBy" in HTMLDialogElement.prototype)) {
      const isOutside = (e: MouseEvent | PointerEvent) => {
        if (e.target !== dialog) return false;
        const r = dialog.getBoundingClientRect();
        return (
          e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom
        );
      };
      const onPointerDown = (e: PointerEvent) => {
        pressedOutsideRef.current = isOutside(e);
      };
      const onPointerUp = (e: PointerEvent) => {
        if (pressedOutsideRef.current && isOutside(e)) {
          dialog.close();
        }
        pressedOutsideRef.current = false;
      };
      dialog.addEventListener("pointerdown", onPointerDown);
      dialog.addEventListener("pointerup", onPointerUp);
      cleanupFallback = () => {
        dialog.removeEventListener("pointerdown", onPointerDown);
        dialog.removeEventListener("pointerup", onPointerUp);
      };
    }

    return () => {
      dialog.removeEventListener("close", handleNativeClose);
      if (cleanupFallback) cleanupFallback();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      {...({ closedby: "any" } as Record<string, string>)}
      {...stylex.props(styles.dialogElement)}
    >
      {documentId && (
        <DocumentModalBody
          key={documentId}
          documentId={documentId}
          initialFilename={initialFilename}
          titleId={titleId}
          onCloseModal={handleCloseModal}
        />
      )}
    </dialog>
  );
}

function DocumentModalBody({
  documentId,
  initialFilename,
  titleId,
  onCloseModal,
}: {
  documentId: string;
  initialFilename?: string;
  titleId: string;
  onCloseModal: () => void;
}) {
  const [detail, setDetail] = React.useState<DocumentDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [activeTab, setActiveTab] = React.useState<"full" | "chunks">("full");
  const [copied, setCopied] = React.useState(false);

  // Fetch full document content and ordered chunks on mount for this documentId
  React.useEffect(() => {
    let cancelled = false;
    getDocumentDetail(documentId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : "加载文档内容失败";
          setError(msg || "加载文档内容失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  // Poll while the opened document is still processing in background
  React.useEffect(() => {
    if (detail?.status !== "processing") return;

    let cancelled = false;
    const timer = setInterval(() => {
      getDocumentDetail(documentId)
        .then((data) => {
          if (!cancelled) setDetail(data);
        })
        .catch(() => {
          // Ignore transient polling error while modal is already showing initial state
        });
    }, 2000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [documentId, detail?.status]);

  const handleCopyContent = async () => {
    if (!detail?.content) return;
    try {
      await navigator.clipboard.writeText(detail.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Fallback if clipboard API is restricted
    }
  };

  const handleOpenInNewTab = () => {
    if (!detail) return;
    const blob = new Blob([detail.content || ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  const displayFilename = detail?.filename || initialFilename || "文档内容预览";
  const isPdf = displayFilename.toLowerCase().endsWith(".pdf");

  return (
    <div {...stylex.props(styles.panel)}>
      <div {...stylex.props(styles.header)}>
        <div {...stylex.props(styles.headerTitleArea)}>
          <span {...stylex.props(styles.fileIcon)}>{isPdf ? "📕" : "📄"}</span>
          <div {...stylex.props(styles.titleTextGroup)}>
            <h2 id={titleId} {...stylex.props(styles.dialogTitle)}>
              {displayFilename}
            </h2>
            <div {...stylex.props(styles.metaSubtitle)}>
              <span>文档 ID: {documentId.slice(0, 8)}...</span>
              {detail && <span>· 共 {detail.n_chunks} 个知识切片</span>}
              {detail && <span>· {detail.content.length} 字符</span>}
            </div>
          </div>
        </div>

        <div {...stylex.props(styles.headerActions)}>
          {detail && detail.content && (
            <>
              <button
                type="button"
                onClick={handleCopyContent}
                {...stylex.props(styles.actionBtn, copied && styles.actionBtnSuccess)}
              >
                <span>{copied ? "✓ 已复制全文" : "📋 复制全文"}</span>
              </button>
              <button
                type="button"
                onClick={handleOpenInNewTab}
                {...stylex.props(styles.actionBtn)}
              >
                <span>↗ 新标签页打开</span>
              </button>
            </>
          )}
          <button
            type="button"
            autoFocus
            onClick={onCloseModal}
            {...stylex.props(styles.closeIconButton)}
            aria-label="关闭文档预览"
          >
            ✕
          </button>
        </div>
      </div>

      {detail && (
        <div {...stylex.props(styles.toolbar)}>
          <div {...stylex.props(styles.tabGroup)}>
            <button
              type="button"
              onClick={() => setActiveTab("full")}
              {...stylex.props(styles.tabButton, activeTab === "full" && styles.tabButtonActive)}
            >
              📄 完整文档内容
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("chunks")}
              {...stylex.props(styles.tabButton, activeTab === "chunks" && styles.tabButtonActive)}
            >
              🧩 向量切片视图 ({detail.chunks.length})
            </button>
          </div>
          <span {...stylex.props(styles.statsInfo)}>
            状态:{" "}
            {detail.status === "ready" || detail.status === "completed"
              ? "● 已就绪"
              : detail.status === "processing"
                ? "● 处理中..."
                : detail.status === "failed"
                  ? "✕ 解析失败"
                  : detail.status}
          </span>
        </div>
      )}

      <div {...stylex.props(styles.body)}>
        {loading && (
          <div {...stylex.props(styles.loadingBox)}>
            正在读取文档《{displayFilename}》的完整内容...
          </div>
        )}

        {error && <div {...stylex.props(styles.errorBox)}>读取失败：{error}</div>}

        {detail && !loading && detail.error && (
          <div {...stylex.props(styles.errorBox)}>文档解析异常：{detail.error}</div>
        )}

        {detail && !loading && activeTab === "full" && (
          <div {...stylex.props(styles.fullContentCard)}>
            {detail.content
              ? detail.content
              : detail.status === "processing"
                ? "该文档正在后台进行分块与向量化处理，完成后将自动刷新显示..."
                : detail.error
                  ? `文档解析失败：${detail.error}`
                  : "暂无可显示的文档文本内容。"}
          </div>
        )}

        {detail && !loading && activeTab === "chunks" && (
          <div {...stylex.props(styles.chunkList)}>
            {detail.chunks.length === 0 ? (
              <div {...stylex.props(styles.fullContentCard)}>
                {detail.status === "processing"
                  ? "正在后台切分知识片段与计算向量，完成后将自动展示..."
                  : "当前文档暂无已生成的向量切片。"}
              </div>
            ) : (
              detail.chunks.map((chunk) => (
                <div key={chunk.id} {...stylex.props(styles.chunkItemCard)}>
                  <div {...stylex.props(styles.chunkItemHeader)}>
                    <span {...stylex.props(styles.chunkIdxBadge)}>Chunk #{chunk.idx}</span>
                    <span {...stylex.props(styles.chunkBreadcrumb)}>
                      {chunk.heading
                        ? `章节: ${chunk.heading}`
                        : chunk.page != null
                          ? `第 ${chunk.page} 页`
                          : "正文片段"}
                    </span>
                  </div>
                  <div {...stylex.props(styles.chunkContentText)}>{chunk.content}</div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <div {...stylex.props(styles.footer)}>
        <span {...stylex.props(styles.footerHint)}>
          提示：按 Esc 键或点击弹窗外部空白区域即可关闭预览
        </span>
        <button type="button" onClick={onCloseModal} {...stylex.props(styles.closeButton)}>
          关闭预览
        </button>
      </div>
    </div>
  );
}

export default DocumentModal;
