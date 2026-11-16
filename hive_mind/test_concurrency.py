"""
Multi-Slot Concurrency Test
Spawns two workers with different capacities to show slot-based distribution.
"""

import asyncio
import requests
import time

MASTER_URL = "http://localhost:8000"

async def run_test():
    print("=== STARTING MULTI-SLOT CONCURRENCY TEST ===")
    
    # 1. Register "Baseline" Worker (1 Slot)
    print("[Test] Registering Baseline Worker (1 Slot)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Local-Laptop",
        "capacity": "8GB",
        "total_slots": 1,
        "model_name": "qwen2.5:3b",
        "endpoint_url": "http://localhost:9001"
    })
    
    # 2. Register "Beast" Worker (4 Slots)
    print("[Test] Registering Beast Worker (4 Slots)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "RTX-4090-Server",
        "capacity": "24GB",
        "total_slots": 4,
        "model_name": "qwen2.5:14b",
        "endpoint_url": "http://localhost:9002"
    })
    
    # 3. Submit a goal with many shards
    print("[Test] Submitting Large Goal...")
    goal = "Create a 10-chapter epic space opera outline with character backstories and tech specs for 5 ships."
    res = requests.post(f"{MASTER_URL}/swarm/execute", json={"goal": goal, "phase": 1})
    task_id = res.json()["task_id"]
    
    print(f"\n[Test] Mission Active: {task_id}")
    print("[Test] OPEN THE DASHBOARD TO SEE THE SLOTS IN ACTION:")
    print("URL: http://localhost:8000/dashboard/index.html")
    
    for _ in range(15):
        network_res = requests.get(f"{MASTER_URL}/worker/network")
        data = network_res.json()
        print(f"[Test] Global Load: {data['active_slots']}/{data['total_slots']} Slots Active")
        await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run_test())
