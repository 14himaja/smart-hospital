"""Admin Management and Hospital Document Chunking API Router."""

import io
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from pydantic import BaseModel

from app.authorization.permissions import require_admin
from app.database import db
from app.models import User, UserRole, UserLogin, Token, UserResponse
from app.api.auth import create_access_token
from app.db.repositories.users import verify_password

router = APIRouter(prefix="/admin", tags=["Admin Dashboard & Document Chunking"])


class AdminDocumentCreate(BaseModel):
    title: str
    category: Optional[str] = "General Guidelines"
    content: Optional[str] = ""


class AdminDocumentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract clean text content from uploaded PDF or TXT document file."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text_parts = [p.get_text("text").strip() for p in doc if p.get_text("text").strip()]
            if text_parts:
                return "\n\n".join(text_parts)
        except Exception:
            pass

        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                text_parts = [p.extract_text().strip() for p in pdf.pages if p.extract_text() and p.extract_text().strip()]
                if text_parts:
                    return "\n\n".join(text_parts)
        except Exception:
            pass

    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


@router.post("/login", response_model=Token)
async def admin_login(payload: UserLogin):
    """Authenticate administrator credentials."""
    user = db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect admin email or password.")
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Account is not an administrator.")

    token = create_access_token(user)
    return Token(
        access_token=token,
        user=UserResponse(
            user_id=user.user_id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_verified=user.is_verified,
            preferences=user.preferences
        )
    )


@router.post("/documents", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_hospital_document(
    doc: AdminDocumentCreate,
    admin: Annotated[User, Depends(require_admin)]
):
    """Upload a new raw hospital policy document and split into RAG chunks."""
    if not doc.title or not doc.title.strip():
        raise HTTPException(status_code=400, detail="Document title is required.")
    if not doc.content or not doc.content.strip():
        raise HTTPException(status_code=400, detail="Document content cannot be empty.")

    result = db.add_hospital_document(
        title=doc.title.strip(),
        category=doc.category.strip() if doc.category else "General Guidelines",
        uploaded_by=admin.user_id,
        content=doc.content.strip(),
        file_type="Direct Text Input"
    )

    return {
        "status": "success",
        "message": f"Hospital document '{doc.title}' uploaded and split into {result['chunk_count']} RAG chunks.",
        "document": result
    }


@router.post("/documents/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_hospital_document_file(
    admin: Annotated[User, Depends(require_admin)],
    file: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("General Guidelines"),
    content: Optional[str] = Form(None)
):
    """Upload a hospital document file (PDF / TXT) or raw text and index for RAG."""
    extracted_text = ""
    file_title = title.strip() if title and title.strip() else ""
    file_type = "Direct Text Input"

    if file:
        file_type = f"PDF Document ({file.filename})" if file.filename.lower().endswith(".pdf") else f"Text Document ({file.filename})"
        if not file_title:
            file_title = file.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        file_bytes = await file.read()
        extracted_text = extract_text_from_file(file_bytes, file.filename)

    final_content = (extracted_text + "\n\n" + (content or "")).strip() if extracted_text else (content or "").strip()
    final_title = file_title or "Untitled Hospital Document"
    final_category = category.strip() if category and category.strip() else "General Guidelines"

    if not final_content:
        raise HTTPException(status_code=400, detail="No readable text found in uploaded file or text area.")

    result = db.add_hospital_document(
        title=final_title,
        category=final_category,
        uploaded_by=admin.user_id,
        content=final_content,
        file_type=file_type
    )

    return {
        "status": "success",
        "message": f"Hospital document '{final_title}' uploaded and split into {result['chunk_count']} RAG chunks.",
        "document": result
    }


@router.put("/documents/{doc_id}", response_model=dict)
async def update_hospital_document(
    doc_id: str,
    body: AdminDocumentUpdate,
    admin: Annotated[User, Depends(require_admin)]
):
    """Update document title, category, or content in DB and update chunk index."""
    updated_doc = db.update_hospital_document(
        doc_id=doc_id,
        title=body.title,
        category=body.category,
        content=body.content,
        user_id=admin.user_id
    )
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "status": "success",
        "message": f"Document '{updated_doc['title']}' updated successfully.",
        "document": updated_doc
    }


@router.get("/documents", response_model=dict)
async def list_hospital_documents(admin: Annotated[User, Depends(require_admin)]):
    """List all admin-uploaded hospital documents and their RAG chunk counts."""
    docs = db.get_hospital_documents()
    return {"status": "success", "count": len(docs), "documents": docs}


@router.get("/documents/{doc_id}/chunks", response_model=dict)
async def get_document_chunks(
    doc_id: str,
    admin: Annotated[User, Depends(require_admin)]
):
    """View exact chunked data text blocks for a specific hospital document."""
    chunks = db.get_hospital_doc_chunks(doc_id=doc_id)
    return {"status": "success", "doc_id": doc_id, "chunk_count": len(chunks), "chunks": chunks}


@router.delete("/documents/{doc_id}", response_model=dict)
async def delete_hospital_document(
    doc_id: str,
    admin: Annotated[User, Depends(require_admin)]
):
    """Delete a hospital document and clear its chunks from RAG index."""
    success = db.delete_hospital_document(doc_id=doc_id, user_id=admin.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"status": "success", "message": f"Document {doc_id} and its associated RAG chunks deleted."}


@router.get("/stats", response_model=dict)
async def get_system_stats(admin: Annotated[User, Depends(require_admin)]):
    """Retrieve overall system stats for Admin Dashboard."""
    users = db.get_all_users()
    appts = db.get_all_appointments()
    docs = db.get_all_documents()
    hdocs = db.get_hospital_documents()
    chunks = db.get_hospital_doc_chunks()

    return {
        "status": "success",
        "stats": {
            "total_users": len(users),
            "total_patients": sum(1 for u in users if u.role == UserRole.PATIENT),
            "total_doctors": len(db.get_doctors()),
            "total_appointments": len(appts),
            "total_patient_documents": len(docs),
            "total_hospital_documents": len(hdocs),
            "total_rag_chunks": len(chunks)
        }
    }


@router.get("/patients", response_model=dict)
async def list_registered_patients(admin: Annotated[User, Depends(require_admin)]):
    """Retrieve list of all registered patients for Admin Directory."""
    users = db.get_all_users()
    patients = [
        {
            "user_id": u.user_id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone or "N/A",
            "role": u.role.value,
            "is_verified": u.is_verified,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for u in users if u.role == UserRole.PATIENT
    ]
    return {"status": "success", "count": len(patients), "patients": patients}


@router.get("/appointments", response_model=dict)
async def list_all_hospital_appointments(admin: Annotated[User, Depends(require_admin)]):
    """Retrieve all booked appointments across the hospital for Admin Ledger."""
    appts = db.get_all_appointments()
    users_by_id = {u.user_id: u.name for u in db.get_all_users()}
    result = [
        {
            "id": a.id,
            "user_id": a.user_id,
            "patient_name": users_by_id.get(a.user_id, a.user_id),
            "doctor_name": a.doctor_name,
            "department_name": a.department_name,
            "date": a.date,
            "time": a.time,
            "status": a.status.value,
            "notes": a.notes or "Routine consultation"
        }
        for a in appts
    ]
    return {"status": "success", "count": len(result), "appointments": result}


@router.delete("/appointments/{appointment_id}", response_model=dict)
async def delete_appointment_admin(
    appointment_id: str,
    admin: Annotated[User, Depends(require_admin)]
):
    """Delete an appointment record from the admin portal."""
    success = db.delete_appointment_permanently(appointment_id=appointment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return {"status": "success", "message": f"Appointment {appointment_id} permanently deleted by administrator."}


@router.patch("/appointments/{appointment_id}/complete", response_model=dict)
async def mark_appointment_complete_admin(
    appointment_id: str,
    admin: Annotated[User, Depends(require_admin)]
):
    """Mark an appointment as completed from the admin portal."""
    success = db.complete_appointment(appointment_id=appointment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return {"status": "success", "message": f"Appointment {appointment_id} marked as completed."}
