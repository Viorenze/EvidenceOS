"use client";

import React, { useEffect, useState } from "react";
import { DocumentItem, deleteDocument, listDocuments, uploadDocument } from "../../lib/api";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const data = await listDocuments();
      setDocuments(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || "获取文档列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
    // Poll every 3 seconds if any document is processing
    const interval = setInterval(() => {
      listDocuments()
        .then((data) => {
          setDocuments(data);
          const hasProcessing = data.some((d) => d.status === "processing");
          if (!hasProcessing) {
            // Can slow down or keep as needed
          }
        })
        .catch(() => {});
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Check extension
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "md" && ext !== "pdf" && ext !== "txt") {
      setError("仅支持上传 .md、.pdf 或 .txt 格式的技术文档");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const res = await uploadDocument(file);
      setSuccessMsg(`上传成功！已排队进行分块与向量化处理 (文档 ID: ${res.id.slice(0, 8)}...)`);
      fetchDocs();
    } catch (err: any) {
      setError(err.message || "上传失败");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要彻底删除文档 "${name}" 及其所有关联的向量切片吗？`)) {
      return;
    }

    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      setSuccessMsg(`文档 "${name}" 已成功删除`);
    } catch (err: any) {
      setError(err.message || "删除文档失败");
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return <span className="bg-emerald-100 text-emerald-800 text-xs px-2.5 py-0.5 rounded-full font-medium">已就绪 (Completed)</span>;
      case "processing":
        return <span className="bg-blue-100 text-blue-800 text-xs px-2.5 py-0.5 rounded-full font-medium animate-pulse">处理中 (Processing)</span>;
      case "failed":
        return <span className="bg-rose-100 text-rose-800 text-xs px-2.5 py-0.5 rounded-full font-medium">失败 (Failed)</span>;
      default:
        return <span className="bg-slate-100 text-slate-800 text-xs px-2.5 py-0.5 rounded-full font-medium">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">技术文档库管理</h1>
          <p className="text-sm text-slate-500 mt-1">
            上传 Markdown 或 PDF 文档，系统将自动进行分级标题解析、Jieba 中文分词与 BGE 向量生成。
          </p>
        </div>

        <div>
          <label className={`cursor-pointer inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg shadow-sm transition ${uploading ? "opacity-50 cursor-not-allowed" : ""}`}>
            <span>{uploading ? "正在上传入库..." : "📤 上传新文档 (md/pdf)"}</span>
            <input
              type="file"
              accept=".md,.pdf,.txt"
              className="hidden"
              onChange={handleFileUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 font-bold">✕</button>
        </div>
      )}

      {successMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm flex justify-between items-center">
          <span>{successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-500 font-bold">✕</button>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center">
          <h2 className="text-sm font-semibold text-slate-800">已入库文档 ({documents.length})</h2>
          <button
            onClick={fetchDocs}
            disabled={loading}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
          >
            {loading ? "刷新中..." : "🔄 刷新列表"}
          </button>
        </div>

        {documents.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            暂无已上传的技术文档。请点击上方按钮上传 Markdown 或 PDF 开始。
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">文档文件名</th>
                  <th className="px-6 py-3">状态</th>
                  <th className="px-6 py-3">切片数 (Chunks)</th>
                  <th className="px-6 py-3">入库时间</th>
                  <th className="px-6 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-6 py-4 font-medium text-slate-900 flex items-center gap-2">
                      <span className="text-slate-400">📄</span>
                      {doc.filename}
                    </td>
                    <td className="px-6 py-4">
                      {renderStatusBadge(doc.status)}
                      {doc.error && (
                        <p className="text-xs text-red-500 mt-1 max-w-xs truncate" title={doc.error}>
                          {doc.error}
                        </p>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-600 font-mono">
                      {doc.n_chunks > 0 ? `${doc.n_chunks} chunks` : "-"}
                    </td>
                    <td className="px-6 py-4 text-slate-500 text-xs">
                      {new Date(doc.created_at).toLocaleString("zh-CN")}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        className="text-xs text-rose-600 hover:text-rose-800 font-medium hover:underline"
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
