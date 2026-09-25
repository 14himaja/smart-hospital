"""Audit logging repository."""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import sqlite3

from app.db.connection import get_db_connection
from app.models import AuditLog


def row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    try:
        details = json.loads(row["details"])
    except Exception:
        details = {}
    return AuditLog(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        user_id=row["user_id"],
        action=row["action"],
        details=details,
        status=row["status"]
    )


class AuditRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def log_audit(
        self,
        user_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        status: str = "SUCCESS"
    ) -> AuditLog:
        log_id = f"AUD-{uuid.uuid4().hex[:6].upper()}"
        now = datetime.utcnow()
        now_str = now.isoformat()
        details_json = json.dumps(details or {})

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, now_str, user_id, action, details_json, status)
            )
            conn.commit()

        return AuditLog(
            id=log_id,
            timestamp=now,
            user_id=user_id,
            action=action,
            details=details or {},
            status=status
        )

    def get_audit_logs(self, limit: int = 100, user_id: Optional[str] = None) -> List[AuditLog]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (user_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            return [row_to_audit_log(r) for r in cursor.fetchall()]
