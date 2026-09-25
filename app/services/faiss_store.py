"""
FAISS Vector Store Manager for Smart Hospital Assistant.
Provides persistent vector storage, Cosine Similarity search via faiss.IndexFlatIP,
and vector-index-to-chunk-id metadata mapping.
"""

import json
import os
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import faiss

from app.config import settings
from app.services.embeddings import embedding_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FAISS_DIR = PROJECT_ROOT / "data" / "faiss"
INDEX_PATH = FAISS_DIR / "hospital_documents.index"
MAPPING_PATH = FAISS_DIR / "chunk_mapping.json"


class FAISSVectorStore:
    """
    Persistent FAISS Vector Index Manager.
    Uses faiss.IndexFlatIP with L2-normalized float32 vectors for Cosine Similarity.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.dimension: Optional[int] = None
        self.index: Optional[faiss.IndexFlatIP] = None
        self.mapping: List[Dict[str, Any]] = []
        os.makedirs(FAISS_DIR, exist_ok=True)
        self.load()

    def _init_index(self, dimension: int):
        """Initialize empty FAISS Inner Product index for normalized vectors."""
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)

    def load(self) -> bool:
        """Load FAISS index and metadata chunk mapping from disk if present."""
        if INDEX_PATH.exists() and MAPPING_PATH.exists():
            try:
                self.index = faiss.read_index(str(INDEX_PATH))
                self.dimension = self.index.d
                with open(MAPPING_PATH, "r", encoding="utf-8") as f:
                    self.mapping = json.load(f)
                print(f"[FAISS] Loaded index with {self.index.ntotal} vectors from {INDEX_PATH}")
                return True
            except Exception as e:
                print(f"[FAISS] Error loading existing index: {e}")
                self.index = None
                self.mapping = []
                return False
        return False

    def save(self):
        """Save current FAISS index and chunk mapping to disk."""
        if self.index is not None:
            os.makedirs(FAISS_DIR, exist_ok=True)
            faiss.write_index(self.index, str(INDEX_PATH))
            with open(MAPPING_PATH, "w", encoding="utf-8") as f:
                json.dump(self.mapping, f, indent=2)
            print(f"[FAISS] Saved index ({self.index.ntotal} vectors) to {INDEX_PATH}")

    def add_items(self, items: List[Dict[str, Any]]):
        """
        Add new document/chunk items to FAISS index.
        Each item dict must contain:
          - chunk_id: str
          - doc_id: str
          - text: str
          - user_id: str ("PUBLIC" or specific patient ID)
          - topic: str
          - source: str
        """
        if not items:
            return

        with self._lock:
            texts = [item["text"] for item in items]
            vectors = embedding_service.get_embeddings_batch(texts)
            if not vectors:
                return

            dim = len(vectors[0])
            if self.index is None:
                self._init_index(dim)
            elif self.dimension != dim:
                print(f"[FAISS] Dimension change ({self.dimension} -> {dim}). Rebuilding entire index...")
                existing_items = [
                    {
                        "chunk_id": m["chunk_id"],
                        "doc_id": m.get("doc_id", ""),
                        "text": m.get("chunk_text", ""),
                        "user_id": m.get("user_id", "PUBLIC"),
                        "topic": m.get("topic", ""),
                        "source": m.get("source", "")
                    }
                    for m in self.mapping
                ]
                self.rebuild(existing_items + items)
                return

            matrix = np.array(vectors, dtype=np.float32)
            self.index.add(matrix)

            for i, item in enumerate(items):
                self.mapping.append({
                    "vector_pos": len(self.mapping),
                    "chunk_id": item["chunk_id"],
                    "doc_id": item.get("doc_id", ""),
                    "user_id": item.get("user_id", "PUBLIC"),
                    "topic": item.get("topic", ""),
                    "chunk_text": item.get("text", ""),
                    "source": item.get("source", "hospital_doc")
                })

            self.save()

    def remove_document_chunks(self, doc_id: str):
        """Remove all chunks associated with a specific doc_id by rebuilding index."""
        if not self.mapping:
            return

        remaining_items = [
            {
                "chunk_id": m["chunk_id"],
                "doc_id": m["doc_id"],
                "text": m.get("chunk_text", ""),
                "user_id": m.get("user_id", "PUBLIC"),
                "topic": m.get("topic", ""),
                "source": m.get("source", "")
            }
            for m in self.mapping if m.get("doc_id") != doc_id
        ]
        self.rebuild(remaining_items)

    def update_document_metadata(self, doc_id: str, new_title: str, new_category: Optional[str] = None):
        """Update metadata (topic/title) for all chunks belonging to doc_id without re-embedding."""
        with self._lock:
            updated = False
            for m in self.mapping:
                if m.get("doc_id") == doc_id:
                    m["topic"] = f"{new_title} - {new_category}" if new_category else new_title
                    updated = True
            if updated:
                self.save()

    def search(self, query: str, top_k: int = 15, score_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search against FAISS index.
        Returns candidate matching chunks directly from FAISS vector store filtered by score threshold.
        """
        if self.index is None or self.index.ntotal == 0 or not self.mapping:
            return []

        if score_threshold is None:
            score_threshold = settings.RAG_SCORE_THRESHOLD

        q_vec = embedding_service.get_embedding(query)
        if q_vec is None:
            return []

        # Ensure vector dimension matches FAISS index dimension
        if len(q_vec) != self.dimension:
            print(f"[FAISS] Dimension mismatch query ({len(q_vec)}) vs index ({self.dimension}). Rebuilding index...")
            from app.database import db
            self.rebuild(db.get_all_chunks_for_rebuild())
            q_vec = embedding_service.get_embedding(query)
            if q_vec is None or len(q_vec) != self.dimension:
                return []

        q_matrix = np.array([q_vec], dtype=np.float32)
        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(q_matrix, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.mapping):
                continue
            if score < score_threshold:
                continue
            meta = self.mapping[idx]
            results.append({
                "chunk_id": meta["chunk_id"],
                "doc_id": meta["doc_id"],
                "user_id": meta.get("user_id", "PUBLIC"),
                "topic": meta.get("topic", ""),
                "content": meta.get("chunk_text", ""),
                "source": meta.get("source", ""),
                "score": float(score)
            })

        return results

    def get_chunks(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve chunks directly from FAISS vector store metadata payload.
        If doc_id is provided, filter for chunks matching that doc_id.
        """
        if not self.mapping:
            return []
        if doc_id:
            return [
                {
                    "chunk_id": m["chunk_id"],
                    "doc_id": m["doc_id"],
                    "user_id": m.get("user_id", "PUBLIC"),
                    "chunk_title": m.get("topic", ""),
                    "chunk_text": m.get("chunk_text", ""),
                    "source": m.get("source", ""),
                    "vector_pos": m.get("vector_pos", 0)
                }
                for m in self.mapping if m.get("doc_id") == doc_id
            ]
        return [
            {
                "chunk_id": m["chunk_id"],
                "doc_id": m["doc_id"],
                "user_id": m.get("user_id", "PUBLIC"),
                "chunk_title": m.get("topic", ""),
                "chunk_text": m.get("chunk_text", ""),
                "source": m.get("source", ""),
                "vector_pos": m.get("vector_pos", 0)
            }
            for m in self.mapping
        ]

    def count_chunks_for_doc(self, doc_id: str) -> int:
        """Count total chunks belonging to a document in FAISS store."""
        return sum(1 for m in self.mapping if m.get("doc_id") == doc_id)

    def count_total_chunks(self) -> int:
        """Count total chunks stored across FAISS index."""
        return len(self.mapping)

    def rebuild(self, items: List[Dict[str, Any]]):
        """
        Completely rebuild FAISS index from clean items list.
        Each item must contain chunk_id, doc_id, text, user_id, topic, source.
        """
        print(f"[FAISS] Rebuilding index from {len(items)} chunks...")
        self.index = None
        self.mapping = []

        if not items:
            self.save()
            return

        texts = [item["text"] for item in items]
        vectors = embedding_service.get_embeddings_batch(texts)
        if not vectors:
            self.save()
            return

        dim = len(vectors[0])
        self._init_index(dim)

        matrix = np.array(vectors, dtype=np.float32)
        self.index.add(matrix)

        for i, item in enumerate(items):
            self.mapping.append({
                "vector_pos": i,
                "chunk_id": item["chunk_id"],
                "doc_id": item.get("doc_id", ""),
                "user_id": item.get("user_id", "PUBLIC"),
                "topic": item.get("topic", ""),
                "chunk_text": item.get("text", ""),
                "source": item.get("source", "")
            })

        self.save()
        print(f"[FAISS] Rebuild complete. Total vectors indexed: {self.index.ntotal}")


# Global Singleton FAISS Vector Store
faiss_store = FAISSVectorStore()

