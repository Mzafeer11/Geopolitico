import os
import sys
import json
import traceback

class Tee(object):
    def __init__(self, filename, mode="a"):
        self.file = open(filename, mode, encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, data):
        try:
            self.file.write(data)
            self.file.flush()
        except Exception:
            pass
        self.stdout.write(data)
        self.stdout.flush()

        # Stream meaningful log lines into the active job tracker
        if data and ("[" in data):
            try:
                from backend.job_tracker import append_job_log
                for line in data.splitlines():
                    s = line.strip()
                    if s.startswith("[") and not s.startswith("[DEBUG]"):
                        append_job_log(None, s)
            except Exception:
                pass

    def flush(self):
        try:
            self.file.flush()
        except Exception:
            pass
        self.stdout.flush()

class TeeStderr(object):
    def __init__(self, filename, mode="a"):
        self.file = open(filename, mode, encoding="utf-8")
        self.stderr = sys.stderr

    def write(self, data):
        try:
            self.file.write(data)
            self.file.flush()
        except Exception:
            pass
        self.stderr.write(data)
        self.stderr.flush()

    def flush(self):
        try:
            self.file.flush()
        except Exception:
            pass
        self.stderr.flush()

# Configure logging path in the project root directory (use append mode so reloads never truncate active logs)
log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation.log")
sys.stdout = Tee(log_path, "a")
sys.stderr = TeeStderr(log_path, "a")

from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.simulation_engine import simulate_start, simulate_step, simulate_verify
from backend.config import FRONTEND_DIR, DATA_DIR
from backend.job_tracker import (
    jobs_store, init_job, update_job_stage, append_job_log, complete_job, fail_job
)

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
        init_job(job_id, scenario)
        res = simulate_start(scenario, job_id=job_id)
        sess_id = res.get("session_id") or (res.get("result", {}).get("session_id") if isinstance(res.get("result"), dict) else None)
        payload = res.get("result", res)
        if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict) and "title" in payload["result"]:
            payload = payload["result"]
            
        if res.get("status") == "awaiting_verification":
            complete_job(job_id, payload, sess_id, is_awaiting_verification=True, questions=res.get("questions", []))
        else:
            complete_job(job_id, payload, sess_id, is_awaiting_verification=False)
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[ERR] Start simulation failed for job {job_id}: {e}\n{trace}")
        fail_job(job_id, str(e))

def run_simulate_verify_background(job_id: str, session_id: str, selections: Dict[str, str]):
    """Finalize the simulation in the background with user validation selections."""
    try:
        init_job(job_id, "Applying validation choices")
        update_job_stage(job_id, "audit", "Applying user validation selections and rebuilding territorial boundaries...")
        res = simulate_verify(session_id, selections)
        complete_job(job_id, res["result"], res["session_id"])
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[ERR] Verify simulation failed for job {job_id}: {e}\n{trace}")
        fail_job(job_id, str(e))

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
        
    import uuid
    job_id = str(uuid.uuid4())
    
    background_tasks.add_task(run_simulate_start_background, job_id, req.scenario)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/interactive/step")
async def interactive_step(req: InteractiveRequest, background_tasks: BackgroundTasks):
    """Refine simulation outcome using follow-up text prompt."""
    import uuid
    job_id = str(uuid.uuid4())
    
    background_tasks.add_task(run_simulate_step_background, job_id, req.session_id, req.message)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/simulate/verify")
async def verify_simulation(req: VerifyRequest, background_tasks: BackgroundTasks):
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
