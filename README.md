# 🏥 Smart Hospital AI Assistant (Text & Real-Time Gemini Live Voice)

A conversational healthcare operations assistant built with **Google ADK**, **Google Gemini Live API (Native Audio)**, **FastAPI**, **Pydantic v2**, and **FAISS RAG**.

> **Note:** Voice communication uses Google's Gemini Live API with native audio input/output over WebSockets. **No external Speech-to-Text (STT) or Text-to-Speech (TTS) service is used.**

---

## 🎙️ Real-Time Gemini Live Voice Agent Architecture

The application provides a low-latency, real-time voice-to-voice conversation pipeline:

```text
 Browser Microphone (16kHz PCM Float32 → Int16)
        ↓
 WebSocket (/ws/voice)
        ↓
 FastAPI Backend (Voice Gateway & Transport Abstraction)
        ↓
 Gemini Live API (gemini-3.1-flash-live-preview)
   • Native Audio Understanding
   • Spoken Reasoning
   • Function/Tool Calling & RAG Integration
        ↓
 FastAPI Backend (24kHz Raw PCM Streaming)
        ↓
 WebSocket (/ws/voice)
        ↓
 Browser Speaker (Web Audio API PCM Playback)
```

### Key Voice Features:
1. **Native Voice-to-Voice:** Direct audio stream into Gemini Live without intermediate STT or TTS layers.
2. **Tool Calling & RAG:** Gemini Live directly executes hospital Python tools (`search_doctors`, `get_available_slots`, `book_appointment`, `search_hospital_knowledge`, etc.) during voice calls and speaks the output naturally.
3. **Barge-In / Interruption:** When the caller interrupts Gemini while speaking, the Web Audio queue is instantly cleared, playback stops, and the new user audio is processed.
4. **Transport Abstraction:** Clean `BaseAudioTransport` layer separating the voice engine from the client. Supports `BrowserAudioTransport` today and `SmartfloAudioTransport` for future telephony integration.
5. **Coexistence:** Text Mode (ADK Root Agent) and Voice Mode (Gemini Live Engine) operate side-by-side without breaking existing text endpoints.

---

## 🌟 Key Capabilities

1. **Real-Time Voice Call Agent (`/static/call.html`)**:
   - Web Audio API microphone capture (16kHz PCM mono).
   - Real-time 24kHz PCM audio playback streaming.
   - Interactive status badges (Listening, Thinking, AI Speaking, Interrupted).

2. **Hospital Operations & Catalog**:
   - Department and doctor directory search with fuzzy/root word matching.
   - Real-time slot availability checking.
   - Booking, cancellation, and rescheduling workflows with confirmation guardrails.

3. **Hospital Knowledge Base & FAISS RAG**:
   - Hybrid vector search (SQLite + FAISS) for hospital policies, visiting hours, check-in instructions, and emergency guidelines.

4. **Multi-Agent Architecture with Google ADK**:
   - **`hospital_root_agent`**: Primary text coordinator.
   - **`appointment_agent`**: Doctor search, slots, and booking.
   - **`document_agent`**: Report extraction and plain-English translation.
   - **`info_agent`**: Hospital FAQs and policies.
   - **`history_agent`**: Strictly authorized patient history.

---

## 🚀 Quick Start

### 1. Configure Environment (`.env`)
```ini
GOOGLE_API_KEY=your_google_api_key_here
GEMINI_API_KEY=your_google_api_key_here
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
```

### 2. Run the Server
```bash
python run.py serve
```
- Web UI: 👉 **`http://127.0.0.1:8500/`**
- Real-Time Voice Agent UI: 👉 **`http://127.0.0.1:8500/static/call.html`**
- Interactive API Docs: 👉 **`http://127.0.0.1:8500/docs`**

### 3. Open Voice Agent & Grant Mic Permissions
1. Navigate to `http://127.0.0.1:8500/static/call.html`.
2. Click **"Start Real-Time Voice Call"**.
3. Allow browser microphone access when prompted.
4. Speak naturally (e.g. *"What are the hospital visiting hours?"* or *"Find me a cardiologist doctor"*).

### 4. Run Automated End-to-End Tests
```bash
python scratch/test_voice_e2e.py
python scratch/test_voice_tools_booking.py
```

---

## 📂 Project Structure

```text
smart-hospital/
├── app/
│   ├── config.py             # Configuration & environment settings
│   ├── database.py           # SQLite database & FAISS RAG search
│   ├── main.py               # FastAPI factory, lifespan, and static mounting
│   ├── voice/                # Real-time voice engine package
│   │   ├── transport.py      # AudioTransport abstraction (Browser & Smartflo)
│   │   ├── gemini_live_session.py # Gemini Live API session manager & tool calling
│   │   └── session_manager.py     # Multi-session isolation manager
│   ├── api/                  # REST API & WebSocket routers
│   │   ├── voice_call.py     # /ws/voice & /ws/smartflo WebSockets
│   │   ├── chat.py           # Text Chat endpoint (Google ADK)
│   │   └── hospital.py       # Hospital REST endpoints
│   └── agents/               # Google ADK multi-agent tools & prompts
├── static/
│   ├── call.html             # Real-Time Voice Agent browser UI & Web Audio PCM client
│   └── index.html            # Main Patient Portal UI
├── scratch/
│   ├── test_voice_e2e.py     # End-to-end voice & text test suite
│   └── test_voice_tools_booking.py # Voice tool calling test suite
└── run.py                    # Server & CLI runner
```

---

## 📱 Future Smartflo Integration

Smartflo telephony can be connected to the voice gateway by using `SmartfloAudioTransport` mounted at `/ws/smartflo`. The core `GeminiLiveSession`, hospital tools, database, and RAG layers require **zero changes** when attaching Smartflo or any other telephony provider.

├── requirements.txt
└── .env
```
