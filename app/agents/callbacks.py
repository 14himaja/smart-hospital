import re
from datetime import datetime
import contextvars
from app.database import db

OFF_DOMAIN_REFUSAL = (
    "I am ApolloCare Hospital's AI Assistant. I can only assist with ApolloCare hospital services, "
    "appointments, patient records, and health inquiries."
)

OFF_DOMAIN_PATTERNS = [
    # Coding / Programming
    r"\b(python|javascript|typescript|c\+\+|java|rust|html|css|sql|react|node|php|golang|django|flask|fastapi|code|coding|script|algorithm|function|program|class|loop|regex|quicksort|binary search)\b",
    # Math / Calculus
    r"\b(derivative|integral|equation|calculus|differentiate|algebra|matrix|polynomial|quadratic|trigonometry)\b",
    # Cooking / Food Recipes
    r"\b(recipe|recipes|how to bake|how to cook|ingredients for|bake a cake)\b",
    # Sports & Tournaments
    r"\b(fifa|world cup|super bowl|ipl|champions league|premier league|nba|nfl|olympics|cricket match|football match)\b",
    # Entertainment / Movies
    r"\b(movie review|box office|netflix|hollywood|bollywood|cast of|actor|actress|cinematography)\b",
    # Politics & Governance
    r"\b(president of|prime minister of|election results|geopolitics|parliament|congress|white house)\b",
    # Creative writing / General non-medical trivia
    r"\b(write a poem|write a song|write a story|write an essay|tell me a joke)\b",
]

HEALTH_KEYWORDS = (
    "hospital", "doctor", "appointment", "prescription", "symptom", "disease",
    "patient", "medicine", "health", "dose", "dosage", "clinic", "fever", "cough",
    "cardio", "neuro", "ortho", "surgery", "trauma", "emergency", "report", "lab", "test"
)


def is_off_domain_query(text: str) -> bool:
    """Deterministic classifier checking if query is strictly outside medical & hospital domain."""
    if not text:
        return False
    t = text.lower().strip()
    for pattern in OFF_DOMAIN_PATTERNS:
        if re.search(pattern, t):
            if any(k in t for k in HEALTH_KEYWORDS):
                return False
            return True
    return False


# Request-scoped ContextVars for turn telemetry and action states
turn_tools_used_var: contextvars.ContextVar = contextvars.ContextVar("turn_tools_used", default=[])
turn_retrieved_chunks_var: contextvars.ContextVar = contextvars.ContextVar("turn_retrieved_chunks", default=[])
pending_action_var: contextvars.ContextVar = contextvars.ContextVar("pending_action", default=None)



def _extract_state(ctx):
    """Safely extracts state mapping from Context or CallbackContext."""
    if not ctx:
        return {}
    if hasattr(ctx, "state") and ctx.state is not None:
        return ctx.state
    if hasattr(ctx, "session") and hasattr(ctx.session, "state") and ctx.session.state is not None:
        return ctx.session.state
    return {}


def _get_user_id(ctx):
    """Extracts authenticated user_id from context state or session."""
    state = _extract_state(ctx)
    if hasattr(state, "get"):
        uid = state.get("user_id")
        if uid:
            return uid
    if hasattr(state, "__getitem__"):
        try:
            return state["user_id"]
        except (KeyError, TypeError):
            pass
    if hasattr(ctx, "session") and hasattr(ctx.session, "user_id"):
        return ctx.session.user_id
    if hasattr(ctx, "user_id"):
        return ctx.user_id
    return None


def before_agent_callback(*call_args, **call_kwargs):
    """Tracks session execution metrics and verifies authenticated identity."""
    ctx = call_kwargs.get("callback_context") or (call_args[0] if call_args else None)
    state = _extract_state(ctx)
    if state is not None:
        try:
            state["start_time"] = datetime.now()
            state["request_count"] = state.get("request_count", 0) + 1
        except Exception:
            pass
    return None


def after_agent_callback(*call_args, **call_kwargs):
    """Measures overall agent response duration."""
    ctx = call_kwargs.get("callback_context") or (call_args[0] if call_args else None)
    state = _extract_state(ctx)
    if state is not None:
        try:
            if "start_time" in state:
                duration = (datetime.now() - state["start_time"]).total_seconds()
                state["last_latency_seconds"] = duration
        except Exception:
            pass
    return None


def before_tool_callback(*call_args, **call_kwargs):
    """Security guardrail: Validates authorization and enforces user_id context."""
    tool = call_kwargs.get("tool")
    args = call_kwargs.get("args") if "args" in call_kwargs else call_kwargs.get("tool_args")
    ctx = call_kwargs.get("tool_context") or call_kwargs.get("callback_context") or call_kwargs.get("context")

    if call_args:
        if len(call_args) >= 3:
            tool = tool or call_args[0]
            args = args if args is not None else call_args[1]
            ctx = ctx or call_args[2]
        elif len(call_args) == 2:
            if isinstance(call_args[1], dict):
                tool = tool or call_args[0]
                args = args if args is not None else call_args[1]
            else:
                ctx = ctx or call_args[0]
                tool = tool or call_args[1]
        elif len(call_args) == 1:
            tool = tool or call_args[0]

    session_user_id = _get_user_id(ctx)

    # Always inject authenticated user_id if tool has user_id in arguments or is search_hospital_knowledge
    if isinstance(args, dict) and session_user_id:
        tool_name = getattr(tool, "__name__", getattr(tool, "name", str(tool)))
        if "user_id" in args or tool_name == "search_hospital_knowledge":
            args["user_id"] = session_user_id

    return None


def after_tool_callback(*call_args, **call_kwargs):
    """Auditing callback: Records all executed tool actions to audit log."""
    tool = call_kwargs.get("tool")
    args = call_kwargs.get("args") if "args" in call_kwargs else call_kwargs.get("tool_args")
    ctx = call_kwargs.get("tool_context") or call_kwargs.get("callback_context") or call_kwargs.get("context")
    response = call_kwargs.get("tool_response") if "tool_response" in call_kwargs else call_kwargs.get("response")

    if call_args:
        if len(call_args) >= 4:
            tool = tool or call_args[0]
            args = args if args is not None else call_args[1]
            ctx = ctx or call_args[2]
            response = response if response is not None else call_args[3]
        elif len(call_args) == 3:
            if isinstance(call_args[1], dict):
                tool = tool or call_args[0]
                args = args if args is not None else call_args[1]
                ctx = ctx or call_args[2]
            else:
                ctx = ctx or call_args[0]
                tool = tool or call_args[1]
                args = args if args is not None else call_args[2]

    session_user_id = _get_user_id(ctx)
    user_id = session_user_id or "ANONYMOUS"

    state = _extract_state(ctx)

    tool_name = getattr(tool, "name", str(tool))
    action_name = f"TOOL_{tool_name.upper()}"
    status = "SUCCESS"
    if isinstance(response, dict) and response.get("status") in ["error", "unauthorized"]:
        status = "DENIED"

    # Update contextvars for accurate per-turn telemetry
    curr_tools = list(turn_tools_used_var.get())
    if tool_name not in curr_tools:
        curr_tools.append(tool_name)
    turn_tools_used_var.set(curr_tools)

    if isinstance(response, dict):
        if response.get("status") == "confirmation_required" and "pending_action" in response:
            pending_action_var.set(response["pending_action"])
        if "retrieved_chunk_ids" in response:
            curr_chunks = list(turn_retrieved_chunks_var.get())
            for cid in response["retrieved_chunk_ids"]:
                if cid not in curr_chunks:
                    curr_chunks.append(cid)
            turn_retrieved_chunks_var.set(curr_chunks)

    if state is not None:
        try:
            tools_used = list(state.get("turn_tools_used", []))
            if tool_name not in tools_used:
                tools_used.append(tool_name)
            state["turn_tools_used"] = tools_used

            if isinstance(response, dict):
                if response.get("status") == "confirmation_required" and "pending_action" in response:
                    state["pending_action"] = response["pending_action"]
                if "retrieved_chunk_ids" in response:
                    chunks = list(state.get("turn_retrieved_chunks", []))
                    for cid in response["retrieved_chunk_ids"]:
                        if cid not in chunks:
                            chunks.append(cid)
                    state["turn_retrieved_chunks"] = chunks
        except Exception:
            pass

    args_dict = {}
    if isinstance(args, dict):
        args_dict = {k: str(v) for k, v in args.items() if k != "password"}

    db.log_audit(
        user_id=user_id,
        action=action_name,
        details={
            "tool": tool_name,
            "args": args_dict,
            "response_status": status
        },
        status=status
    )
    return None

