"""Hospital REST endpoints with role-based access control."""

from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_user
from app.authorization.permissions import require_authenticated_user, require_staff_access, require_admin
from app.database import db
from app.models import (
    User, UserRole, Department, Doctor, AppointmentSlot,
    Appointment, AppointmentCreate, MedicalDocument, DocumentType, AuditLog
)

router = APIRouter(prefix="/hospital", tags=["Hospital Backend Services"])


class DocumentUpload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    doc_type: DocumentType = DocumentType.GENERAL
    text_content: str = Field(..., min_length=1, max_length=50_000)


# --- Departments & Doctors ---

@router.get("/departments", response_model=List[Department])
async def list_departments():
    """Retrieve all hospital departments."""
    return db.get_departments()


@router.get("/doctors", response_model=List[Doctor])
async def list_doctors(
    department: Optional[str] = Query(None, description="Filter by department name"),
    specialty: Optional[str] = Query(None, description="Filter by doctor specialty")
):
    """Search for doctors with strict filtering."""
    return db.get_doctors(department_name=department, specialty=specialty)


@router.get("/doctors/{doctor_id}", response_model=Doctor)
async def get_doctor_by_id(doctor_id: str):
    """Retrieve specific doctor details."""
    doc = db.get_doctor(doctor_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doc


@router.get("/slots", response_model=List[AppointmentSlot])
async def get_available_slots(
    doctor_id: Optional[str] = Query(None, description="Filter by doctor ID"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    available_only: bool = Query(False, description="Filter to only available slots")
):
    """Check appointment slots with availability status."""
    return db.get_slots(doctor_id=doctor_id, date_str=date, available_only=available_only)


# --- Appointments (Authorization Aware & Scoped) ---

@router.get("/appointments", response_model=List[Appointment])
async def list_appointments(
    current_user: Annotated[User, Depends(require_authenticated_user)],
    patient_id: Optional[str] = Query(None, description="Admin/Staff lookup for patient ID")
):
    """Retrieve appointments. Scoped by role: patients see theirs, doctors see theirs, admin/staff see all/queried."""
    if current_user.role == UserRole.PATIENT:
        return db.get_user_appointments(current_user.user_id)

    if current_user.role == UserRole.DOCTOR:
        all_appts = db.get_all_appointments()
        return [a for a in all_appts if a.doctor_id == current_user.user_id]

    if patient_id:
        return db.get_user_appointments(patient_id)
    return db.get_all_appointments()


@router.post("/appointments", response_model=Appointment, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Book an appointment for the authenticated patient."""
    appt = db.book_appointment(
        user_id=current_user.user_id,
        doctor_id=payload.doctor_id,
        date_str=payload.date,
        time_str=payload.time,
        notes=payload.notes or ""
    )
    if not appt:
        raise HTTPException(status_code=400, detail="Doctor not found or slot unavailable.")
    return appt


@router.patch("/appointments/{appointment_id}", response_model=Appointment)
async def reschedule_appointment(
    appointment_id: str,
    new_date: str = Query(..., description="New date YYYY-MM-DD"),
    new_time: str = Query(..., description="New time HH:MM"),
    current_user: Annotated[User, Depends(require_authenticated_user)] = None
):
    """Reschedule an existing appointment."""
    appt = db.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if current_user.role == UserRole.PATIENT and appt.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized to modify this appointment.")

    rescheduled = db.reschedule_appointment(
        user_id=current_user.user_id if current_user.role == UserRole.PATIENT else "ADMIN",
        appointment_id=appointment_id,
        new_date=new_date,
        new_time=new_time
    )
    if not rescheduled:
        raise HTTPException(status_code=400, detail="Failed to reschedule appointment.")
    return rescheduled


@router.delete("/appointments/{appointment_id}", response_model=dict)
async def cancel_appointment(
    appointment_id: str,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Cancel an appointment."""
    appt = db.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if current_user.role == UserRole.PATIENT and appt.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized to cancel this appointment.")

    success = db.cancel_appointment(
        user_id=current_user.user_id if current_user.role == UserRole.PATIENT else "ADMIN",
        appointment_id=appointment_id
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to cancel appointment.")

    return {"status": "success", "message": f"Appointment {appointment_id} cancelled."}


@router.delete("/appointments/{appointment_id}/purge", response_model=dict)
async def purge_appointment(
    appointment_id: str,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Permanently delete a cancelled or completed appointment record from history."""
    success = db.delete_appointment_permanently(
        appointment_id=appointment_id,
        user_id=current_user.user_id if current_user.role == UserRole.PATIENT else None
    )
    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found or not eligible for deletion.")
    return {"status": "success", "message": f"Appointment {appointment_id} permanently deleted."}


# --- Documents ---

@router.get("/documents", response_model=List[MedicalDocument])
async def list_documents(current_user: Annotated[User, Depends(require_authenticated_user)]):
    """Retrieve medical documents belonging to the authenticated user."""
    return db.get_user_documents(current_user.user_id)


@router.get("/documents/{document_id}", response_model=MedicalDocument)
async def get_document(
    document_id: str,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Retrieve specific medical document."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if current_user.role == UserRole.PATIENT and doc.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
    return doc


@router.post("/documents", response_model=MedicalDocument, status_code=status.HTTP_201_CREATED)
async def upload_document(
    payload: DocumentUpload,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Upload and store a medical document for the current user via JSON body."""
    return db.add_user_document(
        user_id=current_user.user_id,
        title=payload.title,
        document_type=payload.doc_type,
        extracted_text=payload.text_content
    )


@router.delete("/documents/{document_id}", response_model=dict)
async def delete_document(
    document_id: str,
    current_user: Annotated[User, Depends(require_authenticated_user)]
):
    """Delete a medical document belonging to the user."""
    success = db.delete_user_document(
        document_id=document_id,
        user_id=current_user.user_id if current_user.role == UserRole.PATIENT else "ADMIN"
    )
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or unauthorized.")
    return {"status": "success", "message": f"Document {document_id} deleted."}


# --- Audit Logs (Restricted to Admin Only) ---

@router.get("/audit-logs", response_model=List[AuditLog])
async def get_audit_logs(current_user: Annotated[User, Depends(require_admin)]):
    """View operational audit trail (Restricted strictly to administrators)."""
    return db.get_audit_logs(limit=50)

