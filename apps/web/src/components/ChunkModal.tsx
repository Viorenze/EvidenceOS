"use client";

import React, { useEffect, useState } from "react";
import { ChunkDetail, getChunkDetail } from "../lib/api";

interface ChunkModalProps {
  chunkId: string | null;
  onClose: () => void;
}

export default function ChunkModal({ chunkId, onClose }: ChunkModalProps) {
  const [detail, setDetail] = useState<ChunkDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chunkId) {
      setDetail(null);
      return;
    }

    setLoading(true);
    setError(null);
    getChunkDetail(chunkId)
      .then((data) => setDetail(data))
      .catch((err) => setError(err.message || "Failed to load chunk"))
      .finally(() => setLoading(false));
  }, [chunkId]);

  if (!chunkId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex justify-end transition-opacity">
      <div className="bg-white w-full max-w-xl h-full shadow-2xl flex flex-col p-6 overflow-hidden animate-slide-in">
        <div className="flex items-center justify-between border-b border-slate-200 pb-4">
          <div className="flex items-center space-x-2">
            <span className="bg-blue-100 text-blue-800 text-xs font-semibold px-2.5 py-1 rounded">
              引用原文对账
            </span>
            <span className="text-xs text-slate-400 font-mono">ID: {chunkId.slice(0, 8)}...</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-xl font-bold p-1 rounded-md"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          {loading && (
            <div className="py-20 text-center text-slate-400 text-sm animate-pulse">
              正在从 PostgreSQL + pgvector 获取 Chunk 原文...
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              获取失败：{error}
            </div>
          )}

          {detail && (
            <>
              <div className="bg-slate-50 border border-slate-200 rounded p-3 text-xs space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">来源文档:</span>
                  <span className="text-slate-900 font-semibold">{detail.document}</span>
                </div>
                {detail.page && (
                  <div className="flex justify-between">
                    <span className="text-slate-500 font-medium">页码:</span>
                    <span className="text-slate-900">第 {detail.page} 页</span>
                  </div>
                )}
                {detail.heading && (
                  <div className="flex justify-between">
                    <span className="text-slate-500 font-medium">章节面包屑:</span>
                    <span className="text-slate-700 font-mono text-[11px] text-right truncate max-w-[280px]">
                      {detail.heading}
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">文档切片序号:</span>
                  <span className="text-slate-900 font-mono">Chunk #{detail.idx}</span>
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  切片完整原文 (Full Chunk Content)
                </h4>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 text-sm leading-relaxed whitespace-pre-wrap font-sans">
                  {detail.content}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="border-t border-slate-200 pt-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded font-medium transition"
          >
            完成查看
          </button>
        </div>
      </div>
    </div>
  );
}
