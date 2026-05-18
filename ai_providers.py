"""
ExecSlate AI Provider Fallback Chain
=====================================
Cascading AI providers: OpenAI → Gemini(s) → Groq(s) → Cerebras → OpenRouter → None

Supports MULTIPLE keys per provider via comma-separated env vars:
    GEMINI_API_KEY=key1,key2,key3
    GROQ_API_KEY=key1,key2

When one key hits a rate limit, the next key is tried automatically.
All providers use the OpenAI-compatible API format.

Setup:
    Set any combination of these environment variables:
    - OPENAI_API_KEY      → OpenAI (gpt-4.1-mini)
    - GEMINI_API_KEY      → Google Gemini (gemini-2.0-flash) — FREE: 15 RPM, 1M tokens/day per key
    - GROQ_API_KEY        → Groq (llama-3.3-70b-versatile) — FREE: 30 RPM per key
    - CEREBRAS_API_KEY    → Cerebras (llama-3.3-70b) — FREE: ultra-fast wafer-scale inference
    - OPENROUTER_API_KEY  → OpenRouter (routes to best free model) — FREE: many models available

    Multiple keys: separate with commas (no spaces):
    - GEMINI_API_KEY=AIzaKey1,AIzaKey2
    - GROQ_API_KEY=gsk_key1,gsk_key2
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List

# Load .env file if present (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on system env vars

logger = logging.getLogger(__name__)

# ==================== PROVIDER CONFIGURATION ====================

PROVIDERS = []


def _parse_keys(env_var: str) -> List[str]:
    """Parse comma-separated API keys from an environment variable."""
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _init_providers():
    """Initialize available AI providers from environment variables."""
    global PROVIDERS
    PROVIDERS = []

    # Provider 1: OpenAI (typically single key)
    for key in _parse_keys("OPENAI_API_KEY"):
        PROVIDERS.append({
            "name": "OpenAI",
            "api_key": key,
            "base_url": None,
            "model": "gpt-4.1-mini",
            "max_tokens": 2000,
        })
        logger.info(f"✅ AI Provider: OpenAI (key: {key[:8]}...{key[-4:]})")

    # Provider 2: Google Gemini — supports multiple keys
    gemini_keys = _parse_keys("GEMINI_API_KEY")
    for i, key in enumerate(gemini_keys):
        PROVIDERS.append({
            "name": f"Gemini{'[' + str(i+1) + ']' if len(gemini_keys) > 1 else ''}",
            "api_key": key,
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": "gemini-2.0-flash",
            "max_tokens": 2000,
        })
        logger.info(f"✅ AI Provider: Gemini key {i+1}/{len(gemini_keys)} ({key[:8]}...{key[-4:]})")

    # Provider 3: Groq — supports multiple keys
    groq_keys = _parse_keys("GROQ_API_KEY")
    for i, key in enumerate(groq_keys):
        PROVIDERS.append({
            "name": f"Groq{'[' + str(i+1) + ']' if len(groq_keys) > 1 else ''}",
            "api_key": key,
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 2000,
        })
        logger.info(f"✅ AI Provider: Groq key {i+1}/{len(groq_keys)} ({key[:8]}...{key[-4:]})")

    # Provider 4: Cerebras — ultra-fast wafer-scale inference
    cerebras_keys = _parse_keys("CEREBRAS_API_KEY")
    for i, key in enumerate(cerebras_keys):
        PROVIDERS.append({
            "name": f"Cerebras{'[' + str(i+1) + ']' if len(cerebras_keys) > 1 else ''}",
            "api_key": key,
            "base_url": "https://api.cerebras.ai/v1",
            "model": "llama-3.3-70b",
            "max_tokens": 2000,
        })
        logger.info(f"✅ AI Provider: Cerebras key {i+1}/{len(cerebras_keys)} ({key[:8]}...{key[-4:]})")

    # Provider 5: OpenRouter — gateway to dozens of models (ultimate safety net)
    openrouter_keys = _parse_keys("OPENROUTER_API_KEY")
    for i, key in enumerate(openrouter_keys):
        PROVIDERS.append({
            "name": f"OpenRouter{'[' + str(i+1) + ']' if len(openrouter_keys) > 1 else ''}",
            "api_key": key,
            "base_url": "https://openrouter.ai/api/v1",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "max_tokens": 2000,
        })
        logger.info(f"✅ AI Provider: OpenRouter key {i+1}/{len(openrouter_keys)} ({key[:8]}...{key[-4:]})")

    if not PROVIDERS:
        logger.warning("⚠️ No AI providers configured — AI insights will use statistical fallback")
    else:
        chain = " → ".join(p["name"] for p in PROVIDERS)
        logger.info(f"🔗 AI fallback chain ({len(PROVIDERS)} providers): {chain} → Statistical Fallback")


# Initialize on module load
_init_providers()


# ==================== CORE API CALL ====================

def _try_provider(provider: Dict, prompt: str, temperature: float = 0.3) -> Optional[str]:
    """
    Try a single AI provider. Returns response text or None on failure.
    Uses the OpenAI Python library with custom base_url for Gemini/Groq.
    """
    from openai import OpenAI

    try:
        kwargs = {"api_key": provider["api_key"]}
        if provider["base_url"]:
            kwargs["base_url"] = provider["base_url"]

        client = OpenAI(**kwargs)

        response = client.chat.completions.create(
            model=provider["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=provider["max_tokens"],
        )

        content = response.choices[0].message.content.strip()
        logger.info(f"✨ AI response from {provider['name']} ({provider['model']})")
        return content

    except Exception as e:
        error_str = str(e).lower()

        # Classify the error for clear logging
        if "rate" in error_str or "quota" in error_str or "limit" in error_str or "429" in error_str:
            logger.warning(f"⚠️ {provider['name']}: Rate limit/quota exceeded — trying next provider")
        elif "auth" in error_str or "key" in error_str or "invalid" in error_str or "401" in error_str:
            logger.warning(f"⚠️ {provider['name']}: Authentication failed — trying next provider")
        elif "billing" in error_str or "payment" in error_str or "insufficient" in error_str:
            logger.warning(f"⚠️ {provider['name']}: Billing/credits exhausted — trying next provider")
        else:
            logger.warning(f"⚠️ {provider['name']}: {e} — trying next provider")

        return None


# ==================== PUBLIC API ====================

def get_ai_response(prompt: str, temperature: float = 0.3) -> Optional[str]:
    """
    Try each AI provider in the fallback chain.
    Returns the response text from the first provider that succeeds,
    or None if all providers fail.

    The chain: OpenAI → Gemini → Groq → Cerebras → OpenRouter → None
    """
    if not PROVIDERS:
        logger.info("No AI providers available — using statistical fallback")
        return None

    for provider in PROVIDERS:
        result = _try_provider(provider, prompt, temperature)
        if result:
            return result

    logger.warning(f"❌ All {len(PROVIDERS)} AI providers failed — falling back to statistical insights")
    return None


def is_ai_available() -> bool:
    """Check if at least one AI provider is configured."""
    return len(PROVIDERS) > 0


def get_provider_status() -> List[Dict[str, str]]:
    """Return status of configured providers (for admin dashboard)."""
    return [
        {"name": p["name"], "model": p["model"], "status": "configured"}
        for p in PROVIDERS
    ]
