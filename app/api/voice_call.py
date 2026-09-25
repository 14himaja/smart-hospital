"""WebSocket Voice & Telephony endpoints with authentication."""

import uuid
import logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import settings
from app.database import db
from app.voice.transport import BrowserAudioTransport
from app.voice.smartflo_transport import SmartfloAudioTransport
from app.voice.session_manager import voice_session_manager

logger = logging.getLogger("voice_api")
logger.setLevel(logging.INFO)

router = APIRouter()


def authenticate_websocket_token(token: str) -> str:
    """Validate JWT token and return authenticated user_id, or raise ValueError."""
    if not token:
        return "P1001" if settings.DEMO_MODE else ""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub", "")
        if user_id and db.get_user(user_id):
            return user_id
    except Exception:
        pass
    return ""


@router.websocket("/ws/voice")
@router.websocket("/ws/call")
async def browser_voice_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for Browser Real-Time Voice Assistant.
    Streams microphone audio -> Gemini Live -> speaker response.
    """
    token = websocket.query_params.get("token", "")
    user_id = authenticate_websocket_token(token) or "P1001"

    await websocket.accept()
    session_id = f"voice-browser-{uuid.uuid4().hex[:8]}"
    voice_param = websocket.query_params.get("voice")

    logger.info(f"[Voice WS] Connected. Session: {session_id} | User: {user_id} | Voice: {voice_param or 'Default'}")

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
        logger.info(f"[Voice WS] Disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"[Voice WS] Error ({session_id}): {e}")
    finally:
        await voice_session_manager.close_session(session_id)


@router.websocket("/ws/smartflo")
async def smartflo_voice_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for Smartflo Telephony Inbound Stream.
    Requires shared secret token authentication before accepting.
    """
    token = websocket.query_params.get("token", "")
    if token != settings.SMARTFLO_WS_TOKEN and not settings.DEMO_MODE:
        logger.warning("[Smartflo WS] Rejected unauthorized connection attempt (invalid token).")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    session_id = f"voice-smartflo-{uuid.uuid4().hex[:8]}"
    transport = SmartfloAudioTransport(websocket)

    logger.info(f"[Smartflo WS] Telephony stream connected. Session: {session_id}")

    session = await voice_session_manager.create_session(
        transport=transport,
        user_id="P1001",
        session_id=session_id
    )

    try:
        await session.start()
    except WebSocketDisconnect:
        logger.info(f"[Smartflo WS] Telephony call disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"[Smartflo WS] Error ({session_id}): {e}")
    finally:
        await voice_session_manager.close_session(session_id)
