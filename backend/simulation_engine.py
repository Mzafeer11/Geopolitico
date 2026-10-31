"""
Simulation Engine API Gateway for Geopolitico.
Exposes public engine entrypoints delegating execution to the LangGraph StateGraph Orchestrator.
"""

import uuid
from typing import Dict, Any

from backend.orchestrator.graph import simulation_graph
from backend.orchestrator.graph_nodes import verification_apply_node as verify_node

# In-memory active session store
_sessions: Dict[str, Dict[str, Any]] = {}


def simulate_start(scenario: str, job_id: str = None) -> Dict[str, Any]:
    """
    Start a geopolitical counterfactual simulation.
    Invokes the pure LangGraph orchestrator graph.
    """
    import importlib
    from backend.tools.spatial_cache import SimulationCache
    SimulationCache.get_instance().clear()

    # Hot-reload pipeline & orchestrator modules so disk changes apply immediately without restarting uvicorn
    try:
        import backend.tools.gis_tools as _m_gis
        import backend.tools.baseline_resolver as _m_br
        import backend.tools.compiler as _m_comp
        import backend.helpers.programmatic_validator as _m_pv
        import backend.pipelines.partition as _m_part
        import backend.pipelines.conquest as _m_conq
        import backend.pipelines.compounding as _m_cmpd
        import backend.pipelines.demographic as _m_demo
        import backend.orchestrator.graph_nodes as _m_gn
        import backend.orchestrator.graph as _m_gr
        for _mod in (_m_gis, _m_br, _m_comp, _m_pv, _m_part, _m_conq, _m_cmpd, _m_demo, _m_gn, _m_gr):
            importlib.reload(_mod)
        active_graph = _m_gr.simulation_graph
    except Exception:
        active_graph = simulation_graph
    
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "scenario": scenario,
        "raw_scenario": scenario,
        "session_id": session_id,
        "job_id": job_id or session_id
    }
    
    output_state = active_graph.invoke(initial_state, config)
    _sessions[session_id] = output_state
    
    status_val = output_state.get("status", "completed")
    res_payload = output_state.get("results", {})
    if isinstance(res_payload, dict):
        res_payload["session_id"] = session_id
        res_payload["guardrail_logs"] = output_state.get("guardrail_logs", {})
        
    if status_val == "awaiting_verification":
        return {
            "status": "awaiting_verification",
            "session_id": session_id,
            "questions": output_state.get("anomalies", []),
            "result": res_payload
        }
        
    return {
        "status": "completed",
        "result": res_payload,
        "session_id": session_id
    }


def simulate_verify(session_id: str, selections: Dict[str, str]) -> Dict[str, Any]:
    """
    Apply user validation selections to resolve geopolitical anomalies and finalize simulation.
    """
    config = {"configurable": {"thread_id": session_id}}
    snapshot = simulation_graph.get_state(config)
    
    current_state = dict(snapshot.values) if snapshot and snapshot.values else _sessions.get(session_id, {})
    if not current_state:
        raise ValueError("Invalid or expired session ID.")
        
    current_state["user_selections"] = selections
    update_dict = verify_node(current_state)
    current_state.update(update_dict)
    
    _sessions[session_id] = current_state
    res_payload = current_state.get("results", {})
    if isinstance(res_payload, dict):
        res_payload["session_id"] = session_id
        
    return {
        "status": "completed",
        "result": res_payload,
        "session_id": session_id
    }


def simulate_step(session_id: str, message: str) -> Dict[str, Any]:
    """
    Apply post-simulation refinement instruction and re-run simulation graph.
    """
    context = _sessions.get(session_id, {})
    original_scenario = context.get("raw_scenario", context.get("scenario", ""))
    refined_prompt = f"{original_scenario} (Instruction: {message})" if original_scenario else message
    
    res = simulate_start(refined_prompt)
    res["session_id"] = session_id
    return res
