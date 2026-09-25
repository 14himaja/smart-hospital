"""Doctor and department repository."""

import json
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
import sqlite3

from app.db.connection import get_db_connection
from app.models import Department, Doctor, AppointmentSlot


def row_to_department(row: sqlite3.Row) -> Department:
    return Department(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        location=row["location"]
    )


def row_to_doctor(row: sqlite3.Row) -> Doctor:
    try:
        days = json.loads(row["available_days"])
    except Exception:
        days = []
    return Doctor(
        id=row["id"],
        name=row["name"],
        department_id=row["department_id"],
        department_name=row["department_name"],
        specialty=row["specialty"],
        available_days=days,
        consultation_fee=float(row["consultation_fee"])
    )


def row_to_slot(row: sqlite3.Row) -> AppointmentSlot:
    return AppointmentSlot(
        slot_id=row["slot_id"],
        doctor_id=row["doctor_id"],
        doctor_name=row["doctor_name"],
        department_name=row["department_name"],
        date=row["date"],
        time=row["time"],
        is_available=bool(row["is_available"])
    )


class DoctorRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_departments(self) -> List[Department]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM departments")
            return [row_to_department(r) for r in cursor.fetchall()]

    def get_department(self, dept_id: str) -> Optional[Department]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM departments WHERE id = ?", (dept_id,))
            row = cursor.fetchone()
            return row_to_department(row) if row else None

    def get_doctors(self, department_name: Optional[str] = None, specialty: Optional[str] = None) -> List[Doctor]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM doctors WHERE 1=1"
            params = []
            if department_name:
                query += " AND LOWER(department_name) LIKE ?"
                params.append(f"%{department_name.lower().strip()}%")
            if specialty:
                clean_spec = specialty.lower().strip()
                root_spec = clean_spec.replace("ist", "").replace("y", "").replace("ics", "").replace("ic", "").rstrip("s")
                query += " AND (LOWER(specialty) LIKE ? OR LOWER(department_name) LIKE ? OR LOWER(specialty) LIKE ? OR LOWER(department_name) LIKE ?)"
                params.extend([f"%{clean_spec}%", f"%{clean_spec}%", f"%{root_spec}%", f"%{root_spec}%"])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Do NOT fallback to all doctors if specialty was provided but not found!
            return [row_to_doctor(r) for r in rows]

    def get_doctor(self, doctor_id: str) -> Optional[Doctor]:
        if not doctor_id:
            return None
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            clean_id = str(doctor_id).strip()

            # 1. Exact ID match (e.g. DOC-001)
            cursor.execute("SELECT * FROM doctors WHERE UPPER(id) = UPPER(?)", (clean_id,))
            row = cursor.fetchone()
            if row:
                return row_to_doctor(row)

            # 2. Exact name match (case-insensitive)
            cursor.execute("SELECT * FROM doctors WHERE LOWER(name) = LOWER(?)", (clean_id,))
            row = cursor.fetchone()
            if row:
                return row_to_doctor(row)

            cursor.execute("SELECT * FROM doctors")
            all_docs = [row_to_doctor(r) for r in cursor.fetchall()]

            def normalize_name(s: str) -> str:
                s = s.lower().replace(".", " ").replace(",", " ")
                s = re.sub(r"\b(dr|doctor|prof|physician|specialist)\b", "", s)
                return re.sub(r"\s+", " ", s).strip()

            norm_query = normalize_name(clean_id)
            if not norm_query:
                return None

            # 3. Match normalized exact name
            for d in all_docs:
                if normalize_name(d.name) == norm_query:
                    return d

            # 4. Token match in doctor name
            query_tokens = [t for t in norm_query.split() if len(t) > 1]
            for d in all_docs:
                doc_norm = normalize_name(d.name)
                if norm_query in doc_norm or doc_norm in norm_query:
                    return d
                doc_tokens = doc_norm.split()
                if query_tokens and all(any(qt in dt or dt in qt for dt in doc_tokens) for qt in query_tokens):
                    return d

            return None

    def get_slots(self, doctor_id: str, date_str: Optional[str] = None, available_only: bool = True) -> List[AppointmentSlot]:
        self.ensure_active_slots()
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM slots WHERE doctor_id = ?"
            params = [doctor_id]
            if date_str:
                query += " AND date = ?"
                params.append(date_str)
            if available_only:
                query += " AND is_available = 1"
            query += " ORDER BY date, time"
            cursor.execute(query, params)
            return [row_to_slot(r) for r in cursor.fetchall()]

    def ensure_active_slots(self, days_ahead: int = 14) -> None:
        """Ensure active slots exist in SQLite for the upcoming days for all doctors."""
        today = date.today()
        time_options = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]
        weekday_map = {
            0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
            4: "Friday", 5: "Saturday", 6: "Sunday"
        }

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM doctors")
            docs = cursor.fetchall()

            for doc in docs:
                doc_id = doc["id"]
                doc_name = doc["name"]
                dept_name = doc["department_name"]
                try:
                    avail_days = json.loads(doc["available_days"])
                except Exception:
                    avail_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

                for offset in range(0, days_ahead + 1):
                    target_date = today + timedelta(days=offset)
                    target_weekday = weekday_map[target_date.weekday()]
                    if target_weekday not in avail_days:
                        continue

                    target_date_str = target_date.isoformat()
                    for t in time_options:
                        slot_id = f"SLOT-{doc_id}-{target_date_str}-{t.replace(':', '')}"
                        # Insert slot if not already existing
                        cursor.execute(
                            "INSERT OR IGNORE INTO slots (slot_id, doctor_id, doctor_name, department_name, date, time, is_available) VALUES (?, ?, ?, ?, ?, ?, 1)",
                            (slot_id, doc_id, doc_name, dept_name, target_date_str, t)
                        )
            conn.commit()
