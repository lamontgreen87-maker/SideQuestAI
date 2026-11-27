import sys
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import json
import os
import requests
import threading
import uuid
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from overmind import Overmind
from telemetry import TelemetryLogger, LoopGuard
from science_bot import ScienceBot
from shaman_journal import ShamanJournal
from math_solver import looks_like_math, solve_math_exact

app = FastAPI(title="Hive Mind Impossible Engine API")

# Mount dashboard as static files
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

science_bot = ScienceBot()
shaman_journal = ShamanJournal()

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


@app.get("/chat")
async def chat_dashboard():
    return FileResponse(os.path.join(DASHBOARD_DIR, "chat.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/chat/models")
async def list_chat_models():
    loop = asyncio.get_event_loop()
    def _fetch():
        models: List[str] = []
        if os.getenv("OPENROUTER_API_KEY"):
            models.append("openrouter:openrouter/free")
        groq_key = os.getenv("GROQ_API_KEY") or (
            os.getenv("BRAIN_API_KEY") if (os.getenv("BRAIN_API_KEY") or "").startswith("gsk_") else ""
        )
        if groq_key:
            models.append("groq:openai/gpt-oss-120b")
        try:
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            if r.ok:
                models.extend(m.get("name") for m in r.json().get("models", []) if m.get("name"))
        except Exception:
            pass
        return models
    models = await loop.run_in_executor(None, _fetch)
    return {"models": models}


@app.get("/api/journal/entries")
async def get_journal_entries(q: str = ""):
    entries = shaman_journal.list_entries(query=q, limit=200)
    return {
        "total": len(entries),
        "symbols": shaman_journal.get_symbol_counts(top_n=25),
        "entries": entries,
    }


@app.delete("/api/journal/entries/{entry_id}")
async def delete_journal_entry(entry_id: str):
    deleted = shaman_journal.delete_entry(entry_id)
    return {"deleted": deleted}


@app.get("/api/journal/grimoire")
async def get_journal_grimoire():
    return shaman_journal.build_grimoire()


@app.post("/api/charts/lookup")
async def lookup_single_chart(request: Request):
    from chart_symbiosis import inspect_single_chart
    body = await request.json()
    dt_local = str(body.get("dt_local") or "1987-11-09T17:04")
    tz_offset = float(body.get("tz_offset", -8.0))
    try:
        return inspect_single_chart(dt_local=dt_local, tz_offset=tz_offset)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/charts/compare")
async def compare_birth_charts(request: Request):
    from chart_symbiosis import compare_charts
    body = await request.json()
    dt_a = str(body.get("dt_a") or "1987-11-09T17:04")
    dt_b = str(body.get("dt_b") or "1990-05-15T12:00")
    tz_a = float(body.get("tz_a", -8.0))
    tz_b = float(body.get("tz_b", -8.0))
    try:
        return compare_charts(dt_a=dt_a, dt_b=dt_b, tz_a=tz_a, tz_b=tz_b)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/charts/oracle")
async def chart_oracle_now(request: Request):
    from datetime import datetime, timedelta, timezone
    from chart_symbiosis import compare_charts
    body = await request.json()
    dt_a = str(body.get("dt_a") or "1987-11-09T17:04")
    tz_a = float(body.get("tz_a", -8.0))
    now_local = (datetime.now(timezone.utc) + timedelta(hours=tz_a)).strftime("%Y-%m-%dT%H:%M")
    try:
        res = compare_charts(dt_a=dt_a, dt_b=now_local, tz_a=tz_a, tz_b=tz_a)
        top_transits = (res.get("aspects") or [])[:5]
        if top_transits:
            summary_bits = [
                f"Sky {t['body_b']} {t['aspect']} Natal {t['body_a']} ({t['orb_deg']}° orb)"
                for t in top_transits
            ]
            synopsis = (
                f"Current Sky ({now_local.replace('T', ' ')}) vs. Birth Chart: "
                + "; ".join(summary_bits)
                + ". "
                + (" ".join(res.get("notes", [])[:2]))
            )
        else:
            synopsis = f"Current Sky ({now_local.replace('T', ' ')}) shows no tight major transits within orb."
        return {**res, "now_local": now_local, "synopsis": synopsis}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/charts/saved")
async def get_saved_charts():
    from chart_symbiosis import list_saved_charts
    return {"charts": list_saved_charts()}


@app.post("/api/charts/saved")
async def create_saved_chart(request: Request):
    from chart_symbiosis import save_chart
    body = await request.json()
    name = str(body.get("name") or "").strip()
    dt_local = str(body.get("dt_local") or "").strip()
    tz_offset = float(body.get("tz_offset", -8.0))
    if not dt_local:
        return JSONResponse({"error": "dt_local is required"}, status_code=400)
    return {"chart": save_chart(name=name, dt_local=dt_local, tz_offset=tz_offset)}


@app.delete("/api/charts/saved/{chart_id}")
async def remove_saved_chart(chart_id: str):
    from chart_symbiosis import delete_saved_chart
    return {"deleted": delete_saved_chart(chart_id)}


@app.post("/api/chat/stream")
async def stream_local_chat(request: Request):
    body = await request.json()
    model = str(body.get("model") or "qwen2.5:3b")
    messages = list(body.get("messages") or [])
    journal_mode = bool(body.get("journal_mode", True))
    image_preview = str(body.get("image_preview") or "")

    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = str(m.get("content") or "")
            break

    ollama_messages = messages[-6:]
    if journal_mode:
        sys_prompt = shaman_journal.build_memory_system_prompt(current_query=user_text, max_recent=5, max_recalled=4)
        ollama_messages = [{"role": "system", "content": sys_prompt}] + ollama_messages

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _worker():
        collected: List[str] = []
        run_messages = list(ollama_messages)
        try:
            if user_text.strip() and looks_like_math(user_text):
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    json.dumps({"message": {"thinking": "Computing exact math..."}}) + "\n",
                )
                math_res = solve_math_exact(user_text, model=model)
                if math_res and math_res.get("output"):
                    prefix = f"Exact Calculation (Python/SymPy):\n{math_res['output']}\n\n"
                    collected.append(prefix)
                    loop.call_soon_threadsafe(
                        q.put_nowait,
                        json.dumps({"message": {"content": prefix}}) + "\n",
                    )
                    run_messages = run_messages + [
                        {
                            "role": "system",
                            "content": (
                                "Verified Python/SymPy calculation output:\n"
                                f"{math_res['output']}\n"
                                "Briefly explain this exact answer without altering any numbers."
                            ),
                        }
                    ]

            if model.startswith(("openrouter:", "groq:")):
                prefix, remote_model = model.split(":", 1)
                providers = {
                    "openrouter": (
                        "OpenRouter",
                        "https://openrouter.ai/api/v1/chat/completions",
                        os.getenv("OPENROUTER_API_KEY") or "",
                    ),
                    "groq": (
                        "Groq",
                        "https://api.groq.com/openai/v1/chat/completions",
                        os.getenv("GROQ_API_KEY") or os.getenv("BRAIN_API_KEY") or "",
                    ),
                }
                provider_label, endpoint_url, api_key = providers[prefix]
                with requests.post(
                    endpoint_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": remote_model, "messages": run_messages, "stream": True, "max_tokens": 900},
                    stream=True,
                    timeout=(10, 60),
                ) as r:
                    if not r.ok:
                        err_detail = (r.text or "").strip()[:250]
                        msg = f"{provider_label} HTTP {r.status_code}" + (f": {err_detail}" if err_detail else "")
                        loop.call_soon_threadsafe(q.put_nowait, json.dumps({"error": msg}) + "\n")
                    else:
                        for line in r.iter_lines():
                            if not line:
                                continue
                            text_line = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                            if not text_line.startswith("data:"):
                                continue
                            payload_str = text_line[5:].strip()
                            if payload_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload_str)
                                delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                                if delta:
                                    collected.append(delta)
                                    loop.call_soon_threadsafe(
                                        q.put_nowait,
                                        json.dumps({"message": {"content": delta}}) + "\n",
                                    )
                            except Exception:
                                pass
            else:
                with requests.post(
                    "http://127.0.0.1:11434/api/chat",
                    json={
                        "model": model,
                        "messages": run_messages,
                        "stream": True,
                        "keep_alive": "30m",
                        "options": {"num_predict": 450},
                    },
                    stream=True,
                    timeout=(10, 600),
                ) as r:
                    if not r.ok:
                        loop.call_soon_threadsafe(q.put_nowait, json.dumps({"error": f"HTTP {r.status_code}"}) + "\n")
                    else:
                        for line in r.iter_lines():
                            if line:
                                text_line = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                                try:
                                    parsed = json.loads(text_line)
                                    piece = (parsed.get("message") or {}).get("content") or ""
                                    if piece:
                                        collected.append(piece)
                                except Exception:
                                    pass
                                loop.call_soon_threadsafe(q.put_nowait, text_line + "\n")
            if journal_mode and user_text.strip() and collected:
                shaman_journal.add_entry(
                    user_text=user_text,
                    reflection="".join(collected).strip(),
                    model=model,
                    image_preview=image_preview,
                )
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, json.dumps({"error": str(exc)}) + "\n")
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=_worker, daemon=True).start()

    async def _gen():
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield "\n"
                continue
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


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


@app.get("/api/science/dual-progress")
async def get_science_dual_progress():
    from pathlib import Path
    import collections
    mem_dir = Path(science_bot.DB_FILE).parent if hasattr(science_bot, "DB_FILE") else Path(__file__).resolve().parent / "memory"
    dpo_file = mem_dir / "training" / "onpolicy_dpo_pairs_v3.jsonl"
    live_file = mem_dir / "training" / "runpod_live_progress.json"
    dpo_count = 0
    modes = collections.Counter()
    if dpo_file.exists():
        for line in dpo_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            dpo_count += 1
            try:
                m = json.loads(line).get("failure_mode") or "other"
                modes[m] += 1
            except Exception:
                pass
    live = {}
    if live_file.exists():
        try:
            live = json.loads(live_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            live = {}
    return {
        "pod1_a40": {
            "dpo_pairs": dpo_count,
            "target": 692,
            "failure_modes": dict(modes),
        },
        "pod2_4090": live,
    }


@app.post("/api/science/alerts")
async def toggle_science_phone_alerts(request: Request):
    body = await request.json()
    enabled = bool(body.get("enabled", True))
    os.environ["PHONE_ALERTS_ENABLED"] = "1" if enabled else "0"
    science_bot._emit("status", science_bot.get_status())
    return {"status": science_bot.get_status(), "phone_alerts_enabled": enabled}


@app.post("/api/science/test-alert")
async def test_science_phone_alert():
    from science_bot import send_phone_alert
    ok = send_phone_alert(
        {
            "id": "",
            "title": "SideQuestAI Phone Alerts Active",
            "domain": "ScienceBot",
            "insight": "You will get a push notification whenever ScienceBot verifies a high-novelty or Empirical Lead discovery.",
            "novelty_score": 85,
            "is_unique": True,
            "verified": True,
        },
        force=True,
    )
    return {"sent": ok, "topic": os.getenv("NTFY_TOPIC", "")}


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
