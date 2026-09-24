from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_user
from app.database import db
from app.models import (
    User, UserRole, Department, Doctor, AppointmentSlot,
    Appointment, AppointmentCreate, MedicalDocument, DocumentType, AuditLog
)

router = APIRouter(prefix="/hospital", tags=["Mock Hospital Backend Services"])


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
    """Search for doctors."""
    return db.get_doctors(department_name=department, specialty=specialty)


@router.get("/doctors/{doctor_id}", response_model=Doctor)
async def get_doctor_by_id(doctor_id: str):
    """Retrieve specific doctor details."""
    doc = db.doctors.get(doctor_id)
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


# --- Appointments (Authorization Aware) ---

@router.get("/appointments", response_model=List[Appointment])
async def list_appointments(
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: Optional[str] = Query(None, description="Admin/Staff lookup for patient ID")
):
    """Retrieve appointments. Patients can ONLY see their own records."""
    if current_user.role == UserRole.PATIENT:
        # Strict isolation: ignore patient_id override if patient tries to query another user
        return db.get_user_appointments(current_user.user_id)

    # Doctor or Staff can query a requested patient_id or see all
    if patient_id:
        return db.get_user_appointments(patient_id)
    return list(db.appointments.values())


@router.post("/appointments", response_model=Appointment, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Book an appointment for the authenticated patient."""
    appt = db.book_appointment(
        user_id=current_user.user_id,
        doctor_id=payload.doctor_id,
        date_str=payload.date,
        time_str=payload.time,
        notes=payload.notes
    )
    if not appt:
        raise HTTPException(status_code=400, detail="Doctor not found or slot unavailable.")
    return appt


@router.patch("/appointments/{appointment_id}", response_model=Appointment)
async def reschedule_appointment(
    appointment_id: str,
    new_date: str = Query(..., description="New date YYYY-MM-DD"),
    new_time: str = Query(..., description="New time HH:MM"),
    current_user: Annotated[User, Depends(get_current_user)] = None
):
    """Reschedule an existing appointment."""
    appt = db.appointments.get(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if current_user.role == UserRole.PATIENT and appt.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized to modify this appointment.")

    rescheduled = db.reschedule_appointment(
        user_id=appt.user_id,
        appointment_id=appointment_id,
        new_date=new_date,
        new_time=new_time
    )
    return rescheduled


@router.delete("/appointments/{appointment_id}", response_model=dict)
async def cancel_appointment(
    appointment_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Cancel an appointment."""
    appt = db.appointments.get(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if current_user.role == UserRole.PATIENT and appt.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized to cancel this appointment.")

    success = db.cancel_appointment(user_id=appt.user_id, appointment_id=appointment_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to cancel appointment.")

    return {"status": "success", "message": f"Appointment {appointment_id} cancelled."}


@router.delete("/appointments/{appointment_id}/purge", response_model=dict)
async def purge_appointment(
    appointment_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Permanently delete a cancelled or completed appointment record from history."""
    success = db.delete_appointment_permanently(appointment_id=appointment_id, user_id=current_user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found or not eligible for deletion (only cancelled or completed appointments can be removed).")
    return {"status": "success", "message": f"Appointment {appointment_id} permanently deleted."}


# --- Documents ---

@router.get("/documents", response_model=List[MedicalDocument])
async def list_documents(current_user: Annotated[User, Depends(get_current_user)]):
    """Retrieve medical documents belonging to the authenticated user."""
    return db.get_user_documents(current_user.user_id)


@router.get("/documents/{document_id}", response_model=MedicalDocument)
async def get_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Retrieve specific medical document."""
    doc = db.documents.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if current_user.role == UserRole.PATIENT and doc.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied to this document.")
    return doc


@router.post("/documents", response_model=MedicalDocument, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str,
    doc_type: DocumentType,
    text_content: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Upload and store a medical document for the current user."""
    return db.add_document(
        user_id=current_user.user_id,
        title=title,
        doc_type=doc_type,
        extracted_text=text_content
    )


@router.delete("/documents/{document_id}", response_model=dict)
async def delete_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Delete a medical document (lab report or prescription) belonging to the user."""
    success = db.delete_document(document_id=document_id, user_id=current_user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or unauthorized.")
    return {"status": "success", "message": f"Document {document_id} deleted."}


# --- Audit Logs ---

@router.get("/audit-logs", response_model=List[AuditLog])
async def get_audit_logs(current_user: Annotated[User, Depends(get_current_user)] = None):
    """View operational audit trail."""
    return db.audit_logs[-30:]
