import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing, radii } from "../styles/tokens.stylex";
import { listDocuments, uploadDocument, deleteDocument, type DocumentItem } from "../lib/api";
import { ensureBackendReadinessProbe, useChatSession } from "../lib/chatStore";
import { DocumentModal } from "../components/DocumentModal";

const pulse = stylex.keyframes({
  "0%": { opacity: 1 },
  "50%": { opacity: 0.4 },
  "100%": { opacity: 1 },
});

const spin = stylex.keyframes({
  "0%": { transform: "rotate(0deg)" },
  "100%": { transform: "rotate(360deg)" },
});

const progressSlide = stylex.keyframes({
  "0%": { transform: "translateX(-100%)" },
  "100%": { transform: "translateX(250%)" },
});

const rowRefreshFlash = stylex.keyframes({
  "0%": { backgroundColor: "#dbeafe" },
  "100%": { backgroundColor: "transparent" },
});

const styles = stylex.create({
  container: {
    display: "flex",
    flexDirection: "column",
    gap: spacing.lg,
    width: "100%",
  },
  headerRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  titleGroup: {
    display: "flex",
    flexDirection: "column",
    gap: spacing.xs,
  },
  title: {
    fontSize: "1.5rem",
    fontWeight: 700,
    color: colors.textMain,
    margin: 0,
    letterSpacing: "-0.025em",
  },
  subtitle: {
    fontSize: "0.875rem",
    color: colors.textMuted,
    margin: 0,
    lineHeight: 1.5,
  },
  actionGroup: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  syncTimeBadge: {
    fontSize: "0.75rem",
    color: colors.textMuted,
    backgroundColor: colors.bgSubtle,
    paddingTop: "5px",
    paddingBottom: "5px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.full,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
  },
  uploadButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: {
      default: colors.primary,
      ":hover": colors.primaryHover,
    },
    color: "#ffffff",
    paddingTop: "9px",
    paddingBottom: "9px",
    paddingLeft: "16px",
    paddingRight: "16px",
    borderRadius: radii.md,
    fontSize: "0.875rem",
    fontWeight: 600,
    cursor: "pointer",
    borderWidth: 0,
    transition: "background-color 0.15s ease",
  },
  uploadButtonDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
    backgroundColor: {
      default: colors.primary,
      ":hover": colors.primary,
    },
  },
  refreshButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: {
      default: colors.bgCard,
      ":hover": colors.bgSubtle,
    },
    color: colors.textMain,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: colors.borderLight,
      ":hover": colors.primary,
    },
    paddingTop: "8px",
    paddingBottom: "8px",
    paddingLeft: "14px",
    paddingRight: "14px",
    borderRadius: radii.md,
    fontSize: "0.875rem",
    fontWeight: 500,
    cursor: "pointer",
    transform: {
      default: "none",
      ":active": "scale(0.97)",
    },
    transition: "all 0.18s ease",
  },
  refreshButtonActive: {
    backgroundColor: colors.primaryLight,
    color: colors.primaryText,
    borderColor: colors.primary,
    cursor: "wait",
  },
  refreshButtonSuccess: {
    backgroundColor: colors.successBg,
    color: colors.successText,
    borderColor: colors.successBorder,
  },
  refreshIcon: {
    display: "inline-block",
    lineHeight: 1,
  },
  refreshIconSpinning: {
    animationName: spin,
    animationDuration: "0.65s",
    animationTimingFunction: "linear",
    animationIterationCount: "infinite",
  },
  hiddenInput: {
    display: "none",
  },
  bannerSuccess: {
    backgroundColor: colors.successBg,
    color: colors.successText,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.successBorder,
    borderRadius: radii.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
    fontSize: "0.875rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  bannerError: {
    backgroundColor: colors.errorBg,
    color: colors.errorText,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    borderRadius: radii.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
    fontSize: "0.875rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  bannerDismiss: {
    backgroundColor: "transparent",
    borderWidth: 0,
    borderStyle: "none",
    color: "currentColor",
    cursor: "pointer",
    fontSize: "1.1rem",
    paddingTop: 0,
    paddingBottom: 0,
    paddingLeft: "4px",
    paddingRight: "4px",
    opacity: {
      default: 0.7,
      ":hover": 1,
    },
  },
  card: {
    position: "relative",
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.05)",
    overflow: "hidden",
    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
  },
  cardRefreshing: {
    borderColor: "#93c5fd",
    boxShadow: "0 0 0 3px rgba(37, 99, 235, 0.1)",
  },
  progressTrack: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: "3px",
    backgroundColor: colors.primaryLight,
    overflow: "hidden",
    zIndex: 2,
  },
  progressBar: {
    width: "45%",
    height: "100%",
    backgroundColor: colors.primary,
    borderRadius: radii.full,
    animationName: progressSlide,
    animationDuration: "0.75s",
    animationTimingFunction: "ease-in-out",
    animationIterationCount: "infinite",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    textAlign: "left",
    fontSize: "0.875rem",
    transition: "opacity 0.2s ease",
  },
  tableRefreshing: {
    opacity: 0.55,
  },
  th: {
    backgroundColor: colors.bgSubtle,
    color: colors.textMuted,
    fontWeight: 600,
    fontSize: "0.75rem",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
  },
  tr: {
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    cursor: "pointer",
    userSelect: "none",
    backgroundColor: {
      default: "transparent",
      ":hover": "#eff6ff",
    },
    transition: "background-color 0.15s ease",
  },
  trActive: {
    backgroundColor: "#eff6ff",
  },
  trFlash: {
    animationName: rowRefreshFlash,
    animationDuration: "0.75s",
    animationTimingFunction: "ease-out",
  },
  td: {
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    paddingLeft: spacing.md,
    paddingRight: spacing.md,
    color: colors.textMain,
    verticalAlign: "middle",
    transition: "box-shadow 0.15s ease",
  },
  tdFirstActive: {
    boxShadow: "inset 4px 0 0 0 #2563eb",
  },
  docNameWrapper: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    fontWeight: 500,
    flexWrap: "wrap",
  },
  docIcon: {
    fontSize: "1.1rem",
  },
  docFilenameText: {
    transition: "color 0.15s ease",
  },
  docFilenameHovered: {
    color: colors.primary,
    fontWeight: 600,
  },
  dblClickHintBadge: {
    fontSize: "0.7rem",
    fontWeight: 600,
    color: colors.primaryText,
    backgroundColor: colors.primaryLight,
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.full,
    opacity: 0,
    transform: "translateX(-4px)",
    transition: "opacity 0.15s ease, transform 0.15s ease",
  },
  dblClickHintVisible: {
    opacity: 1,
    transform: "translateX(0)",
  },
  badgeBase: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.full,
    fontSize: "0.75rem",
    fontWeight: 600,
    borderWidth: 1,
    borderStyle: "solid",
  },
  badgeReady: {
    backgroundColor: colors.successBg,
    color: colors.successText,
    borderColor: colors.successBorder,
  },
  badgeProcessing: {
    backgroundColor: colors.primaryLight,
    color: colors.primaryText,
    borderColor: "#bfdbfe",
    animationName: pulse,
    animationDuration: "2s",
    animationTimingFunction: "cubic-bezier(0.4, 0, 0.6, 1)",
    animationIterationCount: "infinite",
  },
  badgeFailed: {
    backgroundColor: colors.errorBg,
    color: colors.errorText,
    borderColor: colors.errorBorder,
  },
  chunkCountBadge: {
    display: "inline-flex",
    alignItems: "center",
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.md,
    fontSize: "0.8125rem",
    backgroundColor: colors.bgSubtle,
    color: colors.textMuted,
    fontWeight: 500,
  },
  timeText: {
    color: colors.textMuted,
    fontSize: "0.8125rem",
  },
  rowActionsGroup: {
    display: "inline-flex",
    alignItems: "center",
    gap: spacing.xs,
  },
  viewButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.md,
    fontSize: "0.75rem",
    fontWeight: 500,
    color: colors.primaryText,
    backgroundColor: {
      default: colors.primaryLight,
      ":hover": "#bfdbfe",
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "#bfdbfe",
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  deleteButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.md,
    fontSize: "0.75rem",
    fontWeight: 500,
    color: colors.errorText,
    backgroundColor: {
      default: colors.errorBg,
      ":hover": "#ffe4e6",
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: colors.errorBorder,
      ":hover": "#fda4af",
    },
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  emptyState: {
    paddingTop: spacing.xxl,
    paddingBottom: spacing.xxl,
    textAlign: "center",
    color: colors.textMuted,
    fontSize: "0.875rem",
  },
});

export const Route = createFileRoute("/documents")({
  component: DocumentsComponent,
});

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

let cachedDocuments: DocumentItem[] = [];
let hasFetchedDocuments = false;
let cachedUploading = false;
let cachedError: string | null = null;
let cachedSuccessMsg: string | null = null;

function DocumentsComponent() {
  const { backendReady, readinessStatus } = useChatSession();
  const [documents, setDocuments] = React.useState<DocumentItem[]>(() => cachedDocuments);
  const [loading, setLoading] = React.useState<boolean>(() => !hasFetchedDocuments);
  const [uploading, setUploadingState] = React.useState<boolean>(() => cachedUploading);
  const [error, setErrorState] = React.useState<string | null>(() => cachedError);
  const [successMsg, setSuccessMsgState] = React.useState<string | null>(() => cachedSuccessMsg);

  // Manual refresh visual state
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [justRefreshed, setJustRefreshed] = React.useState(false);
  const [lastSyncedAt, setLastSyncedAt] = React.useState<string | null>(null);
  const refreshTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // Row hover & double-click document preview modal state
  const [hoveredDocId, setHoveredDocId] = React.useState<string | null>(null);
  const [previewDoc, setPreviewDoc] = React.useState<{ id: string; filename: string } | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const setUploading = React.useCallback((val: boolean) => {
    cachedUploading = val;
    setUploadingState(val);
  }, []);

  const setError = React.useCallback((val: string | null) => {
    cachedError = val;
    setErrorState(val);
  }, []);

  const setSuccessMsg = React.useCallback((val: string | null) => {
    cachedSuccessMsg = val;
    setSuccessMsgState(val);
  }, []);

  const fetchDocs = React.useCallback(
    async (isManual: boolean = false) => {
      try {
        const items = await listDocuments();
        cachedDocuments = items;
        hasFetchedDocuments = true;
        setDocuments(items);
        setError(null);
        setLoading(false);
        return true;
      } catch (err: unknown) {
        if (!isManual && !backendReady && readinessStatus === "checking") {
          // Backend is still warming up; wait for readiness probe without flashing an error banner
          return false;
        }
        const msg = err instanceof Error ? err.message : "获取文档列表失败";
        setError(msg || "获取文档列表失败");
        setLoading(false);
        return false;
      }
    },
    [backendReady, readinessStatus, setError],
  );

  const handleManualRefresh = React.useCallback(async () => {
    if (isRefreshing) return;
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    setIsRefreshing(true);
    setJustRefreshed(false);

    // Ensure at least 480ms of visual feedback so fast local responses still feel tactile
    const [ok] = await Promise.all([
      fetchDocs(true),
      new Promise((resolve) => setTimeout(resolve, 480)),
    ]);

    setIsRefreshing(false);
    if (ok) {
      const nowStr = new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setLastSyncedAt(nowStr);
      setJustRefreshed(true);
      refreshTimerRef.current = setTimeout(() => {
        setJustRefreshed(false);
      }, 1600);
    }
  }, [fetchDocs, isRefreshing]);

  React.useEffect(() => {
    ensureBackendReadinessProbe();
    let cancelled = false;
    const initialTimer = setTimeout(() => {
      if (!cancelled) {
        void fetchDocs(false);
      }
    }, 0);
    const interval = setInterval(() => {
      if (!cancelled) {
        void fetchDocs(false);
      }
    }, 4000);
    return () => {
      cancelled = true;
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [fetchDocs]);

  React.useEffect(() => {
    return () => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
      }
    };
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (![".md", ".pdf", ".txt", ".markdown"].includes(ext)) {
      setError("仅支持上传 .md、.pdf 或 .txt 格式的技术文档");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const res = await uploadDocument(file);
      setSuccessMsg(`上传成功！已排队进行分块与向量化处理 (文档 ID: ${res.id})`);
      await fetchDocs(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "上传失败";
      setError(msg || "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (doc: DocumentItem) => {
    if (!confirm(`确定要彻底删除文档 "${doc.filename}" 及其关联切片吗？`)) {
      return;
    }

    try {
      await deleteDocument(doc.id);
      if (previewDoc?.id === doc.id) {
        setPreviewDoc(null);
      }
      setDocuments((prev) => {
        const next = prev.filter((d) => d.id !== doc.id);
        cachedDocuments = next;
        return next;
      });
      setSuccessMsg(`文档 "${doc.filename}" 已成功删除`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除文档失败";
      setError(msg || "删除文档失败");
    }
  };

  return (
    <div {...stylex.props(styles.container)}>
      <div {...stylex.props(styles.headerRow)}>
        <div {...stylex.props(styles.titleGroup)}>
          <h1 {...stylex.props(styles.title)}>技术文档管理 (Documents)</h1>
          <p {...stylex.props(styles.subtitle)}>
            管理检索增强生成 (RAG) 系统的源文件。支持 Markdown 与 PDF
            格式，入库后自动提取分块与语义向量。鼠标悬停高亮并左键双击任意文档即可打开查看内容。
          </p>
        </div>

        <div {...stylex.props(styles.actionGroup)}>
          {lastSyncedAt && (
            <span {...stylex.props(styles.syncTimeBadge)}>最后刷新: {lastSyncedAt}</span>
          )}

          <button
            type="button"
            disabled={isRefreshing}
            {...stylex.props(
              styles.refreshButton,
              isRefreshing && styles.refreshButtonActive,
              justRefreshed && !isRefreshing && styles.refreshButtonSuccess,
            )}
            onClick={handleManualRefresh}
          >
            <span {...stylex.props(styles.refreshIcon, isRefreshing && styles.refreshIconSpinning)}>
              {justRefreshed && !isRefreshing ? "✅" : "🔄"}
            </span>
            <span>
              {isRefreshing
                ? "正在刷新..."
                : justRefreshed
                  ? `已刷新 (${documents.length} 篇)`
                  : "刷新列表"}
            </span>
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.pdf,.txt,.markdown"
            onChange={handleFileChange}
            {...stylex.props(styles.hiddenInput)}
          />

          <button
            type="button"
            disabled={uploading}
            {...stylex.props(styles.uploadButton, uploading && styles.uploadButtonDisabled)}
            onClick={() => fileInputRef.current?.click()}
          >
            <span>📤</span>
            <span>{uploading ? "正在上传入库..." : "上传新文档 (md/pdf)"}</span>
          </button>
        </div>
      </div>

      {successMsg && (
        <div {...stylex.props(styles.bannerSuccess)}>
          <span>{successMsg}</span>
          <button
            type="button"
            {...stylex.props(styles.bannerDismiss)}
            onClick={() => setSuccessMsg(null)}
          >
            ×
          </button>
        </div>
      )}

      {error && (
        <div {...stylex.props(styles.bannerError)}>
          <span>{error}</span>
          <button
            type="button"
            {...stylex.props(styles.bannerDismiss)}
            onClick={() => setError(null)}
          >
            ×
          </button>
        </div>
      )}

      <div {...stylex.props(styles.card, isRefreshing && styles.cardRefreshing)}>
        {isRefreshing && (
          <div {...stylex.props(styles.progressTrack)}>
            <div {...stylex.props(styles.progressBar)} />
          </div>
        )}

        <table {...stylex.props(styles.table, isRefreshing && styles.tableRefreshing)}>
          <thead>
            <tr>
              <th {...stylex.props(styles.th)}>文档名称 (双击行打开)</th>
              <th {...stylex.props(styles.th)}>状态</th>
              <th {...stylex.props(styles.th)}>切片数量</th>
              <th {...stylex.props(styles.th)}>上传时间</th>
              <th {...stylex.props(styles.th)}>操作</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 && loading ? (
              <tr>
                <td colSpan={5} {...stylex.props(styles.emptyState)}>
                  正在加载技术文档列表...
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={5} {...stylex.props(styles.emptyState)}>
                  暂无已上传文档，请点击上方按钮上传技术文档 (.md / .pdf / .txt)
                </td>
              </tr>
            ) : (
              documents.map((doc) => {
                const isReady = doc.status === "ready" || doc.status === "completed";
                const isProcessing = doc.status === "processing";
                const isFailed = doc.status === "failed";
                const isHovered = hoveredDocId === doc.id;
                const isSelected = previewDoc?.id === doc.id;
                const isRowActive = isHovered || isSelected;

                return (
                  <tr
                    key={doc.id}
                    title="鼠标左键双击打开并查看文档内容"
                    onMouseEnter={() => setHoveredDocId(doc.id)}
                    onMouseLeave={() => setHoveredDocId((prev) => (prev === doc.id ? null : prev))}
                    onDoubleClick={(e) => {
                      if (e.button !== 0) return;
                      setPreviewDoc({ id: doc.id, filename: doc.filename });
                    }}
                    {...stylex.props(
                      styles.tr,
                      isRowActive && styles.trActive,
                      justRefreshed && !isRowActive && styles.trFlash,
                    )}
                  >
                    <td {...stylex.props(styles.td, isRowActive && styles.tdFirstActive)}>
                      <div {...stylex.props(styles.docNameWrapper)}>
                        <span {...stylex.props(styles.docIcon)}>
                          {doc.filename.endsWith(".pdf") ? "📕" : "📄"}
                        </span>
                        <span
                          {...stylex.props(
                            styles.docFilenameText,
                            isRowActive && styles.docFilenameHovered,
                          )}
                        >
                          {doc.filename}
                        </span>
                        <span
                          {...stylex.props(
                            styles.dblClickHintBadge,
                            isRowActive && styles.dblClickHintVisible,
                          )}
                        >
                          双击打开查看
                        </span>
                      </div>
                    </td>
                    <td {...stylex.props(styles.td)}>
                      {isReady && (
                        <span {...stylex.props(styles.badgeBase, styles.badgeReady)}>
                          ● 已就绪 (Ready)
                        </span>
                      )}
                      {isProcessing && (
                        <span {...stylex.props(styles.badgeBase, styles.badgeProcessing)}>
                          ● 处理中 (Processing)
                        </span>
                      )}
                      {isFailed && (
                        <span
                          title={doc.error || "Ingestion error"}
                          {...stylex.props(styles.badgeBase, styles.badgeFailed)}
                        >
                          ✕ 失败 (Failed)
                        </span>
                      )}
                    </td>
                    <td {...stylex.props(styles.td)}>
                      <span {...stylex.props(styles.chunkCountBadge)}>{doc.n_chunks} chunks</span>
                    </td>
                    <td {...stylex.props(styles.td)}>
                      <span {...stylex.props(styles.timeText)}>{formatDate(doc.created_at)}</span>
                    </td>
                    <td {...stylex.props(styles.td)} onDoubleClick={(e) => e.stopPropagation()}>
                      <div {...stylex.props(styles.rowActionsGroup)}>
                        <button
                          type="button"
                          {...stylex.props(styles.viewButton)}
                          onClick={(e) => {
                            e.stopPropagation();
                            setPreviewDoc({ id: doc.id, filename: doc.filename });
                          }}
                        >
                          📖 查看
                        </button>
                        <button
                          type="button"
                          {...stylex.props(styles.deleteButton)}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDelete(doc);
                          }}
                        >
                          🗑️ 删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <DocumentModal
        documentId={previewDoc?.id ?? null}
        initialFilename={previewDoc?.filename}
        onClose={() => setPreviewDoc(null)}
      />
    </div>
  );
}
