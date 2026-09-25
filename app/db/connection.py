"""SQLite database connection and schema management."""

import sqlite3
from typing import Optional
from app.config import settings


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create a sqlite3 connection with Row factory and 10s timeout."""
    path = db_path or str(settings.DB_PATH)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Create all required tables and indexes if they do not exist."""
    with get_db_connection(db_path) as conn:
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
        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appointments_user ON appointments(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appointments_doc_date ON appointments(doctor_id, date, time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_slots_doc_date ON slots(doctor_id, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        conn.commit()
