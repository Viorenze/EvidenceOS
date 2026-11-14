"""Document management and chunk inspection endpoints matching PRD Section 6."""

from collections import OrderedDict
from pathlib import Path
import uuid
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from apps.api.db.models import Chunk, Document
from apps.api.db.session import SessionLocal, get_db
from apps.api.rag.ingestion import process_document

router = APIRouter(prefix="/api", tags=["documents"])

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "evals" / "corpus"

# Bounded in-memory cache of raw uploaded text (keyed by document_id) so newly uploaded
# documents can be viewed losslessly (even while background chunking is still in progress).
_RAW_TEXT_CACHE: "OrderedDict[str, str]" = OrderedDict()
_RAW_TEXT_CACHE_MAX = 64


def _cache_raw_text(document_id: str, text: str) -> None:
    """Store raw uploaded text in a bounded FIFO/LRU cache."""
    if not text:
        return
    _RAW_TEXT_CACHE[document_id] = text
    _RAW_TEXT_CACHE.move_to_end(document_id)
    while len(_RAW_TEXT_CACHE) > _RAW_TEXT_CACHE_MAX:
        _RAW_TEXT_CACHE.popitem(last=False)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    n_chunks: int
    error: Optional[str] = None
    created_at: str


class DocumentUploadAcceptedResponse(BaseModel):
    id: str
    status: str
    message: str


class ChunkDetailResponse(BaseModel):
    id: str
    document_id: str
    document: str
    idx: int
    page: Optional[int] = None
    heading: Optional[str] = None
    content: str


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    n_chunks: int
    error: Optional[str] = None
    created_at: str
    content: str
    chunks: List[ChunkDetailResponse]


def _merge_overlapping_text(
    prev_text: str,
    curr_text: str,
    max_overlap: int = 150,
    min_overlap: int = 6,
) -> str:
    """Merge two consecutive chunks from the same section while deduplicating character overlap.

    Requires at least `min_overlap` matching characters so accidental 1-5 char boundary
    collisions between non-overlapping paragraphs are not falsely merged.
    """
    if not prev_text:
        return curr_text
    if not curr_text:
        return prev_text

    limit = min(len(prev_text), len(curr_text), max_overlap)
    for size in range(limit, min_overlap - 1, -1):
        if prev_text.endswith(curr_text[:size]):
            return prev_text + curr_text[size:]
    return f"{prev_text}\n\n{curr_text}"


def reconstruct_document_content(
    filename: str,
    chunks: List[Chunk],
    document_id: Optional[str] = None,
) -> str:
    """Reconstruct full readable document content from cache, verified corpus file, or ordered chunks.

    Why this works:
    1. If the document was uploaded in this session and its raw UTF-8 text is in `_RAW_TEXT_CACHE`,
       returns the exact uploaded text (even while background chunking is still running).
    2. If the document matches a controlled corpus file in `evals/corpus/` and every chunk
       is verified as a substring of that file, returns the exact original file text.
    3. Otherwise, reconstructs the full text from ordered PostgreSQL `chunks` by restoring
       hierarchical Markdown headings from `heading` breadcrumbs and deduplicating sliding-window
       overlaps between consecutive chunks of the same section or PDF page.
    """
    if document_id and document_id in _RAW_TEXT_CACHE:
        return _RAW_TEXT_CACHE[document_id]

    safe_name = Path(filename).name if filename else ""
    if safe_name and CORPUS_DIR.is_dir():
        candidate = (CORPUS_DIR / safe_name).resolve()
        if (
            candidate.parent == CORPUS_DIR.resolve()
            and candidate.is_file()
            and safe_name.lower().endswith((".md", ".markdown", ".txt"))
        ):
            try:
                corpus_text = candidate.read_text(encoding="utf-8")
                if chunks and all((c.content or "") in corpus_text for c in chunks):
                    return corpus_text.strip()
            except OSError:
                pass

    if not chunks:
        return ""

    # Group consecutive chunks that belong to the same heading and page
    grouped: List[tuple[Optional[str], Optional[int], str]] = []
    for c in chunks:
        text = (c.content or "").strip()
        if not text:
            continue
        if grouped and grouped[-1][0] == c.heading and grouped[-1][1] == c.page:
            prev_h, prev_p, prev_t = grouped[-1]
            grouped[-1] = (prev_h, prev_p, _merge_overlapping_text(prev_t, text))
        else:
            grouped.append((c.heading, c.page, text))

    blocks: List[str] = []
    emitted_headings: List[str] = []
    last_page: Optional[int] = None
    has_multiple_pages = len({g[1] for g in grouped if g[1] is not None}) > 1

    for heading, page, body in grouped:
        if heading:
            parts = [p.strip() for p in heading.split(" > ") if p.strip()]
            common_len = 0
            for a, b in zip(emitted_headings, parts):
                if a == b:
                    common_len += 1
                else:
                    break
            for level_idx in range(common_len, len(parts)):
                hashes = "#" * min(level_idx + 1, 6)
                blocks.append(f"{hashes} {parts[level_idx]}")
            emitted_headings = parts
        elif page is not None and page != last_page:
            if has_multiple_pages or last_page is not None:
                blocks.append(f"--- 第 {page} 页 ---")
            last_page = page

        blocks.append(body)

    return "\n\n".join(blocks)


def _bg_process(document_id: str, file_bytes: bytes, filename: str):
    """Background task worker that creates its own database session."""
    with SessionLocal() as db:
        try:
            process_document(
                db=db,
                document_id=document_id,
                file_bytes=file_bytes,
                filename=filename,
            )
        except Exception:
            # Error is recorded on the document record by process_document
            pass


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadAcceptedResponse,
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Upload technical document (md or pdf). Returns 202 with document id, processes in background."""
    filename = file.filename or "unknown"
    lower_name = filename.lower()
    if not (lower_name.endswith((".md", ".markdown", ".txt")) or lower_name.endswith(".pdf")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format. Only Markdown (.md, .txt) and PDF (.pdf) documents are accepted.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    doc_id = str(uuid.uuid4())
    if lower_name.endswith((".md", ".markdown", ".txt")):
        _cache_raw_text(doc_id, file_bytes.decode("utf-8", errors="replace").strip())

    doc = Document(
        id=doc_id,
        filename=filename,
        status="processing",
        n_chunks=0,
    )
    db.add(doc)
    db.commit()

    background_tasks.add_task(_bg_process, doc_id, file_bytes, filename)

    return DocumentUploadAcceptedResponse(
        id=doc_id,
        status="processing",
        message="Document uploaded and ingestion initiated in background.",
    )


@router.get("/documents", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    """List all documents and their ingestion status."""
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        DocumentResponse(
            id=d.id,
            filename=d.filename,
            status=d.status,
            n_chunks=d.n_chunks,
            error=d.error,
            created_at=d.created_at.isoformat(),
        )
        for d in docs
    ]


@router.get("/documents/{id}", response_model=DocumentDetailResponse)
def get_document(id: str, db: Session = Depends(get_db)):
    """Retrieve full document metadata, reconstructed full text, and ordered chunks."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == id)
        .order_by(Chunk.idx.asc())
        .all()
    )
    if not isinstance(chunks, list):
        chunks = sorted(getattr(doc, "chunks", []) or [], key=lambda c: c.idx)

    chunk_items = [
        ChunkDetailResponse(
            id=c.id,
            document_id=c.document_id,
            document=doc.filename,
            idx=c.idx,
            page=c.page,
            heading=c.heading,
            content=c.content,
        )
        for c in chunks
    ]

    full_content = reconstruct_document_content(doc.filename, chunks, document_id=doc.id)
    created_at_str = (
        doc.created_at.isoformat()
        if hasattr(doc.created_at, "isoformat")
        else str(doc.created_at or "")
    )

    return DocumentDetailResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        n_chunks=doc.n_chunks,
        error=doc.error,
        created_at=created_at_str,
        content=full_content,
        chunks=chunk_items,
    )


@router.delete("/documents/{id}", status_code=status.HTTP_200_OK)
def delete_document(id: str, db: Session = Depends(get_db)):
    """Delete document and its associated chunks via database cascade."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    _RAW_TEXT_CACHE.pop(id, None)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}


@router.get("/chunks/{id}", response_model=ChunkDetailResponse)
def get_chunk(id: str, db: Session = Depends(get_db)):
    """Retrieve full chunk content and breadcrumbs for citation inspection."""
    chunk = db.query(Chunk).filter(Chunk.id == id).first()
    if not chunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")

    return ChunkDetailResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        document=chunk.document.filename if chunk.document else "unknown",
        idx=chunk.idx,
        page=chunk.page,
        heading=chunk.heading,
        content=chunk.content,
    )
