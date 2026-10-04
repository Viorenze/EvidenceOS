"""Document management and chunk inspection endpoints matching PRD Section 6."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from apps.api.db.models import Chunk, Document
from apps.api.db.session import SessionLocal, get_db
from apps.api.rag.ingestion import process_document

router = APIRouter(prefix="/api", tags=["documents"])


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


@router.delete("/documents/{id}", status_code=status.HTTP_200_OK)
def delete_document(id: str, db: Session = Depends(get_db)):
    """Delete document and its associated chunks via database cascade."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

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
