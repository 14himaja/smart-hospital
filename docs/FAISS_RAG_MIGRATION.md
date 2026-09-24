# FAISS Vector Search Migration & Architecture Guide
## Smart Hospital AI Assistant (Google ADK + FastAPI + FAISS + Gemini Embeddings)

### 1. Architectural Overview

The **Smart Hospital AI Assistant** has been upgraded from pure lexical SQLite term-matching to a **Hybrid Vector Search RAG Architecture** combining **FAISS (Facebook AI Similarity Search)** with SQLite metadata isolation.

```text
                                 RAG ARCHITECTURE

         [ User Question ]
                 │
                 ▼
     [ Embedding Service ]  ──> Generates L2-Normalized 1536-dim / 768-dim Vector
                 │
                 ▼
     [ FAISS Vector Search ] ──> faiss.IndexFlatIP (Cosine Similarity)
                 │
                 ▼
        [ Top Candidate IDs ] ──> Vector Index Position -> Chunk ID
                 │
                 ▼
    [ SQLite Metadata Store ] ──> Fetch Chunk Text, Doc Info & Patient Owner ID
                 │
                 ▼
  [ Patient Resource Auth ]  ──> Filter Out Unauthorized Patient Chunks
                 │
                 ▼
    [ Authorized Context ]  ──> Formatted for Google ADK LLM Agents
                 │
                 ▼
       [ Final AI Response ]
```

---

### 2. Dual-Storage Separation of Concerns

1. **FAISS Vector Store (`data/faiss/hospital_documents.index` + `data/faiss/chunk_mapping.json`)**:
   - FAISS handles **100% of document chunks**, chunk text payloads, and dense float32 vector embeddings.
   - `chunk_mapping.json` stores the full chunk metadata payload (`chunk_id`, `doc_id`, `user_id`, `topic`, `chunk_text`, `source`, `vector_pos`).
   - Performs $O(N)$ inner-product cosine similarity search with minimal memory overhead.

2. **SQLite Database (`hospital.db`)**:
   - Primary source of truth for **structured hospital data ONLY**: `users`, `doctors`, `departments`, `slots`, `appointments`, parent `documents` metadata, parent `hospital_documents` metadata, and `audit_logs`.
   - **Contains ZERO document chunk tables** (`hospital_doc_chunks` table dropped). Chunk storage and chunk lookup are handled strictly by the FAISS vector store.

---

### 3. Embedding Model Consistency & Distance Metric

- **Embedding Model**: Configured to use Google Gemini `text-embedding-004` (768 dimensions) or OpenRouter/OpenAI `text-embedding-3-small` (1536 dimensions) via `app/services/embeddings.py`.
- **Normalization**: Every vector is L2-normalized ($\mathbf{v} / \|\mathbf{v}\|_2$) prior to index insertion and query search.
- **FAISS Distance Metric**: Uses `faiss.IndexFlatIP` (Inner Product). Because vectors are L2-normalized, the inner product $A \cdot B$ is mathematically identical to **Cosine Similarity** ($\cos(\theta) \in [-1.0, 1.0]$).

---

### 4. Healthcare Patient Resource Isolation Authorization

A critical requirement in healthcare applications is preventing Patient A from seeing Patient B's private medical documents simply because their symptoms or queries are semantically similar.

**Authorization Flow**:
1. User submits a query to `search_hospital_knowledge(query)`.
2. FAISS performs vector similarity search and returns candidate `chunk_id`s.
3. SQLite looks up chunk details and checks ownership:
   - If `source` is `PUBLIC` (admin policy docs or knowledge base), access is granted.
   - If `source` is `user_document`, SQLite verifies if `chunk_owner_id == requesting_user_id` or `requesting_user_id == "ADMIN"`.
   - If unauthorized, the chunk is silently dropped before reaching the LLM context.

---

### 5. Index Maintenance, Synchronization & Recovery

#### 5.1 Automatic Initialization
On FastAPI server startup ([`app/main.py`](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/smart-hospital/app/main.py)), the application checks if `data/faiss/hospital_documents.index` exists. If missing or empty, it automatically triggers a safe rebuild from SQLite chunks.

#### 5.2 Standalone Migration / Rebuild Script
To manually rebuild the FAISS index from scratch at any time, run:

```bash
python -m scripts.migrate_sqlite_chunks_to_faiss
```

Output:
```text
=================================================================
MIGRATING SQLITE CHUNKS TO FAISS VECTOR STORE
=================================================================

Documents found: 20
Chunks found: 486
Chunks embedded: 486
FAISS vectors: 486
Embedding dimension: 1536

Migration completed successfully
=================================================================
```

#### 5.3 Live Index Synchronization
- **On Admin Document Upload**: New chunks are converted to vectors and appended to FAISS via `faiss_store.add_items()`.
- **On Patient Document Upload**: Document vector is appended to FAISS via `faiss_store.add_items()`.
- **On Document Deletion**: Chunks associated with `doc_id` are removed from FAISS by automatically rebuilding the vector index from the remaining SQLite records via `faiss_store.remove_document_chunks(doc_id)`.

#### 5.4 Disaster Recovery
If the FAISS index or `chunk_mapping.json` is corrupted or deleted:
1. Delete the `data/faiss/` folder.
2. Restart the FastAPI server, or run `python -m scripts.migrate_sqlite_chunks_to_faiss`.
3. The system will rebuild the FAISS index from the non-destructive SQLite database automatically.
