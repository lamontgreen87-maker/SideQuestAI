"""
Fractal Shattering Test
Verifies that complex shards are recursively broken down by 'Manager' models.
"""

import asyncio
import requests
import time

MASTER_URL = "http://localhost:8000"

async def run_test():
    print("=== STARTING FRACTAL SHATTERING TEST ===")
    
    # 1. Register a Tier 3 "Manager" Worker
    # We'll use a mock worker that we know will trigger delegation
    print("[Test] Registering Tier 3 Manager (Server-4090)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Manager-Node",
        "vram_gb": 24,
        "total_slots": 1,
        "model_name": "qwen2.5:32b",
        "endpoint_url": "http://localhost:9005"
    })
    
    # 2. Register a Tier 1 "Muscle" Worker to handle the sub-tasks
    print("[Test] Registering Tier 1 Muscle (Laptop)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Muscle-Node",
        "vram_gb": 8,
        "total_slots": 4,
        "model_name": "qwen2.5:3b",
        "endpoint_url": "http://localhost:9006"
    })

    print("\n[Test] TO MANUALLY TEST DELEGATION:")
    print("1. When the Manager-Node receives a task (check logs below),")
    print("2. It should realize the task is complex (manual or via simulated response).")
    print("3. In this test context, we'll watch how the Overmind handles a 'DELEGATE:' string.")
    
    # 3. Submit a goal that requires planning
    print("\n[Test] Submitting Complex Goal...")
    goal = "Design a complete solar-powered water filtration system for a village of 500 people."
    res = requests.post(f"{MASTER_URL}/swarm/execute", json={"goal": goal, "phase": 1})
    task_id = res.json()["task_id"]
    
    print(f"\n[Test] Mission Active: {task_id}")
    print("[Test] Check the dashboard to see the 'RECURSIVE SHATTER' telemetry!")
    
    for _ in range(10):
        status_res = requests.get(f"{MASTER_URL}/swarm/status/{task_id}")
        data = status_res.json()
        print(f"[Test] Status: {data['status']} | Last Update: {data['result'][:100] if data['result'] else 'None'}")
        if data['status'] == "COMPLETED": break
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_test())
