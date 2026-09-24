"""Semantic and window-based text chunking engine for hospital documents."""

import re
from typing import List, Dict, Any, Optional
from app.config import settings


def chunk_text(
    text: str,
    chunk_size: Optional[int] = None,
    overlap: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Splits document text into overlapping text chunks using configured window and overlap.
    
    Args:
        text: Raw document text content.
        chunk_size: Target size in characters per chunk (defaults to settings.RAG_CHUNK_SIZE).
        overlap: Character overlap between consecutive chunks (defaults to settings.RAG_CHUNK_OVERLAP).
        
    Returns:
        List of chunk dicts containing chunk_index, chunk_title, chunk_text, and word_count.
    """
    if chunk_size is None:
        chunk_size = settings.RAG_CHUNK_SIZE
    if overlap is None:
        overlap = settings.RAG_CHUNK_OVERLAP
    clean_text = text.strip()
    if not clean_text:
        return []

    # First, split into paragraph blocks if double newlines exist
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', clean_text) if p.strip()]
    
    chunks = []
    chunk_index = 0

    for p in paragraphs:
        # If paragraph fits within target chunk_size
        if len(p) <= chunk_size:
            words = p.split()
            chunks.append({
                "chunk_index": chunk_index,
                "chunk_title": p[:40].replace("\n", " ") + ("..." if len(p) > 40 else ""),
                "chunk_text": p,
                "word_count": len(words)
            })
            chunk_index += 1
        else:
            # Sliding window chunking over large paragraphs
            start = 0
            while start < len(p):
                end = start + chunk_size
                # Try to end at a sentence boundary or word boundary if possible
                if end < len(p):
                    break_point = max(
                        p.rfind(". ", start, end),
                        p.rfind("\n", start, end),
                        p.rfind(" ", start, end)
                    )
                    if break_point != -1 and break_point > start + (chunk_size // 2):
                        end = break_point + 1

                chunk_slice = p[start:end].strip()
                if chunk_slice:
                    words = chunk_slice.split()
                    chunks.append({
                        "chunk_index": chunk_index,
                        "chunk_title": chunk_slice[:40].replace("\n", " ") + ("..." if len(chunk_slice) > 40 else ""),
                        "chunk_text": chunk_slice,
                        "word_count": len(words)
                    })
                    chunk_index += 1

                # Advance by chunk_size minus overlap
                step = (end - start) - overlap
                if step <= 0:
                    step = chunk_size // 2
                start += step

    return chunks
