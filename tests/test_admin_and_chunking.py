import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import db
from app.api.auth import create_access_token
from app.services.chunker import chunk_text


from app.models import UserRole


def test_chunking_service():
    """Test text chunker splitting long document into overlapping chunks."""
    sample_text = (
        "ApolloCare Hospital Pediatric ICU Guidelines.\n\n"
        "Section 1: Visitor Eligibility. All visitors entering the Pediatric Intensive Care Unit (PICU) "
        "must be immediate family members aged 18 or older. Visitors must undergo a mandatory sanitation check "
        "and wear protective gowns at all times.\n\n"
        "Section 2: Visiting Hours. PICU visiting hours are strictly enforced from 5:00 PM to 6:00 PM daily. "
        "Only one visitor is permitted at the bedside at any given time. Exceptions require written approval from the Chief Medical Officer.\n\n"
        "Section 3: Infection Control. Hands must be washed with antibacterial solution prior to entering and after exiting."
    )
    
    chunks = chunk_text(sample_text, chunk_size=300, overlap=60)
    assert len(chunks) >= 3
    assert all("chunk_index" in c for c in chunks)
    assert all("chunk_text" in c for c in chunks)
    assert any("PICU visiting hours" in c["chunk_text"] for c in chunks)


def get_or_create_admin():
    admin_user = db.get_user_by_email("admin@hospital.org") or db.get_user("A4001")
    if not admin_user:
        admin_user = db.create_user("Hospital Administrator", "admin@hospital.org", "adminpass123", role=UserRole.ADMIN)
    return admin_user


@pytest.fixture
def admin_headers():
    admin_user = get_or_create_admin()
    token = create_access_token(admin_user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def patient_headers():
    user = db.get_user("P1001")
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_login():
    get_or_create_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/admin/login", json={
            "email": "admin@hospital.org",
            "password": "adminpass123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_patient_forbidden_on_admin_endpoint(patient_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/admin/documents", json={
            "title": "Unauthorized Doc",
            "category": "Policy",
            "content": "Secret text"
        }, headers=patient_headers)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_upload_chunk_and_rag_search(admin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload hospital policy doc as Admin
        policy_title = "Cardiology Post-Surgery Discharge Guidelines"
        policy_content = (
            "Cardiology Post-Surgery Recovery Directives.\n\n"
            "Patients recovering from angioplasty or bypass surgery must refrain from heavy lifting over 10 lbs "
            "for 4 weeks post-discharge. Daily blood pressure and pulse monitoring is required.\n\n"
            "Emergency Warning Signs: Contact emergency services immediately if experiencing persistent chest pressure, "
            "shortness of breath at rest, or sudden swelling in lower extremities."
        )

        upload_resp = await client.post("/api/admin/documents", json={
            "title": policy_title,
            "category": "Clinical Guidelines",
            "content": policy_content
        }, headers=admin_headers)

        assert upload_resp.status_code == 201
        upload_data = upload_resp.json()
        assert upload_data["status"] == "success"
        doc_id = upload_data["document"]["id"]
        assert upload_data["document"]["chunk_count"] >= 2

        # 2. Retrieve document chunks as Admin
        chunks_resp = await client.get(f"/api/admin/documents/{doc_id}/chunks", headers=admin_headers)
        assert chunks_resp.status_code == 200
        assert len(chunks_resp.json()["chunks"]) >= 2

        # 3. Perform RAG Knowledge Search on the newly chunked Admin document!
        rag_results = db.search_knowledge_base(query="post surgery heavy lifting angioplasty")
        assert len(rag_results) > 0
        assert any("heavy lifting" in r["content"].lower() or "angioplasty" in r["content"].lower() for r in rag_results)

        # 4. Clean up test document
        del_resp = await client.delete(f"/api/admin/documents/{doc_id}", headers=admin_headers)
        assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_file_upload_endpoint(admin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test text file upload via multipart/form-data
        file_bytes = b"ApolloCare Hospital General Safety Policy.\nAll medical staff must wear non-slip shoes in operating areas."
        files = {
            "file": ("safety_policy.txt", file_bytes, "text/plain")
        }
        data = {
            "title": "",
            "category": "Safety Guidelines",
            "content": ""
        }

        resp = await client.post("/api/admin/documents/upload", data=data, files=files, headers=admin_headers)
        assert resp.status_code == 201
        res_data = resp.json()
        assert res_data["status"] == "success"
        assert res_data["document"]["title"] == "safety policy"
        assert res_data["document"]["chunk_count"] >= 1

        doc_id = res_data["document"]["id"]

        # Clean up
        await client.delete(f"/api/admin/documents/{doc_id}", headers=admin_headers)


@pytest.mark.asyncio
async def test_admin_update_document_title(admin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create doc
        create_resp = await client.post("/api/admin/documents", json={
            "title": "Initial Document Title",
            "category": "Test Policy",
            "content": "Initial policy text for hospital."
        }, headers=admin_headers)
        assert create_resp.status_code == 201
        doc_id = create_resp.json()["document"]["id"]

        # Update title
        update_resp = await client.put(f"/api/admin/documents/{doc_id}", json={
            "title": "Updated Official Hospital Title",
            "category": "Updated Policy"
        }, headers=admin_headers)
        assert update_resp.status_code == 200
        up_data = update_resp.json()
        assert up_data["document"]["title"] == "Updated Official Hospital Title"

        # Verify chunk title updated
        chunks_resp = await client.get(f"/api/admin/documents/{doc_id}/chunks", headers=admin_headers)
        assert chunks_resp.status_code == 200
        first_chunk = chunks_resp.json()["chunks"][0]
        assert "Updated Official Hospital Title" in first_chunk["chunk_title"]

        # Clean up
        await client.delete(f"/api/admin/documents/{doc_id}", headers=admin_headers)


