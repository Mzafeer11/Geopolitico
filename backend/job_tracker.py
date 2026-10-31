"""
Job Progress and Pipeline Stage Tracker for Geopolitico.
Tracks active simulation stages, details, and live log streaming for frontend status polling.
"""

import time
from typing import Dict, Any, List, Optional

# Predefined standard simulation stages
PIPELINE_STAGES = [
    {
        "id": "guardrail",
        "name": "Stage 1: Refinement of Prompt",
        "detail": "Analyzing counterfactual prompt and verifying historical context...",
        "icon": "🛡️"
    },
    {
        "id": "planner",
        "name": "Stage 2: Scenario Classification & Planning",
        "detail": "Identifying base year, belligerents, and geopolitical mode...",
        "icon": "🏛️"
    },
    {
        "id": "baseline_gis",
        "name": "Stage 3: Historical Baselines & Natural Boundaries",
        "detail": "Querying Cliopatria & resolving natural river/mountain vectors...",
        "icon": "🗺️"
    },
    {
        "id": "simulation",
        "name": "Stage 4: Geopolitical Simulation Execution",
        "detail": "Computing territorial transfers, corridors, and demographic shifts...",
        "icon": "🌍"
    },
    {
        "id": "compilation",
        "name": "Stage 5: Cartographic Compilation & Narrative",
        "detail": "Assembling GeoJSON feature collections and synthesizing timeline...",
        "icon": "🎨"
    },
    {
        "id": "audit",
        "name": "Stage 6: Continuity & Enclave Audit",
        "detail": "Verifying territorial continuity, enclave detection, and final audit...",
        "icon": "🔍"
    }
]

# In-memory store for active job states/results
jobs_store: Dict[str, Dict[str, Any]] = {}
active_job_id: Optional[str] = None


def init_job(job_id: str, scenario: str):
    """Initialize a new simulation job with all pipeline stages."""
    global active_job_id
    active_job_id = job_id
    
    stages = [
        {
            "id": s["id"],
            "name": s["name"],
            "detail": s["detail"],
            "icon": s["icon"],
            "status": "pending"
        }
        for s in PIPELINE_STAGES
    ]
    # First stage begins active immediately
    stages[0]["status"] = "active"
    
    jobs_store[job_id] = {
        "status": "running",
        "scenario": scenario,
        "progress": stages[0]["name"] + " — " + stages[0]["detail"],
        "stage_index": 1,
        "total_stages": len(PIPELINE_STAGES),
        "current_stage": stages[0]["name"],
        "stage_detail": stages[0]["detail"],
        "stages": stages,
        "recent_logs": [
            f"[SYSTEM] Initialized simulation job for: '{scenario[:65]}...'"
        ]
    }


def update_job_stage(job_id: Optional[str], stage_id: str, custom_detail: Optional[str] = None, log_line: Optional[str] = None):
    """Advance or update the active stage of the pipeline."""
    target_id = job_id or active_job_id
    if not target_id or target_id not in jobs_store:
        return
        
    job = jobs_store[target_id]
    stages = job.get("stages", [])
    
    stage_found = False
    current_stage_name = ""
    stage_idx = 1
    
    for idx, s in enumerate(stages, 1):
        if s["id"] == stage_id:
            s["status"] = "active"
            if custom_detail:
                s["detail"] = custom_detail
            current_stage_name = s["name"]
            stage_idx = idx
            stage_found = True
        elif not stage_found:
            s["status"] = "completed"
        else:
            s["status"] = "pending"
            
    job["stage_index"] = stage_idx
    job["current_stage"] = current_stage_name or stage_id
    job["stage_detail"] = custom_detail or (stages[stage_idx - 1]["detail"] if stage_idx <= len(stages) else "")
    job["progress"] = f"{job['current_stage']} — {job['stage_detail']}"
    
    if log_line:
        append_job_log(target_id, log_line)


def append_job_log(job_id: Optional[str], log_line: str):
    """Append a log line to the job's recent log feed."""
    target_id = job_id or active_job_id
    if not target_id or target_id not in jobs_store:
        return
    job = jobs_store[target_id]
    clean_line = (log_line or "").strip()
    if not clean_line:
        return
    logs = job.setdefault("recent_logs", [])
    if logs and logs[-1] == clean_line:
        return
    logs.append(clean_line)
    if len(logs) > 25:
        logs.pop(0)


def complete_job(job_id: str, payload: Dict[str, Any], session_id: Optional[str], is_awaiting_verification: bool = False, questions: List[Any] = None):
    """Mark the job as completed or awaiting verification."""
    if job_id not in jobs_store:
        return
    job = jobs_store[job_id]
    stages = job.get("stages", [])
    for s in stages:
        s["status"] = "completed"
        
    if is_awaiting_verification:
        job.update({
            "status": "awaiting_verification",
            "progress": "Awaiting user verification of geopolitical anomalies",
            "stage_index": len(stages),
            "current_stage": "Verification Required",
            "questions": questions or [],
            "result": payload,
            "session_id": session_id
        })
    else:
        job.update({
            "status": "completed",
            "progress": "Simulation complete",
            "stage_index": len(stages),
            "current_stage": "Simulation Complete",
            "result": payload,
            "session_id": session_id
        })


def fail_job(job_id: str, error_message: str):
    """Mark the job as failed with an error message."""
    if job_id not in jobs_store:
        return
    job = jobs_store[job_id]
    job.update({
        "status": "failed",
        "progress": f"Error: {error_message}",
        "error": error_message
    })

