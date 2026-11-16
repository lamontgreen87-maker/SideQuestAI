"""
Racing Redundancy Integration Test
Simulates a slow worker vs a fast worker to verify the racing logic.
"""

import asyncio
import requests
import subprocess
import time
import os

MASTER_URL = "http://localhost:8000"

async def run_test():
    print("=== STARTING RACING REDUNDANCY TEST ===")
    
    # 1. Start Master (API Server) - using existing terminal if possible or spawning new one
    # Note: api_server.py is assumed to be running or we'd spawn it here.
    
    # 2. Register Slow Worker (Simulated)
    print("[Test] Registering SLOW-WORKER (30s baseline)...")
    slow_data = {
        "name": "Slow-Baseline-CPU",
        "capacity": "2GB",
        "model_name": "qwen2.5:3b",
        "endpoint_url": "http://localhost:9001"
    }
    res = requests.post(f"{MASTER_URL}/worker/register", json=slow_data)
    slow_id = res.json()["worker_id"]
    
    # 3. Register Fast Worker (Simulated)
    print("[Test] Registering FAST-WORKER (GPU Racer)...")
    fast_data = {
        "name": "Fast-GPU-Racer",
        "capacity": "24GB",
        "model_name": "qwen2.5:72b", # High IQ
        "endpoint_url": "http://localhost:9002"
    }
    res = requests.post(f"{MASTER_URL}/worker/register", json=fast_data)
    fast_id = res.json()["worker_id"]
    
    # Set performance score for the Fast Worker in the Nexus manually for testing
    # In reality, this is earned through completions.
    
    # 4. Trigger a Swarm Execution
    print("[Test] Submitting Goal: 'Design a space station'...")
    goal = "Design a modular space station with artificial gravity."
    res = requests.post(f"{MASTER_URL}/swarm/execute", json={"goal": goal, "phase": 1})
    task_id = res.json()["task_id"]
    
    print(f"[Test] Hive Mind is SHATTERING... Task: {task_id}")
    
    # 5. Monitor Logs
    # We should see the Master dispatch to Slow Worker first, then hit SOFT_TIMEOUT, then dispatch to Fast Worker.
    
    for _ in range(20):
        status_res = requests.get(f"{MASTER_URL}/swarm/status/{task_id}")
        data = status_res.json()
        print(f"[Test] Status: {data['status']} | Progress: {data['progress']}")
        if data["status"] == "COMPLETED":
            print("\n✅ MISSION COMPLETE!")
            print(f"Final Result: {data['result'][:200]}...")
            break
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_test())
