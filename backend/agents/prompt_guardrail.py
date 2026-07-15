import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from backend.config import GITHUB_TOKEN, GITHUB_API_URL, GITHUB_MODELS, EXHAUSTED_MODELS

class GuardrailResult(BaseModel):
    refined_prompt: str = Field(description="The cleaned, corrected, and historically aligned prompt.")
    original_prompt: str = Field(description="The original prompt input.")
    corrections_made: str = Field(description="Description of any spelling corrections or historical conceptual alignment made.")
    is_valid: bool = Field(description="True if the prompt is valid and can be simulated, False if it is completely nonsensical or offensive.")

GUARDRAIL_SYSTEM_PROMPT = """You are a geopolitical history guardrail and input refiner.
Your task is to review the user's alternate history scenario prompt and:
1. Correct spelling, punctuation, typos, and grammatical errors (e.g., "formular" -> "formula", "redcliff" -> "Radcliffe").
2. Align historical, geographic, or logical contradictions.
   - For example, if the prompt mixes the 1947 partition of India (Radcliffe Line) with the 1960 Kashmir partition proposal (Chenab Formula), point out the distinction and refine the prompt to be historically coherent (e.g. focusing on the Chenab Formula partition of Kashmir in 1960).
   - If the user asks for a completely geographically impossible action (e.g., "France annexes Tokyo in 732 AD"), flag it or refine it to make physical sense if possible.
3. Keep the user's core intent while making the prompt clear and correct.
4. Output the result in the requested structured JSON schema."""

def refine_user_prompt(scenario: str) -> Dict[str, Any]:
    """Refine user prompt for spelling, grammar, and historical consistency."""
    # Find active model (prioritize gpt-4o for structured output)
    available_models = [m for m in GITHUB_MODELS if m not in EXHAUSTED_MODELS]
    if not available_models:
        available_models = GITHUB_MODELS.copy()
        
    model_to_use = None
    for m in available_models:
        if "gpt-4o" in m.lower():
            model_to_use = m
            break
    if not model_to_use:
        model_to_use = available_models[0]
        
    clean_model = model_to_use.replace("openai/", "", 1) if model_to_use.startswith("openai/") else model_to_use
    token = os.environ.get("GITHUB_TOKEN", GITHUB_TOKEN)
    
    print(f"[GUARDRAIL] Invoking model '{clean_model}' to verify and refine prompt...", flush=True)
    try:
        llm = ChatOpenAI(
            model=clean_model,
            api_key=token,
            base_url=GITHUB_API_URL,
            temperature=0.2,
            max_tokens=1024,
            timeout=40.0
        )
        if "gpt-4o" not in clean_model.lower():
            try:
                llm.supports_function_calling = lambda: False
            except Exception:
                pass
        structured_llm = llm.with_structured_output(GuardrailResult)
        messages = [
            SystemMessage(content=GUARDRAIL_SYSTEM_PROMPT),
            SystemMessage(content=f"User Prompt: {scenario}")
        ]
        res: GuardrailResult = structured_llm.invoke(messages)
        return {
            "refined_prompt": res.refined_prompt,
            "original_prompt": res.original_prompt,
            "corrections_made": res.corrections_made,
            "is_valid": res.is_valid
        }
    except Exception as e:
        print(f"[GUARDRAIL WARN] Guardrail invoke failed: {e}. Falling back to original prompt.", flush=True)
        return {
            "refined_prompt": scenario,
            "original_prompt": scenario,
            "corrections_made": "None (Guardrail model fallback)",
            "is_valid": True
        }
