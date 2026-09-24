import re
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from app.database import db


def normalize_date_str(date_str: Optional[str]) -> Optional[str]:
    """Normalize user or voice spoken relative date strings into standard YYYY-MM-DD."""
    if not date_str:
        return None
    raw = str(date_str).strip().lower()
    today = date.today()

    if raw in ("today", "now"):
        return today.isoformat()
    if raw in ("tomorrow", "tmrw"):
        return (today + timedelta(days=1)).isoformat()
    if raw in ("day after tomorrow", "day after tmrw"):
        return (today + timedelta(days=2)).isoformat()

    weekday_map = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6
    }
    for day_name, day_idx in weekday_map.items():
        if day_name in raw:
            days_ahead = (day_idx - today.weekday() + 7) % 7
            if days_ahead == 0 and ("next" in raw or "upcoming" in raw):
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).isoformat()

    # Match standard YYYY-MM-DD
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Match DD-MM-YYYY
    match_dmy = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", raw)
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
        if m_name in raw:
            day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", raw)
            if day_match:
                d = int(day_match.group(1))
                return f"{today.year:04d}-{m_num:02d}-{d:02d}"

    return raw


def normalize_time_str(time_str: Optional[str]) -> str:
    """Normalize spoken time strings (e.g. '10:00 AM', '10 AM', '2pm') into standard HH:MM."""
    if not time_str:
        return "09:00"
    raw = str(time_str).strip().lower()
    is_pm = "pm" in raw
    is_am = "am" in raw
    clean = re.sub(r"[^\d:]", "", raw)
    if ":" in clean:
        parts = clean.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    elif clean:
        h = int(clean)
        m = 0
    else:
        return time_str

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
                "fee": f"${d.consultation_fee:.2f}"
            }
            for d in docs
        ]
    }


def get_available_slots(doctor_id: str = "", date: str = "") -> Dict[str, Any]:
    """Get available appointment time slots for a given doctor across upcoming dates or for a specific date (YYYY-MM-DD)."""
    clean_date = normalize_date_str(date) if date else None
    doc = db.get_doctor(doctor_id) if doctor_id else None

    if not doc and doctor_id:
        # Try finding doctors by department or specialty
        matched_docs = db.get_doctors(department_name=doctor_id, specialty=doctor_id)
        if matched_docs:
            doc = matched_docs[0]

    if not doc:
        # If doctor still not specified, return directory of active doctors
        all_docs = db.get_doctors()
        return {
            "status": "error",
            "message": "Doctor not found. Please specify one of our hospital doctors.",
            "available_doctors": [
                {"id": d.id, "name": d.name, "department": d.department_name, "specialty": d.specialty, "fee": f"${d.consultation_fee:.2f}", "days": d.available_days}
                for d in all_docs
            ]
        }

    actual_doc_id = doc.id
    doc_name = doc.name

    if clean_date:
        slots = db.get_slots(doctor_id=actual_doc_id, date_str=clean_date, available_only=True)
        times = [s.time for s in slots]
        if times:
            return {
                "status": "success",
                "doctor_id": actual_doc_id,
                "doctor_name": doc_name,
                "department": doc.department_name,
                "specialty": doc.specialty,
                "consultation_fee": f"${doc.consultation_fee:.2f}",
                "date": clean_date,
                "available_slots": times,
                "message": f"Available slots for {doc_name} on {clean_date}: {', '.join(times)}."
            }
        else:
            # If no slots on requested date, also supply upcoming available dates
            upcoming_slots = db.get_slots(doctor_id=actual_doc_id, available_only=True)
            by_date = {}
            for s in upcoming_slots:
                by_date.setdefault(s.date, []).append(s.time)
            return {
                "status": "success",
                "doctor_id": actual_doc_id,
                "doctor_name": doc_name,
                "department": doc.department_name,
                "date": clean_date,
                "available_slots": [],
                "available_slots_by_date": by_date,
                "message": f"No available slots on {clean_date} for {doc_name}. Upcoming available dates: " + ", ".join(list(by_date.keys())[:3])
            }

    # If no specific date was passed, return all upcoming slots grouped by date
    all_slots = db.get_slots(doctor_id=actual_doc_id, available_only=True)
    slots_by_date = {}
    for s in all_slots:
        slots_by_date.setdefault(s.date, []).append(s.time)

    date_summaries = [f"{d}: {', '.join(times)}" for d, times in list(slots_by_date.items())[:4]]
    return {
        "status": "success",
        "doctor_id": actual_doc_id,
        "doctor_name": doc_name,
        "department": doc.department_name,
        "specialty": doc.specialty,
        "consultation_fee": f"${doc.consultation_fee:.2f}",
        "available_days": doc.available_days,
        "available_slots_by_date": slots_by_date,
        "available_dates": list(slots_by_date.keys()),
        "message": f"{doc_name} ({doc.specialty}) has available slots on: " + "; ".join(date_summaries)
    }


def book_appointment(user_id: str, doctor_id: str, date: str, time: str, confirmed: bool = False, notes: str = "") -> Dict[str, Any]:
    """Book an appointment for a patient.
    
    CRITICAL GUARDRAIL: The user must explicitly confirm the booking details before calling this tool with confirmed=True.
    If confirmed is False, return a confirmation prompt request.
    """
    clean_date = normalize_date_str(date) or date
    clean_time = normalize_time_str(time)
    doc = db.get_doctor(doctor_id)
    doc_name = doc.name if doc else doctor_id
    actual_doc_id = doc.id if doc else doctor_id

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": (
                f"Please confirm: Do you want to book an appointment with {doc_name} "
                f"on {clean_date} at {clean_time}? Respond 'Yes, I confirm' to proceed."
            ),
            "pending_action": {
                "action": "book_appointment",
                "doctor_id": actual_doc_id,
                "doctor_name": doc_name,
                "date": clean_date,
                "time": clean_time,
                "notes": notes
            }
        }

    appt = db.book_appointment(user_id=user_id, doctor_id=actual_doc_id, date_str=clean_date, time_str=clean_time, notes=notes)
    if not appt:
        return {
            "status": "error",
            "message": f"Doctor {doc_name} or slot at {clean_time} on {clean_date} not available. Please choose another time."
        }

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
    """Cancel an existing appointment.
    
    CRITICAL GUARDRAIL: The user must explicitly confirm cancellation before confirmed=True is passed.
    """
    appt = db.appointments.get(appointment_id)
    if not appt or appt.user_id != user_id:
        return {
            "status": "error",
            "message": "Appointment not found or you are not authorized to cancel it."
        }

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": (
                f"Are you sure you want to cancel your appointment with {appt.doctor_name} "
                f"on {appt.date} at {appt.time}? Respond 'Confirm cancellation' to proceed."
            ),
            "pending_action": {
                "action": "cancel_appointment",
                "appointment_id": appointment_id
            }
        }

    success = db.cancel_appointment(user_id=user_id, appointment_id=appointment_id)
    if success:
        return {
            "status": "success",
            "message": f"Appointment {appointment_id} has been cancelled."
        }
    return {
        "status": "error",
        "message": "Failed to cancel appointment."
    }


def reschedule_appointment(user_id: str, appointment_id: str, new_date: str, new_time: str, confirmed: bool = False) -> Dict[str, Any]:
    """Reschedule an existing appointment to a new date and time.
    
    CRITICAL GUARDRAIL: User confirmation required before confirmed=True.
    """
    clean_date = normalize_date_str(new_date) or new_date
    clean_time = normalize_time_str(new_time)
    appt = db.appointments.get(appointment_id)
    if not appt or appt.user_id != user_id:
        return {
            "status": "error",
            "message": "Appointment not found or you are not authorized to reschedule it."
        }

    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": (
                f"Please confirm: Reschedule appointment {appointment_id} with {appt.doctor_name} "
                f"to {clean_date} at {clean_time}? Respond 'Yes, confirm reschedule' to proceed."
            ),
            "pending_action": {
                "action": "reschedule_appointment",
                "appointment_id": appointment_id,
                "new_date": clean_date,
                "new_time": clean_time
            }
        }

    rescheduled = db.reschedule_appointment(user_id=user_id, appointment_id=appointment_id, new_date=clean_date, new_time=clean_time)
    if rescheduled:
        return {
            "status": "success",
            "message": f"Appointment {appointment_id} rescheduled to {clean_date} at {clean_time}.",
            "appointment": {
                "id": rescheduled.id,
                "doctor": rescheduled.doctor_name,
                "date": rescheduled.date,
                "time": rescheduled.time
            }
        }
    return {
        "status": "error",
        "message": f"Slot at {clean_time} on {clean_date} is not available. Please choose another time."
    }


def get_appointment_history(user_id: str) -> Dict[str, Any]:
    """Retrieve appointment records for the authenticated user, separating active scheduled appointments from past history."""
    appts = db.get_user_appointments(user_id=user_id)
    today_str = date.today().isoformat()
    
    # Active appointments: confirmed/scheduled on or after today
    scheduled_appts = [a for a in appts if a.status.value in ("confirmed", "scheduled") and a.date >= today_str]
    past_appts = [a for a in appts if a.status.value in ("completed", "cancelled") or (a.status.value in ("confirmed", "scheduled") and a.date < today_str)]

    sorted_sched = sorted(scheduled_appts, key=lambda x: (x.date, x.time))
    
    if sorted_sched:
        summary_items = [f"{a.doctor_name} ({a.department_name}) on {a.date} at {a.time}" for a in sorted_sched[:3]]
        spoken_summary = f"You have {len(sorted_sched)} upcoming appointment(s): " + "; ".join(summary_items) + "."
    else:
        spoken_summary = "You currently have no upcoming scheduled appointments."

    return {
        "status": "success",
        "user_id": user_id,
        "total_appointments": len(appts),
        "scheduled_appointments_count": len(sorted_sched),
        "summary": spoken_summary,
        "scheduled_appointments": [
            {
                "id": a.id,
                "doctor": a.doctor_name,
                "department": a.department_name,
                "date": a.date,
                "time": a.time,
                "status": a.status.value,
                "notes": a.notes
            }
            for a in sorted_sched
        ],
        "past_history_appointments": [
            {
                "id": a.id,
                "doctor": a.doctor_name,
                "department": a.department_name,
                "date": a.date,
                "time": a.time,
                "status": a.status.value,
                "notes": a.notes
            }
            for a in sorted(past_appts, key=lambda x: x.date, reverse=True)
        ]
    }


def get_patient_documents(user_id: str) -> Dict[str, Any]:
    """List medical documents belonging to the authenticated user."""
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
                "summary": d.summary
            }
            for d in docs
        ]
    }


def read_document(user_id: str, document_id: str = "") -> Dict[str, Any]:
    """Read the extracted contents of an authorized document or lab report."""
    docs = db.get_user_documents(user_id=user_id)
    if not docs:
        return {
            "status": "error",
            "message": "No medical documents or lab reports found on file for this patient."
        }

    target_doc = None
    clean_id = (document_id or "").strip().lower()

    if clean_id:
        for d in docs:
            if d.id.lower() == clean_id or clean_id in d.id.lower() or clean_id in d.title.lower():
                target_doc = d
                break

    if not target_doc:
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


def search_hospital_knowledge(query: str) -> Dict[str, Any]:
    """Search hospital general information, policies, visiting hours, and registration FAQs."""
    results = db.search_knowledge_base(query=query)
    chunk_ids = [r["chunk_id"] for r in results if "chunk_id" in r]
    return {
        "status": "success",
        "query": query,
        "knowledge_entries": results,
        "retrieved_chunk_ids": chunk_ids
    }



def prepare_consultation_summary(user_id: str) -> Dict[str, Any]:
    """Aggregate authorized patient history and documents into a structured consultation preparation brief."""
    appts = db.get_user_appointments(user_id=user_id)
    docs = db.get_user_documents(user_id=user_id)
    user = db.get_user(user_id)

    # Resolve patient name from user record, or fall back to appointment records
    patient_name = None
    if user and user.name:
        patient_name = user.name
    elif appts:
        # Some seeded appointments store the patient name indirectly; use user_id as fallback
        patient_name = None
    patient_name = patient_name or (f"Patient {user_id}" if user_id else "Patient")

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
