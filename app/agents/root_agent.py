"""Root Coordinator Agent for the AI Hospital Assistant."""

from google.adk.agents import Agent
from google.adk.runners import Runner
from app.config import settings
from app.agents.llm import llm, GEN_CONFIG
from app.agents.sub_agents import (
    appointment_agent,
    document_agent,
    info_agent,
    history_agent,
    HOSPITAL_POLICY
)
from app.agents.callbacks import (
    before_agent_callback,
    after_agent_callback,
    before_tool_callback,
    after_tool_callback
)

# Create Root Coordinator Agent
root_agent = Agent(
    model=llm,
    name="hospital_root_agent",
    description="Primary conversational AI coordinator for hospital operations and patient assistance.",
    instruction=f"""
    You are the AI Hospital Assistant Root Coordinator for ApolloCare Hospital, Hyderabad, India.
    Your mission is to help authenticated patients and hospital staff navigate hospital services smoothly and safely.

    {HOSPITAL_POLICY}

    AGENT COMMUNICATION & ANONYMITY RULES:
    - NEVER output internal agent names (e.g., info_agent, appointment_agent, document_agent, history_agent, root_agent).
    - Speak naturally as ApolloCare AI Assistant.

    GREETINGS & COURTESY:
    - When the user greets you ('hi', 'hello', 'namaste', 'good morning'), respond warmly and politely.

    DELEGATION DIRECTIVES:
    - General medical education, disease explanations, hospital emergency guidelines, visiting hours, policies, FAQs → delegate to `info_agent`.
    - Uploaded reports, lab tests, prescriptions, medicine explanation → delegate to `document_agent`.
    - Appointments, doctor lookup, slot availability, booking, cancellation, rescheduling, user confirmation → delegate to `appointment_agent`.
    - Patient's past appointments or appointment history → delegate to `history_agent`.

    CORE SAFETY RULES:
    1. Never ask users for internal IDs.
    2. Booking, canceling, rescheduling require explicit user confirmation.
    3. You are an educational AI assistant, not a doctor. Advise consulting qualified physicians.
    """,
    sub_agents=[
        appointment_agent,
        document_agent,
        info_agent,
        history_agent
    ],
    generate_content_config=GEN_CONFIG,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback
)


import os
from google.adk.sessions import DatabaseSessionService, InMemorySessionService

# Persistent session service for Google ADK across restarts & reloads
adk_db_url = os.getenv("ADK_SESSION_DB_URL", "sqlite+aiosqlite:///./adk_sessions.db")
try:
    session_service = DatabaseSessionService(db_url=adk_db_url)
except Exception:
    session_service = InMemorySessionService()

# Global runner instance
runner = Runner(
    agent=root_agent,
    session_service=session_service,
    app_name="smart_hospital",
    auto_create_session=True
)

