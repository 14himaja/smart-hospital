"""Callbacks and security guardrails for Google ADK agents."""

from datetime import datetime
from app.database import db


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

    # Always inject authenticated user_id if tool has user_id in arguments
    if isinstance(args, dict) and session_user_id:
        if "user_id" in args:
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

