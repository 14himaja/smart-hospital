"""Smart Hospital AI Assistant - CLI Runner.

Usage:
    python run.py serve               # Launch the FastAPI REST and Chat Server
    python run.py chat [--user P1001] # Interactive terminal chat with Google ADK
    python run.py test                # Run test suite
"""

import sys
import argparse
import asyncio
import uvicorn
from google.genai import types

from app.config import settings
from app.database import db
from app.agents.root_agent import runner


def run_server():
    """Start the FastAPI server."""
    print(f"Starting {settings.APP_NAME} on http://{settings.HOST}:{settings.PORT}")
    print(f"Interactive API documentation available at http://{settings.HOST}:{settings.PORT}/docs")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        reload_dirs=["app"] if settings.RELOAD else None
    )



async def terminal_chat(user_id: str):
    """Run an interactive conversation loop in the terminal."""
    user = db.get_user(user_id)
    if not user:
        print(f"Error: User ID '{user_id}' not found in hospital database.")
        print("Available test users: P1001 (Rahul), P1002 (Priya), D2001 (Doctor), S3001 (Staff)")
        return

    session_id = f"CLI-{user.user_id}"
    print("=" * 70)
    print(f"🏥 {settings.APP_NAME}")
    print(f"👤 Authenticated as: {user.name} ({user.user_id}) | Role: {user.role.value.upper()}")
    print(f"🤖 Powered by: Google ADK + Groq ({settings.MODEL_NAME})")
    print("Type 'exit' or 'quit' to end the session.")
    print("=" * 70)

    # Initialize ADK session state with authenticated identity context
    session = await runner.session_service.get_session(
        app_name="smart_hospital",
        user_id=user.user_id,
        session_id=session_id
    )
    initial_state = {
        "user_id": user.user_id,
        "user_name": user.name,
        "user_role": user.role.value
    }
    if not session:
        session = await runner.session_service.create_session(
            app_name="smart_hospital",
            user_id=user.user_id,
            session_id=session_id,
            state=initial_state
        )
    else:
        session.state.update(initial_state)

    while True:
        try:
            prompt = input(f"\n{user.name} > ").strip()
            if not prompt:
                continue
            if prompt.lower() in ["exit", "quit", "q"]:
                print("Ending session. Goodbye!")
                break

            print("\nAssistant > ", end="", flush=True)

            content = types.Content(
                parts=[types.Part.from_text(text=prompt)]
            )

            replies = []
            async for event in runner.run_async(
                user_id=user.user_id,
                session_id=session_id,
                new_message=content
            ):
                if hasattr(event, "content") and event.content:
                    for part in getattr(event.content, "parts", []):
                        if hasattr(part, "text") and part.text:
                            replies.append(part.text)

            raw_reply = "".join(replies).strip()
            if not raw_reply:
                msg_lower = prompt.lower().strip()
                if any(g in msg_lower for g in ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings")):
                    full_reply = "Hello! Welcome to ApolloCare. How can I assist you with your appointments, doctors, or medical documents today?"
                else:
                    full_reply = "I am here to assist you with your appointments, medical records, and hospital information. How can I help you today?"
            else:
                full_reply = raw_reply
            print(full_reply)

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")


def run_tests():
    """Run pytest suite."""
    import pytest
    sys.exit(pytest.main(["tests", "-v"]))


def main():
    parser = argparse.ArgumentParser(description="Smart Hospital AI Assistant")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Serve command
    subparsers.add_parser("serve", help="Start the FastAPI backend server")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start terminal chat with ADK assistant")
    chat_parser.add_argument("--user", default="P1001", help="Patient/User ID (default: P1001)")

    # Test command
    subparsers.add_parser("test", help="Run automated tests")

    args = parser.parse_args()

    if args.command == "serve":
        run_server()
    elif args.command == "chat":
        asyncio.run(terminal_chat(user_id=args.user))
    elif args.command == "test":
        run_tests()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
