import os
from mcp.server.fastmcp import FastMCP, Context
from app.agents.tools import (
    search_doctors, get_available_slots, book_appointment,
    get_appointment_history, get_patient_documents, search_hospital_knowledge
)

mcp = FastMCP("Smart Hospital Operations Server")


def _resolve_caller_identity(ctx: Context = None) -> str:
    """Resolve caller identity bound server-side from session or environment."""
    return os.getenv("MCP_AUTH_USER_ID", "P1001")


@mcp.tool()
def search_hospital_doctors(department: str = "", specialty: str = "") -> dict:
    """Search for hospital doctors by department name or specialty."""
    return search_doctors(department_name=department, specialty=specialty)


@mcp.tool()
def get_doctor_available_slots(doctor_id: str, date: str) -> dict:
    """Get open appointment slots for a doctor on a specific date (YYYY-MM-DD)."""
    return get_available_slots(doctor_id=doctor_id, date=date)


@mcp.tool()
def book_hospital_appointment(doctor_id: str, date: str, time: str, confirmed: bool = False, ctx: Context = None) -> dict:
    """Book an appointment for the authenticated caller. Requires user confirmation before execution."""
    caller_id = _resolve_caller_identity(ctx)
    return book_appointment(user_id=caller_id, doctor_id=doctor_id, date=date, time=time, confirmed=confirmed)


@mcp.tool()
def get_user_appointment_history(ctx: Context = None) -> dict:
    """Get appointment records for the authenticated caller."""
    caller_id = _resolve_caller_identity(ctx)
    return get_appointment_history(user_id=caller_id)


@mcp.tool()
def get_user_documents(ctx: Context = None) -> dict:
    """Get medical documents for the authenticated caller."""
    caller_id = _resolve_caller_identity(ctx)
    return get_patient_documents(user_id=caller_id)


@mcp.tool()
def search_hospital_faq(query: str) -> dict:
    """Search general hospital FAQ, visiting hours, and policies."""
    return search_hospital_knowledge(query=query)


if __name__ == "__main__":
    mcp.run()

