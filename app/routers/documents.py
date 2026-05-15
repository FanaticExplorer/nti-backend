"""
Documents router — upload, download, and deletion of application documents.

Handles file management for applications:
- **Upload**: validates MIME type, file extension, and size; supports
  versioning when the same filename is uploaded again
- **Download**: access-controlled file retrieval
- **Delete**: removes both the database record and the file from disk;
  only allowed while the application is still in draft

Allowed MIME types: PDF, JPEG, PNG, DOC, DOCX.
Maximum file size is configured via ``settings.MAX_UPLOAD_SIZE_MB``.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentOut
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}

MAX_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    application_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a document for a specific application.

    Validates:
    - The application exists and belongs to the current user
    - MIME type is in ``ALLOWED_MIME``
    - File extension is in ``ALLOWED_EXTENSIONS``
    - File size does not exceed ``MAX_SIZE``

    If a document with the same filename already exists for this
    application, the version number is incremented.

    The file is saved to disk under ``{UPLOAD_DIR}/{application_id}/``
    and a database record is created. An audit log entry is written.

    **Access**: ``student``, ``team_leader`` (must be the applicant)
    """
    # Check application exists and belongs to user
    app_result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Validate MIME type
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not allowed",
        )

    # Validate file extension
    assert file.filename is not None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' not allowed",
        )

    # Read file and check size
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File too large (max 10 MB)"
        )

    # Check if same filename exists for this application - version increment
    existing_result = await db.execute(
        select(Document).where(
            Document.application_id == application_id,
            Document.filename == file.filename,
        )
    )
    existing = existing_result.scalar_one_or_none()
    version = (existing.version + 1) if existing else 1

    # Save file
    assert file.filename is not None  # UploadFile always has a filename
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(application_id))
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        application_id=application_id,
        uploaded_by=current_user.id,
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        version=version,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    await write_audit_log(
        db,
        current_user.id,
        "document.uploaded",
        "document",
        str(doc.id),
        {"filename": file.filename, "application_id": str(application_id)},
    )

    return doc


@router.get("/{document_id}")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a document by ID.

    Returns the file as a ``FileResponse`` with the original filename
    and MIME type.

    **Access control**:
    - ``nti_admin``, ``evaluator``, ``mentor`` can download any document
    - The original uploader can download their own documents
    - All other roles receive a 403

    Returns 404 if the database record or the file on disk is missing.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Access control
    allowed = ("nti_admin", "evaluator", "mentor")
    if current_user.role not in allowed and doc.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    if not os.path.exists(doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk"
        )

    return FileResponse(doc.file_path, filename=doc.filename, media_type=doc.mime_type)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a document.

    - Only the original uploader can delete
    - Cannot delete documents after the application has been submitted
      (``is_draft == False``)
    - Removes both the database record and the file from disk
    - Writes an audit log entry

    **Access**: ``student``, ``team_leader`` (must be the uploader)
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if doc.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Check application is still in draft
    if doc.application_id:
        app_result = await db.execute(
            select(Application).where(Application.id == doc.application_id)
        )
        app = app_result.scalar_one_or_none()
        if app and not app.is_draft:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete documents after submission",
            )

    # Delete file from disk
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    await db.delete(doc)
    await db.commit()

    await write_audit_log(
        db,
        current_user.id,
        "document.deleted",
        "document",
        str(document_id),
        {"filename": doc.filename},
    )
