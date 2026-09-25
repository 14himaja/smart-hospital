"""
Modular Database Facade for Smart Hospital AI Assistant.
Aggregates repositories for Users, Doctors, Appointments, Documents, and Audit Logs.
"""

from typing import Dict, List, Optional, Any
import sqlite3

from app.config import settings
from app.models import (
    User, UserRole, Department, Doctor, AppointmentSlot,
    Appointment, AppointmentStatus, MedicalDocument, DocumentType, AuditLog
)
from app.db.connection import get_db_connection, init_db
from app.db.seed import seed_data_if_empty
from app.db.repositories.users import UserRepository, hash_password, verify_password
from app.db.repositories.doctors import DoctorRepository
from app.db.repositories.appointments import AppointmentRepository
from app.db.repositories.documents import DocumentRepository
from app.db.repositories.audit import AuditRepository
from app.db.search import search_knowledge_base


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
    """Unified Database Facade for Smart Hospital Assistant."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or settings.DB_PATH)
        init_db(self.db_path)
        seed_data_if_empty(self.db_path)

        # Repositories
        self.user_repo = UserRepository(self.db_path)
        self.doctor_repo = DoctorRepository(self.db_path)
        self.appointment_repo = AppointmentRepository(self.db_path)
        self.document_repo = DocumentRepository(self.db_path)
        self.audit_repo = AuditRepository(self.db_path)

        # Backward compatibility collection stores
        self.doctors = _DoctorStore(self)
        self.appointments = _AppointmentStore(self)
        self.documents = _DocumentStore(self)
        self.users = _UserStore(self)
        self.otps = _OtpStore(self)

    def _get_connection(self) -> sqlite3.Connection:
        return get_db_connection(self.db_path)

    # User & Auth
    def get_user(self, user_id: str) -> Optional[User]:
        return self.user_repo.get_user(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.user_repo.get_user_by_email(email)

    def get_user_by_phone(self, phone: str) -> Optional[User]:
        return self.user_repo.get_user_by_phone(phone)

    def get_all_users(self) -> List[User]:
        return self.user_repo.get_all_users()

    def create_user(self, name: str, email: str, password: str, phone: Optional[str] = None, role: UserRole = UserRole.PATIENT, is_verified: bool = True) -> User:
        return self.user_repo.create_user(name, email, password, phone, role, is_verified)

    def update_user_verification(self, user_id: str, is_verified: bool = True) -> bool:
        return self.user_repo.update_user_verification(user_id, is_verified)

    def set_otp(self, email: str, otp: str) -> None:
        self.user_repo.set_otp(email, otp)

    def get_otp(self, email: str, default: Optional[str] = None) -> Optional[str]:
        return self.user_repo.get_otp(email, default)

    def clear_otp(self, email: str) -> None:
        self.user_repo.clear_otp(email)

    # Departments & Doctors
    def get_departments(self) -> List[Department]:
        return self.doctor_repo.get_departments()

    def get_department(self, dept_id: str) -> Optional[Department]:
        return self.doctor_repo.get_department(dept_id)

    def get_doctors(self, department_name: Optional[str] = None, specialty: Optional[str] = None) -> List[Doctor]:
        return self.doctor_repo.get_doctors(department_name, specialty)

    def get_doctor(self, doctor_id: str) -> Optional[Doctor]:
        return self.doctor_repo.get_doctor(doctor_id)

    def get_slots(self, doctor_id: str, date_str: Optional[str] = None, available_only: bool = True) -> List[AppointmentSlot]:
        return self.doctor_repo.get_slots(doctor_id, date_str, available_only)

    def ensure_active_slots(self, days_ahead: int = 14) -> None:
        self.doctor_repo.ensure_active_slots(days_ahead)

    # Appointments
    def get_appointment(self, appointment_id: str) -> Optional[Appointment]:
        return self.appointment_repo.get_appointment(appointment_id)

    def get_user_appointments(self, user_id: str) -> List[Appointment]:
        return self.appointment_repo.get_user_appointments(user_id)

    def get_all_appointments(self) -> List[Appointment]:
        return self.appointment_repo.get_all_appointments()

    def book_appointment(self, user_id: str, doctor_id: str, date_str: str, time_str: str, notes: str = "") -> Optional[Appointment]:
        doc = self.get_doctor(doctor_id)
        if not doc:
            return None
        appt = self.appointment_repo.book_appointment(user_id, doc, date_str, time_str, notes)
        if appt:
            self.log_audit(user_id=user_id, action="BOOK_APPOINTMENT", details={"appointment_id": appt.id, "doctor": doc.name})
        return appt

    def cancel_appointment(self, user_id: str, appointment_id: str) -> bool:
        success = self.appointment_repo.cancel_appointment(user_id, appointment_id)
        if success:
            self.log_audit(user_id=user_id, action="CANCEL_APPOINTMENT", details={"appointment_id": appointment_id})
        return success

    def reschedule_appointment(self, user_id: str, appointment_id: str, new_date: str, new_time: str) -> Optional[Appointment]:
        appt = self.appointment_repo.reschedule_appointment(user_id, appointment_id, new_date, new_time)
        if appt:
            self.log_audit(user_id=user_id, action="RESCHEDULE_APPOINTMENT", details={"appointment_id": appointment_id, "new_date": new_date, "new_time": new_time})
        return appt

    def delete_appointment_permanently(self, appointment_id: str, user_id: Optional[str] = None) -> bool:
        deleted = self.appointment_repo.delete_appointment_permanently(appointment_id, user_id)
        if deleted:
            self.log_audit(user_id=user_id or "ADMIN", action="PURGE_APPOINTMENT", details={"appointment_id": appointment_id})
        return deleted

    def complete_appointment(self, appointment_id: str) -> bool:
        completed = self.appointment_repo.complete_appointment(appointment_id)
        if completed:
            self.log_audit(user_id="ADMIN", action="COMPLETE_APPOINTMENT", details={"appointment_id": appointment_id})
        return completed

    # Documents
    def get_document(self, document_id: str) -> Optional[MedicalDocument]:
        return self.document_repo.get_document(document_id)

    def get_user_documents(self, user_id: str) -> List[MedicalDocument]:
        return self.document_repo.get_user_documents(user_id)

    def get_all_documents(self) -> List[MedicalDocument]:
        return self.document_repo.get_all_documents()

    def add_user_document(self, user_id: str, title: str, document_type: DocumentType, extracted_text: str, summary: Optional[str] = None, key_findings: Optional[List[str]] = None) -> MedicalDocument:
        doc = self.document_repo.add_user_document(user_id, title, document_type, extracted_text, summary, key_findings)
        self.log_audit(user_id=user_id, action="UPLOAD_DOCUMENT", details={"doc_id": doc.id, "title": title, "type": document_type.value})
        return doc

    def delete_user_document(self, document_id: str, user_id: str) -> bool:
        deleted = self.document_repo.delete_user_document(document_id, user_id)
        if deleted:
            self.log_audit(user_id=user_id, action="DELETE_DOCUMENT", details={"doc_id": document_id})
        return deleted

    def add_hospital_document(self, title: str, category: str, uploaded_by: str, content: str, file_type: str = "Direct Text Input") -> Dict[str, Any]:
        result = self.document_repo.add_hospital_document(title, category, uploaded_by, content, file_type)
        self.log_audit(user_id=uploaded_by, action="ADMIN_UPLOAD_HOSPITAL_DOC", details={"doc_id": result["id"], "title": title, "chunk_count": result["chunk_count"]})
        return result

    def get_hospital_documents(self) -> List[Dict[str, Any]]:
        return self.document_repo.get_hospital_documents()

    def update_hospital_document(self, doc_id: str, title: Optional[str] = None, category: Optional[str] = None, content: Optional[str] = None, user_id: str = "A4001") -> Optional[Dict[str, Any]]:
        result = self.document_repo.update_hospital_document(doc_id, title, category, content, user_id)
        if result:
            self.log_audit(user_id=user_id, action="ADMIN_UPDATE_HOSPITAL_DOC", details={"doc_id": doc_id, "title": result["title"]})
        return result

    def get_hospital_doc_chunks(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.document_repo.get_hospital_doc_chunks(doc_id)

    def delete_hospital_document(self, doc_id: str, user_id: str = "A4001") -> bool:
        deleted = self.document_repo.delete_hospital_document(doc_id, user_id)
        if deleted:
            self.log_audit(user_id=user_id, action="ADMIN_DELETE_HOSPITAL_DOC", details={"doc_id": doc_id})
        return deleted

    # Audit & Search
    def log_audit(self, user_id: str, action: str, details: Optional[Dict[str, Any]] = None, status: str = "SUCCESS") -> AuditLog:
        return self.audit_repo.log_audit(user_id, action, details, status)

    def get_audit_logs(self, limit: int = 100, user_id: Optional[str] = None) -> List[AuditLog]:
        return self.audit_repo.get_audit_logs(limit, user_id)

    @property
    def audit_logs(self) -> List[AuditLog]:
        return self.get_audit_logs()

    def search_knowledge_base(self, query: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return search_knowledge_base(query, user_id, self.db_path)

    def get_all_chunks_for_rebuild(self) -> List[Dict[str, Any]]:
        """Extract all text chunks from both hospital documents and patient documents."""
        all_items = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, category, content FROM hospital_documents")
            for r in cursor.fetchall():
                doc_id = r["id"]
                title = r["title"]
                from app.services.chunker import chunk_text
                chunks = chunk_text(r["content"], chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)
                for c in chunks:
                    all_items.append({
                        "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                        "doc_id": doc_id,
                        "user_id": "PUBLIC",
                        "topic": f"{title}: {c['chunk_title']}",
                        "text": f"{title} - {c['chunk_title']}\n{c['chunk_text']}",
                        "source": "hospital_doc"
                    })

            cursor.execute("SELECT id, user_id, title, document_type, summary, extracted_text FROM documents")
            for r in cursor.fetchall():
                doc_title = r["title"]
                doc_type = r["document_type"]
                doc_summary = r["summary"] or ""
                extracted = r["extracted_text"] or ""
                all_items.append({
                    "chunk_id": f"CHUNK-{r['id']}",
                    "doc_id": r["id"],
                    "user_id": r["user_id"],
                    "topic": f"{doc_title} ({doc_type})",
                    "text": f"Patient Document: {doc_title}\nType: {doc_type}\nSummary: {doc_summary}\nContent: {extracted}",
                    "source": "user_document"
                })
        return all_items


# Global Singleton Database Instance
db = Database()
