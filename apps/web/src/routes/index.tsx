import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing, radii } from "../styles/tokens.stylex";
import { ChunkModal } from "../components/ChunkModal";
import {
  ensureBackendReadinessProbe,
  setChatErrorMessage,
  setChatQuestion,
  setChatSelectedChunkId,
  setChatStepsExpanded,
  startChatAsk,
  stopChatAsk,
  useChatSession,
} from "../lib/chatStore";

const spin = stylex.keyframes({
  "0%": { transform: "rotate(0deg)" },
  "100%": { transform: "rotate(360deg)" },
});

const pulse = stylex.keyframes({
  "0%": { opacity: 1 },
  "50%": { opacity: 0.4 },
  "100%": { opacity: 1 },
});

const styles = stylex.create({
  container: {
    display: "flex",
    flexDirection: "column",
    gap: spacing.lg,
    maxWidth: "896px",
    width: "100%",
    marginLeft: "auto",
    marginRight: "auto",
  },
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    padding: spacing.lg,
    boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05)",
  },
  form: {
    display: "flex",
    flexDirection: {
      default: "column",
      "@media (min-width: 640px)": "row",
    },
    gap: spacing.sm,
  },
  textareaWrapper: {
    flexGrow: 1,
    display: "flex",
  },
  textarea: {
    width: "100%",
    minHeight: "44px",
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "16px",
    paddingRight: "16px",
    fontSize: "0.875rem",
    lineHeight: 1.5,
    backgroundColor: {
      default: colors.bgPage,
      ":focus": colors.bgCard,
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: colors.borderLight,
      ":focus": colors.primary,
    },
    borderRadius: radii.md,
    color: colors.textMain,
    outline: "none",
    resize: "vertical",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    boxSizing: "border-box",
    transition: "border-color 0.15s ease, background-color 0.15s ease",
  },
  textareaDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },
  actionButtonGroup: {
    display: "flex",
    alignItems: "flex-start",
  },
  submitButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    backgroundColor: {
      default: colors.primary,
      ":hover": colors.primaryHover,
    },
    color: "#ffffff",
    borderWidth: 0,
    borderRadius: radii.md,
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "20px",
    paddingRight: "20px",
    fontSize: "0.875rem",
    fontWeight: 600,
    cursor: "pointer",
    minWidth: "110px",
    minHeight: "44px",
    boxShadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    transition: "background-color 0.15s ease",
  },
  submitButtonDisabled: {
    opacity: 0.5,
    cursor: "not-allowed",
    backgroundColor: {
      default: colors.primary,
      ":hover": colors.primary,
    },
  },
  stopButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    backgroundColor: {
      default: colors.errorBg,
      ":hover": "#fee2e2",
    },
    color: colors.errorText,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    borderRadius: radii.md,
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "20px",
    paddingRight: "20px",
    fontSize: "0.875rem",
    fontWeight: 600,
    cursor: "pointer",
    minWidth: "110px",
    minHeight: "44px",
    transition: "background-color 0.15s ease",
  },
  spinner: {
    width: "14px",
    height: "14px",
    borderWidth: 2,
    borderStyle: "solid",
    borderColor: "rgba(255, 255, 255, 0.4)",
    borderTopColor: "#ffffff",
    borderRadius: radii.full,
    animationName: spin,
    animationDuration: "0.8s",
    animationIterationCount: "infinite",
    animationTimingFunction: "linear",
  },
  metaBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: colors.borderSubtle,
    flexWrap: "wrap",
    gap: spacing.sm,
    fontSize: "0.75rem",
  },
  suggestionsGroup: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.xs,
    color: colors.textMuted,
  },
  suggestionsLabel: {
    fontWeight: 600,
    color: colors.textLight,
    marginRight: "2px",
  },
  suggestionButton: {
    backgroundColor: "transparent",
    borderWidth: 0,
    color: colors.primary,
    cursor: "pointer",
    fontSize: "0.75rem",
    padding: 0,
    textDecoration: {
      default: "none",
      ":hover": "underline",
    },
    transition: "text-decoration 0.15s ease",
  },
  suggestionButtonMuted: {
    backgroundColor: "transparent",
    borderWidth: 0,
    color: colors.textMuted,
    cursor: "pointer",
    fontSize: "0.75rem",
    padding: 0,
    textDecoration: {
      default: "none",
      ":hover": "underline",
    },
    transition: "text-decoration 0.15s ease",
  },
  suggestionDot: {
    color: colors.textLight,
    marginLeft: "2px",
    marginRight: "2px",
  },
  readinessBadgeChecking: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "0.75rem",
    color: colors.warningText,
    backgroundColor: colors.warningBg,
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.full,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.warningBorder,
    fontWeight: 500,
  },
  readinessBadgeReady: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "0.75rem",
    color: colors.successText,
    backgroundColor: colors.successBg,
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.full,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.successBorder,
    fontWeight: 500,
  },
  readinessBadgeTimeout: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "0.75rem",
    color: colors.errorText,
    backgroundColor: colors.errorBg,
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "10px",
    paddingRight: "10px",
    borderRadius: radii.full,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    fontWeight: 500,
  },
  statusPulseDot: {
    width: "8px",
    height: "8px",
    borderRadius: radii.full,
    backgroundColor: "#f59e0b",
    animationName: pulse,
    animationDuration: "1.2s",
    animationIterationCount: "infinite",
  },
  statusReadyDot: {
    width: "8px",
    height: "8px",
    borderRadius: radii.full,
    backgroundColor: "#10b981",
  },
  statusTimeoutDot: {
    width: "8px",
    height: "8px",
    borderRadius: radii.full,
    backgroundColor: "#ef4444",
  },
  errorBanner: {
    padding: spacing.md,
    backgroundColor: colors.errorBg,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.errorBorder,
    borderRadius: radii.lg,
    color: colors.errorText,
    fontSize: "0.875rem",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  errorContent: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
  },
  errorDismiss: {
    backgroundColor: "transparent",
    borderWidth: 0,
    color: colors.errorText,
    cursor: "pointer",
    fontSize: "1rem",
    fontWeight: 700,
    padding: spacing.xs,
    lineHeight: 1,
  },
  stepsCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    overflow: "hidden",
    boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.05)",
  },
  stepsHeader: {
    padding: spacing.md,
    backgroundColor: colors.bgPage,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    cursor: "pointer",
    userSelect: "none",
  },
  stepsHeaderLeft: {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  stepsCountBadge: {
    fontSize: "0.75rem",
    backgroundColor: colors.bgMuted,
    color: colors.textMain,
    fontFamily: "monospace",
    fontWeight: 600,
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.sm,
  },
  stepsSubtext: {
    fontSize: "0.75rem",
    color: colors.textMuted,
  },
  stepsToggle: {
    fontSize: "0.75rem",
    color: colors.textLight,
    fontWeight: 500,
  },
  stepsBody: {
    padding: spacing.md,
    display: "flex",
    flexDirection: "column",
    gap: spacing.sm,
    maxHeight: "240px",
    overflowY: "auto",
    fontFamily: "monospace",
    fontSize: "0.75rem",
    backgroundColor: "#fafbfc",
  },
  stepItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: spacing.sm,
  },
  stepBadgeBase: {
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.sm,
    fontSize: "0.6875rem",
    fontWeight: 700,
    textTransform: "uppercase",
    flexShrink: 0,
  },
  badgeRetrieve: {
    backgroundColor: "#e0e7ff",
    color: "#4338ca",
  },
  badgeGrade: {
    backgroundColor: "#fef3c7",
    color: "#b45309",
  },
  badgeRewrite: {
    backgroundColor: "#f3e8ff",
    color: "#7e22ce",
  },
  badgeGenerate: {
    backgroundColor: "#dbeafe",
    color: "#1d4ed8",
  },
  badgeVerifyCitations: {
    backgroundColor: "#d1fae5",
    color: "#047857",
  },
  badgeRefuse: {
    backgroundColor: "#ffe4e6",
    color: "#be123c",
  },
  badgeDefault: {
    backgroundColor: "#e2e8f0",
    color: "#1e293b",
  },
  stepDetail: {
    flexGrow: 1,
    color: colors.textMain,
    wordBreak: "break-word",
    paddingTop: "2px",
  },
  answerCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    padding: spacing.lg,
    display: "flex",
    flexDirection: "column",
    gap: spacing.lg,
    boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.05)",
  },
  answerHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomStyle: "solid",
    borderBottomColor: colors.borderSubtle,
    paddingBottom: spacing.sm,
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  answerHeaderTitle: {
    fontSize: "0.875rem",
    fontWeight: 700,
    color: colors.textMain,
    display: "flex",
    alignItems: "center",
    gap: spacing.xs,
    margin: 0,
  },
  refusalBadge: {
    backgroundColor: colors.errorBg,
    color: colors.errorText,
    fontSize: "0.75rem",
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: radii.full,
    fontWeight: 500,
    marginLeft: spacing.xs,
  },
  metricsBadge: {
    fontSize: "0.75rem",
    color: colors.textLight,
    fontFamily: "monospace",
  },
  answerBody: {
    color: colors.textMain,
    lineHeight: 1.65,
    fontSize: "0.875rem",
    whiteSpace: "pre-wrap",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  streamingPulseText: {
    color: colors.textLight,
    fontSize: "0.75rem",
    animationName: pulse,
    animationDuration: "1.5s",
    animationIterationCount: "infinite",
  },
  codeBlockPre: {
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    padding: spacing.md,
    backgroundColor: "#0f172a",
    color: "#f8fafc",
    borderRadius: radii.md,
    fontSize: "0.75rem",
    fontFamily: "monospace",
    overflowX: "auto",
    whiteSpace: "pre",
    lineHeight: 1.6,
  },
  codeBlockCode: {
    fontFamily: "monospace",
  },
  inlineCode: {
    paddingTop: "2px",
    paddingBottom: "2px",
    paddingLeft: "6px",
    paddingRight: "6px",
    marginLeft: "2px",
    marginRight: "2px",
    backgroundColor: colors.bgSubtle,
    color: colors.textMain,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: colors.borderSubtle,
    borderRadius: radii.sm,
    fontSize: "0.75rem",
    fontFamily: "monospace",
  },
  citationBadgeButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    paddingTop: "1px",
    paddingBottom: "1px",
    paddingLeft: "6px",
    paddingRight: "6px",
    marginLeft: "2px",
    marginRight: "2px",
    fontSize: "0.75rem",
    fontWeight: 700,
    color: "#1d4ed8",
    backgroundColor: {
      default: "#dbeafe",
      ":hover": "#bfdbfe",
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: "#93c5fd",
      ":hover": "#60a5fa",
    },
    borderRadius: radii.sm,
    cursor: "pointer",
    verticalAlign: "baseline",
    lineHeight: 1.2,
    transform: {
      default: "none",
      ":hover": "scale(1.05)",
    },
    transition: "all 0.15s ease",
  },
  footnotesContainer: {
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: colors.borderSubtle,
    paddingTop: spacing.md,
    display: "flex",
    flexDirection: "column",
    gap: spacing.sm,
  },
  footnotesTitle: {
    fontSize: "0.75rem",
    fontWeight: 700,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    display: "flex",
    alignItems: "center",
    gap: spacing.xs,
    margin: 0,
  },
  citationGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: spacing.sm,
  },
  citationCard: {
    padding: spacing.md,
    backgroundColor: {
      default: colors.bgPage,
      ":hover": "#eff6ff",
    },
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: {
      default: colors.borderSubtle,
      ":hover": "#93c5fd",
    },
    borderRadius: radii.md,
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    fontSize: "0.75rem",
    transition: "all 0.15s ease",
  },
  citationCardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    fontWeight: 500,
  },
  citationDocName: {
    color: colors.primaryText,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    gap: "4px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "200px",
  },
  citationPage: {
    color: colors.textLight,
    flexShrink: 0,
  },
  citationHeading: {
    fontSize: "0.6875rem",
    color: colors.textMuted,
    fontFamily: "monospace",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    margin: 0,
  },
  citationSnippet: {
    color: colors.textMain,
    fontSize: "0.6875rem",
    fontStyle: "italic",
    margin: 0,
    lineHeight: 1.4,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
});

export const Route = createFileRoute("/")({
  component: ChatRouteComponent,
});

function ChatRouteComponent() {
  const {
    question,
    isStreaming,
    steps,
    answer,
    citations,
    doneData,
    errorMessage,
    backendReady,
    readinessStatus,
    selectedChunkId,
    stepsExpanded,
  } = useChatSession();

  const setQuestion = setChatQuestion;
  const setSelectedChunkId = setChatSelectedChunkId;
  const setStepsExpanded = setChatStepsExpanded;
  const setErrorMessage = setChatErrorMessage;

  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  // Ensure singleton backend readiness probe is active
  React.useEffect(() => {
    ensureBackendReadinessProbe();
  }, []);

  const handleAsk = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    await startChatAsk();
  };

  const handleStop = () => {
    stopChatAsk();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      if (e.nativeEvent.isComposing || e.keyCode === 229) {
        return;
      }
      e.preventDefault();
      void handleAsk();
    }
  };

  const selectSuggestion = (text: string) => {
    setQuestion(text);
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  const getNodeBadgeStyle = (node: string) => {
    switch (node) {
      case "retrieve":
        return styles.badgeRetrieve;
      case "grade":
        return styles.badgeGrade;
      case "rewrite":
        return styles.badgeRewrite;
      case "generate":
        return styles.badgeGenerate;
      case "verify_citations":
        return styles.badgeVerifyCitations;
      case "refuse":
        return styles.badgeRefuse;
      default:
        return styles.badgeDefault;
    }
  };

  /**
   * Render answer text and turn valid [n] markers into clickable citation badges.
   * Shields code fences and inline code, and ignores array/subscript notation like arr[1] or data[0].
   */
  const renderFormattedAnswer = (text: string) => {
    if (!text) return null;

    // 1. Split text into alternating prose and code blocks (fenced ```...``` or inline `...`)
    const segments = text.split(/(```[\s\S]*?```|`[^`\n]+`)/g);

    return segments.map((segment, segIdx) => {
      // If segment is a fenced code block
      if (segment.startsWith("```") && segment.endsWith("```")) {
        const codeLines = segment.slice(3, -3).replace(/^[a-zA-Z0-9_+-]*\r?\n/, "");
        return (
          <pre key={segIdx} {...stylex.props(styles.codeBlockPre)}>
            <code {...stylex.props(styles.codeBlockCode)}>{codeLines}</code>
          </pre>
        );
      }

      // If segment is inline code
      if (segment.startsWith("`") && segment.endsWith("`") && segment.length >= 2) {
        const inlineCode = segment.slice(1, -1);
        return (
          <code key={segIdx} {...stylex.props(styles.inlineCode)}>
            {inlineCode}
          </code>
        );
      }

      // 2. In prose: match [n] not preceded by identifier/subscript characters (?<![a-zA-Z0-9_])
      // Only match 1-indexed citations [1], [2], etc. (never [0])
      const parts = segment.split(/(?<![a-zA-Z0-9_])(\[[1-9]\d*\])/g);

      return (
        <span key={segIdx}>
          {parts.map((part, partIdx) => {
            const match = part.match(/^\[([1-9]\d*)\]$/);
            if (match) {
              const n = parseInt(match[1], 10);
              const citation = citations.find((c) => c.n === n);
              if (citation) {
                return (
                  <button
                    key={partIdx}
                    type="button"
                    onClick={() => setSelectedChunkId(citation.chunk_id)}
                    title={`查看引用 [${n}]: ${citation.document} (点击对账原文)`}
                    {...stylex.props(styles.citationBadgeButton)}
                  >
                    [{n}]
                  </button>
                );
              }
            }
            return <span key={partIdx}>{part}</span>;
          })}
        </span>
      );
    });
  };

  return (
    <div {...stylex.props(styles.container)}>
      {/* Question Form */}
      <div {...stylex.props(styles.card)}>
        <form onSubmit={handleAsk} {...stylex.props(styles.form)}>
          <div {...stylex.props(styles.textareaWrapper)}>
            <textarea
              ref={textareaRef}
              rows={2}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                backendReady
                  ? "针对已上传的技术文档提问（例如：FastAPI 如何做依赖注入？pgvector 索引类型有哪些？）..."
                  : "正在启动 AI 引擎，请稍候..."
              }
              disabled={isStreaming}
              {...stylex.props(styles.textarea, isStreaming && styles.textareaDisabled)}
            />
          </div>
          <div {...stylex.props(styles.actionButtonGroup)}>
            {!isStreaming ? (
              <button
                type="submit"
                disabled={!backendReady || !question.trim()}
                {...stylex.props(
                  styles.submitButton,
                  (!backendReady || !question.trim()) && styles.submitButtonDisabled,
                )}
              >
                {!backendReady ? (
                  <>
                    <span {...stylex.props(styles.spinner)} />
                    <span>启动中...</span>
                  </>
                ) : (
                  <span>提问 (Ask)</span>
                )}
              </button>
            ) : (
              <button type="button" onClick={handleStop} {...stylex.props(styles.stopButton)}>
                停止 (Stop)
              </button>
            )}
          </div>
        </form>

        <div {...stylex.props(styles.metaBar)}>
          <div {...stylex.props(styles.suggestionsGroup)}>
            <span {...stylex.props(styles.suggestionsLabel)}>试一试:</span>
            <button
              type="button"
              onClick={() => selectSuggestion("FastAPI 如何做依赖注入？")}
              {...stylex.props(styles.suggestionButton)}
            >
              FastAPI 依赖注入
            </button>
            <span {...stylex.props(styles.suggestionDot)}>·</span>
            <button
              type="button"
              onClick={() => selectSuggestion("pgvector 支持哪些相似度索引？")}
              {...stylex.props(styles.suggestionButton)}
            >
              pgvector 索引类型
            </button>
            <span {...stylex.props(styles.suggestionDot)}>·</span>
            <button
              type="button"
              onClick={() => selectSuggestion("超导量子计算机接入配置方案是什么？")}
              {...stylex.props(styles.suggestionButtonMuted)}
            >
              超导量子计算机 (测试拒答)
            </button>
          </div>

          <div>
            {readinessStatus === "checking" && (
              <span {...stylex.props(styles.readinessBadgeChecking)}>
                <span {...stylex.props(styles.statusPulseDot)} />
                正在启动 AI 引擎…
              </span>
            )}
            {readinessStatus === "ready" && (
              <span {...stylex.props(styles.readinessBadgeReady)}>
                <span {...stylex.props(styles.statusReadyDot)} />
                AI 引擎已就绪
              </span>
            )}
            {readinessStatus === "timeout" && (
              <span {...stylex.props(styles.readinessBadgeTimeout)}>
                <span {...stylex.props(styles.statusTimeoutDot)} />
                AI 引擎响应超时
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div {...stylex.props(styles.errorBanner)}>
          <div {...stylex.props(styles.errorContent)}>
            <span>⚠️</span>
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            {...stylex.props(styles.errorDismiss)}
            aria-label="关闭错误提示"
          >
            ✕
          </button>
        </div>
      )}

      {/* LangGraph Thinking Steps Accordion */}
      {steps.length > 0 && (
        <div {...stylex.props(styles.stepsCard)}>
          <div
            {...stylex.props(styles.stepsHeader)}
            onClick={() => setStepsExpanded(!stepsExpanded)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setStepsExpanded(!stepsExpanded);
              }
            }}
          >
            <div {...stylex.props(styles.stepsHeaderLeft)}>
              <span {...stylex.props(styles.stepsCountBadge)}>
                LangGraph 思考回路 ({steps.length})
              </span>
              <span {...stylex.props(styles.stepsSubtext)}>
                {isStreaming ? "Agent 正在执行循环条件图..." : "执行完成"}
              </span>
            </div>
            <span {...stylex.props(styles.stepsToggle)}>
              {stepsExpanded ? "折叠 ▲" : "展开详情 ▼"}
            </span>
          </div>

          {stepsExpanded && (
            <div {...stylex.props(styles.stepsBody)}>
              {steps.map((st, i) => (
                <div key={i} {...stylex.props(styles.stepItem)}>
                  <span {...stylex.props(styles.stepBadgeBase, getNodeBadgeStyle(st.node))}>
                    {st.node}
                  </span>
                  <div {...stylex.props(styles.stepDetail)}>{st.detail}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Answer & Citations Container */}
      {(answer || isStreaming) && (
        <div {...stylex.props(styles.answerCard)}>
          <div {...stylex.props(styles.answerHeader)}>
            <h3 {...stylex.props(styles.answerHeaderTitle)}>
              <span>🤖</span>
              <span>EvidenceOS 严谨回答</span>
              {doneData?.refused && (
                <span {...stylex.props(styles.refusalBadge)}>无证据已拒答 (Refused)</span>
              )}
            </h3>

            {doneData && (
              <span {...stylex.props(styles.metricsBadge)}>
                耗时: {doneData.latency_ms} ms · Run ID: {doneData.run_id.slice(0, 8)}...
              </span>
            )}
          </div>

          {/* Answer Body */}
          <div {...stylex.props(styles.answerBody)}>
            {renderFormattedAnswer(answer)}
            {isStreaming && !answer && (
              <span {...stylex.props(styles.streamingPulseText)}>
                检索与引用校验中，即将流式呈现最终答案...
              </span>
            )}
          </div>

          {/* Citation List Footnote */}
          {citations.length > 0 && (
            <div {...stylex.props(styles.footnotesContainer)}>
              <h4 {...stylex.props(styles.footnotesTitle)}>
                <span>📚</span>
                <span>引用来源依据 (点击查看切片原文)</span>
              </h4>

              <div {...stylex.props(styles.citationGrid)}>
                {citations.map((c) => (
                  <div
                    key={c.n}
                    onClick={() => setSelectedChunkId(c.chunk_id)}
                    {...stylex.props(styles.citationCard)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedChunkId(c.chunk_id);
                      }
                    }}
                  >
                    <div {...stylex.props(styles.citationCardHeader)}>
                      <span {...stylex.props(styles.citationDocName)}>
                        [{c.n}] {c.document}
                      </span>
                      {c.page != null && (
                        <span {...stylex.props(styles.citationPage)}>P.{c.page}</span>
                      )}
                    </div>

                    {c.heading && <p {...stylex.props(styles.citationHeading)}>{c.heading}</p>}

                    <p {...stylex.props(styles.citationSnippet)}>"{c.snippet}"</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Chunk Detail Inspection Modal */}
      <ChunkModal chunkId={selectedChunkId} onClose={() => setSelectedChunkId(null)} />
    </div>
  );
}
