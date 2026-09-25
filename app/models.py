from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- Role & Auth Models ---

class UserRole(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    STAFF = "staff"
    ADMIN = "admin"


class User(BaseModel):
    user_id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole = UserRole.PATIENT
    is_verified: bool = True
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    preferences: Dict[str, Any] = Field(default_factory=lambda: {"language": "English"})


class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=6, max_length=128)
    phone: Optional[str] = Field(None, max_length=25)
    role: Optional[UserRole] = None  # Ignored on public self-registration; always forced to PATIENT


class UserLogin(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)


class VerifyOTPRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    otp: str = Field(..., min_length=4, max_length=10)


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    is_verified: bool
    preferences: Dict[str, Any]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# --- Hospital Domain Models ---

class Department(BaseModel):
    id: str
    name: str
    description: str
    location: str


class Doctor(BaseModel):
    id: str
    name: str
    department_id: str
    department_name: str
    specialty: str
    available_days: List[str]
    consultation_fee: float


class AppointmentSlot(BaseModel):
    slot_id: str
    doctor_id: str
    doctor_name: str
    department_name: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    is_available: bool = True


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Appointment(BaseModel):
    id: str
    user_id: str
    doctor_id: str
    doctor_name: str
    department_name: str
    date: str
    time: str
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppointmentCreate(BaseModel):
    doctor_id: str = Field(..., min_length=1, max_length=50)
    date: str = Field(..., min_length=8, max_length=20)
    time: str = Field(..., min_length=3, max_length=10)
    notes: Optional[str] = Field(None, max_length=500)
    confirmed: bool = False


# --- Document & Medical History ---

class DocumentType(str, Enum):
    GENERAL = "general"
    LAB_REPORT = "laboratory_report"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    REFERRAL = "referral"


class MedicalDocument(BaseModel):
    id: str
    user_id: str
    title: str
    document_type: DocumentType
    upload_date: str
    extracted_text: str
    summary: Optional[str] = None
    key_findings: List[str] = Field(default_factory=list)


# --- Audit Log Model ---

class AuditLog(BaseModel):
    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    status: str = "SUCCESS"


# --- Conversational / Chat Models ---

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = Field(None, max_length=100)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    active_agent: Optional[str] = "root_agent"
    state: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_details: Optional[Dict[str, Any]] = None
    # Response source telemetry & classification
    source_type: Optional[str] = "llm"  # "llm", "rag", "llm_rag", "tool", "deterministic"
    llm_used: bool = True
    rag_used: bool = False
    tools_used: List[str] = Field(default_factory=list)
    retrieved_chunks: List[str] = Field(default_factory=list)
    trace_id: Optional[str] = None



# --- Structured Output Models (Section 34) ---

class AppointmentSummary(BaseModel):
    appointment_id: str
    doctor_name: str
    department_name: str
    date: str
    time: str
    status: str
    notes: Optional[str] = None


class ConsultationSummary(BaseModel):
    patient_id: str
    patient_name: str
    upcoming_appointment: Optional[Dict[str, Any]] = None
    previous_appointments: List[Dict[str, Any]] = Field(default_factory=list)
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str
    limitations: List[str] = Field(default_factory=lambda: [
        "This summary is for preparation only and does not constitute a medical diagnosis or treatment plan.",
        "Please discuss all clinical symptoms and test interpretations directly with your physician."
    ])


class ToolResult(BaseModel):
    status: str
    message: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    action: Optional[str] = None


class AgentResponse(BaseModel):
    agent_name: str
    content: str
    structured_data: Optional[Dict[str, Any]] = None
    sources: List[str] = Field(default_factory=list)

