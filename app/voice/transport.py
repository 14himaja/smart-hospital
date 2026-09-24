import abc
import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger("voice_transport")
logger.setLevel(logging.INFO)


class BaseAudioTransport(abc.ABC):
    """
    Abstract Audio Transport interface.
    Decouples audio source (Browser WebSocket, Smartflo Telephony, etc.)
    from the core Gemini Live processing engine.
    """

    @abc.abstractmethod
    async def receive_pcm_chunk(self) -> Optional[bytes]:
        """Receive a raw 16-bit PCM audio chunk from the client (16kHz mono)."""
        pass

    @abc.abstractmethod
    async def send_pcm_chunk(self, pcm_data: bytes) -> None:
        """Send a raw 16-bit PCM response audio chunk to the client (24kHz mono)."""
        pass

    @abc.abstractmethod
    async def send_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Send a control/status event message to the client."""
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the client transport connection."""
        pass


class BrowserAudioTransport(BaseAudioTransport):
    """
    Audio Transport implementation for Browser WebSockets.
    Supports raw PCM binary frames and JSON event payloads (base64 audio).
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self._is_closed = False
        self._send_lock = asyncio.Lock()

    async def receive_pcm_chunk(self) -> Optional[Any]:
        """
        Reads from WebSocket. Handles binary PCM frames, base64 JSON audio, or text prompt events.
        Returns:
            - bytes: Raw 16kHz Int16 PCM audio chunk
            - dict: Event dict (e.g. {"type": "text", "text": "..."})
            - None: On explicit user disconnect or socket close
        """
        if self._is_closed:
            return None

        try:
            message = await self.websocket.receive()
            msg_type = message.get("type")
            if msg_type in ("websocket.disconnect", "websocket.close"):
                logger.info("[BrowserAudioTransport] WebSocket disconnected by client.")
                self._is_closed = True
                return None

            # Handle binary PCM frame directly
            if "bytes" in message and message["bytes"]:
                return message["bytes"]

            # Handle JSON text message
            if "text" in message and message["text"]:
                data = json.loads(message["text"])
                event_type = data.get("event")

                if event_type == "audio":
                    payload = data.get("data") or data.get("audio") or data.get("payload")
                    if payload:
                        return base64.b64decode(payload)

                elif event_type == "text":
                    txt = data.get("text") or data.get("prompt")
                    if txt:
                        return {"type": "text", "text": txt}

                elif event_type == "media":
                    payload = data.get("media", {}).get("payload") or data.get("payload")
                    transcript = data.get("transcript")
                    if transcript:
                        return {"type": "text", "text": transcript}
                    if payload:
                        try:
                            return base64.b64decode(payload)
                        except Exception:
                            pass

                elif event_type == "stop":
                    logger.info("[BrowserAudioTransport] Received explicit stop/end call event from user.")
                    self._is_closed = True
                    return None

            return b""
        except Exception as e:
            logger.debug(f"[BrowserAudioTransport] Read error or timeout: {e}")
            # Check if underlying socket is actually closed before marking transport closed
            if getattr(self.websocket, "client_state", None) and self.websocket.client_state.name == "DISCONNECTED":
                self._is_closed = True
                return None
            return b""

    async def send_pcm_chunk(self, pcm_data: bytes) -> None:
        """Send 24kHz 16-bit PCM chunk encoded as base64 in a JSON event."""
        if self._is_closed or not pcm_data:
            return

        async with self._send_lock:
            try:
                b64_audio = base64.b64encode(pcm_data).decode("utf-8")
                await self.websocket.send_json({
                    "event": "audio",
                    "data": b64_audio,
                    "mime": "audio/pcm;rate=24000"
                })
            except Exception as e:
                logger.warning(f"[BrowserAudioTransport] Send audio chunk warning: {e}")

    async def send_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Send control/status event message to browser client."""
        if self._is_closed:
            return

        msg = {"event": event_type}
        if payload:
            msg.update(payload)

        async with self._send_lock:
            try:
                await self.websocket.send_json(msg)
            except Exception as e:
                logger.warning(f"[BrowserAudioTransport] Send event warning ({event_type}): {e}")

    async def close(self) -> None:
        """Close WebSocket connection."""
        if not self._is_closed:
            self._is_closed = True
            try:
                await self.websocket.close()
            except Exception:
                pass


class SmartfloAudioTransport(BaseAudioTransport):
    """
    Audio Transport implementation for Smartflo Telephony Inbound WebSocket.
    Adapts Smartflo event payloads ('start', 'media', 'stop') to Gemini Live audio.
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self._is_closed = False
        self.stream_sid: str = "smartflo-stream-001"

    async def receive_pcm_chunk(self) -> Optional[bytes]:
        if self._is_closed:
            return None

        try:
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                self._is_closed = True
                return None

            if "text" in message and message["text"]:
                data = json.loads(message["text"])
                event = data.get("event")

                if event == "start":
                    self.stream_sid = data.get("streamSid") or data.get("start", {}).get("callId", self.stream_sid)
                    return b""

                elif event == "media":
                    media_info = data.get("media", {})
                    payload = media_info.get("payload") or data.get("payload")
                    if payload:
                        return base64.b64decode(payload)

                elif event == "stop":
                    self._is_closed = True
                    return None

            return b""
        except Exception as e:
            logger.debug(f"[SmartfloAudioTransport] Read error or disconnect: {e}")
            self._is_closed = True
            return None

    async def send_pcm_chunk(self, pcm_data: bytes) -> None:
        if self._is_closed or not pcm_data:
            return

        try:
            b64_audio = base64.b64encode(pcm_data).decode("utf-8")
            await self.websocket.send_json({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": b64_audio}
            })
        except Exception as e:
            logger.error(f"[SmartfloAudioTransport] Error sending audio chunk: {e}")
            self._is_closed = True

    async def send_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self._is_closed:
            return

        msg = {"event": event_type, "streamSid": self.stream_sid}
        if payload:
            msg.update(payload)

        try:
            await self.websocket.send_json(msg)
        except Exception as e:
            logger.error(f"[SmartfloAudioTransport] Error sending event {event_type}: {e}")
            self._is_closed = True

    async def close(self) -> None:
        if not self._is_closed:
            self._is_closed = True
            try:
                await self.websocket.close()
            except Exception:
                pass
