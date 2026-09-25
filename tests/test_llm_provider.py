import os
import pytest
from app.config import Settings
from app.agents.llm import get_llm


def clear_llm_env(monkeypatch):
    """Helper to clear LLM environment variables for clean isolation."""
    for key in [
        "LLM_PROVIDER", "PROVIDER", "LLM_VENDOR",
        "MODEL", "LLM_MODEL", "MODEL_NAME",
        "API_KEY", "LLM_API_KEY",
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "GROQ_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
        "API_BASE", "LLM_API_BASE"
    ]:
        monkeypatch.delenv(key, raising=False)


def test_openrouter_provider_config(monkeypatch):
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MODEL", "qwen/qwen3.8-27b")
    monkeypatch.setenv("API_KEY", "sk-or-v1-testkey123")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] == "openrouter"
    assert cfg["model_name"] == "openrouter/qwen/qwen3.8-27b"
    assert cfg["api_key"] == "sk-or-v1-testkey123"

    llm = get_llm()
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-v1-testkey123"
    assert llm.model == "openrouter/qwen/qwen3.8-27b"


def test_gemini_provider_config(monkeypatch):
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "google/gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey456")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] == "gemini"
    assert cfg["model_name"] == "gemini/gemini-2.5-flash-lite"
    assert cfg["api_key"] == "AIzaSyTestKey456"

    llm = get_llm()
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSyTestKey456"
    assert os.environ.get("GOOGLE_API_KEY") == "AIzaSyTestKey456"
    assert llm.model == "gemini/gemini-2.5-flash-lite"


def test_groq_provider_config(monkeypatch):
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_GroqTestKey789")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] == "groq"
    assert cfg["model_name"] == "groq/llama-3.3-70b-versatile"
    assert cfg["api_key"] == "gsk_GroqTestKey789"

    llm = get_llm()
    assert os.environ.get("GROQ_API_KEY") == "gsk_GroqTestKey789"
    assert llm.model == "groq/llama-3.3-70b-versatile"


def test_grok_xai_provider_config(monkeypatch):
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "grok")
    monkeypatch.setenv("MODEL", "grok-2-latest")
    monkeypatch.setenv("GROK_API_KEY", "xai-groktestkey")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] in ("grok", "xai")
    assert cfg["model_name"] == "xai/grok-2-latest"
    assert cfg["api_key"] == "xai-groktestkey"

    llm = get_llm()
    assert os.environ.get("XAI_API_KEY") == "xai-groktestkey"
    assert llm.model == "xai/grok-2-latest"


def test_api_key_in_llm_provider_env_variable(monkeypatch):
    """Test handling when user puts an OpenRouter API key directly in LLM_PROVIDER in .env"""
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "sk-or-v1-dummykey123")
    monkeypatch.setenv("MODEL", "google/gemini-2.5-flash-lite")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] == "openrouter"
    assert cfg["model_name"] == "openrouter/google/gemini-2.5-flash-lite"
    assert cfg["api_key"] == "sk-or-v1-dummykey123"


def test_custom_provider_and_api_base(monkeypatch):
    clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.setenv("MODEL", "llama-3-8b")
    monkeypatch.setenv("API_KEY", "custom-key")
    monkeypatch.setenv("API_BASE", "http://localhost:8000/v1")

    s = Settings()
    cfg = s.get_llm_config()

    assert cfg["provider"] == "vllm"
    assert cfg["model_name"] == "vllm/llama-3-8b"
    assert cfg["api_base"] == "http://localhost:8000/v1"
