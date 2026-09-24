"""
Unified Embedding Generator Service for Smart Hospital Assistant.
Supports Google Gemini Embeddings (text-embedding-004 / embedding-001)
and OpenRouter/OpenAI Embeddings with automatic L2 normalization for Cosine Similarity.
"""

from typing import List, Optional
import numpy as np
import requests
from app.config import settings


class EmbeddingService:
    """Generates normalized vector embeddings for document chunks and user queries."""

    def __init__(self):
        self.config = settings.get_llm_config()
        self.api_key = self.config.get("api_key", "")
        self.provider = self.config.get("provider", "").lower()
        self.raw_model = self.config.get("raw_model", "").lower()

    def _normalize(self, vector: List[float]) -> np.ndarray:
        """L2 normalize a 1D float vector so inner product equals Cosine Similarity."""
        arr = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr

    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate a single L2-normalized float32 embedding vector for text."""
        batch_res = self.get_embeddings_batch([text])
        if batch_res and len(batch_res) > 0:
            return batch_res[0]
        return None

    def get_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate a batch of L2-normalized float32 embedding vectors for list of texts."""
        if not texts:
            return []

        clean_texts = [t.strip() if t and t.strip() else " " for t in texts]
        results = []
        batch_size = 32

        for i in range(0, len(clean_texts), batch_size):
            chunk = clean_texts[i:i + batch_size]
            chunk_results = []

            # 1. Try Google Gemini Embeddings API if Gemini/Google key is configured
            if "gemini" in self.provider or "google" in self.provider or self.api_key.startswith("AIzaSy"):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"
                    for t in chunk:
                        payload = {"content": {"parts": [{"text": t}]}}
                        res = requests.post(url, json=payload, timeout=10)
                        if res.status_code == 200:
                            vals = res.json().get("embedding", {}).get("values", [])
                            if vals:
                                chunk_results.append(self._normalize(vals))
                except Exception as e:
                    print(f"[EmbeddingService] Gemini API error: {e}")

            # 2. Try OpenRouter / OpenAI Embeddings API
            if len(chunk_results) < len(chunk) and self.api_key:
                try:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                    url = "https://openrouter.ai/api/v1/embeddings" if "openrouter" in self.provider or self.api_key.startswith("sk-or-v1-") else "https://api.openai.com/v1/embeddings"
                    payload = {
                        "model": "text-embedding-3-small",
                        "input": chunk
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        data = res.json().get("data", [])
                        for item in data:
                            vals = item.get("embedding", [])
                            if vals:
                                chunk_results.append(self._normalize(vals))
                except Exception as e:
                    print(f"[EmbeddingService] OpenRouter/OpenAI API error: {e}")

            # 3. Fallback deterministic pseudo-embedding generator
            if len(chunk_results) < len(chunk):
                # Infer dimension from existing results or default to 1536
                dim = len(results[0]) if results else (len(chunk_results[0]) if chunk_results else 1536)
                for t in chunk[len(chunk_results):]:
                    seed = abs(hash(t)) % (2**31)
                    rng = np.random.RandomState(seed)
                    arr = rng.randn(dim).astype(np.float32)
                    chunk_results.append(self._normalize(arr.tolist()))

            results.extend(chunk_results)

        return results


# Global Singleton Embedding Service
embedding_service = EmbeddingService()
