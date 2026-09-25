"""User and authentication repository."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Dict, List, Optional, Any
import sqlite3

from app.db.connection import get_db_connection
from app.models import User, UserRole


import os

def hash_password(password: str) -> str:
    """
    Hash a password with scrypt and a random 16-byte salt.
    Format: scrypt$salt_hex$hash_hex
    """
    if not password:
        return ""
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored hash (supports scrypt, PBKDF2, and legacy SHA-256)."""
    if not plain_password or not hashed_password:
        return False
    if hashed_password.startswith("scrypt$"):
        try:
            _, salt_hex, dk_hex = hashed_password.split("$")
            dk = hashlib.scrypt(plain_password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
            return hmac.compare_digest(dk.hex(), dk_hex)
        except Exception:
            return False
    elif hashed_password.startswith("pbkdf2_sha256$") or hashed_password.startswith("pbkdf2$"):
        try:
            parts = hashed_password.split("$")
            if len(parts) == 4:
                _, iter_str, salt, target_hash = parts
                iterations = int(iter_str)
            else:
                _, salt, target_hash = parts
                iterations = 100_000
            computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations)
            return hmac.compare_digest(computed.hex(), target_hash)
        except Exception:
            return False
    # Legacy SHA-256 fallback with constant-time comparison
    legacy_hash = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, hashed_password)


def row_to_user(row: sqlite3.Row) -> User:
    try:
        pref = json.loads(row["preferences"])
    except Exception:
        pref = {}
    return User(
        user_id=row["user_id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        role=UserRole(row["role"]),
        is_verified=bool(row["is_verified"]),
        hashed_password=row["hashed_password"],
        created_at=datetime.fromisoformat(row["created_at"]),
        preferences=pref
    )


class UserRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_user(self, user_id: str) -> Optional[User]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
            row = cursor.fetchone()
            return row_to_user(row) if row else None

    def get_user_by_phone(self, phone: str) -> Optional[User]:
        """Lookup user by phone number using last 10 digits normalisation."""
        if not phone:
            return None
        clean_digits = "".join(c for c in phone if c.isdigit())
        if len(clean_digits) >= 10:
            last10 = clean_digits[-10:]
        else:
            last10 = clean_digits

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE phone IS NOT NULL")
            for row in cursor.fetchall():
                p = row["phone"] or ""
                p_digits = "".join(c for c in p if c.isdigit())
                if p_digits.endswith(last10):
                    return row_to_user(row)
        return None

    def get_all_users(self) -> List[User]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            return [row_to_user(r) for r in cursor.fetchall()]

    def create_user(
        self,
        name: str,
        email: str,
        password: str,
        phone: Optional[str] = None,
        role: UserRole = UserRole.PATIENT,
        is_verified: bool = True
    ) -> User:
        import uuid
        user_id = f"P{uuid.uuid4().hex[:4].upper()}" if role == UserRole.PATIENT else f"A{uuid.uuid4().hex[:4].upper()}"
        now_str = datetime.utcnow().isoformat()
        h_pass = hash_password(password)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, email, phone, role.value, int(is_verified), h_pass, now_str, "{}")
            )
            conn.commit()

        return User(
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            role=role,
            is_verified=is_verified,
            hashed_password=h_pass,
            created_at=datetime.fromisoformat(now_str),
            preferences={}
        )

    def update_user_verification(self, user_id: str, is_verified: bool = True) -> bool:
        """Persist verified status for a user in the database."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_verified = ? WHERE user_id = ?", (int(is_verified), user_id))
            conn.commit()
            return cursor.rowcount > 0

    def set_otp(self, email: str, otp: str) -> None:
        now_str = datetime.utcnow().isoformat()
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO otps (email, otp, created_at) VALUES (?, ?, ?)",
                (email.lower(), otp, now_str)
            )
            conn.commit()

    def get_otp(self, email: str, default: Optional[str] = None) -> Optional[str]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT otp FROM otps WHERE LOWER(email) = LOWER(?)", (email,))
            row = cursor.fetchone()
            return row["otp"] if row else default

    def clear_otp(self, email: str) -> None:
        """Remove one-time passcode after successful verification."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM otps WHERE LOWER(email) = LOWER(?)", (email,))
            conn.commit()

