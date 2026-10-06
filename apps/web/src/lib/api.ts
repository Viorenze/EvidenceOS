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

export interface HealthStatus {
  status: string;
  ready: boolean;
  components?: {
    database?: string;
    embedding?: {
      provider: string;
      model: string;
      ready: boolean;
    };
  };
}

/**
 * Probe backend readiness status.
 * Returns ready=false on any connection errors (e.g. backend still starting up).
 */
export async function checkHealthReadiness(signal?: AbortSignal): Promise<{ ready: boolean; raw?: HealthStatus }> {
  try {
    const res = await fetch(`${API_BASE}/api/health?details=true`, {
      method: "GET",
      signal,
      cache: "no-store",
    });
    if (!res.ok) {
      return { ready: false };
    }
    const data: HealthStatus = await res.json();
    return { ready: data.ready === true, raw: data };
  } catch {
    // Network down / port closed / proxy 500 during backend startup
    return { ready: false };
  }
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
  let res: Response | null = null;
  let attempts = 0;
  const maxAttempts = 2; // At most 1 brief retry for rare network/proxy race conditions

  while (attempts < maxAttempts) {
    attempts++;
    try {
      res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal,
      });

      if (res.ok) {
        break;
      }

      // If an unexpected 500/502/ECONNREFUSED occurs on attempt 1, brief pause and retry once
      if (attempts < maxAttempts && res.status >= 500 && !signal?.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        continue;
      }
      break;
    } catch (netErr: any) {
      if (signal?.aborted) throw netErr;
      if (attempts < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        continue;
      }
      throw netErr;
    }
  }

  if (!res || !res.ok) {
    const status = res ? res.status : 500;
    const errorBody = res ? await res.json().catch(() => ({ detail: `HTTP ${status}` })) : { detail: "网络连接失败" };
    callbacks.onError(errorBody.detail || `Request failed with status ${status}`);
    return;
  }

  if (!res.body) {
    callbacks.onError("ReadableStream not supported by browser/environment");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  let completed = false;

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
              completed = true;
              callbacks.onDone(parsed as DoneData);
              break;
            case "error":
              completed = true;
              callbacks.onError(parsed.message || "Unknown server error");
              break;
          }
        } catch (jsonErr) {
          console.warn("Failed to parse SSE JSON frame:", dataStr, jsonErr);
        }
      }
    }

    if (!completed && !signal?.aborted) {
      callbacks.onError("Stream terminated unexpectedly before completion");
    }
  } catch (readErr: any) {
    if (readErr.name === "AbortError" || signal?.aborted) {
      return;
    }
    callbacks.onError(readErr.message || "Stream connection interrupted");
  }
}
