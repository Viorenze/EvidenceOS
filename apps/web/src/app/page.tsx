"use client";

import React, { useState, useRef } from "react";
import ChunkModal from "../components/ChunkModal";
import { CitationItem, DoneData, StepItem, streamChat } from "../lib/api";

export default function ChatPage() {
  const [question, setQuestion] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [steps, setSteps] = useState<StepItem[]>([]);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<CitationItem[]>([]);
  const [doneData, setDoneData] = useState<DoneData | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Active chunk inspected in modal
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [stepsExpanded, setStepsExpanded] = useState(true);

  const abortControllerRef = useRef<AbortController | null>(null);

  const handleAsk = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = question.trim();
    if (!q || isStreaming) return;

    // Reset state for new round
    setIsStreaming(true);
    setSteps([]);
    setAnswer("");
    setCitations([]);
    setDoneData(null);
    setErrorMessage(null);
    setStepsExpanded(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await streamChat(
        q,
        {
          onStep: (step) => {
            setSteps((prev) => [...prev, step]);
          },
          onToken: (token) => {
            setAnswer((prev) => prev + token);
          },
          onCitations: (cits) => {
            setCitations(cits);
          },
          onDone: (done) => {
            setDoneData(done);
            setIsStreaming(false);
          },
          onError: (errMsg) => {
            setErrorMessage(errMsg);
            setIsStreaming(false);
          },
        },
        controller.signal
      );
    } catch (err: any) {
      setErrorMessage(err.message || "流式传输异常");
      setIsStreaming(false);
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
  };

  /**
   * Render answer text and turn [n] markers into clickable citation badges.
   */
  const renderFormattedAnswer = (text: string) => {
    if (!text) return null;

    // Split by citation markers like [1], [2]
    const parts = text.split(/(\[\d+\])/g);

    return parts.map((part, index) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (match) {
        const n = parseInt(match[1], 10);
        const citation = citations.find((c) => c.n === n);
        return (
          <button
            key={index}
            onClick={() => {
              if (citation) setSelectedChunkId(citation.chunk_id);
            }}
            title={citation ? `查看引用 [${n}]: ${citation.document} (点击对账原文)` : `引用 [${n}]`}
            className="inline-flex items-center justify-center px-1.5 py-0.5 mx-0.5 text-xs font-bold text-blue-700 bg-blue-100 hover:bg-blue-200 border border-blue-300 rounded transition transform hover:scale-105 align-baseline"
          >
            [{n}]
          </button>
        );
      }
      return <span key={index}>{part}</span>;
    });
  };

  return (
    <div className="flex-1 flex flex-col max-w-4xl w-full mx-auto space-y-6">
      {/* Question Form */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <form onSubmit={handleAsk} className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="针对已上传的技术文档提问（例如：FastAPI 如何做依赖注入？pgvector 索引类型有哪些？）..."
            className="flex-1 px-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            disabled={isStreaming}
          />
          <div className="flex gap-2">
            {!isStreaming ? (
              <button
                type="submit"
                disabled={!question.trim()}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg shadow-sm transition"
              >
                提问 (Ask)
              </button>
            ) : (
              <button
                type="button"
                onClick={handleStop}
                className="px-5 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 text-sm font-medium rounded-lg transition"
              >
                停止 (Stop)
              </button>
            )}
          </div>
        </form>

        <div className="flex flex-wrap gap-2 mt-3 text-xs text-slate-500">
          <span className="font-semibold text-slate-400">试一试:</span>
          <button
            type="button"
            onClick={() => setQuestion("FastAPI 如何做依赖注入？")}
            className="text-blue-600 hover:underline"
          >
            FastAPI 依赖注入
          </button>
          <span>·</span>
          <button
            type="button"
            onClick={() => setQuestion("pgvector 支持哪些相似度索引？")}
            className="text-blue-600 hover:underline"
          >
            pgvector 索引类型
          </button>
          <span>·</span>
          <button
            type="button"
            onClick={() => setQuestion("超导量子计算机接入配置方案是什么？")}
            className="text-slate-600 hover:underline"
          >
            超导量子计算机 (测试拒答)
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-rose-500 text-base">⚠️</span>
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-rose-400 hover:text-rose-700">✕</button>
        </div>
      )}

      {/* Agent Thinking Steps Accordion */}
      {steps.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden transition">
          <div
            onClick={() => setStepsExpanded(!stepsExpanded)}
            className="p-3.5 bg-slate-50 border-b border-slate-200 flex justify-between items-center cursor-pointer hover:bg-slate-100/70 transition"
          >
            <div className="flex items-center gap-2">
              <span className="text-xs bg-slate-200 text-slate-700 font-mono font-semibold px-2 py-0.5 rounded">
                LangGraph 思考回路 ({steps.length})
              </span>
              <span className="text-xs text-slate-500">
                {isStreaming ? "Agent 正在执行循环条件图..." : "执行完成"}
              </span>
            </div>
            <span className="text-xs text-slate-400 font-medium">
              {stepsExpanded ? "折叠 ▲" : "展开详情 ▼"}
            </span>
          </div>

          {stepsExpanded && (
            <div className="p-4 space-y-2.5 bg-slate-50/50 max-h-60 overflow-y-auto font-mono text-xs">
              {steps.map((st, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase shrink-0 ${
                    st.node === "retrieve" ? "bg-indigo-100 text-indigo-700" :
                    st.node === "grade" ? "bg-amber-100 text-amber-700" :
                    st.node === "rewrite" ? "bg-purple-100 text-purple-700" :
                    st.node === "generate" ? "bg-blue-100 text-blue-700" :
                    st.node === "verify_citations" ? "bg-emerald-100 text-emerald-700" :
                    st.node === "refuse" ? "bg-rose-100 text-rose-700" :
                    "bg-slate-200 text-slate-800"
                  }`}>
                    {st.node}
                  </span>
                  <div className="flex-1 text-slate-700 break-words pt-0.5">
                    {st.detail}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Answer & Citations Container */}
      {(answer || isStreaming) && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span>🤖</span>
              <span>EvidenceOS 严谨回答</span>
              {doneData?.refused && (
                <span className="bg-rose-100 text-rose-800 text-xs px-2 py-0.5 rounded-full font-medium ml-2">
                  无证据已拒答 (Refused)
                </span>
              )}
            </h3>

            {doneData && (
              <span className="text-xs text-slate-400 font-mono">
                耗时: {doneData.latency_ms} ms · Run ID: {doneData.run_id.slice(0, 8)}...
              </span>
            )}
          </div>

          {/* Answer Body */}
          <div className="text-slate-800 leading-relaxed text-sm whitespace-pre-wrap font-sans">
            {renderFormattedAnswer(answer)}
            {isStreaming && !answer && (
              <span className="text-slate-400 text-xs animate-pulse">
                检索与引用校验中，即将流式呈现最终答案...
              </span>
            )}
          </div>

          {/* Citation List Footnote */}
          {citations.length > 0 && (
            <div className="border-t border-slate-100 pt-4 space-y-3">
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                <span>📚</span>
                <span>引用来源依据 (点击查看切片原文)</span>
              </h4>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {citations.map((c) => (
                  <div
                    key={c.n}
                    onClick={() => setSelectedChunkId(c.chunk_id)}
                    className="p-3 bg-slate-50 hover:bg-blue-50/70 border border-slate-200 hover:border-blue-300 rounded-lg cursor-pointer transition text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between font-medium">
                      <span className="text-blue-700 font-bold flex items-center gap-1">
                        [{c.n}] {c.document}
                      </span>
                      {c.page && <span className="text-slate-400">P.{c.page}</span>}
                    </div>

                    {c.heading && (
                      <p className="text-[11px] text-slate-500 font-mono truncate">
                        {c.heading}
                      </p>
                    )}

                    <p className="text-slate-600 line-clamp-2 text-[11px] italic">
                      "{c.snippet}"
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Chunk Detail Inspection Modal */}
      <ChunkModal
        chunkId={selectedChunkId}
        onClose={() => setSelectedChunkId(null)}
      />
    </div>
  );
}
