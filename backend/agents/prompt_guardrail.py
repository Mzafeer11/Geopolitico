import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from backend.helpers.llm import invoke_structured_with_fallback

class GuardrailResult(BaseModel):
    refined_prompt: str = Field(description="The cleaned, corrected, and historically aligned prompt.")
    original_prompt: str = Field(description="The original prompt input.")
    corrections_made: str = Field(description="Description of any spelling corrections or historical conceptual alignment made.")
    is_valid: bool = Field(description="True if the prompt is valid and can be simulated, False if it is completely nonsensical or offensive.")

GUARDRAIL_SYSTEM_PROMPT = """You are a geopolitical history guardrail and input refiner for an ALTERNATE HISTORY simulation engine.
Your task is to review the user's alternate history scenario prompt and:
1. Correct spelling, punctuation, typos, and grammatical errors (e.g., "formular" -> "formula", "redcliff" -> "Radcliffe", "What ottomans won the war of vienna" -> "What if the Ottomans won the Siege of Vienna in 1529?").
2. ABSOLUTE COUNTERFACTUAL RULE: The user is explicitly exploring speculative "what if" counterfactual alternate histories (e.g. "What if the Ottomans won the Siege of Vienna in 1529?", "What if the Umayyads won the Battle of Tours in 732?").
   - NEVER contradict, reject, or undo the user's "what if" counterfactual premise!
   - NEVER rephrase a counterfactual question into real-world factual history (e.g. do NOT change "What if Ottomans won in 1529" to "Which Ottoman forces were involved and what was the actual outcome?").
   - ALWAYS preserve the speculative counterfactual victory or event intact.
3. Align geographic or logical contradictions if they conflate unrelated real-world events:
   - For example, if the prompt mixes the 1947 partition of India (Radcliffe Line) with the 1960 Kashmir partition proposal (Chenab Formula), point out the distinction and refine the prompt to be historically coherent.
   - If the user asks for a completely geographically impossible action (e.g., "France annexes Tokyo in 732 AD"), flag it or refine it to make physical sense if possible.
4. Keep the user's core counterfactual intent while making the prompt clear and grammatically correct.
5. Output the result in the requested structured JSON schema."""

def refine_user_prompt(scenario: str) -> Dict[str, Any]:
    """Refine user prompt for spelling, grammar, and historical consistency."""
    print(f"[GUARDRAIL] Verifying and refining prompt via LLM fallback chain...", flush=True)
    try:
        messages = [
            SystemMessage(content=GUARDRAIL_SYSTEM_PROMPT),
            SystemMessage(content=f"User Prompt: {scenario}")
        ]
        res: GuardrailResult = invoke_structured_with_fallback(GuardrailResult, messages, temperature=0.2, is_simple=True)
        return {
            "refined_prompt": res.refined_prompt,
            "original_prompt": res.original_prompt,
            "corrections_made": res.corrections_made,
            "is_valid": res.is_valid
        }
    except Exception as e:
        print(f"[GUARDRAIL WARN] Guardrail invoke failed: {e}.", flush=True)
        return {
            "refined_prompt": scenario,
            "original_prompt": scenario,
            "corrections_made": f"Guardrail evaluation failed due to exception: {e}",
            "is_valid": False
        }
