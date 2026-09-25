import asyncio
import logging
import uuid
from typing import Dict, Optional
from app.voice.transport import BaseAudioTransport
from app.voice.gemini_live_session import GeminiLiveSession

logger = logging.getLogger("voice_session_manager")
logger.setLevel(logging.INFO)


class VoiceSessionManager:
    """
    Manages isolated real-time voice sessions for multiple simultaneous callers/browsers.
    Guarantees strict session isolation and resource cleanup on disconnect.
    """

    def __init__(self):
        self._sessions: Dict[str, GeminiLiveSession] = {}

    async def create_session(
        self,
        transport: BaseAudioTransport,
        user_id: str = "P1001",
        session_id: Optional[str] = None,
        voice_name: Optional[str] = None
    ) -> GeminiLiveSession:
        """Create and start a new isolated Gemini Live voice session."""
        sid = session_id or f"voice-session-{uuid.uuid4().hex[:8]}"

        # Close existing session with same ID if any
        if sid in self._sessions:
            await self.close_session(sid)

        logger.info(f"✨ [VoiceSessionManager] Creating session {sid} for user {user_id} (Voice: {voice_name or 'Default Male Puck'})")
        session = GeminiLiveSession(session_id=sid, transport=transport, user_id=user_id, voice_name=voice_name)
        self._sessions[sid] = session
        return session

    async def close_session(self, session_id: str) -> None:
        """Stop and remove an active session."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"🧹 [VoiceSessionManager] Cleaning up session {session_id}")
            await session.stop()

    def get_session(self, session_id: str) -> Optional[GeminiLiveSession]:
        return self._sessions.get(session_id)

    def active_sessions_count(self) -> int:
        return len(self._sessions)


# Global Singleton Manager Instance
voice_session_manager = VoiceSessionManager()
