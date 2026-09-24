"""FastMCP Server exposing Hospital services via Model Context Protocol."""

from mcp.server.fastmcp import FastMCP
from app.agents.tools import (
    search_doctors, get_available_slots, book_appointment,
    get_appointment_history, get_patient_documents, search_hospital_knowledge
)

mcp = FastMCP("Smart Hospital Operations Server")


@mcp.tool()
def search_hospital_doctors(department: str = "", specialty: str = "") -> dict:
    """Search for hospital doctors by department name or specialty."""
    return search_doctors(department_name=department, specialty=specialty)


@mcp.tool()
def get_doctor_available_slots(doctor_id: str, date: str) -> dict:
    """Get open appointment slots for a doctor on a specific date (YYYY-MM-DD)."""
    return get_available_slots(doctor_id=doctor_id, date=date)


@mcp.tool()
def book_hospital_appointment(user_id: str, doctor_id: str, date: str, time: str, confirmed: bool = False) -> dict:
    """Book an appointment. Requires user confirmation before execution."""
    return book_appointment(user_id=user_id, doctor_id=doctor_id, date=date, time=time, confirmed=confirmed)


@mcp.tool()
def get_user_appointment_history(user_id: str) -> dict:
    """Get appointment records for an authorized patient."""
    return get_appointment_history(user_id=user_id)


@mcp.tool()
def get_user_documents(user_id: str) -> dict:
    """Get medical documents for an authorized patient."""
    return get_patient_documents(user_id=user_id)


@mcp.tool()
def search_hospital_faq(query: str) -> dict:
    """Search general hospital FAQ, visiting hours, and policies."""
    return search_hospital_knowledge(query=query)


if __name__ == "__main__":
    mcp.run()
