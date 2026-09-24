import os
import warnings
import litellm
from google.adk.models.lite_llm import LiteLlm
from app.config import settings

# Suppress LiteLLM and Google ADK verbose warnings and logs
os.environ["ADK_SUPPRESS_GEMINI_LITELLM_WARNINGS"] = "true"
os.environ["LITELLM_LOG"] = "ERROR"
litellm.suppress_debug_info = True
litellm.set_verbose = False
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Provider-agnostic message sanitization wrapper
def _sanitize_messages(messages):
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                msg.pop("reasoning_content", None)
                msg.pop("reasoning", None)
            elif hasattr(msg, "reasoning_content"):
                try:
                    delattr(msg, "reasoning_content")
                except Exception:
                    pass

import asyncio
import time

_orig_acompletion = litellm.acompletion
async def _safe_acompletion(*args, **kwargs):
    if "messages" in kwargs:
        _sanitize_messages(kwargs["messages"])
    elif len(args) > 1:
        _sanitize_messages(args[1])
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await _orig_acompletion(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if attempt < max_retries - 1 and any(token in err_str for token in ("429", "rate limit", "ratelimit", "retry shortly")):
                await asyncio.sleep(2 * (attempt + 1))
                continue
            raise e

litellm.acompletion = _safe_acompletion

_orig_completion = litellm.completion
def _safe_completion(*args, **kwargs):
    if "messages" in kwargs:
        _sanitize_messages(kwargs["messages"])
    elif len(args) > 1:
        _sanitize_messages(args[1])
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return _orig_completion(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if attempt < max_retries - 1 and any(token in err_str for token in ("429", "rate limit", "ratelimit", "retry shortly")):
                time.sleep(2 * (attempt + 1))
                continue
            raise e

litellm.completion = _safe_completion


def get_llm():
    """Create and return the ADK LLM model instance dynamically based on configured provider and API key."""
    config = settings.get_llm_config()
    provider = config["provider"]
    api_key = config["api_key"]
    model_name = config["model_name"]
    api_base = config["api_base"]

    # Export API Key to environment variables for LiteLLM internal provider routing
    if api_key:
        if provider == "openrouter" or api_key.startswith("sk-or-v1-"):
            os.environ["OPENROUTER_API_KEY"] = api_key
        elif provider in ("gemini", "google") or api_key.startswith("AIzaSy"):
            os.environ["GEMINI_API_KEY"] = api_key
            os.environ["GOOGLE_API_KEY"] = api_key
        elif provider == "groq" or api_key.startswith("gsk_"):
            os.environ["GROQ_API_KEY"] = api_key
            os.environ["GROK_API_KEY"] = api_key
        elif provider in ("grok", "xai"):
            os.environ["XAI_API_KEY"] = api_key
            os.environ["GROK_API_KEY"] = api_key
        elif provider == "openai":
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "deepseek":
            os.environ["DEEPSEEK_API_KEY"] = api_key
        elif provider == "mistral":
            os.environ["MISTRAL_API_KEY"] = api_key

    kwargs = {"model": model_name}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    return LiteLlm(**kwargs)

