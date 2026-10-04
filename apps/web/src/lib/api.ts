/**
 * API client and SSE streaming parser for EvidenceOS.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export interface DocumentItem {
  id: string;
  filename: string;
  status: "processing" | "completed" | "failed";
  n_chunks: number;
  error?: string | null;
  created_at: string;
}

export interface ChunkDetail {
  id: string;
  document_id: string;
  document: string;
  idx: number;
  page?: number | null;
  heading?: string | null;
  content: string;
}

export interface CitationItem {
  n: number;
  chunk_id: string;
  document: string;
  page?: number | null;
  heading?: string | null;
  snippet: string;
}

export interface StepItem {
  node: string;
  status: string;
  detail: string;
}

export interface DoneData {
  run_id: string;
  refused: boolean;
  latency_ms: number;
}

export async function uploadDocument(file: File): Promise<{ id: string; status: string; message: string }> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/documents`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Failed to upload document");
  }

  return res.json();
}

export async function listDocuments(): Promise<DocumentItem[]> {
  const res = await fetch(`${API_BASE}/api/documents`);
  if (!res.ok) {
    throw new Error("Failed to fetch documents");
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error("Failed to delete document");
  }
}

export async function getChunkDetail(chunkId: string): Promise<ChunkDetail> {
  const res = await fetch(`${API_BASE}/api/chunks/${chunkId}`);
  if (!res.ok) {
    throw new Error("Failed to retrieve chunk detail");
  }
  return res.json();
}

export interface ChatStreamCallbacks {
  onStep: (step: StepItem) => void;
  onToken: (token: string) => void;
  onCitations: (citations: CitationItem[]) => void;
  onDone: (done: DoneData) => void;
  onError: (errorMsg: string) => void;
}

/**
 * Stream chat SSE events using fetch and ReadableStream reader.
 */
export async function streamChat(
  question: string,
  callbacks: ChatStreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    callbacks.onError(errorBody.detail || `Request failed with status ${res.status}`);
    return;
  }

  if (!res.body) {
    callbacks.onError("ReadableStream not supported by browser/environment");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;

        let eventType = "message";
        let dataStr = "";

        const lines = block.split("\n");
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.slice(6).trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);
          switch (eventType) {
            case "step":
              callbacks.onStep(parsed as StepItem);
              break;
            case "token":
              if (parsed.text) callbacks.onToken(parsed.text);
              break;
            case "citations":
              callbacks.onCitations(parsed.items || []);
              break;
            case "done":
              callbacks.onDone(parsed as DoneData);
              break;
            case "error":
              callbacks.onError(parsed.message || "Unknown server error");
              break;
          }
        } catch (jsonErr) {
          console.warn("Failed to parse SSE JSON frame:", dataStr, jsonErr);
        }
      }
    }
  } catch (readErr: any) {
    if (readErr.name === "AbortError") {
      return;
    }
    callbacks.onError(readErr.message || "Stream connection interrupted");
  }
}
