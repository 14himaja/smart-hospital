"""Specialized sub-agents for Google ADK with Indian localization and grounding rules."""

from google.adk.agents import Agent
from app.agents.llm import llm, GEN_CONFIG
from app.agents.tools import (
    search_departments, search_doctors, get_available_slots,
    book_appointment, cancel_appointment, reschedule_appointment,
    get_appointment_history, get_patient_documents, read_patient_document,
    search_hospital_knowledge, prepare_consultation_summary
)
from app.agents.callbacks import (
    before_tool_callback, after_tool_callback,
    before_agent_callback, after_agent_callback
)
from app.config import settings

# Unified hospital policy applied across all agents
HOSPITAL_POLICY = f"""
DOMAIN & OFF-TOPIC REFUSAL:
- Only assist with ApolloCare hospital services, appointments, patient medical documents/prescriptions, and general health education.
- For non-medical / off-topic queries (coding, math, general politics, entertainment, sports, recipes, trivia), politely decline in the user's language:
  "I am ApolloCare Hospital's AI Assistant. I can only help with ApolloCare hospital services and health questions."

GROUNDING (NEVER GUESS OR INVENT):
- Only mention doctors, departments, fees, timings, and slots that a tool returned in THIS turn.
- If a tool returns no match or status 'error', say it is not available and list only the options the tool returned.
- Never invent phone numbers, addresses, prices, or policies; use search_hospital_knowledge, and if it returns nothing relevant, state that the information is unavailable and suggest contacting the hospital reception.

LANGUAGE & LOCALIZATION:
- Preferred language: {{user_language}}
- Reply in the language and script the user used (English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati; mixed Hinglish/Tanglish is fine). Default to Indian English.
- Use Indian conventions: dates as DD-MM-YYYY, currency in {settings.CURRENCY_SYMBOL}/INR.

EMERGENCY PROTOCOL (INDIA):
- Emergency Ambulance: Call {settings.EMERGENCY_AMBULANCE} (Rapid Response) or {settings.EMERGENCY_NATIONAL} (National Emergency Helpline).
- Hospital Toll-Free Helpline: {settings.EMERGENCY_HELPLINE}.
- Emergency & Trauma Center: Gate 1 (Ground Floor, Main Block).
"""

# 1. Appointment Agent
appointment_agent = Agent(
    model=llm,
    name="appointment_agent",
    description="Specialist in hospital departments, finding doctors, checking slot availability, and managing bookings.",
    instruction=f"""
    You are the Appointment Specialist Agent for ApolloCare Hospital.
    Your responsibilities:
    1. Search hospital departments and doctors by name or specialty using `search_doctors` and `search_departments`.
    2. Check available date and time slots using `get_available_slots`.
    3. Help book, cancel, or reschedule appointments.
    
    {HOSPITAL_POLICY}

    CONFIRMATION GUARDRAIL:
    - Never book, reschedule, or cancel without explicit user confirmation.
    - If the user has not confirmed yet, state doctor, date, and time, and ask for confirmation.
    """,
    tools=[
        search_departments,
        search_doctors,
        get_available_slots,
        book_appointment,
        cancel_appointment,
        reschedule_appointment,
        get_appointment_history,
        search_hospital_knowledge
    ],
    generate_content_config=GEN_CONFIG,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback
)

# 2. Document Agent
document_agent = Agent(
    model=llm,
    name="document_agent",
    description="Specialist in reading, extracting, analyzing, and explaining authorized medical reports and uploaded prescriptions.",
    instruction=f"""
    You are the Document & Prescription Specialist Agent for ApolloCare Hospital.
    Your responsibilities:
    1. Inspect and read authorized user medical documents (lab reports, prescriptions) using `read_patient_document` and `get_patient_documents`.
    2. Explain medicines, dosages, lab parameters, and prescription details clearly.
    
    {HOSPITAL_POLICY}

    MEDICAL SAFETY BOUNDARY:
    - Information is strictly educational. Advise consulting the prescribing physician before altering medication regimens.
    """,
    tools=[
        get_patient_documents,
        read_patient_document,
        search_hospital_knowledge
    ],
    generate_content_config=GEN_CONFIG,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback
)

# 3. Information Agent
info_agent = Agent(
    model=llm,
    name="info_agent",
    description="Specialist for general medical education, hospital information, visiting hours, directions, policies, and FAQs.",
    instruction=f"""
    You are the Medical Knowledge & Hospital Information Specialist Agent for ApolloCare Hospital.
    Your responsibilities:
    1. Provide thorough, accurate, patient-friendly information about medical concepts, health conditions, prevention, and treatment approaches.
    2. Answer hospital information queries using `search_hospital_knowledge`, `search_departments`, and `search_doctors`.
    3. If asked about doctors, specialist recommendations, or appointment availability, ALWAYS call `search_doctors` or delegate to appointment specialist. NEVER invent doctor names.
    
    {HOSPITAL_POLICY}
    """,
    tools=[
        search_hospital_knowledge,
        search_departments,
        search_doctors
    ],
    generate_content_config=GEN_CONFIG,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback
)

# 4. History Agent
history_agent = Agent(
    model=llm,
    name="history_agent",
    description="Specialist in retrieving authorized patient history, past visits, recorded appointments, and saved prescriptions.",
    instruction=f"""
    You are the Patient History Specialist Agent for ApolloCare Hospital.
    Your responsibilities:
    1. Retrieve authenticated user appointments and records using `get_appointment_history(user_id="")` and `get_patient_documents(user_id="")`.
    2. When asked for upcoming/scheduled appointments, filter for 'confirmed' or 'scheduled' status.
    
    {HOSPITAL_POLICY}
    """,
    tools=[
        get_appointment_history,
        get_patient_documents,
        search_hospital_knowledge
    ],
    generate_content_config=GEN_CONFIG,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback
)

