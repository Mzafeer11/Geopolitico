"""
LLM invocation helper module for Geopolitico simulation engine.
Handles structured output generation and model blacklist/rate-limit fallback management.
"""

import os
import json
from pathlib import Path
from typing import Any, List
from langchain_openai import ChatOpenAI
from backend.config import GITHUB_TOKEN, GITHUB_API_URL, GITHUB_MODELS, EXHAUSTED_MODELS, DATA_DIR

_BLACKLIST_FILE = Path(DATA_DIR) / "blacklisted_models.json"
_BLACKLISTED_MODELS = set()
if _BLACKLIST_FILE.exists():
    try:
        with open(_BLACKLIST_FILE, "r") as _f:
            _BLACKLISTED_MODELS = set(json.load(_f))
    except Exception:
        pass


def invoke_structured_with_fallback(schema, messages, temperature=0.5, seed=42):
    """Tries to invoke structured output, falling back across models on RateLimitError."""
    import time
    
    # Preferred structured models (OpenAI models on GitHub API with schema support)
    primary_models = [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "openai/gpt-4.1-mini",
        "openai/gpt-4.1",
        "openai/gpt-5-mini",
        "openai/gpt-5"
    ]
    
    attempt_list = [m for m in primary_models if m not in EXHAUSTED_MODELS]
    if not attempt_list:
        EXHAUSTED_MODELS.clear()
        attempt_list = list(primary_models)
        
    last_error = None
    for model in attempt_list:
        clean_model = model.replace("openai/", "", 1) if model.startswith("openai/") else model
        token = os.environ.get("GITHUB_TOKEN", GITHUB_TOKEN)
        print(f"[SIMULATOR] Invoking model '{clean_model}' for structured output...", flush=True)
        model_max_tokens = 16384 if "gpt-5" in clean_model.lower() else 4096
        
        try:
            llm = ChatOpenAI(
                model=clean_model,
                api_key=token,
                base_url=GITHUB_API_URL,
                temperature=temperature,
                max_tokens=model_max_tokens,
                timeout=120.0,
                seed=seed
            )
            structured_llm = llm.with_structured_output(schema, method="function_calling")
            res = structured_llm.invoke(messages)
            if res:
                try:
                    if hasattr(res, "model_dump_json"):
                        print(f"[DEBUG] Model '{clean_model}' returned structured result:\n{res.model_dump_json(indent=2)}", flush=True)
                    else:
                        print(f"[DEBUG] Model '{clean_model}' returned result: {res}", flush=True)
                except Exception as print_err:
                    print(f"[DEBUG] Error printing model result: {print_err}", flush=True)
            return res
        except Exception as e:
            print(f"[WARN] Model '{clean_model}' failed structured invoke: {e}", flush=True)
            last_error = e
            err_msg = str(e).lower()
            if "rate limit" in err_msg or "429" in err_msg or "quota" in err_msg or "too many requests" in err_msg:
                EXHAUSTED_MODELS.add(model)
                print(f"[SIMULATOR] Transiently marking '{clean_model}' as rate-limited. Retrying with next model...", flush=True)
                time.sleep(1.0)
                
    # Fallback retry loop if primary models were temporarily rate-limited
    EXHAUSTED_MODELS.clear()
    for model in ["openai/gpt-4o-mini", "openai/gpt-4o"]:
        clean_model = model.replace("openai/", "")
        token = os.environ.get("GITHUB_TOKEN", GITHUB_TOKEN)
        try:
            print(f"[SIMULATOR] Retry attempt with '{clean_model}'...", flush=True)
            llm = ChatOpenAI(model=clean_model, api_key=token, base_url=GITHUB_API_URL, temperature=temperature, timeout=120.0)
            return llm.with_structured_output(schema, method="function_calling").invoke(messages)
        except Exception as fallback_e:
            last_error = fallback_e
            
    raise last_error or RuntimeError("All models failed to complete structured schema generation.")
