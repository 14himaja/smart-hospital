import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.config import settings
from app.services.chunker import chunk_text
from app.models import (
    User, UserRole, Department, Doctor, AppointmentSlot,
    Appointment, AppointmentStatus, MedicalDocument, DocumentType, AuditLog
)


def hash_password(password: str) -> str:
    """Deterministic hash for auth."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class _DoctorStore:
    def __init__(self, db: "Database"):
        self._db = db

    def get(self, doctor_id: str) -> Optional[Doctor]:
        return self._db.get_doctor(doctor_id)

    def values(self) -> List[Doctor]:
        return self._db.get_doctors()

    def __getitem__(self, doctor_id: str) -> Doctor:
        doc = self.get(doctor_id)
        if not doc:
            raise KeyError(doctor_id)
        return doc


class _AppointmentStore:
    def __init__(self, db: "Database"):
        self._db = db

    def get(self, appointment_id: str) -> Optional[Appointment]:
        return self._db.get_appointment(appointment_id)

    def values(self) -> List[Appointment]:
        return self._db.get_all_appointments()

    def __getitem__(self, appointment_id: str) -> Appointment:
        appt = self.get(appointment_id)
        if not appt:
            raise KeyError(appointment_id)
        return appt


class _DocumentStore:
    def __init__(self, db: "Database"):
        self._db = db

    def get(self, document_id: str) -> Optional[MedicalDocument]:
        return self._db.get_document(document_id)

    def values(self) -> List[MedicalDocument]:
        return self._db.get_all_documents()

    def __getitem__(self, document_id: str) -> MedicalDocument:
        doc = self.get(document_id)
        if not doc:
            raise KeyError(document_id)
        return doc


class _UserStore:
    def __init__(self, db: "Database"):
        self._db = db

    def get(self, user_id: str) -> Optional[User]:
        return self._db.get_user(user_id)

    def values(self) -> List[User]:
        return self._db.get_all_users()

    def __len__(self) -> int:
        with self._db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]


class _OtpStore:
    def __init__(self, db: "Database"):
        self._db = db

    def __setitem__(self, email: str, otp: str):
        self._db.set_otp(email, otp)

    def __getitem__(self, email: str) -> str:
        otp = self.get(email)
        if otp is None:
            raise KeyError(email)
        return otp

    def get(self, email: str, default: Optional[str] = None) -> Optional[str]:
        return self._db.get_otp(email, default)


class Database:
    """SQLite-backed database for Smart Hospital Assistant."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or settings.DB_PATH)
        self._init_db()
        self._seed_data_if_empty()

        # Backward compatibility stores
        self.doctors = _DoctorStore(self)
        self.appointments = _AppointmentStore(self)
        self.documents = _DocumentStore(self)
        self.users = _UserStore(self)
        self.otps = _OtpStore(self)

    @property
    def audit_logs(self) -> List[AuditLog]:
        """Provide list-like access to recent audit logs."""
        return self.get_audit_logs()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    location TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    specialty TEXT NOT NULL,
                    available_days TEXT NOT NULL,
                    consultation_fee REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id TEXT PRIMARY KEY,
                    doctor_id TEXT NOT NULL,
                    doctor_name TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    is_available INTEGER NOT NULL DEFAULT 1
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT,
                    role TEXT NOT NULL,
                    is_verified INTEGER NOT NULL DEFAULT 1,
                    hashed_password TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    preferences TEXT NOT NULL DEFAULT '{}'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    doctor_name TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    summary TEXT,
                    key_findings TEXT NOT NULL DEFAULT '[]'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS otps (
                    email TEXT PRIMARY KEY,
                    otp TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hospital_documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    uploaded_by TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    file_type TEXT DEFAULT 'Direct Text'
                )
            """)
            try:
                cursor.execute("ALTER TABLE hospital_documents ADD COLUMN file_type TEXT DEFAULT 'Direct Text'")
            except Exception:
                pass
            conn.commit()

    def _seed_data_if_empty(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM departments")
            if cursor.fetchone()[0] > 0:
                return  # Database already seeded

            # 1. Seed Departments
            depts = [
                ("DEP-DERM", "Dermatology", "Skin, hair, and nail health, cosmetic dermatology, and skin allergy management.", "Building A, 2nd Floor, Wing B"),
                ("DEP-CARD", "Cardiology", "Comprehensive heart disease diagnostics, ECG, echocardiograms, and cardiac rehabilitation.", "Building B, 1st Floor, Heart Center"),
                ("DEP-ORTHO", "Orthopedics", "Bone and joint health, sports injuries, fractures, and spine care.", "Building A, Ground Floor"),
                ("DEP-PED", "Pediatrics", "Child wellness, vaccinations, neonatal care, and adolescent medicine.", "Building C, 3rd Floor"),
                ("DEP-RAD", "Radiology", "Diagnostic imaging including X-Ray, MRI, CT scans, and ultrasound.", "Building B, Basement Level 1")
            ]
            cursor.executemany("INSERT INTO departments VALUES (?, ?, ?, ?)", depts)

            # 2. Seed Doctors
            docs = [
                ("DOC-001", "Dr. Sarah Jenkins", "DEP-DERM", "Dermatology", "General & Cosmetic Dermatology", json.dumps(["Monday", "Wednesday", "Friday"]), 120.0),
                ("DOC-002", "Dr. B. K. Sharma", "DEP-DERM", "Dermatology", "Pediatric Dermatology & Allergy", json.dumps(["Monday", "Tuesday", "Thursday"]), 150.0),
                ("DOC-003", "Dr. Alan Vance", "DEP-CARD", "Cardiology", "Interventional Cardiology", json.dumps(["Tuesday", "Thursday", "Saturday"]), 200.0),
                ("DOC-004", "Dr. Elena Rostova", "DEP-ORTHO", "Orthopedics", "Joint Replacement & Sports Medicine", json.dumps(["Monday", "Wednesday", "Thursday"]), 180.0)
            ]
            cursor.executemany("INSERT INTO doctors VALUES (?, ?, ?, ?, ?, ?, ?)", docs)

            # 3. Seed Slots for next 7 days
            today = date.today()
            time_options = ["09:00", "10:00", "11:30", "14:00", "15:30", "16:30"]
            slots = []
            for i in range(1, 8):
                slot_date = (today + timedelta(days=i)).isoformat()
                for doc in docs:
                    doc_id, doc_name, _, dept_name, _, _, _ = doc
                    for t in time_options[:3]:
                        slot_id = f"SLOT-{doc_id}-{slot_date}-{t.replace(':', '')}"
                        slots.append((slot_id, doc_id, doc_name, dept_name, slot_date, t, 1))
            cursor.executemany("INSERT INTO slots VALUES (?, ?, ?, ?, ?, ?, ?)", slots)

            # 4. Seed Users
            now_str = datetime.utcnow().isoformat()
            users = [
                ("P1001", "Rahul Sharma", "rahul@example.com", "+91-9876543210", UserRole.PATIENT.value, 1, hash_password("password123"), now_str, json.dumps({"language": "English", "preferred_department": "Dermatology"})),
                ("P1002", "Priya Patel", "priya@example.com", "+91-9876543211", UserRole.PATIENT.value, 1, hash_password("password123"), now_str, json.dumps({"language": "English"})),
                ("D2001", "Dr. B. K. Sharma", "dr.b@hospital.org", None, UserRole.DOCTOR.value, 1, hash_password("doctorpass"), now_str, json.dumps({"language": "English"})),
                ("S3001", "Hospital Desk Staff", "staff@hospital.org", None, UserRole.STAFF.value, 1, hash_password("staffpass"), now_str, json.dumps({"language": "English"})),
                ("A4001", "Hospital Administrator", "admin@hospital.org", "+91-9999988888", UserRole.ADMIN.value, 1, hash_password("adminpass123"), now_str, json.dumps({"language": "English"}))
            ]
            cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", users)

            # 5. Seed Past & Upcoming Appointments (Covering All Statuses)
            past_appts = [
                ("APPT-1001", "P1001", "DOC-002", "Dr. B. K. Sharma", "Dermatology", (today - timedelta(days=14)).isoformat(), "10:00", AppointmentStatus.COMPLETED.value, "Initial consultation for skin eczema. Prescribed topical ointment.", now_str),
                ("APPT-1002", "P1001", "DOC-001", "Dr. Ananya Roy", "Cardiology", (today + timedelta(days=2)).isoformat(), "11:30", AppointmentStatus.CONFIRMED.value, "Routine cardiovascular checkup.", now_str),
                ("APPT-1003", "P1002", "DOC-003", "Dr. Rajesh Gupta", "Orthopedics", (today + timedelta(days=5)).isoformat(), "14:00", AppointmentStatus.SCHEDULED.value, "Knee joint pain evaluation.", now_str),
                ("APPT-1004", "P1002", "DOC-004", "Dr. Sunita Rao", "Pediatrics", (today - timedelta(days=7)).isoformat(), "09:00", AppointmentStatus.CANCELLED.value, "Patient requested cancellation.", now_str)
            ]
            cursor.executemany("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", past_appts)


            # 6. Seed Documents for P1001
            doc_text = (
                "Patient: Rahul Sharma (P1001)\n"
                "Date: 2026-09-08\n"
                "Test: Complete Blood Count (CBC) & Serum IgE Panel\n"
                "Hemoglobin: 14.5 g/dL (Normal Range: 13.5 - 17.5)\n"
                "WBC: 6,800 /mcL (Normal Range: 4,500 - 11,000)\n"
                "Platelets: 250,000 /mcL (Normal Range: 150,000 - 450,000)\n"
                "Serum IgE: 240 IU/mL (Elevated, Normal < 100 IU/mL)\n"
                "Impression: Mild allergic diathesis corresponding to atopic dermatitis."
            )
            doc_summary = "Lab report indicates normal blood counts with elevated Serum IgE (240 IU/mL), consistent with mild allergic sensitivity / atopic dermatitis."
            doc_findings = json.dumps(["Normal Hemoglobin & Platelets", "Elevated Serum IgE (240 IU/mL)"])
            docs_seed = [
                ("DOC-LAB-101", "P1001", "Complete Blood Count & Allergy Panel", DocumentType.LAB_REPORT.value, (today - timedelta(days=13)).isoformat(), doc_text, doc_summary, doc_findings)
            ]
            cursor.executemany("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)", docs_seed)

            # 7. Seed Knowledge Base
            kb = [
                ("Visiting Hours", "General hospital visiting hours are daily from 10:00 AM to 1:00 PM and 4:30 PM to 8:00 PM. In ICU units, visiting is restricted to 5:00 PM to 6:00 PM with a maximum of one visitor per patient."),
                ("Registration Requirements", "First-time patients must bring a government-issued photo ID (Passport, Driving License, or National ID), their insurance card if applicable, and any previous medical records or prescriptions. Online registration provides a digital Patient ID (e.g. P1001) for swift check-in at the kiosk."),
                ("Dermatology Procedures", "The Dermatology department provides diagnostic skin allergy testing, mole evaluations, eczema management, cryotherapy, and light therapy. Routine consultations take approximately 20 minutes."),
                ("Cardiology Services & Location", "Cardiology is located in Building B, 1st Floor Heart Center. It handles chest pain evaluation, hypertension management, ECG, stress tests, and echocardiograms. Fast-track triage is available for acute chest pain."),
                ("Emergency and Ambulatory Care", "Emergency trauma and acute care operates 24/7 at Gate 1 on the Ground Floor. For life-threatening emergencies, call the hospital rapid ambulance line directly at 911 or local emergency services.")
            ]
            cursor.executemany("INSERT INTO knowledge_base (topic, content) VALUES (?, ?)", kb)
            conn.commit()

    # --- Properties ---

    @property
    def audit_logs(self) -> List[AuditLog]:
        return self.get_audit_logs()

    @property
    def slots(self) -> List[AppointmentSlot]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM slots")
            return [
                AppointmentSlot(
                    slot_id=r["slot_id"],
                    doctor_id=r["doctor_id"],
                    doctor_name=r["doctor_name"],
                    department_name=r["department_name"],
                    date=r["date"],
                    time=r["time"],
                    is_available=bool(r["is_available"])
                )
                for r in cursor.fetchall()
            ]

    # --- Users ---

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,))
            row = cursor.fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                name=row["name"],
                email=row["email"],
                phone=row["phone"],
                role=UserRole(row["role"]),
                is_verified=bool(row["is_verified"]),
                hashed_password=row["hashed_password"],
                created_at=datetime.fromisoformat(row["created_at"]),
                preferences=json.loads(row["preferences"] or "{}")
            )

    def get_user(self, user_id: str) -> Optional[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                name=row["name"],
                email=row["email"],
                phone=row["phone"],
                role=UserRole(row["role"]),
                is_verified=bool(row["is_verified"]),
                hashed_password=row["hashed_password"],
                created_at=datetime.fromisoformat(row["created_at"]),
                preferences=json.loads(row["preferences"] or "{}")
            )

    def get_all_users(self) -> List[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            return [
                User(
                    user_id=r["user_id"],
                    name=r["name"],
                    email=r["email"],
                    phone=r["phone"],
                    role=UserRole(r["role"]),
                    is_verified=bool(r["is_verified"]),
                    hashed_password=r["hashed_password"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    preferences=json.loads(r["preferences"] or "{}")
                )
                for r in cursor.fetchall()
            ]

    def create_user(
        self,
        name: str,
        email: str,
        password: str,
        role: UserRole = UserRole.PATIENT,
        phone: Optional[str] = None,
        is_verified: bool = True
    ) -> User:
        user_id = f"P{1000 + len(self.users) + 1}"
        created_at = datetime.utcnow()
        new_user = User(
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            role=role,
            is_verified=is_verified,
            hashed_password=hash_password(password),
            created_at=created_at,
            preferences={"language": "English"}
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_user.user_id,
                    new_user.name,
                    new_user.email,
                    new_user.phone,
                    new_user.role.value,
                    1 if is_verified else 0,
                    new_user.hashed_password,
                    created_at.isoformat(),
                    json.dumps(new_user.preferences)
                )
            )
            conn.commit()
        return new_user

    def update_user_verification(self, user_id: str, verified: bool = True) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_verified = ? WHERE user_id = ?",
                (1 if verified else 0, user_id)
            )
            conn.commit()
        return True

    # --- Departments & Doctors ---

    def get_departments(self) -> List[Department]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM departments")
            return [
                Department(
                    id=r["id"],
                    name=r["name"],
                    description=r["description"] or "",
                    location=r["location"] or ""
                )
                for r in cursor.fetchall()
            ]

    def _row_to_doctor(self, row: Any) -> Doctor:
        days = row["available_days"]
        if isinstance(days, str):
            try:
                days = json.loads(days)
            except Exception:
                days = [d.strip() for d in days.split(",") if d.strip()]
        return Doctor(
            id=row["id"],
            name=row["name"],
            department_id=row["department_id"],
            department_name=row["department_name"],
            specialty=row["specialty"],
            available_days=days if isinstance(days, list) else [],
            consultation_fee=float(row["consultation_fee"])
        )

    def get_doctor(self, doctor_id: str) -> Optional[Doctor]:
        if not doctor_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            clean_id = str(doctor_id).strip()

            # 1. Exact ID match (e.g. DOC-001)
            cursor.execute("SELECT * FROM doctors WHERE UPPER(id) = UPPER(?)", (clean_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_doctor(row)

            # 2. Exact name match (case-insensitive)
            cursor.execute("SELECT * FROM doctors WHERE LOWER(name) = LOWER(?)", (clean_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_doctor(row)

            cursor.execute("SELECT * FROM doctors")
            all_docs = [self._row_to_doctor(r) for r in cursor.fetchall()]

            import re
            def normalize_name(s: str) -> str:
                s = s.lower().replace(".", " ").replace(",", " ")
                s = re.sub(r"\b(dr|doctor|prof|physician|specialist)\b", "", s)
                return re.sub(r"\s+", " ", s).strip()

            norm_query = normalize_name(clean_id)
            if not norm_query:
                return all_docs[0] if all_docs else None

            # 3. Match normalized exact name
            for d in all_docs:
                if normalize_name(d.name) == norm_query:
                    return d

            # 4. Token substring matching in doctor name
            query_tokens = [t for t in norm_query.split() if len(t) > 1]
            for d in all_docs:
                doc_norm = normalize_name(d.name)
                if norm_query in doc_norm or doc_norm in norm_query:
                    return d
                doc_tokens = doc_norm.split()
                if query_tokens and all(any(qt in dt or dt in qt for dt in doc_tokens) for qt in query_tokens):
                    return d

            # 5. Partial token match (e.g. "Sarah", "Alan", "Elena", "BK", "Sharma")
            for d in all_docs:
                doc_norm = normalize_name(d.name)
                for qt in query_tokens:
                    if qt in doc_norm.split() or (len(qt) >= 3 and qt in doc_norm):
                        return d

            # 6. Match by specialty or department (e.g. "cardiologist", "dermatologist", "orthopedic")
            for d in all_docs:
                spec_norm = normalize_name(d.specialty)
                dept_norm = normalize_name(d.department_name)
                for qt in query_tokens:
                    root = qt.rstrip("s").replace("ist", "").replace("y", "").replace("ics", "").replace("ic", "")
                    if (qt in spec_norm or qt in dept_norm) or (len(root) >= 4 and (root in spec_norm or root in dept_norm)):
                        return d

            return None

    def get_doctors(self, department_name: Optional[str] = None, specialty: Optional[str] = None) -> List[Doctor]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM doctors WHERE 1=1"
            params = []
            if department_name:
                query += " AND LOWER(department_name) LIKE ?"
                params.append(f"%{department_name.lower()}%")
            if specialty:
                clean_spec = specialty.lower().strip()
                root_spec = clean_spec.replace("ist", "").replace("y", "").replace("ics", "").replace("ic", "").rstrip("s")
                query += " AND (LOWER(specialty) LIKE ? OR LOWER(department_name) LIKE ? OR LOWER(specialty) LIKE ? OR LOWER(department_name) LIKE ?)"
                params.extend([f"%{clean_spec}%", f"%{clean_spec}%", f"%{root_spec}%", f"%{root_spec}%"])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Fallback if no exact match found but specialty was provided
            if not rows and specialty:
                cursor.execute("SELECT * FROM doctors")
                rows = cursor.fetchall()
            return [self._row_to_doctor(r) for r in rows]

    def ensure_active_slots(self, days_ahead: int = 14) -> None:
        """Ensure active slots exist in SQLite for the upcoming days for all doctors."""
        today = date.today()
        time_options = ["09:00", "10:00", "11:30", "14:00", "15:30", "16:30"]
        weekday_map = {
            0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
            4: "Friday", 5: "Saturday", 6: "Sunday"
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM doctors")
            docs = cursor.fetchall()

            new_slots = []
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
                    for t in time_options[:4]:
                        slot_id = f"SLOT-{doc_id}-{target_date_str}-{t.replace(':', '')}"
                        new_slots.append((slot_id, doc_id, doc_name, dept_name, target_date_str, t, 1))

            if new_slots:
                cursor.executemany(
                    "INSERT OR IGNORE INTO slots (slot_id, doctor_id, doctor_name, department_name, date, time, is_available) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    new_slots
                )
                conn.commit()

    # --- Slots ---

    def get_slots(self, doctor_id: Optional[str] = None, date_str: Optional[str] = None, available_only: bool = False) -> List[AppointmentSlot]:
        self.ensure_active_slots()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM slots WHERE 1=1"
            params = []
            if doctor_id:
                doc = self.get_doctor(doctor_id)
                actual_id = doc.id if doc else doctor_id
                query += " AND doctor_id = ?"
                params.append(actual_id)
            if date_str and date_str.strip():
                query += " AND date = ?"
                params.append(date_str.strip())
            query += " ORDER BY date ASC, time ASC"
            cursor.execute(query, params)
            slots_rows = cursor.fetchall()

            # Cross-reference with active appointments in DB to guarantee accurate availability
            cursor.execute(
                "SELECT doctor_id, date, time FROM appointments WHERE status IN (?, ?)",
                (AppointmentStatus.CONFIRMED.value, AppointmentStatus.SCHEDULED.value)
            )
            booked_set = {(r["doctor_id"], r["date"], r["time"]) for r in cursor.fetchall()}

            result = []
            for r in slots_rows:
                is_booked = (r["doctor_id"], r["date"], r["time"]) in booked_set
                is_avail = not is_booked
                if available_only and not is_avail:
                    continue
                result.append(
                    AppointmentSlot(
                        slot_id=r["slot_id"],
                        doctor_id=r["doctor_id"],
                        doctor_name=r["doctor_name"],
                        department_name=r["department_name"],
                        date=r["date"],
                        time=r["time"],
                        is_available=is_avail
                    )
                )
            return result

    # --- Appointments ---

    def get_appointment(self, appointment_id: str) -> Optional[Appointment]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
            row = cursor.fetchone()
            if not row:
                return None
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

    def get_all_appointments(self) -> List[Appointment]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments ORDER BY date DESC, time DESC")
            return [
                Appointment(
                    id=r["id"],
                    user_id=r["user_id"],
                    doctor_id=r["doctor_id"],
                    doctor_name=r["doctor_name"],
                    department_name=r["department_name"],
                    date=r["date"],
                    time=r["time"],
                    status=AppointmentStatus(r["status"]),
                    notes=r["notes"],
                    created_at=datetime.fromisoformat(r["created_at"])
                )
                for r in cursor.fetchall()
            ]

    def get_user_appointments(self, user_id: str) -> List[Appointment]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments WHERE user_id = ? ORDER BY date DESC, time DESC", (user_id,))
            return [
                Appointment(
                    id=r["id"],
                    user_id=r["user_id"],
                    doctor_id=r["doctor_id"],
                    doctor_name=r["doctor_name"],
                    department_name=r["department_name"],
                    date=r["date"],
                    time=r["time"],
                    status=AppointmentStatus(r["status"]),
                    notes=r["notes"],
                    created_at=datetime.fromisoformat(r["created_at"])
                )
                for r in cursor.fetchall()
            ]

    def book_appointment(self, user_id: str, doctor_id: str, date_str: str, time_str: str, notes: Optional[str] = None) -> Optional[Appointment]:
        doc = self.get_doctor(doctor_id)
        if not doc:
            return None

        actual_doctor_id = doc.id
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Prevent double booking: verify no active (confirmed/scheduled) appointment exists for this doctor, date, and time
            cursor.execute(
                "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND time = ? AND status IN (?, ?)",
                (actual_doctor_id, date_str, time_str, AppointmentStatus.CONFIRMED.value, AppointmentStatus.SCHEDULED.value)
            )
            if cursor.fetchone():
                # Slot is already booked by another user!
                return None

            # Mark slot unavailable if exists in slots table
            cursor.execute(
                "UPDATE slots SET is_available = 0 WHERE doctor_id = ? AND date = ? AND time = ?",
                (actual_doctor_id, date_str, time_str)
            )

            appt_id = f"APPT-{uuid.uuid4().hex[:6].upper()}"
            now_str = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    appt_id,
                    user_id,
                    actual_doctor_id,
                    doc.name,
                    doc.department_name,
                    date_str,
                    time_str,
                    AppointmentStatus.CONFIRMED.value,
                    notes,
                    now_str
                )
            )
            conn.commit()

        appt = Appointment(
            id=appt_id,
            user_id=user_id,
            doctor_id=doc.id,
            doctor_name=doc.name,
            department_name=doc.department_name,
            date=date_str,
            time=time_str,
            status=AppointmentStatus.CONFIRMED,
            notes=notes,
            created_at=datetime.fromisoformat(now_str)
        )
        self.log_audit(user_id=user_id, action="BOOK_APPOINTMENT", details={"appointment_id": appt.id, "doctor": doc.name})
        return appt

    def cancel_appointment(self, user_id: str, appointment_id: str) -> bool:
        appt = self.get_appointment(appointment_id)
        if not appt or appt.user_id != user_id:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE appointments SET status = ? WHERE id = ?", (AppointmentStatus.CANCELLED.value, appointment_id))
            cursor.execute("UPDATE slots SET is_available = 1 WHERE doctor_id = ? AND date = ? AND time = ?", (appt.doctor_id, appt.date, appt.time))
            conn.commit()

        self.log_audit(user_id=user_id, action="CANCEL_APPOINTMENT", details={"appointment_id": appt.id})
        return True

    def delete_appointment_permanently(self, appointment_id: str, user_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                # Patient deletion: allow deleting if CANCELLED or COMPLETED
                cursor.execute(
                    "DELETE FROM appointments WHERE id = ? AND user_id = ? AND status IN (?, ?)",
                    (appointment_id, user_id, AppointmentStatus.CANCELLED.value, AppointmentStatus.COMPLETED.value)
                )
            else:
                # Admin deletion: can delete any appointment
                cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            self.log_audit(user_id=user_id or "ADMIN", action="PURGE_APPOINTMENT", details={"appointment_id": appointment_id})
        return deleted

    def complete_appointment(self, appointment_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE appointments SET status = ? WHERE id = ?",
                (AppointmentStatus.COMPLETED.value, appointment_id)
            )
            conn.commit()
            updated = cursor.rowcount > 0
        if updated:
            self.log_audit(user_id="ADMIN", action="COMPLETE_APPOINTMENT", details={"appointment_id": appointment_id})
        return updated

    def reschedule_appointment(self, user_id: str, appointment_id: str, new_date: str, new_time: str) -> Optional[Appointment]:
        appt = self.get_appointment(appointment_id)
        if not appt or appt.user_id != user_id:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Free old slot
            cursor.execute("UPDATE slots SET is_available = 1 WHERE doctor_id = ? AND date = ? AND time = ?", (appt.doctor_id, appt.date, appt.time))
            # Reserve new slot
            cursor.execute("UPDATE slots SET is_available = 0 WHERE doctor_id = ? AND date = ? AND time = ?", (appt.doctor_id, new_date, new_time))
            # Update appointment
            cursor.execute(
                "UPDATE appointments SET date = ?, time = ?, status = ? WHERE id = ?",
                (new_date, new_time, AppointmentStatus.CONFIRMED.value, appointment_id)
            )
            conn.commit()

        appt.date = new_date
        appt.time = new_time
        appt.status = AppointmentStatus.CONFIRMED

        self.log_audit(user_id=user_id, action="RESCHEDULE_APPOINTMENT", details={"appointment_id": appt.id, "new_date": new_date, "new_time": new_time})
        return appt

    # --- Documents ---

    def get_document(self, document_id: str) -> Optional[MedicalDocument]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return MedicalDocument(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                document_type=DocumentType(row["document_type"]),
                upload_date=row["upload_date"],
                extracted_text=row["extracted_text"],
                summary=row["summary"],
                key_findings=json.loads(row["key_findings"] or "[]")
            )

    def get_all_documents(self) -> List[MedicalDocument]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents")
            return [
                MedicalDocument(
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    document_type=DocumentType(r["document_type"]),
                    upload_date=r["upload_date"],
                    extracted_text=r["extracted_text"],
                    summary=r["summary"],
                    key_findings=json.loads(r["key_findings"] or "[]")
                )
                for r in cursor.fetchall()
            ]

    def get_user_documents(self, user_id: str) -> List[MedicalDocument]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE user_id = ? ORDER BY upload_date DESC", (user_id,))
            return [
                MedicalDocument(
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    document_type=DocumentType(r["document_type"]),
                    upload_date=r["upload_date"],
                    extracted_text=r["extracted_text"],
                    summary=r["summary"],
                    key_findings=json.loads(r["key_findings"] or "[]")
                )
                for r in cursor.fetchall()
            ]

    def add_document(self, user_id: str, title: str, doc_type: DocumentType, extracted_text: str, summary: Optional[str] = None, key_findings: Optional[List[str]] = None) -> MedicalDocument:
        doc_id = f"DOC-{uuid.uuid4().hex[:6].upper()}"
        today_str = date.today().isoformat()

        # Generate summary if missing
        if not summary:
            clean_lines = [line.strip() for line in (extracted_text or "").split("\n") if line.strip() and not line.strip().startswith("#")]
            if clean_lines:
                summary = " ".join(clean_lines[:2])
                if len(summary) > 200:
                    summary = summary[:197] + "..."
            else:
                summary = f"{doc_type.value.replace('_', ' ').title()} uploaded on {today_str}."

        # Extract key findings if missing
        findings = list(key_findings or [])
        if not findings and extracted_text:
            lines = [l.strip() for l in extracted_text.split("\n") if l.strip()]
            for line in lines:
                lower = line.lower()
                if any(kw in lower for kw in ("impression:", "diagnosis:", "result:", "test:", "detected", "elevated", "normal", "abnormal", "positive", "negative", "rx:", "tab", "capsule", "syrup", "dosage:")):
                    clean = line.lstrip("-*•> ").strip()
                    if clean and len(clean) <= 60 and clean not in findings:
                        findings.append(clean)
                if len(findings) >= 3:
                    break

        doc = MedicalDocument(
            id=doc_id,
            user_id=user_id,
            title=title,
            document_type=doc_type,
            upload_date=today_str,
            extracted_text=extracted_text,
            summary=summary,
            key_findings=findings
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc.id,
                    doc.user_id,
                    doc.title,
                    doc.document_type.value,
                    doc.upload_date,
                    doc.extracted_text,
                    doc.summary,
                    json.dumps(doc.key_findings)
                )
            )
            conn.commit()

        self.log_audit(user_id=user_id, action="UPLOAD_DOCUMENT", details={"document_id": doc.id, "title": title})

        # Sync FAISS vector store
        try:
            from app.services.faiss_store import faiss_store
            type_str = doc_type.value if hasattr(doc_type, "value") else str(doc_type)
            faiss_store.add_items([{
                "chunk_id": doc.id,
                "doc_id": doc.id,
                "text": f"Patient Document: {title}\nType: {type_str}\nSummary: {doc.summary}\nContent: {extracted_text}",
                "user_id": user_id,
                "topic": title,
                "source": "user_document"
            }])
        except Exception as e:
            print(f"[FAISS Sync Warning] Error adding patient document to FAISS: {e}")

        return doc

    def delete_document(self, document_id: str, user_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id and user_id != "ADMIN":
                cursor.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
            else:
                cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            self.log_audit(user_id=user_id or "UNKNOWN", action="DELETE_USER_DOCUMENT", details={"document_id": document_id})
            # Sync FAISS vector store
            try:
                from app.services.faiss_store import faiss_store
                faiss_store.remove_document_chunks(document_id)
            except Exception as e:
                print(f"[FAISS Sync Warning] Error removing patient document from FAISS: {e}")
        return deleted

    # --- Admin Hospital Documents & FAISS-backed Chunk Management ---

    def add_hospital_document(
        self,
        title: str,
        category: str,
        uploaded_by: str,
        content: str,
        file_type: str = "Direct Text"
    ) -> Dict[str, Any]:
        doc_id = f"HDOC-{uuid.uuid4().hex[:6].upper()}"
        today_str = date.today().isoformat()
        
        # 1. Save parent document metadata in SQLite (structured data only)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO hospital_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, title, category, uploaded_by, today_str, content, file_type)
            )
            conn.commit()

        # 2. Chunk document and store chunks strictly in FAISS vector store
        chunks = chunk_text(content, chunk_size=400, overlap=80)
        self.log_audit(user_id=uploaded_by, action="ADMIN_UPLOAD_HOSPITAL_DOC", details={"doc_id": doc_id, "title": title, "file_type": file_type, "chunk_count": len(chunks)})
        
        try:
            from app.services.faiss_store import faiss_store
            faiss_items = [
                {
                    "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                    "doc_id": doc_id,
                    "text": f"{c['chunk_title']}\n{c['chunk_text']}",
                    "user_id": "PUBLIC",
                    "topic": f"Doc Chunk: {c['chunk_title']}",
                    "source": "hospital_doc"
                }
                for c in chunks
            ]
            faiss_store.add_items(faiss_items)
        except Exception as e:
            print(f"[FAISS Sync Warning] Error adding hospital doc chunks to FAISS: {e}")

        return {
            "id": doc_id,
            "title": title,
            "category": category,
            "uploaded_by": uploaded_by,
            "upload_date": today_str,
            "file_type": file_type,
            "chunk_count": len(chunks),
            "chunks": chunks
        }

    def get_hospital_documents(self) -> List[Dict[str, Any]]:
        """Retrieve hospital parent documents from SQLite and augment with FAISS chunk counts."""
        try:
            from app.services.faiss_store import faiss_store
        except Exception:
            faiss_store = None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, category, uploaded_by, upload_date, content,
                       COALESCE(file_type, 'Direct Text') as file_type
                FROM hospital_documents
                ORDER BY upload_date DESC
            """)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                doc_id = r["id"]
                c_count = faiss_store.count_chunks_for_doc(doc_id) if faiss_store else 0
                results.append({
                    "id": doc_id,
                    "title": r["title"],
                    "category": r["category"],
                    "uploaded_by": r["uploaded_by"],
                    "upload_date": r["upload_date"],
                    "content": r["content"],
                    "file_type": r["file_type"],
                    "chunk_count": c_count
                })
            return results

    def update_hospital_document(
        self,
        doc_id: str,
        title: Optional[str] = None,
        category: Optional[str] = None,
        content: Optional[str] = None,
        user_id: str = "A4001"
    ) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hospital_documents WHERE id = ?", (doc_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                return None

            new_title = title.strip() if title and title.strip() else doc_row["title"]
            new_category = category.strip() if category and category.strip() else doc_row["category"]
            new_content = content.strip() if content and content.strip() else doc_row["content"]

            cursor.execute(
                "UPDATE hospital_documents SET title = ?, category = ?, content = ? WHERE id = ?",
                (new_title, new_category, new_content, doc_id)
            )
            conn.commit()

        self.log_audit(user_id=user_id, action="ADMIN_UPDATE_HOSPITAL_DOC", details={"doc_id": doc_id, "title": new_title})

        # Update FAISS chunks if content changed
        if content and content.strip() and content.strip() != doc_row["content"]:
            try:
                from app.services.faiss_store import faiss_store
                faiss_store.remove_document_chunks(doc_id)
                chunks = chunk_text(new_content, chunk_size=400, overlap=80)
                faiss_items = [
                    {
                        "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                        "doc_id": doc_id,
                        "text": f"{c['chunk_title']}\n{c['chunk_text']}",
                        "user_id": "PUBLIC",
                        "topic": f"Doc Chunk: {c['chunk_title']}",
                        "source": "hospital_doc"
                    }
                    for c in chunks
                ]
                faiss_store.add_items(faiss_items)
            except Exception as e:
                print(f"[FAISS Sync Warning] Error updating FAISS index on content update: {e}")

        docs = [d for d in self.get_hospital_documents() if d["id"] == doc_id]
        return docs[0] if docs else None

    def get_hospital_doc_chunks(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve document chunks directly from FAISS vector store."""
        try:
            from app.services.faiss_store import faiss_store
            return faiss_store.get_chunks(doc_id)
        except Exception as e:
            print(f"[FAISS Error] Failed to fetch chunks from FAISS vector store: {e}")
            return []

    def delete_hospital_document(self, doc_id: str, user_id: str = "A4001") -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hospital_documents WHERE id = ?", (doc_id,))
            conn.commit()
        self.log_audit(user_id=user_id, action="ADMIN_DELETE_HOSPITAL_DOC", details={"doc_id": doc_id})

        # Sync FAISS vector store
        try:
            from app.services.faiss_store import faiss_store
            faiss_store.remove_document_chunks(doc_id)
        except Exception as e:
            print(f"[FAISS Sync Warning] Error updating FAISS index on delete: {e}")

        return True

    def get_all_chunks_for_rebuild(self) -> List[Dict[str, Any]]:
        """Extract parent document records from SQLite and compute chunk list for FAISS rebuild."""
        all_items = []
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Hospital Documents
            cursor.execute("SELECT id, title, content FROM hospital_documents")
            for r in cursor.fetchall():
                doc_id = r["id"]
                title = r["title"] or ""
                content = r["content"] or ""
                chunks = chunk_text(content, chunk_size=400, overlap=80)
                for c in chunks:
                    all_items.append({
                        "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                        "doc_id": doc_id,
                        "user_id": "PUBLIC",
                        "topic": f"Doc Chunk: {c['chunk_title']}",
                        "text": f"{c['chunk_title']}\n{c['chunk_text']}",
                        "source": "hospital_doc"
                    })

            # 2. Knowledge Base Seed Items
            cursor.execute("SELECT id, topic, content FROM knowledge_base")
            for r in cursor.fetchall():
                topic = r["topic"] or ""
                kb_content = r["content"] or ""
                all_items.append({
                    "chunk_id": f"kb_{r['id']}",
                    "doc_id": "kb",
                    "user_id": "PUBLIC",
                    "topic": topic,
                    "text": f"{topic}\n{kb_content}",
                    "source": "knowledge_base"
                })

            # 3. Patient Medical Documents
            cursor.execute("SELECT id, user_id, title, document_type, extracted_text, summary FROM documents")
            for r in cursor.fetchall():
                doc_title = r["title"] or ""
                extracted = r["extracted_text"] or ""
                doc_summary = r["summary"] or ""
                doc_type = r["document_type"] or "medical_record"
                all_items.append({
                    "chunk_id": r["id"],
                    "doc_id": r["id"],
                    "user_id": r["user_id"],
                    "topic": f"{doc_title} ({doc_type})",
                    "text": f"Patient Document: {doc_title}\nType: {doc_type}\nSummary: {doc_summary}\nContent: {extracted}",
                    "source": "user_document"
                })

        return all_items


    # --- Knowledge Base & Multi-Source RAG Search (FAISS + SQLite Hybrid) ---

    def search_knowledge_base(self, query: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform RAG knowledge search.
        Step 1: FAISS Vector Similarity Search -> Candidate vector matches & chunk text payloads
        Step 2: Patient Resource Authorization Check
        """
        authorized_results = []
        try:
            from app.services.faiss_store import faiss_store
            candidates = faiss_store.search(query=query, top_k=15)
            
            if candidates:
                for c in candidates:
                    doc_owner = c.get("user_id", "PUBLIC")
                    # Patient Resource Isolation Authorization Check
                    if doc_owner != "PUBLIC" and user_id and user_id != "ADMIN" and doc_owner != user_id:
                        # Unauthorized: Filter out another patient's private chunk!
                        continue
                    
                    authorized_results.append({
                        "chunk_id": c["chunk_id"],
                        "doc_id": c["doc_id"],
                        "topic": c.get("topic", "Knowledge Chunk"),
                        "content": c.get("content", ""),
                        "source": c.get("source", ""),
                        "score": c.get("score", 0.0)
                    })

                # Sort by vector similarity score descending
                authorized_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                if authorized_results:
                    return authorized_results[:10]

        except Exception as e:
            print(f"[FAISS Search Warning] Falling back to SQLite term match: {e}")

        # Fallback: SQLite Keyword Search if FAISS index empty or error
        q = query.lower()
        stop_words = {"policy", "hospital", "general", "rules", "guidelines", "about", "what", "with", "from"}
        query_terms = [t for t in q.split() if len(t) > 3 and t not in stop_words]
        scored_results = []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id, title, category, content FROM hospital_documents")
            for r in cursor.fetchall():
                title = r["title"] or ""
                text = r["content"] or ""
                full_text = f"{title} {text}".lower()
                matched = sum(1 for term in query_terms if term in full_text) if query_terms else 0
                if matched > 0 or not query_terms:
                    scored_results.append((matched, {
                        "chunk_id": f"HDOC-{r['id']}",
                        "doc_id": r["id"],
                        "topic": f"Doc: {title}",
                        "content": text[:500],
                        "source": f"hospital_doc:{r['id']}"
                    }))

            cursor.execute("SELECT id, topic, content FROM knowledge_base")
            for r in cursor.fetchall():
                topic = r["topic"] or ""
                content = r["content"] or ""
                full_text = f"{topic} {content}".lower()
                matched = sum(1 for term in query_terms if term in full_text) if query_terms else 0
                if matched > 0 or not query_terms:
                    scored_results.append((matched, {
                        "chunk_id": f"kb_{r['id']}",
                        "doc_id": "kb",
                        "topic": topic,
                        "content": content,
                        "source": "knowledge_base"
                    }))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_results[:10]]

    # --- Audit Logs ---

    def log_audit(self, user_id: str, action: str, details: Dict[str, Any], status: str = "SUCCESS"):
        log_id = f"LOG-{uuid.uuid4().hex[:8]}"
        now_str = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, now_str, user_id, action, json.dumps(details), status)
            )
            conn.commit()

    def get_audit_logs(self) -> List[AuditLog]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp ASC")
            return [
                AuditLog(
                    id=r["id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    user_id=r["user_id"],
                    action=r["action"],
                    details=json.loads(r["details"] or "{}"),
                    status=r["status"]
                )
                for r in cursor.fetchall()
            ]

    # --- OTPs ---

    def set_otp(self, email: str, otp: str):
        now_str = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO otps (email, otp, created_at) VALUES (?, ?, ?)",
                (email.lower(), otp, now_str)
            )
            conn.commit()

    def get_otp(self, email: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT otp FROM otps WHERE email = ?", (email.lower(),))
            row = cursor.fetchone()
            if row:
                return row["otp"]
            return default


# Global Database instance
db = Database()
