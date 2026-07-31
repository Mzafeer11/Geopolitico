"""
LLM invocation helper module for Geopolitico simulation engine.
Configured exclusively for Groq Cloud API with verified structured output models.
"""

import os
import json
import time
import httpx
from pathlib import Path
from typing import Any, List, Optional
from groq import Groq
from langchain_groq import ChatGroq
from backend.config import (
    GROQ_API_KEY,
    GROQ_SIMPLE_MODEL,
    GROQ_HEAVY_MODEL,
    DATA_DIR
)

# Verified Groq models that support Pydantic structured output / function calling
VERIFIED_STRUCTURED_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b"
]


def get_groq_client() -> Groq:
    """Returns an initialized Groq SDK client using GROQ_API_KEY from environment."""
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in environment or .env file.")
    return Groq(api_key=api_key)


def fetch_available_groq_models() -> List[str]:
    """Fetches real-time list of available models from https://api.groq.com/openai/v1/models and filters for structured output support."""
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        return VERIFIED_STRUCTURED_MODELS

    try:
        url = "https://api.groq.com/openai/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = httpx.get(url, headers=headers, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            raw_models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            valid = [m for m in raw_models if m in VERIFIED_STRUCTURED_MODELS]
            if valid:
                return valid
    except Exception as e:
        print(f"[WARN] Failed to fetch Groq model list dynamically: {e}", flush=True)

    return VERIFIED_STRUCTURED_MODELS


from langchain_openai import ChatOpenAI

def invoke_structured_with_fallback(schema, messages, temperature=0.3, is_simple=False, seed=42):
    """
    Invokes structured schema generation for the Geopolitico simulation engine.
    - Centralized entrypoint for ALL LLM calls across the codebase.
    - Priority 1: OpenRouter (nvidia/nemotron-3-ultra-550b-a55b:free) via OPEN_ROUTER_API key.
    - Priority 2: Fallback to verified Groq models (llama-3.3-70b-versatile, etc.).
    """
    # 1. Primary Attempt: OpenRouter (nvidia/nemotron-3-ultra-550b-a55b:free)
    openrouter_key = (os.getenv("OPEN_ROUTER_API") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        openrouter_model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
        print(f"[SIMULATOR-LLM] Attempting OpenRouter primary model '{openrouter_model}'...", flush=True)
        try:
            llm_or = ChatOpenAI(
                model=openrouter_model,
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=temperature,
                max_tokens=4096,
                timeout=60.0,
                max_retries=2
            )
            structured_llm_or = llm_or.with_structured_output(schema)
            res_or = structured_llm_or.invoke(messages)
            if res_or:
                try:
                    if hasattr(res_or, "model_dump_json"):
                        print(f"[DEBUG] OpenRouter Model '{openrouter_model}' returned structured result:\n{res_or.model_dump_json(indent=2)}", flush=True)
                    else:
                        print(f"[DEBUG] OpenRouter Model '{openrouter_model}' returned result: {res_or}", flush=True)
                except Exception:
                    pass
                return res_or
        except Exception as e_or:
            print(f"[SIMULATOR-LLM WARN] OpenRouter model '{openrouter_model}' attempt failed: {e_or}. Retrying with Groq fallback...", flush=True)

    # 2. Secondary Fallback: Groq Models
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        raise ValueError("Neither OPEN_ROUTER_API nor GROQ_API_KEY is set in environment or .env file.")

    # Filter dynamically for verified structured output models
    available_groq = fetch_available_groq_models()

    if is_simple:
        candidate_priority = [
            os.getenv("GROQ_SIMPLE_MODEL", GROQ_SIMPLE_MODEL),
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b"
        ]
    else:
        candidate_priority = [
            os.getenv("GROQ_HEAVY_MODEL", GROQ_HEAVY_MODEL),
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant"
        ]

    # Restrict strictly to models that support function calling
    models_to_try = [m for m in candidate_priority if m in available_groq and m in VERIFIED_STRUCTURED_MODELS]
    for m in candidate_priority:
        if m in VERIFIED_STRUCTURED_MODELS and m not in models_to_try:
            models_to_try.append(m)

    if not models_to_try:
        models_to_try = VERIFIED_STRUCTURED_MODELS.copy()

    last_error = None
    for model_name in models_to_try:
        print(f"[SIMULATOR-LLM] Invoking Groq fallback model '{model_name}' for structured output...", flush=True)
        try:
            llm = ChatGroq(
                model=model_name,
                api_key=api_key,
                temperature=temperature,
                max_tokens=4096,
                timeout=90.0,
                max_retries=2
            )
            structured_llm = llm.with_structured_output(schema)
            res = structured_llm.invoke(messages)
            if res:
                try:
                    if hasattr(res, "model_dump_json"):
                        print(f"[DEBUG] Groq Model '{model_name}' returned structured result:\n{res.model_dump_json(indent=2)}", flush=True)
                    else:
                        print(f"[DEBUG] Groq Model '{model_name}' returned result: {res}", flush=True)
                except Exception:
                    pass
                return res
        except Exception as e:
            last_error = e
            print(f"[WARN] Groq model '{model_name}' attempt failed: {e}. Retrying next available model...", flush=True)
            time.sleep(1.0)

    raise last_error or RuntimeError("All available OpenRouter and Groq models failed to generate structured output.")
