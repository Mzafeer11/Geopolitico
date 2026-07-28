"""
StateGraph compiler and execution graph for Geopolitico simulation engine.
"""

import os
from typing import TypedDict, Optional, List, Dict, Any, Tuple
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.config import DATA_DIR
from backend.orchestrator.graph_nodes import (
    guardrail_node, planner_node, compound_splitter_node, shared_preprocess_node,
    ownership_analysis_node, demographic_node, partition_node,
    conquest_node, conquest_stage1_node, conquest_stage2_node, conquest_retry_node,
    result_assembly_node, anomaly_check_node, verification_apply_node
)
from backend.orchestrator.graph_routers import mode_router, pipeline_router, optimistic_gate, anomaly_gate


class SimulationState(TypedDict, total=False):
    session_id: str
    job_id: str
    status: str
    error: Optional[str]
    raw_scenario: str
    scenario: str
    guardrail_logs: Dict[str, str]
    year: int
    parties: List[str]
    baseline_polities: List[str]
    simulation_mode: str
    target_region: str
    target_countries: List[str]
    baseline_description: str
    compounding_plan: Optional[Dict[str, Any]]
    stage1_real_conquests_str: str
    stage1_opt_conquests_str: str
    compounding_baselines_real: Dict[str, Any]
    compounding_baselines_opt: Dict[str, Any]
    compounding_resolved_geoms: Dict[str, Any]
    compounding_resolved_geoms_real: Dict[str, Any]
    compounding_resolved_geoms_opt: Dict[str, Any]
    stage2_baselines: Optional[Dict[str, Any]]
    osm_boundaries: Dict[str, Any]
    osm_boundary_geometry: Any
    osm_boundary_name: str
    geocoded_landmark_name: Optional[str]
    geocoded_landmark_coords: Optional[Tuple[float, float]]
    demographics_context: str
    gis_context: str
    contested_provinces: List[str]
    ownership_str: str
    prompt_contested: Any
    res_real: Optional[Dict[str, Any]]
    res_opt: Optional[Dict[str, Any]]
    realistic_features: List[Dict[str, Any]]
    optimistic_features: List[Dict[str, Any]]
    optimistic_retry_count: int
    optimistic_max_retries: int
    optimistic_is_valid: bool
    pending_real_result: Optional[Dict[str, Any]]
    pending_opt_result: Optional[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    clarifying_questions: List[Dict[str, Any]]
    user_selections: Optional[Dict[str, str]]
    results: Dict[str, Any]
    map_markers: List[Dict[str, Any]]
    refinement_message: Optional[str]
    answers: Optional[Dict[str, str]]
    geojson_before: Dict[str, Any]


def build_simulation_graph():
    """Build and compile the pure orchestrator LangGraph StateGraph."""
    graph = StateGraph(SimulationState)
    
    # ─── Add Nodes ────────────────────────────────────────────────────────
    graph.add_node("guardrail_node", guardrail_node)
    graph.add_node("planner_node", planner_node)
    graph.add_node("compound_splitter_node", compound_splitter_node)
    graph.add_node("shared_preprocess_node", shared_preprocess_node)
    graph.add_node("ownership_analysis_node", ownership_analysis_node)
    graph.add_node("demographic_node", demographic_node)
    graph.add_node("partition_node", partition_node)
    graph.add_node("conquest_node", conquest_node)
    graph.add_node("conquest_stage1_node", conquest_stage1_node)
    graph.add_node("conquest_stage2_node", conquest_stage2_node)
    graph.add_node("conquest_retry_node", conquest_retry_node)
    graph.add_node("result_assembly_node", result_assembly_node)
    graph.add_node("anomaly_check_node", anomaly_check_node)
    graph.add_node("verify_node", verification_apply_node)
    
    # ─── Entry Point & Fixed Edges ────────────────────────────────────────
    graph.set_entry_point("guardrail_node")
    graph.add_edge("guardrail_node", "planner_node")
    graph.add_edge("compound_splitter_node", "shared_preprocess_node")
    graph.add_edge("shared_preprocess_node", "ownership_analysis_node")
    graph.add_edge("conquest_stage1_node", "conquest_stage2_node")
    graph.add_edge("partition_node", "result_assembly_node")
    graph.add_edge("demographic_node", "result_assembly_node")
    graph.add_edge("result_assembly_node", "anomaly_check_node")
    graph.add_edge("verify_node", END)
    
    # ─── Conditional Edges ────────────────────────────────────────────────
    graph.add_conditional_edges("planner_node", mode_router, {
        "demographic_node": "demographic_node",
        "compound_splitter_node": "compound_splitter_node",
        "shared_preprocess_node": "shared_preprocess_node"
    })
    graph.add_conditional_edges("ownership_analysis_node", pipeline_router, {
        "partition_node": "partition_node",
        "conquest_stage1_node": "conquest_stage1_node",
        "conquest_node": "conquest_node"
    })
    graph.add_conditional_edges("conquest_node", optimistic_gate, {
        "result_assembly_node": "result_assembly_node",
        "conquest_retry_node": "conquest_retry_node"
    })
    graph.add_conditional_edges("conquest_stage2_node", optimistic_gate, {
        "result_assembly_node": "result_assembly_node",
        "conquest_retry_node": "conquest_retry_node"
    })
    graph.add_conditional_edges("conquest_retry_node", optimistic_gate, {
        "result_assembly_node": "result_assembly_node",
        "conquest_retry_node": "conquest_retry_node"
    })
    graph.add_conditional_edges("anomaly_check_node", anomaly_gate, {
        "awaiting_verification": END,
        "completed": END
    })
    
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Singleton instance of compiled graph
simulation_graph = build_simulation_graph()
