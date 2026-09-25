"""
Medical and Hospital Tools for Smart Hospital Assistant.
Shared across ADK agents, Gemini Live Voice, and MCP Server.
"""

import re
import datetime as dt
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db


def normalize_date_str(date_str: Optional[str]) -> Optional[str]:
    """Normalize user or voice spoken relative date strings into standard YYYY-MM-DD."""
    if not date_str:
        return None
    raw = str(date_str).strip().lower()
    today = dt.date.today()

    if raw in ("today", "now"):
        return today.isoformat()
    if raw in ("tomorrow", "tmrw"):
        return (today + timedelta(days=1)).isoformat()
    if raw in ("day after tomorrow", "day after tmrw"):
        return (today + timedelta(days=2)).isoformat()

    weekday_patterns = [
        (r"\b(monday|mon)\b", 0),
        (r"\b(tuesday|tue|tues)\b", 1),
        (r"\b(wednesday|wed)\b", 2),
        (r"\b(thursday|thu|thur|thurs)\b", 3),
        (r"\b(friday|fri)\b", 4),
        (r"\b(saturday|sat)\b", 5),
        (r"\b(sunday|sun)\b", 6)
    ]
    for pattern, day_idx in weekday_patterns:
        if re.search(pattern, raw):
            days_ahead = (day_idx - today.weekday() + 7) % 7
            if days_ahead == 0 and ("next" in raw or "upcoming" in raw):
                days_ahead = 7
            elif days_ahead == 0:
                days_ahead = 0
            return (today + timedelta(days=days_ahead)).isoformat()

    # Match standard YYYY-MM-DD
    match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", raw)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Match DD-MM-YYYY
    match_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", raw)
    if match_dmy:
        d, m, y = match_dmy.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Match Month Day (e.g. Sep 25, September 25, 25th September)
    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12
    }
    for m_name, m_num in months.items():
        if re.search(rf"\b{m_name}\b", raw):
            day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", raw)
            if day_match:
                d = int(day_match.group(1))
                return f"{today.year:04d}-{m_num:02d}-{d:02d}"

    return raw


def normalize_time_str(time_str: Optional[str]) -> str:
    """Normalize spoken time strings (e.g. '10:00 AM', '10.30 am', '2pm', '14:00') into HH:MM."""
    if not time_str:
        return "09:00"
    raw = str(time_str).strip().lower()
    is_pm = "pm" in raw
    is_am = "am" in raw

    # Replace '.' with ':' if used as time separator (e.g. 10.30 am -> 10:30 am)
    raw_cleaned = re.sub(r"(\d{1,2})\.(\d{2})", r"\1:\2", raw)
    clean = re.sub(r"[^\d:]", "", raw_cleaned)

    if ":" in clean:
        parts = clean.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    elif clean:
        h = int(clean)
        m = 0
    else:
        return "09:00"

    if is_pm and h < 12:
        h += 12
    elif is_am and h == 12:
        h = 0
    return f"{h:02d}:{m:02d}"


def search_departments() -> Dict[str, Any]:
    """Retrieve the list of all hospital departments and their locations."""
    depts = db.get_departments()
    return {
        "status": "success",
        "count": len(depts),
        "departments": [
            {
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "location": d.location
            }
            for d in depts
        ]
    }


def search_doctors(department_name: str = "", specialty: str = "") -> Dict[str, Any]:
    """Search for doctors by department name or specialty."""
    docs = db.get_doctors(department_name=department_name or None, specialty=specialty or None)
    if not docs and (department_name or specialty):
        return {
            "status": "error",
            "message": f"No doctors found matching department '{department_name}' or specialty '{specialty}'.",
            "count": 0,
            "doctors": []
        }
    return {
        "status": "success",
        "count": len(docs),
        "doctors": [
            {
                "id": d.id,
                "name": d.name,
                "department": d.department_name,
                "specialty": d.specialty,
                "available_days": d.available_days,
                "fee": f"{settings.CURRENCY_SYMBOL}{d.consultation_fee:.2f}"
            }
            for d in docs
        ]
    }


def get_available_slots(doctor_id: str = "", date: str = "") -> Dict[str, Any]:
    """Get available appointment time slots for a doctor."""
    clean_date = normalize_date_str(date) if date else None
    doc = db.get_doctor(doctor_id) if doctor_id else None

    if not doc:
        return {
            "status": "error",
            "message": f"Doctor '{doctor_id}' not found. Please select a verified hospital specialist.",
            "available_doctors": [
                {"id": d.id, "name": d.name, "department": d.department_name, "specialty": d.specialty, "fee": f"{settings.CURRENCY_SYMBOL}{d.consultation_fee:.2f}"}
                for d in db.get_doctors()
            ]
        }

    actual_doc_id = doc.id
    doc_name = doc.name

    if clean_date:
        slots = db.get_slots(doctor_id=actual_doc_id, date_str=clean_date, available_only=True)
        times = [s.time for s in slots]
        return {
            "status": "success",
            "doctor_id": actual_doc_id,
            "doctor_name": doc_name,
            "department": doc.department_name,
            "specialty": doc.specialty,
            "consultation_fee": f"{settings.CURRENCY_SYMBOL}{doc.consultation_fee:.2f}",
            "date": clean_date,
            "available_slots": times,
            "message": f"Available slots for {doc_name} on {clean_date}: {', '.join(times) if times else 'None'}."
        }

    all_slots = db.get_slots(doctor_id=actual_doc_id, available_only=True)
    slots_by_date = {}
    for s in all_slots:
        slots_by_date.setdefault(s.date, []).append(s.time)

    return {
        "status": "success",
        "doctor_id": actual_doc_id,
        "doctor_name": doc_name,
        "department": doc.department_name,
        "specialty": doc.specialty,
        "consultation_fee": f"{settings.CURRENCY_SYMBOL}{doc.consultation_fee:.2f}",
        "available_days": doc.available_days,
        "available_slots_by_date": slots_by_date,
        "available_dates": list(slots_by_date.keys()),
        "message": f"{doc_name} ({doc.specialty}) has available slots on upcoming dates."
    }


def book_appointment(user_id: str, doctor_id: str, date: str, time: str, confirmed: bool = False, notes: str = "") -> Dict[str, Any]:
    """Book an appointment with guardrail confirmation."""
    clean_date = normalize_date_str(date) or date
    clean_time = normalize_time_str(time)
    doc = db.get_doctor(doctor_id)
    if not doc:
        return {"status": "error", "message": f"Doctor '{doctor_id}' not found."}

    # Validate date
    try:
        appt_date = dt.date.fromisoformat(clean_date)
        if appt_date < dt.date.today():
            return {"status": "error", "message": f"Cannot book appointments in the past ({clean_date})."}
    except Exception:
        return {"status": "error", "message": f"Invalid date format '{clean_date}'."}

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": f"Please confirm: Do you want to book an appointment with {doc.name} on {clean_date} at {clean_time}? Respond 'Yes, I confirm' to proceed.",
            "pending_action": {
                "action": "book_appointment",
                "doctor_id": doc.id,
                "doctor_name": doc.name,
                "date": clean_date,
                "time": clean_time,
                "notes": notes
            }
        }

    appt = db.book_appointment(user_id=user_id, doctor_id=doc.id, date_str=clean_date, time_str=clean_time, notes=notes)
    if not appt:
        return {"status": "error", "message": f"Doctor {doc.name} or slot at {clean_time} on {clean_date} is unavailable."}

    return {
        "status": "success",
        "message": f"Appointment successfully booked with {appt.doctor_name} for {appt.date} at {appt.time}.",
        "appointment_id": appt.id,
        "details": {
            "doctor": appt.doctor_name,
            "department": appt.department_name,
            "date": appt.date,
            "time": appt.time,
            "status": appt.status.value
        }
    }


def cancel_appointment(user_id: str, appointment_id: str, confirmed: bool = False) -> Dict[str, Any]:
    """Cancel an existing appointment with guardrail confirmation."""
    appt = db.get_appointment(appointment_id)
    if not appt or (user_id != "ADMIN" and appt.user_id != user_id):
        return {"status": "error", "message": "Appointment not found or you are not authorized to cancel it."}

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": f"Are you sure you want to cancel your appointment with {appt.doctor_name} on {appt.date} at {appt.time}? Respond 'Confirm cancellation' to proceed.",
            "pending_action": {"action": "cancel_appointment", "appointment_id": appointment_id}
        }

    success = db.cancel_appointment(user_id=user_id, appointment_id=appointment_id)
    if not success:
        return {"status": "error", "message": "Failed to cancel appointment."}

    return {
        "status": "success",
        "message": f"Appointment {appointment_id} with {appt.doctor_name} on {appt.date} at {appt.time} has been cancelled.",
        "appointment_id": appointment_id
    }


def reschedule_appointment(user_id: str, appointment_id: str, new_date: str, new_time: str, confirmed: bool = False) -> Dict[str, Any]:
    """Reschedule an existing appointment."""
    clean_date = normalize_date_str(new_date) or new_date
    clean_time = normalize_time_str(new_time)
    appt = db.get_appointment(appointment_id)
    if not appt or (user_id != "ADMIN" and appt.user_id != user_id):
        return {"status": "error", "message": "Appointment not found or you are not authorized to modify it."}

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": f"Please confirm: Do you want to reschedule appointment {appointment_id} to {clean_date} at {clean_time}? Respond 'Confirm reschedule' to proceed.",
            "pending_action": {
                "action": "reschedule_appointment",
                "appointment_id": appointment_id,
                "new_date": clean_date,
                "new_time": clean_time
            }
        }

    rescheduled = db.reschedule_appointment(user_id=user_id, appointment_id=appointment_id, new_date=clean_date, new_time=clean_time)
    if not rescheduled:
        return {"status": "error", "message": "Failed to reschedule appointment. The selected slot may be unavailable."}

    return {
        "status": "success",
        "message": f"Appointment {appointment_id} rescheduled to {rescheduled.date} at {rescheduled.time}.",
        "appointment_id": appointment_id,
        "details": {"doctor": rescheduled.doctor_name, "date": rescheduled.date, "time": rescheduled.time}
    }


def get_appointment_history(user_id: str) -> Dict[str, Any]:
    """Retrieve all past and upcoming appointments for the authenticated patient."""
    appts = db.get_user_appointments(user_id=user_id)
    return {
        "status": "success",
        "user_id": user_id,
        "count": len(appts),
        "appointments": [
            {
                "id": a.id,
                "doctor": a.doctor_name,
                "department": a.department_name,
                "date": a.date,
                "time": a.time,
                "status": a.status.value,
                "notes": a.notes
            }
            for a in appts
        ]
    }


def get_patient_documents(user_id: str) -> Dict[str, Any]:
    """Retrieve list of medical documents for the patient."""
    docs = db.get_user_documents(user_id=user_id)
    return {
        "status": "success",
        "user_id": user_id,
        "count": len(docs),
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "type": d.document_type.value,
                "upload_date": d.upload_date,
                "summary": d.summary,
                "key_findings": d.key_findings
            }
            for d in docs
        ]
    }


def read_patient_document(user_id: str, document_id: str) -> Dict[str, Any]:
    """Read a specific authorized patient medical document."""
    docs = db.get_user_documents(user_id=user_id)
    if not docs:
        return {"status": "error", "message": "No medical documents found for this patient."}

    clean_id = (document_id or "").strip().lower()
    target_doc = None
    if clean_id:
        for d in docs:
            if d.id.lower() == clean_id or clean_id in d.id.lower() or clean_id in d.title.lower():
                target_doc = d
                break
        if not target_doc:
            return {"status": "error", "message": f"Document '{document_id}' not found."}
    else:
        target_doc = sorted(docs, key=lambda x: x.upload_date, reverse=True)[0]

    return {
        "status": "success",
        "document_id": target_doc.id,
        "title": target_doc.title,
        "type": target_doc.document_type.value,
        "upload_date": target_doc.upload_date,
        "content": target_doc.extracted_text,
        "summary": target_doc.summary,
        "key_findings": target_doc.key_findings,
        "message": f"Document '{target_doc.title}' ({target_doc.document_type.value}): {target_doc.summary}"
    }


def search_hospital_knowledge(query: str, user_id: str = "") -> Dict[str, Any]:
    """Search hospital general information, policies, visiting hours, and registration FAQs."""
    results = db.search_knowledge_base(query=query, user_id=user_id or None)
    chunk_ids = [r["chunk_id"] for r in results if "chunk_id" in r]
    return {
        "status": "success",
        "query": query,
        "knowledge_entries": results,
        "retrieved_chunk_ids": chunk_ids
    }


def prepare_consultation_summary(user_id: str) -> Dict[str, Any]:
    """Aggregate patient history and documents into a structured consultation preparation brief."""
    appts = db.get_user_appointments(user_id=user_id)
    docs = db.get_user_documents(user_id=user_id)
    user = db.get_user(user_id)
    patient_name = user.name if user else f"Patient {user_id}"

    recent_appts = sorted(appts, key=lambda x: x.date, reverse=True)[:3]
    recent_docs = sorted(docs, key=lambda x: x.upload_date, reverse=True)[:3]

    return {
        "status": "success",
        "patient_id": user_id,
        "patient_name": patient_name,
        "summary_brief": {
            "total_past_appointments": len(appts),
            "recent_appointments": [
                f"{a.date} - {a.doctor_name} ({a.department_name}) [{a.status.value}]"
                for a in recent_appts
            ] if recent_appts else ["No past appointments found."],
            "relevant_documents": [
                f"{d.title} ({d.document_type.value}) uploaded on {d.upload_date}: {d.summary or 'Document on file'}"
                for d in recent_docs
            ] if recent_docs else ["No medical documents uploaded yet."]
        }
    }


# Backwards compatibility alias
read_document = read_patient_document

