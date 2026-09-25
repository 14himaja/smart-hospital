"""Medical documents and hospital policy documents repository."""

import json
import uuid
from datetime import datetime, date
from typing import Dict, List, Optional, Any
import sqlite3

from app.db.connection import get_db_connection
from app.models import MedicalDocument, DocumentType
from app.services.chunker import chunk_text
from app.config import settings


def row_to_document(row: sqlite3.Row) -> MedicalDocument:
    try:
        findings = json.loads(row["key_findings"])
    except Exception:
        findings = []
    return MedicalDocument(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        document_type=DocumentType(row["document_type"]),
        upload_date=row["upload_date"],
        extracted_text=row["extracted_text"],
        summary=row["summary"],
        key_findings=findings
    )


class DocumentRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_document(self, document_id: str) -> Optional[MedicalDocument]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
            row = cursor.fetchone()
            return row_to_document(row) if row else None

    def get_user_documents(self, user_id: str) -> List[MedicalDocument]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE user_id = ? ORDER BY upload_date DESC", (user_id,))
            return [row_to_document(r) for r in cursor.fetchall()]

    def get_all_documents(self) -> List[MedicalDocument]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents ORDER BY upload_date DESC")
            return [row_to_document(r) for r in cursor.fetchall()]

    def add_user_document(
        self,
        user_id: str,
        title: str,
        document_type: DocumentType,
        extracted_text: str,
        summary: Optional[str] = None,
        key_findings: Optional[List[str]] = None
    ) -> MedicalDocument:
        doc_id = f"DOC-{uuid.uuid4().hex[:6].upper()}"
        today_str = date.today().isoformat()
        findings_json = json.dumps(key_findings or [])

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, user_id, title, document_type.value, today_str, extracted_text, summary, findings_json)
            )
            conn.commit()

        # Add to FAISS index with patient user_id tagging
        try:
            from app.services.faiss_store import faiss_store
            faiss_store.add_items([{
                "chunk_id": f"CHUNK-{doc_id}",
                "doc_id": doc_id,
                "text": f"Patient Document: {title}\nType: {document_type.value}\nSummary: {summary or ''}\nContent: {extracted_text}",
                "user_id": user_id,
                "topic": f"{title} ({document_type.value})",
                "source": "user_document"
            }])
        except Exception as e:
            print(f"[FAISS Sync Error] Failed to index patient document: {e}")

        return MedicalDocument(
            id=doc_id,
            user_id=user_id,
            title=title,
            document_type=document_type,
            upload_date=today_str,
            extracted_text=extracted_text,
            summary=summary,
            key_findings=key_findings or []
        )

    def delete_user_document(self, document_id: str, user_id: str) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if user_id == "ADMIN":
                cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            else:
                cursor.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            try:
                from app.services.faiss_store import faiss_store
                faiss_store.remove_document_chunks(document_id)
            except Exception as e:
                print(f"[FAISS Sync Error] Failed to remove document from FAISS: {e}")

        return deleted

    # Admin Hospital Documents (Policies, Guides, FAQs)

    def add_hospital_document(
        self,
        title: str,
        category: str,
        uploaded_by: str,
        content: str,
        file_type: str = "Direct Text Input"
    ) -> Dict[str, Any]:
        doc_id = f"HDOC-{uuid.uuid4().hex[:6].upper()}"
        today_str = date.today().isoformat()

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO hospital_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, title, category, uploaded_by, today_str, content, file_type)
            )
            conn.commit()

        chunks = chunk_text(content, chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)

        try:
            from app.services.faiss_store import faiss_store
            faiss_items = [
                {
                    "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                    "doc_id": doc_id,
                    "text": f"{title} - {c['chunk_title']}\n{c['chunk_text']}",
                    "user_id": "PUBLIC",
                    "topic": f"{title}: {c['chunk_title']}",
                    "source": "hospital_doc"
                }
                for c in chunks
            ]
            faiss_store.add_items(faiss_items)
        except Exception as e:
            print(f"[FAISS Sync Error] Failed to index hospital document chunks: {e}")

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
        try:
            from app.services.faiss_store import faiss_store
        except Exception:
            faiss_store = None

        with get_db_connection(self.db_path) as conn:
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
        with get_db_connection(self.db_path) as conn:
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

        # Update FAISS chunks
        try:
            from app.services.faiss_store import faiss_store
            if content and content.strip() and content.strip() != doc_row["content"]:
                faiss_store.remove_document_chunks(doc_id)
                chunks = chunk_text(new_content, chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)
                faiss_items = [
                    {
                        "chunk_id": f"CHUNK-{doc_id}-{c['chunk_index']}",
                        "doc_id": doc_id,
                        "text": f"{new_title} - {c['chunk_title']}\n{c['chunk_text']}",
                        "user_id": "PUBLIC",
                        "topic": f"{new_title}: {c['chunk_title']}",
                        "source": "hospital_doc"
                    }
                    for c in chunks
                ]
                faiss_store.add_items(faiss_items)
            else:
                # Content didn't change, but title or category did -> update FAISS metadata directly
                faiss_store.update_document_metadata(doc_id=doc_id, new_title=new_title, new_category=new_category)
        except Exception as e:
            print(f"[FAISS Sync Error] Error updating FAISS index: {e}")

        docs = [d for d in self.get_hospital_documents() if d["id"] == doc_id]
        return docs[0] if docs else None

    def get_hospital_doc_chunks(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            from app.services.faiss_store import faiss_store
            return faiss_store.get_chunks(doc_id)
        except Exception as e:
            print(f"[FAISS Error] Failed to fetch chunks: {e}")
            return []

    def delete_hospital_document(self, doc_id: str, user_id: str = "A4001") -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hospital_documents WHERE id = ?", (doc_id,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            try:
                from app.services.faiss_store import faiss_store
                faiss_store.remove_document_chunks(doc_id)
            except Exception as e:
                print(f"[FAISS Error] Failed to remove document from FAISS: {e}")

        return deleted
