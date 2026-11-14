/**
 * Global client-side session store for EvidenceOS Chat & Readiness state.
 *
 * Why this store exists:
 * When a user submits a question on the Chat page (`/`) and navigates to the
 * Documents page (`/documents`) while the LangGraph agent is still retrieving,
 * grading, rewriting, or streaming tokens, component-local state would unmount
 * and abort the in-flight SSE stream.
 * By managing the chat session and AbortController at module scope and exposing
 * it via `React.useSyncExternalStore`, the SSE stream continues running in the
 * background across route transitions and immediately reflects live progress
 * when the user returns to the Chat page.
 */

import * as React from "react";
import {
  type CitationItem,
  type DoneData,
  type StepItem,
  checkHealthReadiness,
  streamChat,
} from "./api";

export interface ChatSessionState {
  question: string;
  isStreaming: boolean;
  steps: StepItem[];
  answer: string;
  citations: CitationItem[];
  doneData: DoneData | null;
  errorMessage: string | null;
  backendReady: boolean;
  readinessStatus: "checking" | "ready" | "timeout";
  selectedChunkId: string | null;
  stepsExpanded: boolean;
}

const INITIAL_STATE: ChatSessionState = {
  question: "",
  isStreaming: false,
  steps: [],
  answer: "",
  citations: [],
  doneData: null,
  errorMessage: null,
  backendReady: false,
  readinessStatus: "checking",
  selectedChunkId: null,
  stepsExpanded: true,
};

let currentState: ChatSessionState = INITIAL_STATE;
const listeners = new Set<() => void>();

let activeAbortController: AbortController | null = null;
let readinessProbeActive = false;

function emitChange() {
  for (const listener of listeners) {
    listener();
  }
}

function updateState(
  updater: Partial<ChatSessionState> | ((prev: ChatSessionState) => Partial<ChatSessionState>),
) {
  const patch = typeof updater === "function" ? updater(currentState) : updater;
  currentState = { ...currentState, ...patch };
  emitChange();
}

export function subscribeChatStore(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getChatStoreSnapshot(): ChatSessionState {
  return currentState;
}

export function getChatStoreServerSnapshot(): ChatSessionState {
  return INITIAL_STATE;
}

export function useChatSession(): ChatSessionState {
  return React.useSyncExternalStore(
    subscribeChatStore,
    getChatStoreSnapshot,
    getChatStoreServerSnapshot,
  );
}

export function setChatQuestion(question: string): void {
  updateState({ question });
}

export function setChatSelectedChunkId(selectedChunkId: string | null): void {
  updateState({ selectedChunkId });
}

export function setChatStepsExpanded(stepsExpanded: boolean): void {
  updateState({ stepsExpanded });
}

export function setChatErrorMessage(errorMessage: string | null): void {
  updateState({ errorMessage });
}

/**
 * Start a singleton background readiness probe until the backend is ready or times out (60s).
 * Safe to call on every component mount; only runs one active polling loop.
 */
export function ensureBackendReadinessProbe(): void {
  if (typeof window === "undefined" || currentState.backendReady || readinessProbeActive) {
    return;
  }

  readinessProbeActive = true;
  if (currentState.readinessStatus === "timeout") {
    updateState({ readinessStatus: "checking" });
  }

  const startTime = Date.now();
  const TIMEOUT_MS = 60000;

  const poll = async () => {
    try {
      const { ready } = await checkHealthReadiness();
      if (ready) {
        readinessProbeActive = false;
        updateState({
          backendReady: true,
          readinessStatus: "ready",
        });
        return;
      }
    } catch {
      // Ignore transient network errors during backend startup
    }

    if (Date.now() - startTime > TIMEOUT_MS) {
      readinessProbeActive = false;
      updateState({ readinessStatus: "timeout" });
      return;
    }

    setTimeout(poll, 500);
  };

  void poll();
}

/**
 * Launch an SSE chat stream in the background. Continues running across route changes.
 */
export async function startChatAsk(): Promise<void> {
  const q = currentState.question.trim();
  if (!currentState.backendReady || !q || currentState.isStreaming) {
    return;
  }

  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
  }

  const controller = new AbortController();
  activeAbortController = controller;

  updateState({
    isStreaming: true,
    steps: [],
    answer: "",
    citations: [],
    doneData: null,
    errorMessage: null,
    selectedChunkId: null,
    stepsExpanded: true,
  });

  try {
    await streamChat(
      q,
      {
        onStep: (step) => {
          if (activeAbortController !== controller) return;
          updateState((prev) => ({
            steps: [...prev.steps, step],
          }));
        },
        onToken: (token) => {
          if (activeAbortController !== controller) return;
          updateState((prev) => ({
            answer: prev.answer + token,
          }));
        },
        onCitations: (citations) => {
          if (activeAbortController !== controller) return;
          updateState({ citations });
        },
        onDone: (doneData) => {
          if (activeAbortController !== controller) return;
          updateState({ doneData });
        },
        onError: (errorMessage) => {
          if (activeAbortController !== controller) return;
          updateState({ errorMessage });
        },
      },
      controller.signal,
    );
  } catch (err: unknown) {
    if (!controller.signal.aborted && activeAbortController === controller) {
      const message = err instanceof Error ? err.message : "流式传输异常";
      updateState({ errorMessage: message });
    }
  } finally {
    if (activeAbortController === controller) {
      activeAbortController = null;
      updateState({ isStreaming: false });
    }
  }
}

/**
 * Explicitly stop the active SSE stream when the user clicks the Stop button.
 */
export function stopChatAsk(): void {
  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
  }
  updateState({ isStreaming: false });
}
