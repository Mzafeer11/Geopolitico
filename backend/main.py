import os
import json
import traceback
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.simulation_engine import simulate_start, simulate_step, simulate_verify
from backend.config import FRONTEND_DIR, DATA_DIR

app = FastAPI(
    title="Geopolitico — Unified Alternate History Geopolitical Simulator",
    description="A streamlined Python/LangChain geopolitical simulation engine.",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# In-memory store for active job states/results
jobs_store = {}

class SimulationRequest(BaseModel):
    scenario: str
    token: Optional[str] = ""

class VerifyRequest(BaseModel):
    session_id: str
    selections: Dict[str, str]


class InteractiveRequest(BaseModel):
    session_id: str
    message: str
    token: Optional[str] = ""

def run_simulate_start_background(job_id: str, scenario: str):
    """Start the simulation pipeline in the background."""
    try:
        jobs_store[job_id] = {
            "status": "running",
            "progress": "Analyzing geopolitical counterfactual context..."
        }
        res = simulate_start(scenario)
        if res.get("status") == "awaiting_verification":
            jobs_store[job_id] = {
                "status": "awaiting_verification",
                "progress": "Awaiting user verification of geopolitical anomalies",
                "questions": res["questions"],
                "result": res["result"],
                "session_id": res["session_id"]
            }
        else:
            jobs_store[job_id] = {
                "status": "completed",
                "progress": "Simulation complete",
                "result": res["result"],
                "session_id": res["session_id"]
            }
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[ERR] Start simulation failed for job {job_id}: {e}\n{trace}")
        jobs_store[job_id] = {
            "status": "failed",
            "progress": f"Error: {str(e)}",
            "error": str(e)
        }

def run_simulate_verify_background(job_id: str, session_id: str, selections: Dict[str, str]):
    """Finalize the simulation in the background with user validation selections."""
    try:
        jobs_store[job_id] = {
            "status": "running",
            "progress": "Finalizing boundaries with selected validation edits..."
        }
        res = simulate_verify(session_id, selections)
        jobs_store[job_id] = {
            "status": "completed",
            "progress": "Simulation complete",
            "result": res["result"],
            "session_id": res["session_id"]
        }
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[ERR] Verify simulation failed for job {job_id}: {e}\n{trace}")
        jobs_store[job_id] = {
            "status": "failed",
            "progress": f"Error: {str(e)}",
            "error": str(e)
        }

def run_simulate_step_background(job_id: str, session_id: str, message: str):
    """Refine the simulation timeline in the background with user instructions."""
    try:
        jobs_store[job_id] = {
            "status": "running",
            "progress": "Applying refinement instructions and regenerating maps..."
        }
        res = simulate_step(session_id, message)
        jobs_store[job_id] = {
            "status": "completed",
            "progress": "Simulation refined successfully",
            "result": res["result"],
            "session_id": res["session_id"]
        }
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[ERR] Refine simulation failed for job {job_id}: {e}\n{trace}")
        jobs_store[job_id] = {
            "status": "failed",
            "progress": f"Error: {str(e)}",
            "error": str(e)
        }


@app.post("/api/simulate")
async def simulate(req: SimulationRequest, background_tasks: BackgroundTasks):
    """Start a simulation job."""
    if not req.scenario:
        raise HTTPException(status_code=400, detail="Scenario input cannot be empty.")
        
    token_to_use = req.token or os.environ.get("GITHUB_TOKEN")
    if not token_to_use:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is missing.")
        
    if req.token:
        os.environ["GITHUB_TOKEN"] = req.token
        
    import uuid
    job_id = str(uuid.uuid4())
    
    background_tasks.add_task(run_simulate_start_background, job_id, req.scenario)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/interactive/step")
async def interactive_step(req: InteractiveRequest, background_tasks: BackgroundTasks):
    """Refine simulation outcome using follow-up text prompt."""
    import uuid
    job_id = str(uuid.uuid4())
    
    if req.token:
        os.environ["GITHUB_TOKEN"] = req.token
        
    background_tasks.add_task(run_simulate_step_background, job_id, req.session_id, req.message)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/simulate/verify")
async def simulate_verify(req: VerifyRequest, background_tasks: BackgroundTasks):
    """Finalize job with validation selections."""
    import uuid
    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_simulate_verify_background, job_id, req.session_id, req.selections)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Retrieve job status, questions, or final simulation result."""
    job = jobs_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
else:
    @app.get("/")
    def read_root():
        return {"message": "Frontend files not found. Place them in the frontend folder."}
