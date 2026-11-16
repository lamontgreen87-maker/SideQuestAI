import sys
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import uuid
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from overmind import Overmind
from telemetry import TelemetryLogger, LoopGuard
from science_bot import ScienceBot

app = FastAPI(title="Hive Mind Impossible Engine API")

# Mount dashboard as static files
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

science_bot = ScienceBot()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulation of a task database
tasks_db = {}

# Distributed Worker Nexus
from worker_nexus import WorkerNexus
nexus = WorkerNexus()

class WorkerRegister(BaseModel):
    name: str
    vram_gb: int
    total_slots: int
    model_name: str
    endpoint_url: str

@app.post("/worker/register")
async def register_worker(request: WorkerRegister):
    worker_id = nexus.register_worker(request.dict())
    return {"worker_id": worker_id, "message": "Successfully registered to the Hive Nexus."}

@app.post("/worker/heartbeat/{worker_id}")
async def worker_heartbeat(worker_id: str, request: Request):
    data = await request.json()
    active_slots = data.get("active_slots", 0)
    success = nexus.heartbeat(worker_id, active_slots=active_slots)
    if not success:
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"status": "alive", "load": active_slots}

class ShardCompletion(BaseModel):
    worker_id: str
    duration: float
    credits: float = 1.0

@app.post("/worker/complete")
async def worker_complete(request: ShardCompletion):
    # 1. Record speed for performance tracking
    nexus.record_completion(request.worker_id, request.duration)
    # 2. Record payout with multipliers
    nexus.record_payout(request.worker_id, request.credits)
    
    return {"status": "success", "performance": nexus.active_workers.get(request.worker_id, {}).get("performance_score")}

@app.get("/worker/network")
async def get_worker_network():
    stats = nexus.get_status()
    # Add active missions and escrow pool
    active_missions = len([t for t in tasks_db.values() if t["status"] not in ["COMPLETED", "ERROR"]])
    stats["active_missions"] = active_missions
    stats["total_escrow_pool"] = sum(v["amount"] for v in nexus.pending_escrow.values())
    return stats

class SwarmRequest(BaseModel):
    goal: str
    redundancy: Optional[int] = 3
    depth: Optional[int] = 3
    phase: Optional[int] = 1 # 1 = Local, 2 = Remote
    output_format: Optional[str] = "single_file"
    output_file: Optional[str] = "app.py"

class TaskStatus(BaseModel):
    id: str
    goal: str
    status: str
    progress: float
    result: Optional[str] = None
    last_update: Optional[str] = None

@app.post("/swarm/execute")
async def execute_swarm(request: SwarmRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {
        "id": task_id,
        "goal": request.goal,
        "status": "SHATTERING",
        "progress": 0.0,
        "result": None,
        "last_update": "Drafting initial mission shard map..."
    }
    
    print(f"[API] Igniting Swarm: {task_id} | Goal: {request.goal[:50]}...", flush=True)
    
    # Run swarm in background
    hub = Overmind(
        redundancy_factor=request.redundancy,
        phase=request.phase,
        nexus=nexus,
        output_format=request.output_format,
        output_file=request.output_file,
    )
    background_tasks.add_task(run_background_swarm, task_id, hub, request.goal, request.depth)
    
    return {"task_id": task_id, "status": "SHATTERING"}

@app.get("/swarm/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_db[task_id]

async def run_background_swarm(task_id: str, hub: Overmind, goal: str, max_depth: int):
    print(f"[API] Background loop STARTED for {task_id}", flush=True)
    telemetry = TelemetryLogger()
    guard = LoopGuard(f"api.task.{task_id}", telemetry)
    telemetry.log("swarm_request", task_id=task_id, goal=goal[:300], max_depth=max_depth)
    
    # Task to run the swarm
    swarm_task = asyncio.create_task(hub.run_swarm(goal, max_depth=max_depth))
    
    # Task to monitor the hub status
    last_log = ""
    while not swarm_task.done():
        tasks_db[task_id]["status"] = hub.status
        tasks_db[task_id]["last_update"] = hub.last_update
        guard.tick(
            "status_loop",
            status=hub.status,
            last_update=hub.last_update[:200],
        )
        
        # Proactively push logs to the result field so index.html addLog picks them up
        if hub.last_update != last_log:
            tasks_db[task_id]["result"] = hub.last_update
            last_log = hub.last_update
            guard.mark_progress("status_update", status=hub.status)
            
        await asyncio.sleep(0.5)

    try:
        results = await swarm_task
        print(f"[API] [{task_id}] Swarm task COMPLETED.", flush=True)
        telemetry.log("swarm_complete", task_id=task_id)
        
        # Handle the dictionary return from Overmind.run_swarm
        if isinstance(results, dict) and "shards" in results:
            shards = results["shards"]
            final_report = results.get("final_report", "Mission Success. No summary provided.")
            
            if getattr(hub, "output_format", "") == "single_file":
                tasks_db[task_id]["result"] = final_report
            else:
                # Format shards into a clean registry for the dashboard
                shards_summary = "\n".join([f"Task {res.get('id', '?')}: {res.get('outcome', 'No outcome')}" if isinstance(res, dict) else str(res) for res in shards])
                tasks_db[task_id]["result"] = f"### FINAL PROJECT SYNTHESIS ###\n{final_report}\n\n### SHARD REGISTRY ###\n{shards_summary}"
        else:
            # Fallback for simple list or string returns
            tasks_db[task_id]["result"] = str(results)
            
        tasks_db[task_id]["status"] = "COMPLETED"
        tasks_db[task_id]["progress"] = 1.0
        tasks_db[task_id]["last_update"] = "Mission Success. Synthesis ready."
    except Exception as e:
        print(f"[API] [{task_id}] SWARM ERROR: {e}")
        telemetry.log("swarm_error", task_id=task_id, error=str(e))
        tasks_db[task_id]["status"] = f"ERROR: {str(e)}"


class ScienceConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    topic_focus: Optional[str] = None
    mode: Optional[str] = None
    arxiv_grounding: Optional[bool] = None
    provider: Optional[str] = None
    workers_per_run: Optional[int] = None
    research_phase: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None


@app.on_event("startup")
async def start_science_bot():
    asyncio.create_task(science_bot.run_loop())


@app.get("/science")
async def science_dashboard():
    return FileResponse(os.path.join(DASHBOARD_DIR, "science.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/science/feed")
async def get_science_feed():
    return {
        "status": science_bot.get_status(),
        "feed": science_bot.feed,
        "recent_runs": science_bot.load_recent_runs(25),
    }


@app.get("/api/science/index")
async def get_science_index():
    return science_bot.build_dictionary_index()


@app.get("/api/science/search")
async def search_science_articles(q: str = "", domain: str = ""):
    matches = science_bot.search_articles(query=q, domain=domain)
    return {"count": len(matches), "results": matches}


@app.post("/api/science/run-now")
async def run_science_now():
    started = await science_bot.trigger_now()
    return {"started": started, "status": science_bot.get_status()}


@app.post("/api/science/config")
async def update_science_config(req: ScienceConfigRequest):
    status = science_bot.update_config(
        enabled=req.enabled,
        interval_minutes=req.interval_minutes,
        topic_focus=req.topic_focus,
        mode=req.mode,
        arxiv_grounding=req.arxiv_grounding,
        provider=req.provider,
        workers_per_run=req.workers_per_run,
        research_phase=req.research_phase,
        schedule_enabled=req.schedule_enabled,
        schedule_start=req.schedule_start,
        schedule_end=req.schedule_end,
    )
    return {"status": status}


@app.get("/api/science/author-draft/{article_id}")
async def get_author_draft(article_id: str):
    from author_outreach import build_author_draft
    article = next((a for a in science_bot.feed if str(a.get("id")) == article_id), None)
    if not article:
        return JSONResponse({"error": "Article not found"}, status_code=404)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, build_author_draft, article)


@app.get("/api/science/author-omnibus")
async def get_author_omnibus(hours: int = 24):
    from author_outreach import build_author_omnibus
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, build_author_omnibus, list(science_bot.feed), hours)


@app.get("/api/science/stream")
async def stream_science_updates(request: Request):
    queue = science_bot.subscribe()

    async def event_generator():
        try:
            init_payload = json.dumps({"type": "status", "data": science_bot.get_status()})
            yield f"data: {init_payload}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            science_bot.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
