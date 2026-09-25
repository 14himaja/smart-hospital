"""
Dedicated Smartflo Inbound Telephony Audio Transport.
Implements numpy-based μ-law 8kHz <-> PCM 16kHz conversion, 160-byte outbound RTP framing,
barge-in clearing, and caller phone identification without relying on deprecated audioop.
"""

import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional
import numpy as np
from fastapi import WebSocket

from app.database import db
from app.voice.transport import BaseAudioTransport

logger = logging.getLogger("smartflo_transport")
logger.setLevel(logging.INFO)


def mulaw_to_pcm16(data: bytes) -> np.ndarray:
    """Convert 8-bit G.711 mu-law byte string to 16-bit linear PCM array."""
    if not data:
        return np.array([], dtype=np.int16)
    u = ~np.frombuffer(data, dtype=np.uint8)
    t = ((u & 0x0F).astype(np.int32) << 3) + 0x84
    t <<= (u & 0x70).astype(np.int32) >> 4
    return np.where(u & 0x80, 0x84 - t, t - 0x84).astype(np.int16)


def pcm16_to_mulaw(pcm: np.ndarray) -> bytes:
    """Convert 16-bit linear PCM array to 8-bit G.711 mu-law bytes."""
    if len(pcm) == 0:
        return b""
    x = pcm.astype(np.int32)
    sign = np.where(x < 0, 0x80, 0)
    x = np.minimum(np.abs(x), 32635) + 0x84
    exp = np.floor(np.log2(x)).astype(np.int32) - 7
    mant = (x >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mant) & 0xFF).astype(np.uint8).tobytes()


def resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear interpolation resampling for telephone-band speech."""
    if len(pcm) == 0:
        return np.array([], dtype=np.int16)
    n = int(len(pcm) * dst_rate / src_rate)
    return np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.int16)


class SmartfloAudioTransport(BaseAudioTransport):
    """
    Audio Transport for Tata Tele / Smartflo Telephony Inbound WebSocket.
    - Inbound: 8kHz μ-law -> resampled to 16kHz Linear PCM for Gemini Live.
    - Outbound: 24kHz Linear PCM -> resampled to 8kHz μ-law in 160-byte (20ms) frames.
    - Barge-in: Sends 'clear' event to flush buffered audio on Smartflo media server.
    """

    FRAME_BYTES = 160  # 20 ms of 8 kHz mu-law; Smartflo requires multiples of 160

    def __init__(self, websocket: Optional[WebSocket] = None):
        self.websocket = websocket
        self._is_closed = False
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.caller_phone: Optional[str] = None
        self.caller_user_id: Optional[str] = None
        self.custom_parameters: dict = {}
        self._send_lock = asyncio.Lock()
        self._out = bytearray()

    def _ulaw_to_pcm16(self, ulaw_data: bytes) -> bytes:
        """Helper for converting μ-law 8kHz bytes to 16kHz PCM bytes."""
        pcm8k = mulaw_to_pcm16(ulaw_data)
        pcm16k = resample(pcm8k, 8000, 16000)
        return pcm16k.tobytes()

    def _pcm24_to_ulaw(self, pcm24_data: bytes) -> bytes:
        """Helper for converting 24kHz PCM bytes to 8kHz μ-law bytes."""
        pcm24 = np.frombuffer(pcm24_data, dtype=np.int16)
        pcm8k = resample(pcm24, 24000, 8000)
        return pcm16_to_mulaw(pcm8k)

    async def receive_pcm_chunk(self) -> Optional[Any]:
        """
        Receive message from Smartflo WebSocket.
        Parses 'start', 'media', and 'stop' events.
        """
        if self._is_closed:
            return None

        try:
            message = await self.websocket.receive()
            if message.get("type") in ("websocket.disconnect", "websocket.close"):
                self._is_closed = True
                return None

            data = json.loads(message.get("text") or "{}")
            event = data.get("event")

            if event == "start":
                start = data.get("start", {})
                self.stream_sid = data.get("streamSid") or start.get("streamSid")
                self.call_sid = start.get("callSid")
                self.caller_phone = start.get("from")
                self.custom_parameters = start.get("customParameters") or {}

                media_format = start.get("mediaFormat", {})
                if media_format.get("encoding") and media_format.get("encoding") != "audio/x-mulaw":
                    logger.warning(f"[Smartflo] Unexpected audio format: {media_format}")

                logger.info(f"[Smartflo] Call started: callSid={self.call_sid}, from={self.caller_phone}")

                if self.caller_phone:
                    user = db.get_user_by_phone(self.caller_phone)
                    if user:
                        self.caller_user_id = user.user_id
                        logger.info(f"[Smartflo] Identified caller: {user.name} ({user.user_id})")

                return b""

            elif event == "media":
                media_payload = data.get("media", {}).get("payload") or data.get("payload")
                if media_payload:
                    ulaw = base64.b64decode(media_payload)
                    return self._ulaw_to_pcm16(ulaw)

            elif event == "stop":
                logger.info(f"[Smartflo] Call ended (stop event): {self.call_sid}")
                self._is_closed = True
                return None

            return b""
        except Exception as e:
            logger.debug(f"[Smartflo] Receive error or disconnect: {e}")
            self._is_closed = True
            return None

    async def send_pcm_chunk(self, pcm_data: bytes) -> None:
        """
        Convert 24kHz PCM from Gemini Live to 8kHz μ-law and send in 160-byte frames.
        """
        if self._is_closed or not pcm_data or not self.stream_sid:
            return

        ulaw_chunk = self._pcm24_to_ulaw(pcm_data)
        if not ulaw_chunk:
            return

        self._out += ulaw_chunk
        n = len(self._out) - len(self._out) % self.FRAME_BYTES
        if n and self.stream_sid:
            chunk, self._out = bytes(self._out[:n]), self._out[n:]
            async with self._send_lock:
                try:
                    await self.websocket.send_json({
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {"payload": base64.b64encode(chunk).decode("utf-8")}
                    })
                except Exception as e:
                    logger.warning(f"[Smartflo] Frame send warning: {e}")

    async def send_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Send event message to Smartflo (handles barge-in clear event)."""
        if self._is_closed or not self.stream_sid:
            return

        if event_type == "interrupted":
            # Barge-in: clear Smartflo playback buffer
            self._out.clear()
            async with self._send_lock:
                try:
                    await self.websocket.send_json({
                        "event": "clear",
                        "streamSid": self.stream_sid
                    })
                except Exception as e:
                    logger.warning(f"[Smartflo] Clear event error: {e}")
        # "status", "transcript", "error" are browser-only events; do not forward to Smartflo

    async def handle_barge_in(self) -> None:
        """Interrupt playback and clear Smartflo media buffer."""
        await self.send_event("interrupted")

    async def close(self) -> None:
        """Close Smartflo WebSocket connection."""
        if not self._is_closed:
            self._is_closed = True
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception:
                    pass

