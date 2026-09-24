import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import db
from app.api.auth import create_access_token
from app.models import UserRole
from app.agents.tools import (
    search_departments, search_doctors, get_available_slots,
    book_appointment, cancel_appointment, reschedule_appointment,
    get_appointment_history, get_patient_documents, search_hospital_knowledge,
    prepare_consultation_summary
)
from app.agents.workflows import (
    document_sequential_workflow, consultation_prep_workflow, summary_refinement_loop
)


@pytest.fixture
def auth_headers_p1001():
    user = db.get_user("P1001")
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_p1002():
    user = db.get_user("P1002")
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


# --- 1. Authentication & Identity Tests ---

@pytest.mark.asyncio
async def test_auth_registration_and_login():
    import time
    test_email = f"arjun_{int(time.time())}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register new patient
        reg_resp = await client.post("/api/auth/register", json={
            "name": "Arjun Das",
            "email": test_email,
            "password": "mypassword123",
            "phone": "+91-9123456789"
        })
        assert reg_resp.status_code == 201
        data = reg_resp.json()
        assert data["status"] == "success"
        assert "user_id" in data
        otp = data["demo_otp"]

        # Verify OTP
        otp_resp = await client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": otp
        })
        assert otp_resp.status_code == 200
        assert "access_token" in otp_resp.json()

        # Login with password
        login_resp = await client.post("/api/auth/login", json={
            "email": test_email,
            "password": "mypassword123"
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert "access_token" in login_data
        assert login_data["user"]["name"] == "Arjun Das"


# --- 2. Authorization & Isolation Tests ---

@pytest.mark.asyncio
async def test_appointment_authorization_isolation(auth_headers_p1001, auth_headers_p1002):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Patient P1001 queries appointments
        resp_1 = await client.get("/api/hospital/appointments", headers=auth_headers_p1001)
        assert resp_1.status_code == 200
        appts_1 = resp_1.json()
        for a in appts_1:
            assert a["user_id"] == "P1001"

        # Patient P1002 queries appointments
        resp_2 = await client.get("/api/hospital/appointments", headers=auth_headers_p1002)
        assert resp_2.status_code == 200
        appts_2 = resp_2.json()
        for a in appts_2:
            assert a["user_id"] == "P1002"


# --- 3. Hospital REST Endpoints ---

@pytest.mark.asyncio
async def test_hospital_catalog_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Departments
        depts_resp = await client.get("/api/hospital/departments")
        assert depts_resp.status_code == 200
        depts = depts_resp.json()
        assert len(depts) >= 5

        # Doctors filtered by department
        docs_resp = await client.get("/api/hospital/doctors?department=Dermatology")
        assert docs_resp.status_code == 200
        docs = docs_resp.json()
        assert len(docs) >= 1
        assert all("Dermatology" in d["department_name"] for d in docs)

        # Slots
        slots_resp = await client.get(f"/api/hospital/slots?doctor_id={docs[0]['id']}")
        assert slots_resp.status_code == 200
        assert isinstance(slots_resp.json(), list)


# --- 4. Tool & Confirmation Guardrail Tests ---

def test_booking_confirmation_guardrail():
    # Without confirmation -> must demand confirmation
    unconfirmed = book_appointment(
        user_id="P1001",
        doctor_id="DOC-001",
        date="2026-09-25",
        time="10:00",
        confirmed=False
    )
    assert unconfirmed["status"] == "confirmation_required"
    assert "Please confirm" in unconfirmed["message"]

    # With confirmation -> must book
    confirmed = book_appointment(
        user_id="P1001",
        doctor_id="DOC-001",
        date="2026-09-25",
        time="10:00",
        confirmed=True
    )
    assert confirmed["status"] == "success"
    assert "appointment_id" in confirmed
    appt_id = confirmed["appointment_id"]

    # Cancellation confirmation guardrail
    cancel_prompt = cancel_appointment(user_id="P1001", appointment_id=appt_id, confirmed=False)
    assert cancel_prompt["status"] == "confirmation_required"

    cancel_done = cancel_appointment(user_id="P1001", appointment_id=appt_id, confirmed=True)
    assert cancel_done["status"] == "success"

    # Clean up test appointment so pytest runs do not pollute persistent hospital.db
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
        conn.commit()



def test_history_and_knowledge_tools():
    # History retrieval
    history = get_appointment_history(user_id="P1001")
    assert history["status"] == "success"
    assert history["user_id"] == "P1001"

    # Documents retrieval
    docs = get_patient_documents(user_id="P1001")
    assert docs["status"] == "success"
    assert docs["count"] >= 1

    # RAG Knowledge search
    kb_res = search_hospital_knowledge(query="visiting hours")
    assert kb_res["status"] == "success"
    assert len(kb_res["knowledge_entries"]) > 0
    assert any("Visiting" in k["topic"] for k in kb_res["knowledge_entries"])

    # Consultation summary
    summary = prepare_consultation_summary(user_id="P1001")
    assert summary["status"] == "success"
    assert "summary_brief" in summary


# --- 5. ADK Workflows Definition Test ---

def test_adk_workflow_agents_structure():
    assert document_sequential_workflow.name == "document_processing_pipeline"
    assert len(document_sequential_workflow.sub_agents) == 3

    assert consultation_prep_workflow.name == "consultation_prep_workflow"
    assert len(consultation_prep_workflow.sub_agents) == 2

    assert summary_refinement_loop.name == "summary_refinement_loop"
    assert summary_refinement_loop.max_iterations == 2


# --- 6. End-to-End Chat Endpoint Test ---

@pytest.mark.asyncio
async def test_chat_endpoint_with_adk(auth_headers_p1001, monkeypatch):
    from unittest.mock import AsyncMock
    from app.agents.root_agent import runner

    async def mock_run_async(*args, **kwargs):
        class MockEvent:
            def __init__(self):
                self.text = "We have Cardiology, Dermatology, Orthopedics, Pediatrics, and General Medicine available."
                self.author = "hospital_root_agent"
            def is_final_response(self):
                return True

        yield MockEvent()

    monkeypatch.setattr(runner, "run_async", mock_run_async)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat", json={
            "message": "Hello, what departments are available at the hospital?",
            "session_id": "TEST-CHAT-SESSION"
        }, headers=auth_headers_p1001)

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert len(data["reply"]) > 0
        assert data["session_id"] == "TEST-CHAT-SESSION"
        assert "source_type" in data
        assert "trace_id" in data


# --- 7. RAG Grounding & Negative Case Tests ---

def test_rag_grounding_update_and_negative_case():
    # 1. Negative Case: Irrelevant policy query (e.g. underwater surgery)
    negative_res = db.search_knowledge_base(query="underwater surgery policy")
    assert len(negative_res) == 0, "Non-existent policy should return 0 chunks"

    # 2. RAG Grounding: Upload initial policy
    doc_result = db.add_hospital_document(
        title="NICU Visiting Hours Policy",
        category="Policy",
        uploaded_by="A4001",
        content="NICU visiting hours are strictly 4 PM to 5 PM daily. Only parents allowed."
    )
    doc_id = doc_result["id"]

    res_1 = db.search_knowledge_base(query="NICU visiting hours")
    assert len(res_1) > 0
    assert any("4 PM to 5 PM" in r["content"] for r in res_1)

    # 3. Policy Update: Admin updates policy
    db.delete_hospital_document(doc_id=doc_id, user_id="A4001")
    db.add_hospital_document(
        title="NICU Visiting Hours Policy",
        category="Policy",
        uploaded_by="A4001",
        content="NICU visiting hours are updated to 6 PM to 7 PM daily. Only parents allowed."
    )

    res_2 = db.search_knowledge_base(query="NICU visiting hours")
    assert len(res_2) > 0
    assert any("6 PM to 7 PM" in r["content"] for r in res_2)
    assert not any("4 PM to 5 PM" in r["content"] for r in res_2), "Old policy content must no longer be returned"

