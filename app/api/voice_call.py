import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.voice.transport import BrowserAudioTransport, SmartfloAudioTransport
from app.voice.session_manager import voice_session_manager

logger = logging.getLogger("voice_api")
logger.setLevel(logging.INFO)

router = APIRouter()


@router.websocket("/ws/voice")
@router.websocket("/ws/call")
async def browser_voice_websocket(websocket: WebSocket):
    """
    FastAPI WebSocket endpoint for Browser Real-Time Voice Agent.
    Streams native microphone audio -> Gemini Live API -> native audio speaker response.
    """
    await websocket.accept()
    session_id = f"voice-browser-{uuid.uuid4().hex[:8]}"
    user_id = "P1001"  # Default active patient (Rahul Sharma)

    # Extract voice preference from query string if present (e.g. ?voice=Puck)
    voice_param = websocket.query_params.get("voice")

    logger.info(f"[Voice WS] Browser WebSocket connected. Session: {session_id} | Voice: {voice_param or 'Default Male Puck'}")

    transport = BrowserAudioTransport(websocket)
    session = await voice_session_manager.create_session(
        transport=transport,
        user_id=user_id,
        session_id=session_id,
        voice_name=voice_param
    )

    try:
        await session.start()
    except WebSocketDisconnect:
        logger.info(f"[Voice WS] Client disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"[Voice WS] Error in browser voice endpoint ({session_id}): {e}")
    finally:
        await voice_session_manager.close_session(session_id)


@router.websocket("/ws/smartflo")
async def smartflo_voice_websocket(websocket: WebSocket):
    """
    FastAPI WebSocket endpoint for Smartflo Telephony Inbound Stream compatibility.
    Adapts Smartflo phone audio transport to Gemini Live API engine.
    """
    await websocket.accept()
    session_id = f"voice-smartflo-{uuid.uuid4().hex[:8]}"
    user_id = "P1001"

    logger.info(f"[Smartflo WS] Telephony WebSocket connected. Session: {session_id}")

    transport = SmartfloAudioTransport(websocket)
    session = await voice_session_manager.create_session(
        transport=transport,
        user_id=user_id,
        session_id=session_id
    )

    try:
        await session.start()
    except WebSocketDisconnect:
        logger.info(f"[Smartflo WS] Call disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"[Smartflo WS] Error in Smartflo endpoint ({session_id}): {e}")
    finally:
        await voice_session_manager.close_session(session_id)
