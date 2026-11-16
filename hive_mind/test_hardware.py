"""
Hardware Tier Multiplier Test
Demonstrates how different GPUs earn credits based on VRAM and model size.
"""

import asyncio
import requests
import time

MASTER_URL = "http://localhost:8000"

async def run_test():
    print("=== STARTING HARDWARE TIER TEST ===")
    
    # 1. Baseline Worker (8GB VRAM, 7B Model) -> 1.0x
    print("[Test] Registering Baseline (8GB, 7B)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Laptop-Host",
        "vram_gb": 8,
        "total_slots": 1,
        "model_name": "qwen2.5:7b",
        "endpoint_url": "http://localhost:9001"
    })
    
    # 2. Pro Worker (16GB VRAM, 14B Model) -> 1.3x * 2.0x = 2.6x
    print("[Test] Registering Pro (16GB, 14B)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Workstation-3080",
        "vram_gb": 16,
        "total_slots": 2,
        "model_name": "qwen2.5:14b",
        "endpoint_url": "http://localhost:9002"
    })
    
    # 3. Ultra Worker (24GB VRAM, 32B Model) -> 2.0x * 3.5x = 7.0x
    print("[Test] Registering Ultra (24GB, 32B)...")
    requests.post(f"{MASTER_URL}/worker/register", json={
        "name": "Server-4090",
        "vram_gb": 24,
        "total_slots": 4,
        "model_name": "qwen2.5:32b",
        "endpoint_url": "http://localhost:9003"
    })
    
    print("\n[Test] Hardware Grid Initialized.")
    print("[Test] Check the dashboard to see the 'EARN' multipliers reflect hardware tiers!")
    print("URL: http://localhost:8000/dashboard/index.html")
    
    # 4. Trigger a small mission to generate completions and payouts
    print("\n[Test] Triggering Mission to verify Payout Logic...")
    requests.post(f"{MASTER_URL}/swarm/execute", json={"goal": "Verify the payout stack.", "phase": 1})
    
    for _ in range(5):
        network_res = requests.get(f"{MASTER_URL}/worker/network")
        data = network_res.json()
        print(f"[Test] Global Credits Generated: {data['total_payout_pool']:.1f}")
        await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run_test())
