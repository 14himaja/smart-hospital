import uuid
from google.genai import types
from app.agents.root_agent import runner
from app.api.chat import clean_user_facing_reply
from app.database import db

async def process_voice_message(user_text: str, session_id: str = "voice-session-demo") -> str:
    """
    Processes a patient's voice transcript through the Google ADK Root Agent.
    Invokes hospital database tools (Doctor Search, Slots, Booking, History) and returns a clean, speakable text response.
    """
    # Use default active patient ID P1001 (Rahul Sharma) for database tool access
    user_id = "P1001"
    
    # Retrieve or create session
    session = await runner.session_service.get_session(
        app_name="smart_hospital",
        user_id=user_id,
        session_id=session_id
    )

    initial_state = {
        "user_id": user_id,
        "user_name": "Rahul Sharma",
        "user_role": "patient"
    }

    if not session:
        session = await runner.session_service.create_session(
            app_name="smart_hospital",
            user_id=user_id,
            session_id=session_id,
            state=initial_state
        )
    else:
        session.state.update(initial_state)

    # Format message for Google ADK
    content = types.Content(
        parts=[types.Part.from_text(text=user_text)]
    )

    replies = []
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        ):
            if hasattr(event, "content") and event.content:
                for part in getattr(event.content, "parts", []):
                    if hasattr(part, "text") and part.text:
                        replies.append(part.text)
    except Exception as e:
        print(f"❌ [Voice Bridge ADK Error]: {e}")
        return "I experienced an issue processing your request. Please try asking again."

    raw_reply = "".join(replies).strip()
    cleaned_reply = clean_user_facing_reply(raw_reply)

    if not cleaned_reply:
        return "I am here to assist you with ApolloCare hospital appointments, doctors, and medical guidelines. How can I help you?"

    # Strip markdown formatting (*, #, `, _) so Text-to-Speech reads clean sentences
    speakable_reply = (
        cleaned_reply
        .replace("**", "")
        .replace("###", "")
        .replace("##", "")
        .replace("#", "")
        .replace("`", "")
        .replace("*", "")
    )
    return speakable_reply
