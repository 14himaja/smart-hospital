"""Hybrid RAG knowledge search with fail-closed patient privacy authorization."""

from typing import Dict, List, Optional, Any
import sqlite3
from app.db.connection import get_db_connection


def search_knowledge_base(
    query: str,
    user_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform authorized RAG knowledge search across FAISS vector store and SQLite.
    
    CRITICAL SECURITY INVARIANT: Fail closed.
    - If user_id is empty or None, ONLY 'PUBLIC' hospital knowledge documents are returned.
    - Private patient documents are returned ONLY if user_id matches the document owner (or user_id is ADMIN).
    - Unrelated queries below the relevance score threshold return 0 results.
    """
    if not query or not query.strip():
        return []

    authorized_results = []
    faiss_active = False
    try:
        from app.services.faiss_store import faiss_store
        if faiss_store.index is not None and faiss_store.index.ntotal > 0:
            faiss_active = True
            candidates = faiss_store.search(query=query.strip(), top_k=15)
            for c in candidates:
                doc_owner = c.get("user_id", "PUBLIC")
                # Fail-closed authorization check
                if doc_owner != "PUBLIC":
                    if not user_id:
                        # Reject: Anonymous query cannot access private patient documents!
                        continue
                    if user_id != "ADMIN" and doc_owner != user_id:
                        # Reject: Patient cannot access another patient's document!
                        continue

                authorized_results.append({
                    "chunk_id": c["chunk_id"],
                    "doc_id": c["doc_id"],
                    "topic": c.get("topic", "Knowledge Chunk"),
                    "content": c.get("content", ""),
                    "source": c.get("source", ""),
                    "score": c.get("score", 0.0)
                })

            authorized_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
            return authorized_results[:10]

    except Exception as e:
        print(f"[FAISS Search Warning] {e}")

    # If FAISS was active and returned its results, we do not fall back to loose keyword matching
    if faiss_active:
        return []

    # Fallback to SQLite keyword match if FAISS store is empty or uninitialized
    q = query.lower()
    stop_words = {"policy", "hospital", "general", "rules", "guidelines", "about", "what", "with", "from", "is", "the", "and", "or"}
    query_terms = [t for t in q.split() if len(t) > 3 and t not in stop_words]
    if not query_terms:
        return []

    scored_results = []
    min_required_matches = len(query_terms) if len(query_terms) <= 2 else max(2, int(len(query_terms) * 0.6))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Public hospital documents
        cursor.execute("SELECT id, title, category, content FROM hospital_documents")
        for r in cursor.fetchall():
            title = r["title"] or ""
            text = r["content"] or ""
            full_text = f"{title} {text}".lower()
            matched = sum(1 for term in query_terms if term in full_text)
            if matched >= min_required_matches:
                scored_results.append((matched, {
                    "chunk_id": f"HDOC-{r['id']}",
                    "doc_id": r["id"],
                    "topic": f"Doc: {title}",
                    "content": text[:500],
                    "source": f"hospital_doc:{r['id']}"
                }))

        # Patient documents (ONLY if user_id is provided)
        if user_id:
            cursor.execute(
                "SELECT id, title, document_type, extracted_text FROM documents WHERE user_id = ?",
                (user_id,)
            )
            for r in cursor.fetchall():
                title = r["title"] or ""
                text = r["extracted_text"] or ""
                full_text = f"{title} {text}".lower()
                matched = sum(1 for term in query_terms if term in full_text)
                if matched >= min_required_matches:
                    scored_results.append((matched, {
                        "chunk_id": f"DOC-{r['id']}",
                        "doc_id": r["id"],
                        "topic": f"Patient Doc: {title}",
                        "content": text[:500],
                        "source": f"user_doc:{r['id']}"
                    }))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in scored_results[:10]]

