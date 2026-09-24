import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

from app.config import settings
from app.voice.transport import BaseAudioTransport
from app.agents.tools import (
    search_departments, search_doctors, get_available_slots,
    book_appointment, cancel_appointment, reschedule_appointment,
    get_appointment_history, get_patient_documents, read_document,
    search_hospital_knowledge, prepare_consultation_summary
)

logger = logging.getLogger("gemini_live_session")
logger.setLevel(logging.INFO)

# Map tool names to Python implementations in app/agents/tools.py
TOOL_EXECUTORS = {
    "search_departments": search_departments,
    "search_doctors": search_doctors,
    "get_available_slots": get_available_slots,
    "book_appointment": book_appointment,
    "cancel_appointment": cancel_appointment,
    "reschedule_appointment": reschedule_appointment,
    "get_appointment_history": get_appointment_history,
    "get_patient_documents": get_patient_documents,
    "read_document": read_document,
    "search_hospital_knowledge": search_hospital_knowledge,
    "prepare_consultation_summary": prepare_consultation_summary,
}


def build_hospital_tool_declarations() -> List[types.Tool]:
    """Build Gemini Live API function declarations for all 11 hospital tools."""
    return [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="search_departments",
                description="Retrieve the list of all hospital departments and their locations.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={}
                )
            ),
            types.FunctionDeclaration(
                name="search_doctors",
                description="Search for doctors by department name or specialty.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "department_name": types.Schema(type=types.Type.STRING, description="Department name (e.g. Cardiology, Orthopedics, Dermatology)"),
                        "specialty": types.Schema(type=types.Type.STRING, description="Specialty or doctor role (e.g. Cardiologist, Orthopedic, Dermatologist)")
                    }
                )
            ),
            types.FunctionDeclaration(
                name="get_available_slots",
                description="Get available appointment time slots for a given doctor across upcoming dates or for a specific date (YYYY-MM-DD).",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "doctor_id": types.Schema(type=types.Type.STRING, description="Doctor ID (e.g. DOC-001) or Doctor Name (e.g. Dr. Sarah Jenkins, Dr. Alan Vance)"),
                        "date": types.Schema(type=types.Type.STRING, description="Optional date in YYYY-MM-DD format or relative date like 'tomorrow', 'Friday'. If omitted, returns all upcoming available slots.")
                    },
                    required=["doctor_id"]
                )
            ),
            types.FunctionDeclaration(
                name="book_appointment",
                description="Book an appointment for a patient. CRITICAL: The user MUST explicitly confirm the booking details before calling with confirmed=True.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)"),
                        "doctor_id": types.Schema(type=types.Type.STRING, description="Doctor ID or Doctor Name"),
                        "date": types.Schema(type=types.Type.STRING, description="Date in YYYY-MM-DD format or relative date like 'tomorrow', 'Friday'"),
                        "time": types.Schema(type=types.Type.STRING, description="Time slot (e.g. 09:00, 10:00, 11:30, 14:00)"),
                        "confirmed": types.Schema(type=types.Type.BOOLEAN, description="Whether the patient explicitly confirmed booking"),
                        "notes": types.Schema(type=types.Type.STRING, description="Additional medical notes")
                    },
                    required=["user_id", "doctor_id", "date", "time"]
                )
            ),
            types.FunctionDeclaration(
                name="cancel_appointment",
                description="Cancel an existing appointment for a patient. Requires explicit user confirmation.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)"),
                        "appointment_id": types.Schema(type=types.Type.STRING, description="Appointment ID"),
                        "confirmed": types.Schema(type=types.Type.BOOLEAN, description="Whether patient explicitly confirmed cancellation")
                    },
                    required=["user_id", "appointment_id"]
                )
            ),
            types.FunctionDeclaration(
                name="reschedule_appointment",
                description="Reschedule an existing appointment to a new date and time.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)"),
                        "appointment_id": types.Schema(type=types.Type.STRING, description="Appointment ID"),
                        "new_date": types.Schema(type=types.Type.STRING, description="New date YYYY-MM-DD or relative date like 'tomorrow'"),
                        "new_time": types.Schema(type=types.Type.STRING, description="New time slot"),
                        "confirmed": types.Schema(type=types.Type.BOOLEAN, description="Whether patient explicitly confirmed reschedule")
                    },
                    required=["user_id", "appointment_id", "new_date", "new_time"]
                )
            ),
            types.FunctionDeclaration(
                name="get_appointment_history",
                description="Retrieve appointment records for the patient, separating active scheduled visits from past history.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)")
                    }
                )
            ),
            types.FunctionDeclaration(
                name="get_patient_documents",
                description="List medical documents belonging to the authenticated patient.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)")
                    }
                )
            ),
            types.FunctionDeclaration(
                name="read_document",
                description="Read extracted contents of an authorized medical document or report.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)"),
                        "document_id": types.Schema(type=types.Type.STRING, description="Document ID")
                    },
                    required=["user_id", "document_id"]
                )
            ),
            types.FunctionDeclaration(
                name="search_hospital_knowledge",
                description="Search hospital general information, policies, visiting hours, emergency guidelines, and FAQs using RAG.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Search query")
                    },
                    required=["query"]
                )
            ),
            types.FunctionDeclaration(
                name="prepare_consultation_summary",
                description="Aggregate authorized patient history and documents into a consultation summary brief.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(type=types.Type.STRING, description="Patient ID (default P1001)")
                    }
                )
            )
        ])
    ]


SYSTEM_INSTRUCTION_VOICE = """
You are ApolloCare Hospital's Real-Time Voice AI Assistant, speaking directly with callers over an active phone call.

ACCURATE REAL HOSPITAL DATA (STRICT ZERO HALLUCINATION):
- Doctors:
  * Dr. Sarah Jenkins (DOC-001): Department: Dermatology, Specialty: General & Cosmetic Dermatology, Fee: $120.00, Available Days: Monday, Wednesday, Friday
  * Dr. B. K. Sharma (DOC-002): Department: Dermatology, Specialty: Pediatric Dermatology & Allergy, Fee: $150.00, Available Days: Monday, Tuesday, Thursday
  * Dr. Alan Vance (DOC-003): Department: Cardiology, Specialty: Interventional Cardiology, Fee: $200.00, Available Days: Tuesday, Thursday, Saturday
  * Dr. Elena Rostova (DOC-004): Department: Orthopedics, Specialty: Joint Replacement & Sports Medicine, Fee: $180.00, Available Days: Monday, Wednesday, Thursday
- Departments & Locations:
  * Dermatology: Building A, 2nd Floor, Wing B
  * Cardiology: Building B, 1st Floor, Heart Center
  * Orthopedics: Building A, Ground Floor
  * Pediatrics: Building C, 3rd Floor
  * Radiology: Building B, Basement Level 1
- Emergency & 24/7 Trauma Center: Gate 1 Main Block, 24/7 Trauma Care, Emergency Hotline 1800-APOLLO-911 (+1-800-276-5569)
- Visiting Hours: Daily 10:00 AM - 1:00 PM and 4:30 PM - 8:00 PM (ICU: 5:00 PM - 6:00 PM)
- Authenticated Caller: Rahul Sharma (Patient ID: P1001)

PROTOCOL FOR UNCLEAR AUDIO OR UNAVAILABLE SERVICES:
1. UNCLEAR / UNINTELLIGIBLE AUDIO: If the caller's speech is silent, muffled, garbled, or you did not understand what they said, politely say:
   "I'm sorry, I couldn't hear you clearly. Could you please repeat yourself?"
2. UNAVAILABLE OR MISHEARD SERVICES: If the caller asks for a doctor, department, or medical service NOT available at ApolloCare (such as Neurology, Oncology, Dental, or a non-existent doctor), clearly state that it is not available and give the correct available options at ApolloCare:
   "We do not have that service at ApolloCare. Our available departments are Dermatology, Cardiology, Orthopedics, Pediatrics, and Radiology."

CORE HOSPITAL CAPABILITIES (ALWAYS USE TOOLS FOR FACTUAL DATA):
- Checking Doctor Slots: Call `get_available_slots` and speak upcoming dates/times warmly and clearly.
- Booking & Managing Appointments: Always confirm Doctor Name, Date, and Time with the caller before calling `book_appointment`, `cancel_appointment`, or `reschedule_appointment` with confirmed=True.
- Patient Lab Reports: Call `read_document` or `get_patient_documents` to explain lab findings (e.g. CBC test, IgE allergy levels).
- Checking Patient History: Call `get_appointment_history` to summarize active upcoming scheduled appointments or past visits.
- Emergency & Policies: Call `search_hospital_knowledge` for hospital guidelines, triage, and FAQs.
- General Health Questions: Explain human diseases, symptoms, causes, and standard medical explanations concisely.

SPEAKING STYLE:
- Speak naturally, warmly, and concisely as a helpful male hospital receptionist (1-2 sentences per spoken turn). Avoid long, overwhelming lists.
"""


class GeminiLiveSession:
    """
    Manages a single real-time Gemini Live WebSocket session connected to an AudioTransport.
    Handles concurrent audio streaming, turn history memory, tool calling, and barge-in / interruption events.
    """

    def __init__(self, session_id: str, transport: BaseAudioTransport, user_id: str = "P1001", voice_name: Optional[str] = None):
        self.session_id = session_id
        self.transport = transport
        self.user_id = user_id
        self.voice_name = voice_name or os.getenv("GEMINI_VOICE_NAME", "Puck")
        self.model_name = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

        self._inbound_task: Optional[asyncio.Task] = None
        self._outbound_task: Optional[asyncio.Task] = None
        self._running = False
        self._session = None
        self.turn_history: List[str] = []

    def _build_system_instruction(self) -> str:
        base = SYSTEM_INSTRUCTION_VOICE
        if self.turn_history:
            recent_turns = "\n".join(self.turn_history[-10:])
            base += f"\n\nCONVERSATION HISTORY SO FAR IN THIS CALL:\n{recent_turns}\n"
        return base

    async def start(self) -> None:
        """Initialize Gemini Live connection and keep the session active for the entire call."""
        if not self.api_key:
            logger.error(f"[GeminiLiveSession {self.session_id}] GEMINI_API_KEY / GOOGLE_API_KEY is missing!")
            await self.transport.send_event("error", {"message": "API key configuration missing."})
            return

        self._running = True
        client = genai.Client(api_key=self.api_key)
        selected_voice = self.voice_name or "Puck"

        logger.info(f"[Voice Session {self.session_id}] Starting live call for user {self.user_id} using Male Voice '{selected_voice}'...")
        await self.transport.send_event("status", {"status": "Connected"})

        # Outer loop: Keep call active as long as caller is connected (until explicit End Call)
        while self._running and not self.transport._is_closed:
            config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=selected_voice)
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=self._build_system_instruction())]
                ),
                tools=build_hospital_tool_declarations()
            )

            logger.info(f"[Voice Session {self.session_id}] Connecting to Gemini Live API ({self.model_name})...")

            try:
                async with client.aio.live.connect(model=self.model_name, config=config) as session:
                    self._session = session
                    logger.info(f"[Voice Session {self.session_id}] Gemini Live stream active.")

                    self._inbound_task = asyncio.create_task(self._process_inbound_audio())
                    self._outbound_task = asyncio.create_task(self._process_outbound_responses())

                    # Wait until one of the streaming tasks completes or session is cancelled
                    done, pending = await asyncio.wait(
                        [self._inbound_task, self._outbound_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()

            except Exception as e:
                logger.error(f"[Voice Session {self.session_id}] Gemini Live stream exception: {e}")
                if self.transport._is_closed:
                    break
                await asyncio.sleep(0.3)

        logger.info(f"[Voice Session {self.session_id}] Call session loop ended.")
        await self.stop()

    async def _process_inbound_audio(self) -> None:
        """Task 1: Browser/Transport Microphone PCM or Text Prompt -> Gemini Live API."""
        logger.info(f"[Voice Session {self.session_id}] Listening for audio input...")
        while self._running and not self.transport._is_closed:
            if not self._session:
                await asyncio.sleep(0.05)
                continue

            item = await self.transport.receive_pcm_chunk()
            if item is None:
                logger.info(f"[Voice Session {self.session_id}] Client transport disconnected.")
                break

            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text", "").strip()
                if txt:
                    logger.info(f"[Voice Session {self.session_id}] Received text turn: '{txt}'")
                    self.turn_history.append(f"User: {txt}")
                    try:
                        await self._session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part.from_text(text=txt)]),
                            turn_complete=True
                        )
                    except Exception as e:
                        logger.error(f"[Voice Session {self.session_id}] Error sending text turn: {e}")
                        break

            elif isinstance(item, bytes) and len(item) > 0:
                try:
                    await self._session.send_realtime_input(
                        audio=types.Blob(data=item, mime_type="audio/pcm;rate=16000")
                    )
                except Exception as e:
                    logger.error(f"[Voice Session {self.session_id}] Error sending audio chunk: {e}")
                    break

    async def _process_outbound_responses(self) -> None:
        """Task 2: Gemini Live API -> Browser/Transport Speaker PCM + Tool Calls."""
        logger.info(f"[Voice Session {self.session_id}] Receiving Gemini Live responses...")

        try:
            async for response in self._session.receive():
                if not self._running or self.transport._is_closed:
                    break

                # 1. Handle Interruption / Barge-in
                server_content = getattr(response, "server_content", None)
                if server_content:
                    if getattr(server_content, "interrupted", False):
                        logger.info(f"[Voice Session {self.session_id}] Interruption detected. Clearing playback.")
                        await self.transport.send_event("interrupted")

                    # Check output transcription text from Gemini Live
                    output_tx = getattr(server_content, "output_transcription", None)
                    has_output_tx = False
                    if output_tx and getattr(output_tx, "text", None):
                        tx_text = output_tx.text
                        has_output_tx = True
                        logger.info(f"[Gemini Spoke]: {tx_text}")
                        self.turn_history.append(f"AI: {tx_text}")
                        await self.transport.send_event("transcript", {
                            "role": "ai",
                            "text": tx_text
                        })

                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn:
                        for part in model_turn.parts:
                            # Stream raw 24kHz PCM audio back to transport/browser
                            if part.inline_data and part.inline_data.data:
                                await self.transport.send_pcm_chunk(part.inline_data.data)

                            # Send text transcript only if output_transcription was not present
                            if not has_output_tx and part.text:
                                logger.info(f"[Gemini Spoke]: {part.text}")
                                self.turn_history.append(f"AI: {part.text}")
                                await self.transport.send_event("transcript", {
                                    "role": "ai",
                                    "text": part.text
                                })

                # 2. Handle Tool Calls
                tool_call = getattr(response, "tool_call", None)
                if tool_call:
                    await self._handle_tool_call(tool_call)

        except Exception as e:
            logger.error(f"[Voice Session {self.session_id}] Outbound stream error: {e}")

    async def _handle_tool_call(self, tool_call: Any) -> None:
        """Execute Python hospital tool and return FunctionResponse to Gemini Live."""
        function_calls = getattr(tool_call, "function_calls", [])
        for fc in function_calls:
            name = getattr(fc, "name", "")
            fc_id = getattr(fc, "id", "")
            raw_args = getattr(fc, "args", {}) or {}

            logger.info(f"[Voice Tool Call] Tool: '{name}' | ID: '{fc_id}' | Raw Args: {raw_args}")
            await self.transport.send_event("status", {"status": f"Calling tool: {name}"})

            executor = TOOL_EXECUTORS.get(name)
            if not executor:
                res_dict = {"status": "error", "message": f"Unknown tool function: {name}"}
            else:
                try:
                    import inspect
                    sig = inspect.signature(executor)

                    # Normalize argument aliases from Gemini Live
                    clean_args = dict(raw_args)
                    if "doctor_name" in clean_args and "doctor_id" not in clean_args:
                        clean_args["doctor_id"] = clean_args.pop("doctor_name")
                    if "doctor" in clean_args and "doctor_id" not in clean_args:
                        clean_args["doctor_id"] = clean_args.pop("doctor")
                    if "time_slot" in clean_args and "time" not in clean_args:
                        clean_args["time"] = clean_args.pop("time_slot")
                    if "slot" in clean_args and "time" not in clean_args:
                        clean_args["time"] = clean_args.pop("slot")
                    if "appt_id" in clean_args and "appointment_id" not in clean_args:
                        clean_args["appointment_id"] = clean_args.pop("appt_id")
                    if "doc_id" in clean_args and "document_id" not in clean_args:
                        clean_args["document_id"] = clean_args.pop("doc_id")
                    if "dept" in clean_args and "department_name" not in clean_args:
                        clean_args["department_name"] = clean_args.pop("dept")

                    # Inject patient user_id if expected by tool signature
                    if "user_id" in sig.parameters and "user_id" not in clean_args:
                        clean_args["user_id"] = self.user_id

                    # Filter only accepted parameters
                    accepted_args = {k: v for k, v in clean_args.items() if k in sig.parameters}

                    # Execute deterministic tool function
                    if asyncio.iscoroutinefunction(executor):
                        res_dict = await executor(**accepted_args)
                    else:
                        res_dict = executor(**accepted_args)

                except Exception as ex:
                    logger.error(f"[Tool Execution Error] {name}: {ex}", exc_info=True)
                    res_dict = {"status": "error", "message": str(ex)}

            logger.info(f"[Tool Result] {name} -> {res_dict}")
            self.turn_history.append(f"[Tool Executed: {name}({raw_args}) -> Result: {res_dict}]")

            # Send FunctionResponse back to Gemini Live
            try:
                await self._session.send_tool_response(
                    function_responses=types.FunctionResponse(
                        name=name,
                        id=fc_id,
                        response=res_dict
                    )
                )
            except Exception as ex:
                logger.error(f"[Send Tool Response Error] {name}: {ex}")

    async def stop(self) -> None:
        """Clean up and close voice session."""
        if self._running:
            self._running = False
            logger.info(f"[Voice Session {self.session_id}] Stopping session.")
            if self._inbound_task and not self._inbound_task.done():
                self._inbound_task.cancel()
            if self._outbound_task and not self._outbound_task.done():
                self._outbound_task.cancel()

            await self.transport.send_event("status", {"status": "Disconnected"})
            await self.transport.close()
