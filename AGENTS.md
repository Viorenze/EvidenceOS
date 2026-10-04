# AGENTS.md — EvidenceOS

You are helping build EvidenceOS, a small AI full-stack app: upload technical docs, hybrid retrieval, a LangGraph agent that grades evidence and refuses when evidence is missing, streamed answers with verifiable citations, and a CLI evaluation.

`docs/PRD.md` is the source of truth for scope, API, data model, agent graph and eval. Read it before every task. If a task conflicts with it, stop and say so instead of improvising.

The owner has one week and must be able to explain every core module in an interview. Prefer simple, readable code over clever code.

## Locked stack

- Frontend: Next.js, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, Pydantic, SQLAlchemy
- Database: PostgreSQL + pgvector (vectors and full-text in the same database)
- Chinese full-text: segment with jieba, store in `content_seg`, index with `to_tsvector('simple', ...)`
- Embedding: local `BAAI/bge-small-zh-v1.5` (512 dims) behind an `EMBEDDING_PROVIDER` switch
- LLM: OpenAI-compatible HTTP API (domestic providers), configured via `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Agent: LangGraph
- Tooling: Docker Compose, pytest, Git

Do not add any other framework, database, queue or cache without asking. Not in scope: auth, multi-workspace, Redis, MCP, multi-agent, reranker, web search, conversation memory, Kubernetes, cloud deployment.

## Layout

```text
apps/web/            Next.js app
apps/api/            FastAPI app
  routers/
  services/
  rag/               chunking, ingestion, retrieval (hybrid + RRF)
  agent/             state, nodes, graph
  llm/               provider abstraction
  db/                models, session, migrations
evals/               dataset.jsonl, corpus/, runner
reports/             generated eval reports
docs/                PRD.md, DECISIONS.md
tests/
docker-compose.yml
Makefile
```

Commands are defined in the Makefile at M0 and kept current: `make up`, `make test`, `make eval`. Always use them rather than ad-hoc commands, and update this section when they change.

## Rules

1. One repo, one architecture. Never create separate sub-projects to merge later.
2. Every LLM call goes through `apps/api/llm/`. Every embedding call goes through the embedding abstraction. No provider SDKs scattered across the code.
3. Secrets only in environment variables. Commit `.env.example`, never `.env`.
4. Do not silently change the API contract, SSE event schema or database schema. If a change is needed, update `docs/PRD.md` in the same commit and say so.
5. The agent graph must keep its conditional loop: retrieve, grade, rewrite (at most 2), then generate or refuse. Do not flatten it into a linear chain.
6. The server validates citations. Never trust citation markers from the model without checking them against the retrieved chunks.
7. Refusal must not call the LLM to invent an answer. Use the fixed refusal text.
8. All thresholds and sizes (chunk size, top-k, RRF k, max rewrites) live in config, not hard-coded in logic.
9. Evaluation numbers come from real runs only. Never write placeholder or invented metrics anywhere, including docs and README.
10. Stay inside the current task. Do not add features, refactor unrelated code, or add dependencies "while you're there".
11. Keep files small and functions short. Add a brief docstring to each core function (chunker, retrieval, RRF, graph nodes, citation check, eval metrics) explaining why it works the way it does, since the owner must explain it in interviews.

## Working loop

For each task:

1. Read `docs/PRD.md` and the relevant code.
2. Write a short plan (files to touch, tests to add). Wait for approval if the task touches schema, API or the agent graph.
3. Implement only that task.
4. Run `make test`. For retrieval or agent changes, also run the relevant slice of `make eval` and report the numbers.
5. Fix failures. Do not weaken or delete tests to get green.
6. Commit with a conventional message (`feat:`, `fix:`, `test:`, `docs:`).
7. Report: what changed, files touched, test and eval results, anything left undone or uncertain.

Mark work as done only when it was actually run and verified. If something could not be verified (for example no API key available), say so plainly.

## Definition of done (project)

- `docker compose up` brings up the whole app on a clean clone using only README steps
- Upload md/pdf, ask a question, receive a streamed answer with clickable citations
- Questions with no answer in the knowledge base are refused
- `make eval` produces `reports/eval.md` comparing vector-only, hybrid and hybrid+agent
- pytest passes; README has an architecture diagram and known limitations
- `docs/DECISIONS.md` has short entries for: pgvector over a separate vector DB, hybrid over vector-only, LangGraph with a conditional loop, SSE over WebSocket, jieba segmentation

## Testing expectations

- Unit tests for: chunker, RRF fusion, citation validation, eval metrics
- Integration test for: upload → ingest → search
- Agent tests use a fake LLM provider so they run offline and deterministically
- Tests must not call real LLM APIs by default
