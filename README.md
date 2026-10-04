# EvidenceOS

EvidenceOS is a verifiable AI technical documentation QA system featuring:
- Document ingestion with Markdown heading-aware chunking & PDF plain text extraction
- Chinese full-text search with jieba pre-segmentation (`content_seg` + PostgreSQL `tsvector`)
- Dense vector search with `BAAI/bge-small-zh-v1.5` (512 dimensions)
- Hybrid retrieval with Reciprocal Rank Fusion (RRF)
- LangGraph agent with conditional evidence grading, query rewriting, and refusal loop
- Server-side citation validation (verifying citation markers against retrieved chunks, reducing hallucinations)
- Server-Sent Events (SSE) streaming answers with verifiable source provenance
- Automated offline CLI evaluation comparing vector-only, hybrid, and hybrid+agent

## Architecture Overview

```text
Upload (md/pdf) ──> Chunker (Heading-aware) ──> jieba (content_seg) ──> BGE-small-zh ──> PostgreSQL + pgvector
Question ──> Agent Graph [ Retrieve ──> Grade ──> Rewrite (<=2) ──> Generate ──> Verify Citations ] ──> SSE Stream
```

## Implementation Status

- **D1 (Ingestion & Vector)**: Completed. Markdown heading breadcrumbs, PDF extraction, bge-small-zh, pgvector storage.
- **D2 (Hybrid Retrieval & RRF)**: Completed. jieba tokenization, PostgreSQL tsvector (`ts_rank_cd`), RRF rank fusion, `/api/search`.
- **D3 (Agent & Citations)**: Completed & Remediated. LangGraph cyclic graph (`retrieve -> grade -> rewrite/generate -> verify_citations -> refuse`), OpenAI-compatible LLM abstraction, server-side citation normalization & verification, best-effort run persistence.
- **D4 (SSE & Web UI)**: In planning / upcoming.
- **D5 (CLI Evaluation)**: Pending evaluation runner with real docs corpus.

## Known Design Trade-offs & Limitations

1. **Verify-then-Stream (D4 Strategy)**: To honor the core guarantee of verifiable citations and zero dangling references, generation is fully verified and cleansed on the server before tokens stream to the client. This prioritizes correctness and honesty over initial time-to-first-token (TTFT).
2. **Citation Scope**: Server-side citation validation guarantees that every citation index `[n]` points to a valid retrieved chunk within the current retrieval scope (`1 <= n <= k`). It provides structural provenance and mitigates hallucinated markers, but does not perform independent NLI semantic entailment verification.
3. **Database Dependency in Tests**: Unit tests run 100% offline with mocked retrieval and fake providers. Database integration tests explicitly declare `@pytest.mark.integration` and skip gracefully when PostgreSQL is unreachable.

## Quick Start (Development)

1. Start database:
```bash
docker compose up -d db
```

2. Run offline test suite:
```bash
uv run pytest -q
```
