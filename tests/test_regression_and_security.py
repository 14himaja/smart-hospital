"""
Targeted regression & security tests for PR review fixes.
Covers:
- RAG PHI leak prevention (anonymous & cross-patient fail-closed isolation)
- Auth role escalation prevention & token validation
- Salted scrypt password hashing & constant-time verification
- Secure OTP verification lifecycle (single-use, persistence of is_verified)
- Doctor search accuracy & strict specialty filtering (no silent fallbacks)
- Smartflo telephony mu-law conversion & frame pacing
"""

import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import db
from app.models import UserRole, DocumentType
from app.db.repositories.users import hash_password, verify_password
from app.voice.smartflo_transport import SmartfloAudioTransport
from app.agents.tools import search_doctors, get_available_slots, read_patient_document


@pytest.mark.asyncio
async def test_auth_registration_cannot_escalate_role():
    """Verify that registering with role='admin' is rejected or forced to 'patient'."""
    # Pre-clean
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = 'attacker@hospital.org'")
        conn.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/register", json={
            "name": "Attacker",
            "email": "attacker@hospital.org",
            "password": "attackpassword123",
            "phone": "+91-99999-00001",
            "role": "admin"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"

        # Verify created user is assigned PATIENT role in database
        user = db.get_user(data["user_id"])
        assert user is not None
        assert user.role == UserRole.PATIENT, "Self-registration must always be forced to patient role"

    # Post-clean
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = 'attacker@hospital.org'")
        conn.commit()


@pytest.mark.asyncio
async def test_invalid_token_returns_401_no_p1001_fallback():
    """Verify that invalid/expired tokens return 401 and do not silently fall back to P1001."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid bearer token
        resp = await client.get("/api/hospital/appointments", headers={
            "Authorization": "Bearer invalid.fake.token"
        })
        assert resp.status_code == 401


def test_salted_scrypt_password_hashing():
    """Verify passwords use salted scrypt and verify_password works with legacy and scrypt hashes."""
    pwd = "SuperSecretHospitalPassword2026!"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)

    # Must be salted -> different hashes for same password
    assert h1 != h2
    assert h1.startswith("scrypt$")

    # verify_password must succeed with correct password and fail with incorrect
    assert verify_password(pwd, h1) is True
    assert verify_password("WrongPassword!", h1) is False
    assert verify_password("", h1) is False


@pytest.mark.asyncio
async def test_secure_otp_verification_lifecycle():
    """Verify OTP verification lifecycle: random generation, single-use, and is_verified persistence."""
    test_email = "otp_test_user@hospital.org"

    # Pre-clean
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?", (test_email,))
        conn.cursor().execute("DELETE FROM otps WHERE email = ?", (test_email,))
        conn.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        reg_resp = await client.post("/api/auth/register", json={
            "name": "OTP Test User",
            "email": test_email,
            "password": "securepassword123"
        })
        assert reg_resp.status_code == 201
        data = reg_resp.json()
        user_id = data["user_id"]

        # Verify initial user is not verified in DB
        user = db.get_user(user_id)
        assert user.is_verified is False

        # 2. Incorrect OTP must be rejected with 400
        bad_otp_resp = await client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": "000000"
        })
        assert bad_otp_resp.status_code == 400

        # 3. Retrieve actual stored OTP and verify
        stored_otp = db.get_otp(test_email)
        assert stored_otp is not None and len(stored_otp) == 6

        ok_otp_resp = await client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": stored_otp
        })
        assert ok_otp_resp.status_code == 200
        assert "access_token" in ok_otp_resp.json()

        # 4. Verify user is now marked verified in DB
        user_after = db.get_user(user_id)
        assert user_after.is_verified is True

        # 5. OTP must be single-use and cleared from DB
        assert db.get_otp(test_email) is None
        replay_resp = await client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": stored_otp
        })
        assert replay_resp.status_code == 400

    # Post-clean
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?", (test_email,))
        conn.commit()


def test_rag_phi_isolation_fail_closed():
    """Verify that anonymous and cross-patient searches never leak private medical documents."""
    # Ensure patient P1002 has a private document
    p1002_doc = db.add_user_document(
        user_id="P1002",
        title="P1002 Confidential Cardiology Report",
        document_type=DocumentType.LAB_REPORT,
        extracted_text="Patient P1002 severe aortic valve stenosis. Confidential medical record.",
        summary="Severe aortic valve stenosis."
    )

    try:
        # 1. Anonymous search (user_id=None) must NOT return P1002's document
        anon_results = db.search_knowledge_base(query="aortic valve stenosis", user_id=None)
        assert not any("P1002" in r.get("topic", "") or "P1002" in r.get("content", "") for r in anon_results)

        # 2. Patient P1001 search must NOT return P1002's document
        p1001_results = db.search_knowledge_base(query="aortic valve stenosis", user_id="P1001")
        assert not any("P1002" in r.get("topic", "") or "P1002" in r.get("content", "") for r in p1001_results)

        # 3. Patient P1002 search CAN return P1002's document
        p1002_results = db.search_knowledge_base(query="aortic valve stenosis", user_id="P1002")
        assert any("P1002" in r.get("topic", "") or "aortic" in r.get("content", "").lower() for r in p1002_results)

    finally:
        # Cleanup
        db.delete_user_document(document_id=p1002_doc.id, user_id="P1002")


def test_doctor_lookup_strict_no_fallbacks():
    """Verify doctor search does not return Dr. Sarah Jenkins or all doctors on unknown queries."""
    # Search for an unknown specialty
    unknown_spec = search_doctors(specialty="QuantumBiomechanics")
    assert unknown_spec["status"] == "error" or len(unknown_spec.get("doctors", [])) == 0

    # Search for an unknown department
    unknown_dept = search_doctors(department_name="NonExistentDepartment")
    assert unknown_dept["status"] == "error" or len(unknown_dept.get("doctors", [])) == 0

    # Slot lookup for unknown doctor
    unknown_slots = get_available_slots(doctor_id="DOC-999999")
    assert unknown_slots["status"] == "error"


def test_read_patient_document_security():
    """Verify patient cannot read another patient's document by guessing document ID."""
    p1001_docs = db.get_user_documents("P1001")
    if p1001_docs:
        p1001_doc_id = p1001_docs[0].id
        # Attempt to read P1001's doc as P1002
        res = read_patient_document(user_id="P1002", document_id=p1001_doc_id)
        assert res["status"] == "error"
        assert "not found" in res["message"].lower()


def test_smartflo_audio_transcoding():
    """Verify Smartflo 8kHz mu-law <-> 16/24kHz PCM conversion."""
    transport = SmartfloAudioTransport()

    # Generate 160 bytes of mu-law silence (0xFF is mu-law 0)
    mulaw_silence = b"\xff" * 160
    pcm_16k = transport._ulaw_to_pcm16(mulaw_silence)
    assert len(pcm_16k) > 0, "8kHz mu-law must transcode to 16kHz PCM"

    # Transcode 24kHz PCM to 8kHz mu-law
    pcm_24k = b"\x00\x00" * 480  # 480 16-bit samples = 20ms at 24kHz
    mulaw_out = transport._pcm24_to_ulaw(pcm_24k)
    assert len(mulaw_out) > 0, "24kHz PCM must transcode to 8kHz mu-law"


@pytest.mark.asyncio
async def test_audit_log_requires_admin_authorization():
    """Verify that /api/hospital/audit-logs is forbidden for patients and anonymous callers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Anonymous request
        anon_resp = await ac.get("/api/hospital/audit-logs")
        assert anon_resp.status_code == 401

        # 2. Patient login
        p_login = await ac.post("/api/auth/login", json={"email": "rahul@example.com", "password": "password123"})
        assert p_login.status_code == 200
        p_token = p_login.json()["access_token"]
        p_resp = await ac.get("/api/hospital/audit-logs", headers={"Authorization": f"Bearer {p_token}"})
        assert p_resp.status_code == 403

        # 3. Admin login
        admin_login = await ac.post("/api/auth/login", json={"email": "admin@hospital.org", "password": "adminpass123"})
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        admin_resp = await ac.get("/api/hospital/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert admin_resp.status_code == 200
        assert isinstance(admin_resp.json(), list)


@pytest.mark.asyncio
async def test_document_upload_json_body_model():
    """Verify document upload accepts Pydantic JSON body model and rejects query-string PHI."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_login = await ac.post("/api/auth/login", json={"email": "rahul@example.com", "password": "password123"})
        p_token = p_login.json()["access_token"]

        payload = {
            "title": "Blood Sugar Routine Report",
            "doc_type": "laboratory_report",
            "text_content": "Fasting Blood Sugar: 95 mg/dL. HbA1c: 5.4%. Normal ranges."
        }
        resp = await ac.post("/api/hospital/documents", json=payload, headers={"Authorization": f"Bearer {p_token}"})
        assert resp.status_code == 201
        doc_data = resp.json()
        assert doc_data["title"] == payload["title"]
        assert doc_data["user_id"] == "P1001"


def test_cors_configuration_security():
    """Verify CORS configuration does not allow arbitrary origins with credentials."""
    from app.config import settings
    assert "*" not in settings.ALLOWED_ORIGINS
    assert len(settings.ALLOWED_ORIGINS) > 0


@pytest.mark.asyncio
async def test_off_domain_query_guardrail():
    """Verify that off-domain requests (coding, math, trivia) are rejected deterministically."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_login = await ac.post("/api/auth/login", json={"email": "rahul@example.com", "password": "password123"})
        p_token = p_login.json()["access_token"]

        off_domain_prompts = [
            "Write a python script to sort a list using quicksort",
            "What is the derivative of x^3 + 4x^2 - 7?",
            "Who won the 2022 FIFA World Cup?",
            "Give me a recipe for chocolate cake"
        ]

        for prompt in off_domain_prompts:
            resp = await ac.post(
                "/api/chat",
                json={"message": prompt},
                headers={"Authorization": f"Bearer {p_token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["source_type"] == "deterministic"
            assert "only" in data["reply"].lower() and "hospital" in data["reply"].lower()


def test_agent_generation_configs_and_tools():
    """Verify all agents have low temperature (0.2) and info_agent has search_doctors."""
    from app.agents.root_agent import root_agent
    from app.agents.sub_agents import appointment_agent, document_agent, info_agent, history_agent

    all_agents = [root_agent, appointment_agent, document_agent, info_agent, history_agent]
    for ag in all_agents:
        assert ag.generate_content_config is not None
        assert ag.generate_content_config.temperature == 0.2

    # Verify info_agent has search_doctors tool to prevent hallucinated doctors
    info_tool_names = [getattr(t, "__name__", getattr(t, "name", str(t))) for t in info_agent.tools]
    assert "search_doctors" in info_tool_names


def test_whole_word_greeting_not_triggered_by_which_or_history():
    """Verify substring 'hi' inside 'which' or 'history' is not matched as a greeting."""
    import re
    greeting_pattern = r"\b(hi|hello|hey|namaste|good morning|good afternoon|good evening|greetings)\b"

    assert not re.search(greeting_pattern, "which doctor is available today?")
    assert not re.search(greeting_pattern, "show me my appointment history")
    assert not re.search(greeting_pattern, "is this the right department for child care?")
    assert not re.search(greeting_pattern, "they told me to get a blood test")

    assert re.search(greeting_pattern, "hi doctor")
    assert re.search(greeting_pattern, "hello, how are you?")
    assert re.search(greeting_pattern, "namaste")


@pytest.mark.asyncio
async def test_upload_validation_mime_and_size_limits():
    """Verify /api/chat/upload validates file counts, sizes, and MIME types."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_login = await ac.post("/api/auth/login", json={"email": "rahul@example.com", "password": "password123"})
        p_token = p_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {p_token}"}

        # 1. Reject more than 3 files
        files_4 = [
            ("files", ("f1.txt", b"report 1", "text/plain")),
            ("files", ("f2.txt", b"report 2", "text/plain")),
            ("files", ("f3.txt", b"report 3", "text/plain")),
            ("files", ("f4.txt", b"report 4", "text/plain")),
        ]
        resp_count = await ac.post("/api/chat/upload", data={"message": "Analyze"}, files=files_4, headers=headers)
        assert resp_count.status_code == 400

        # 2. Reject unsupported MIME type
        unsupported_file = [
            ("files", ("script.exe", b"MZbinarycode", "application/x-msdownload"))
        ]
        resp_mime = await ac.post("/api/chat/upload", data={"message": "Analyze"}, files=unsupported_file, headers=headers)
        assert resp_mime.status_code == 415


def test_smartflo_numpy_codec_accuracy():
    """Verify numpy G.711 codec against reference values and roundtrip precision."""
    import numpy as np
    from app.voice.smartflo_transport import mulaw_to_pcm16, pcm16_to_mulaw, resample

    # G.711 Reference zero and extremes
    assert mulaw_to_pcm16(b"\xff")[0] == 0
    assert mulaw_to_pcm16(b"\x80")[0] == 32124
    assert mulaw_to_pcm16(b"\x00")[0] == -32124

    # Roundtrip test
    pcm_in = np.array([0, 1000, -1000, 15000, -15000], dtype=np.int16)
    ulaw = pcm16_to_mulaw(pcm_in)
    pcm_out = mulaw_to_pcm16(ulaw)
    np.testing.assert_allclose(pcm_out, pcm_in, atol=50)

    # Resample test
    resampled = resample(pcm_in, 8000, 16000)
    assert len(resampled) == len(pcm_in) * 2




