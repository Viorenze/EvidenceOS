# EvidenceOS

EvidenceOS is a verifiable AI technical documentation QA system featuring:
- Document ingestion with Markdown heading-aware chunking & PDF plain text extraction
- Chinese full-text search with jieba pre-segmentation (`content_seg` + PostgreSQL `tsvector`)
- Dense vector search with `BAAI/bge-small-zh-v1.5` (512 dimensions)
- Hybrid retrieval with Reciprocal Rank Fusion (RRF)
- LangGraph agent with conditional evidence grading, query rewriting, and refusal loop
- Verifiable citation validation and server-sent events (SSE) streaming answers
- Automated offline CLI evaluation comparing vector-only, hybrid, and hybrid+agent

## Architecture Overview

```text
Upload (md/pdf) ──> Chunker (Heading-aware) ──> jieba (content_seg) ──> BGE-small-zh ──> PostgreSQL + pgvector
Question ──> Agent Graph [ Retrieve ──> Grade ──> Rewrite (<=2) ──> Generate ──> Verify Citations ] ──> SSE Stream
```

## Quick Start

```bash
docker compose up -d
```
