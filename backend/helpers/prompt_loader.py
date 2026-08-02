"""
Prompt Template Loader Helper for Geopolitico simulation engine.
Loads text prompt templates from the backend/prompts folder.
"""

import os

def _load_prompt_template(filename: str) -> str:
    """Load a prompt template from the backend/prompts folder."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_file = filename if filename.endswith(".txt") else f"{filename}.txt"
        path = os.path.join(base_dir, "prompts", target_file)
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[WARN] Failed to load prompt template '{filename}': {e}. Using hardcoded fallback.", flush=True)
        return ""
