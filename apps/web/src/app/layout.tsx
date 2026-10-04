import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "EvidenceOS — 可核对引用的技术问答系统",
  description: "基于混合检索、LangGraph 条件循环代理与服务端引用校验的开源知识库问答系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen flex flex-col">
        <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
          <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                <span className="bg-blue-600 text-white w-7 h-7 rounded flex items-center justify-center text-sm font-semibold">E</span>
                EvidenceOS
              </span>
              <span className="text-xs text-slate-500 hidden sm:inline border border-slate-200 px-2 py-0.5 rounded">
                Verifiable RAG
              </span>
            </div>

            <nav className="flex space-x-1 sm:space-x-4 text-sm font-medium">
              <Link
                href="/"
                className="px-3 py-2 rounded-md text-slate-700 hover:text-blue-600 hover:bg-slate-50 transition"
              >
                💬 问答检索 (Chat)
              </Link>
              <Link
                href="/documents"
                className="px-3 py-2 rounded-md text-slate-700 hover:text-blue-600 hover:bg-slate-50 transition"
              >
                📄 文档管理 (Documents)
              </Link>
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 flex flex-col">
          {children}
        </main>

        <footer className="bg-white border-t border-slate-200 py-4 text-center text-xs text-slate-500">
          EvidenceOS · 真实运行核对 · 服务端引用校验 · 无编造保真
        </footer>
      </body>
    </html>
  );
}
