"""
Graph router functions (conditional edges) for Geopolitico LangGraph orchestrator.
"""

from typing import Dict, Any, TypedDict, Optional, List
from backend.models.schemas import ScenarioStateResult


def mode_router(state: Dict[str, Any]) -> str:
    """Route after planning node based on simulation_mode."""
    mode = state.get("simulation_mode", "expansion_conquest")
    if mode == "demographic_shift":
        return "demographic_node"
    elif mode == "compounding_conquest":
        return "compound_splitter_node"
    else:
        # Both expansion_conquest and proposal_partition share preprocessing
        return "shared_preprocess_node"


def pipeline_router(state: Dict[str, Any]) -> str:
    """Route after ownership analysis node to specific execution pipeline."""
    mode = state.get("simulation_mode", "expansion_conquest")
    if mode == "proposal_partition":
        return "partition_node"
    elif mode == "compounding_conquest":
        return "conquest_stage1_node"
    else:
        return "conquest_node"


def optimistic_gate(state: Dict[str, Any]) -> str:
    """Check if optimistic scenario result strictly expands beyond realistic."""
    res_real_dict = state.get("res_real")
    res_opt_dict = state.get("res_opt")
    
    if not res_real_dict or not res_opt_dict:
        return "result_assembly_node"
        
    try:
        res_real = ScenarioStateResult(**res_real_dict) if isinstance(res_real_dict, dict) else res_real_dict
        res_opt = ScenarioStateResult(**res_opt_dict) if isinstance(res_opt_dict, dict) else res_opt_dict
        
        h_real = set()
        for t in res_real.territories:
            h_real.update(getattr(t, "historical_provinces", []) or [])
            
        h_opt = set()
        for t in res_opt.territories:
            h_opt.update(getattr(t, "historical_provinces", []) or [])
            
        retries = state.get("optimistic_retry_count", 0)
        max_retries = state.get("optimistic_max_retries", 2)
        
        # Optimistic must be a strict superset of realistic
        if h_opt.issuperset(h_real) and len(h_opt) > len(h_real):
            return "result_assembly_node"
        elif retries < max_retries:
            return "conquest_retry_node"
        else:
            return "result_assembly_node"
    except Exception as e:
        print(f"[WARN] Optimistic gate check exception: {e}", flush=True)
        return "result_assembly_node"


def anomaly_gate(state: Dict[str, Any]) -> str:
    """Route to interrupt if anomalies exist and require user choice."""
    anomalies = state.get("anomalies", [])
    if anomalies and len(anomalies) > 0:
        return "awaiting_verification"
    return "completed"
