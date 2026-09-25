"""Appointment repository."""

import uuid
from datetime import datetime, date
from typing import Dict, List, Optional, Any
import sqlite3

from app.db.connection import get_db_connection
from app.models import Appointment, AppointmentStatus, Doctor


def row_to_appointment(row: sqlite3.Row) -> Appointment:
    return Appointment(
        id=row["id"],
        user_id=row["user_id"],
        doctor_id=row["doctor_id"],
        doctor_name=row["doctor_name"],
        department_name=row["department_name"],
        date=row["date"],
        time=row["time"],
        status=AppointmentStatus(row["status"]),
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


class AppointmentRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_appointment(self, appointment_id: str) -> Optional[Appointment]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
            row = cursor.fetchone()
            return row_to_appointment(row) if row else None

    def get_user_appointments(self, user_id: str) -> List[Appointment]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM appointments WHERE user_id = ? ORDER BY date DESC, time DESC",
                (user_id,)
            )
            return [row_to_appointment(r) for r in cursor.fetchall()]

    def get_all_appointments(self) -> List[Appointment]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments ORDER BY date DESC, time DESC")
            return [row_to_appointment(r) for r in cursor.fetchall()]

    def book_appointment(
        self,
        user_id: str,
        doctor: Doctor,
        date_str: str,
        time_str: str,
        notes: str = ""
    ) -> Optional[Appointment]:
        """Atomically book an appointment and mark the slot unavailable."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Prevent double booking: verify no active (confirmed/scheduled) appointment exists for this doctor, date, and time
            cursor.execute(
                "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND time = ? AND status IN (?, ?)",
                (doctor.id, date_str, time_str, AppointmentStatus.CONFIRMED.value, AppointmentStatus.SCHEDULED.value)
            )
            if cursor.fetchone():
                return None

            # Mark slot unavailable if exists in slots table
            cursor.execute(
                "UPDATE slots SET is_available = 0 WHERE doctor_id = ? AND date = ? AND time = ?",
                (doctor.id, date_str, time_str)
            )

            appt_id = f"APPT-{uuid.uuid4().hex[:6].upper()}"
            now_str = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    appt_id,
                    user_id,
                    doctor.id,
                    doctor.name,
                    doctor.department_name,
                    date_str,
                    time_str,
                    AppointmentStatus.CONFIRMED.value,
                    notes,
                    now_str
                )
            )
            conn.commit()

        return Appointment(
            id=appt_id,
            user_id=user_id,
            doctor_id=doctor.id,
            doctor_name=doctor.name,
            department_name=doctor.department_name,
            date=date_str,
            time=time_str,
            status=AppointmentStatus.CONFIRMED,
            notes=notes,
            created_at=datetime.fromisoformat(now_str)
        )

    def cancel_appointment(self, user_id: str, appointment_id: str) -> bool:
        appt = self.get_appointment(appointment_id)
        if not appt or (user_id != "ADMIN" and appt.user_id != user_id):
            return False

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE appointments SET status = ? WHERE id = ?",
                (AppointmentStatus.CANCELLED.value, appointment_id)
            )
            cursor.execute(
                "UPDATE slots SET is_available = 1 WHERE doctor_id = ? AND date = ? AND time = ?",
                (appt.doctor_id, appt.date, appt.time)
            )
            conn.commit()
            return cursor.rowcount > 0

    def reschedule_appointment(
        self,
        user_id: str,
        appointment_id: str,
        new_date: str,
        new_time: str
    ) -> Optional[Appointment]:
        appt = self.get_appointment(appointment_id)
        if not appt or (user_id != "ADMIN" and appt.user_id != user_id):
            return None

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            # Free old slot
            cursor.execute(
                "UPDATE slots SET is_available = 1 WHERE doctor_id = ? AND date = ? AND time = ?",
                (appt.doctor_id, appt.date, appt.time)
            )
            # Reserve new slot
            cursor.execute(
                "UPDATE slots SET is_available = 0 WHERE doctor_id = ? AND date = ? AND time = ?",
                (appt.doctor_id, new_date, new_time)
            )
            # Update appointment
            cursor.execute(
                "UPDATE appointments SET date = ?, time = ?, status = ? WHERE id = ?",
                (new_date, new_time, AppointmentStatus.CONFIRMED.value, appointment_id)
            )
            conn.commit()

        appt.date = new_date
        appt.time = new_time
        appt.status = AppointmentStatus.CONFIRMED
        return appt

    def delete_appointment_permanently(self, appointment_id: str, user_id: Optional[str] = None) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "DELETE FROM appointments WHERE id = ? AND user_id = ? AND status IN (?, ?)",
                    (appointment_id, user_id, AppointmentStatus.CANCELLED.value, AppointmentStatus.COMPLETED.value)
                )
            else:
                cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
            conn.commit()
            return cursor.rowcount > 0

    def complete_appointment(self, appointment_id: str) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE appointments SET status = ? WHERE id = ?",
                (AppointmentStatus.COMPLETED.value, appointment_id)
            )
            conn.commit()
            return cursor.rowcount > 0
