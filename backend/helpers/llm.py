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
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
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

def _try_openrouter(schema, messages, temperature=0.3):
    openrouter_key = (os.getenv("OPEN_ROUTER_API") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not openrouter_key:
        return None
    openrouter_candidates = [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
        "inclusionai/ling-3.0-flash:free",
        "cohere/north-mini-code:free",
        "poolside/laguna-s-2.1:free"
    ]
    for or_model in openrouter_candidates:
        print(f"[SIMULATOR-LLM] Attempting OpenRouter model '{or_model}'...", flush=True)
        try:
            llm = ChatOpenAI(
                model=or_model,
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=temperature,
                timeout=45.0,
                max_retries=1
            )
            structured_llm = llm.with_structured_output(schema)
            res = structured_llm.invoke(messages)
            if res:
                try:
                    if hasattr(res, "model_dump_json"):
                        print(f"[DEBUG] OpenRouter Model '{or_model}' returned structured result:\n{res.model_dump_json(indent=2)}", flush=True)
                except Exception:
                    pass
                return res
        except Exception as e_or:
            print(f"[SIMULATOR-LLM WARN] OpenRouter model '{or_model}' attempt failed: {e_or}. Trying next OpenRouter candidate...", flush=True)
            time.sleep(0.5)
    print("[SIMULATOR-LLM WARN] All OpenRouter candidates exhausted.", flush=True)
    return None


def _try_groq(schema, messages, temperature=0.3):
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        return None

    available_groq = fetch_available_groq_models()
    candidate_priority = [
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant"
    ]
    models_to_try = [m for m in candidate_priority if m in available_groq and m in VERIFIED_STRUCTURED_MODELS]
    for m in candidate_priority:
        if m in VERIFIED_STRUCTURED_MODELS and m not in models_to_try:
            models_to_try.append(m)

    if not models_to_try:
        models_to_try = VERIFIED_STRUCTURED_MODELS.copy()

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
                except Exception:
                    pass
                return res
        except Exception as e:
            print(f"[WARN] Groq model '{model_name}' attempt failed: {e}. Retrying next available model...", flush=True)
            time.sleep(1.0)
    return None


def _try_azure(schema, messages, temperature=0.3):
    azure_api_key = (os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_KEY") or "").strip()
    azure_endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    if not azure_api_key:
        return None

    default_azure_models = ["gpt-5.1-codex-mini", "gpt-5.4-mini", "gpt-5.1", "gpt-5.2", "gpt-5.5", "gpt-5.6-sol"]
    raw_models = os.getenv("AZURE_MODELS", "")
    if raw_models:
        azure_candidates = [m.strip() for m in raw_models.split(",") if m.strip()]
    else:
        azure_candidates = default_azure_models

    primary_az = os.getenv("AZURE_OPENAI_MODEL", "").strip()
    if primary_az and primary_az in azure_candidates:
        azure_candidates.remove(primary_az)
        azure_candidates.insert(0, primary_az)

    for az_model in azure_candidates:
        print(f"[SIMULATOR-LLM] Attempting Azure OpenAI deployment '{az_model}' at '{azure_endpoint}'...", flush=True)
        try:
            llm_az = ChatOpenAI(
                model=az_model,
                api_key=azure_api_key,
                base_url=azure_endpoint,
                temperature=temperature,
                timeout=45.0,
                max_retries=1
            )
            structured_llm_az = llm_az.with_structured_output(schema)
            res_az = structured_llm_az.invoke(messages)
            if res_az:
                try:
                    if hasattr(res_az, "model_dump_json"):
                        print(f"[DEBUG] Azure OpenAI Model '{az_model}' returned structured result:\n{res_az.model_dump_json(indent=2)}", flush=True)
                except Exception:
                    pass
                return res_az
        except Exception as e_az:
            print(f"[SIMULATOR-LLM WARN] Azure OpenAI deployment '{az_model}' attempt failed: {e_az}. Trying next Azure candidate...", flush=True)
            time.sleep(0.5)
    return None


def invoke_structured_with_fallback(schema, messages, temperature=0.3, is_simple=False, seed=42):
    """
    Invokes structured schema generation for the Geopolitico simulation engine.
    - Centralized entrypoint for ALL LLM calls across the codebase.
    - Priority order controlled dynamically by LLM_PROVIDER_ORDER env var (Default: "openrouter,groq,azure").
    """
    raw_order = os.getenv("LLM_PROVIDER_ORDER", "openrouter,groq,azure")
    provider_order = [p.strip().lower() for p in raw_order.split(",") if p.strip()]

    for provider in provider_order:
        if provider == "openrouter":
            res = _try_openrouter(schema, messages, temperature)
            if res:
                return res
        elif provider == "groq":
            res = _try_groq(schema, messages, temperature)
            if res:
                return res
        elif provider == "azure":
            res = _try_azure(schema, messages, temperature)
            if res:
                return res

    raise RuntimeError("All LLM providers (OpenRouter, Groq, Azure) failed to return structured output.")
