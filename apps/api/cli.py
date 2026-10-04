"""Command-line interface (CLI) for EvidenceOS.

Provides convenient CLI commands for D1 verification and day-to-day operations:
- ingest: Upload and ingest a local file (Markdown or PDF)
- search: Perform dense vector search on the knowledge base
- list: Display all ingested documents and their status
"""

import argparse
import sys
import uuid
from apps.api.db.models import Document
from apps.api.db.session import SessionLocal, init_db
from apps.api.rag.ingestion import process_document
from apps.api.rag.retrieval import vector_search


def cmd_ingest(args):
    """Ingest a local document file into the database."""
    init_db()
    with open(args.file_path, "rb") as f:
        file_bytes = f.read()

    filename = args.file_path.split("/")[-1].split("\\")[-1]
    db = SessionLocal()
    try:
        doc_id = str(uuid.uuid4())
        doc = Document(id=doc_id, filename=filename, status="processing")
        db.add(doc)
        db.commit()

        print(f"[EvidenceOS] Ingesting '{filename}' (id: {doc_id})...")
        doc = process_document(
            db=db,
            document_id=doc_id,
            file_bytes=file_bytes,
            filename=filename,
        )
        print(f"[EvidenceOS] Success! Status: {doc.status}, Total Chunks: {doc.n_chunks}")
    except Exception as e:
        print(f"[EvidenceOS] Error ingesting document: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def cmd_search(args):
    """Execute dense vector retrieval and print ranked results."""
    db = SessionLocal()
    try:
        print(f"[EvidenceOS] Running vector search for query: '{args.query}' (top_k={args.k})...\n")
        results = vector_search(db=db, query=args.query, k=args.k)
        if not results:
            print("No matching chunks found.")
            return

        for i, r in enumerate(results, start=1):
            heading = r.get("heading") or "No heading"
            score = r.get("score", 0.0)
            doc_name = r.get("document", "Unknown")
            print(f"[{i}] Score: {score:.4f} | Document: {doc_name} | Heading: {heading}")
            print(f"    Snippet: {r['content'][:150].strip()}...")
            print()
    finally:
        db.close()


def cmd_list(args):
    """List all ingested documents and their status."""
    db = SessionLocal()
    try:
        docs = db.query(Document).order_by(Document.created_at.desc()).all()
        if not docs:
            print("[EvidenceOS] No documents found in database.")
            return

        print(f"{'ID':<38} | {'STATUS':<10} | {'CHUNKS':<8} | {'FILENAME'}")
        print("-" * 80)
        for d in docs:
            print(f"{d.id:<38} | {d.status:<10} | {d.n_chunks:<8} | {d.filename}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="EvidenceOS CLI tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest a Markdown or PDF document")
    p_ingest.add_argument("file_path", help="Path to Markdown or PDF file")
    p_ingest.set_defaults(func=cmd_ingest)

    # Search
    p_search = subparsers.add_parser("search", help="Execute vector search for a query")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("-k", type=int, default=5, help="Number of results to retrieve (default: 5)")
    p_search.set_defaults(func=cmd_search)

    # List
    p_list = subparsers.add_parser("list", help="List ingested documents")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
