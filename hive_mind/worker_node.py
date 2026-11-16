"""
Worker Node: Community Muscle
This script runs on a community member's machine.
It connects to the Hive Master and executes worker shards.
"""

import os
import requests
import json
import time
import uuid
import asyncio
import traceback
from fastapi import FastAPI, Request
import uvicorn
import threading

# Configuration from Environment
MASTER_URL = os.getenv("MASTER_URL", "http://localhost:8000")
LOCAL_NAME = os.getenv("WORKER_NAME", f"GPU-Worker-{uuid.uuid4().hex[:4]}")
LOCAL_MODEL = os.getenv("WORKER_MODEL", "qwen2.5:7b")
PORT = int(os.getenv("WORKER_PORT", 9000))
CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", 1))
ERROR_LOG = os.getenv("WORKER_ERROR_LOG", "worker_errors.log")

def get_gpu_vram():
    """Attempt to detect GPU VRAM via nvidia-smi."""
    try:
        import subprocess
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,nounit,noheader"],
            encoding='utf-8'
        )
        # Convert MB to GB
        return int(result.strip().split('\n')[0]) // 1024
    except:
        return 8 # Default fallback

class WorkerNode:
    """A community worker instance with hardware profiling."""
    
    def __init__(self, name, model, port, concurrency):
        self.name = name
        self.model = model
        self.port = port
        self.concurrency = concurrency
        self.vram = int(os.getenv("WORKER_VRAM", get_gpu_vram()))
        self.semaphore = asyncio.Semaphore(concurrency)
        self.worker_id = None
        self.active_tasks = 0
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/execute")
        async def execute_task(request: Request):
            data = await request.json()
            # Wait for a free slot
            async with self.semaphore:
                self.active_tasks += 1
                try:
                    task = data.get("task")
                    if os.getenv("DISABLE_THINK", "0") == "1" and self.model.startswith("qwen3:"):
                        task = f"{task} /no_think"
                    print(f"\n[{self.name}] SLOT ACQUIRED. PROCESSING: {task[:100]}...")
                    
                    start_time = time.time()
                    loop = asyncio.get_event_loop()
                    
                    is_audit = task.strip().upper().startswith("AUDIT") or "AUDIT THE FOLLOWING SHARD OUTCOME" in task.upper()
                    if is_audit:
                        system_prompt = (
                            "You are a strict audit critic. "
                            "Respond with ONLY 'PASS' or 'FAIL: <short reason>'. "
                            "Do not include any other content."
                        )
                    else:
                        system_prompt = (
                            "You are a specialized Hive Mind Worker. "
                            "Provide a direct and concise completion. "
                            "Do NOT delegate or return meta-instructions."
                        )
                    
                    def call_ollama():
                        try:
                            return requests.post(
                                "http://localhost:11434/api/generate",
                                json={
                                    "model": self.model,
                                    "system": system_prompt,
                                    "prompt": task,
                                    "stream": False
                                }
                            )
                        except Exception as exc:
                            try:
                                with open(ERROR_LOG, "a", encoding="utf-8") as log:
                                    log.write(f"[{time.time()}] Ollama request error: {exc}\n")
                                    log.write(traceback.format_exc())
                                    log.write("\n")
                            except Exception:
                                pass
                            return exc

                    response = await loop.run_in_executor(None, call_ollama)
                    duration = time.time() - start_time
                    
                    if isinstance(response, Exception):
                        return {"status": "error", "error": f"Ollama request failed: {response}"}
                    if response.status_code == 200:
                        outcome = response.json().get("response")
                        print(f"[{self.name}] SHARD COMPLETE ({duration:.2f}s)")
                        
                        # Report to Master
                        try:
                            await loop.run_in_executor(None, lambda: requests.post(
                                f"{MASTER_URL}/worker/complete", 
                                json={
                                    "worker_id": self.worker_id,
                                    "duration": duration,
                                    "credits": 1.0
                                }
                            ))
                        except: pass
                            
                        return {"status": "success", "output": outcome, "model_used": self.model, "duration": duration}
                    else:
                        return {"status": "error", "error": f"Ollama failed: {response.status_code}"}
                finally:
                    self.active_tasks -= 1

    def heartbeat_loop(self):
        """Stay alive in the Nexus and report current load."""
        while True:
            try:
                res = requests.post(
                    f"{MASTER_URL}/worker/heartbeat/{self.worker_id}",
                    json={"active_slots": self.active_tasks},
                    timeout=5
                )
                if res.status_code == 404:
                    print(f"[{self.name}] Master lost registration (404). Re-registering...")
                    self.worker_id = None
                    self.start() # This will block until registered again
                    break # Break this loop, start() will spawn a new one
            except Exception as e:
                print(f"[{self.name}] Master heartbeat failed: {e}")
            time.sleep(10) # Faster heartbeat for better responsiveness

    def start(self):
        print(f"--- Hive Worker Node: {self.name} ---")
        print(f"--- Brain: {self.model} | HW: {self.vram}GB VRAM | Slots: {self.concurrency} ---")
        
        while not self.worker_id:
            try:
                my_url = f"http://localhost:{self.port}" 
                reg_data = {
                    "name": self.name,
                    "vram_gb": self.vram,
                    "total_slots": self.concurrency,
                    "model_name": self.model,
                    "endpoint_url": my_url
                }
                
                print(f"[{self.name}] Attempting to register with Master at {MASTER_URL}...", flush=True)
                res = requests.post(f"{MASTER_URL}/worker/register", json=reg_data, timeout=5)
                
                if res.status_code == 200:
                    self.worker_id = res.json().get("worker_id")
                    print(f"[SUCCESS] Registered! ID: {self.worker_id}")
                    threading.Thread(target=self.heartbeat_loop, daemon=True).start()
                else:
                    print(f"[ERROR] Registration failed: {res.text}. Retrying in 5s...", flush=True)
                    time.sleep(5)
            except Exception as e:
                print(f"[ERROR] Could not reach Master: {e}. Retrying in 5s...", flush=True)
                time.sleep(5)

        uvicorn.run(self.app, host="0.0.0.0", port=self.port)

if __name__ == "__main__":
    node = WorkerNode(LOCAL_NAME, LOCAL_MODEL, PORT, CONCURRENCY)
    node.start()
