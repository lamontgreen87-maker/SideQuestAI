"""
Worker Nexus: Distributed Execution Registry
Manages worker registration, health, capacity (slots), and performance-based rewards.
"""

import time
import json
import uuid

class WorkerNexus:
    """Central registry and monitoring for community-hosted workers."""
    
    def __init__(self):
        self.active_workers = {} # worker_id -> info
        self.payout_ledger = {}  # worker_id -> total_credits
        self.pending_escrow = {} # shard_id -> {writer_id, amount}
        self.task_history = []    # List of all completed task metadata
        
    def register_worker(self, data):
        """
        Register a new community worker with hardware stats.
        data: { name, vram_gb, total_slots, model_name, endpoint_url }
        """
        worker_id = str(uuid.uuid4())[:8]
        vram = data.get("vram_gb", 8)
        
        # Hardware Tiering Logic
        # Tier 3 (Baseline): < 12GB VRAM (e.g., Laptop, old GPU)
        # Tier 2 (Pro): 12GB - 23GB VRAM (e.g., 3060, 4070)
        # Tier 1 (Ultra): 24GB+ VRAM (e.g., 3090, 4090, A6000)
        hw_multiplier = 1.0
        if vram >= 24: hw_multiplier = 2.0
        elif vram >= 12: hw_multiplier = 1.3
        
        # Model Complexity Multiplier (Reward hosting larger models)
        model = data.get("model_name", "").lower()
        model_multiplier = 1.0
        capability_tier = 1 # Default (3B models)
        
        if "70b" in model: 
            model_multiplier = 5.0
            capability_tier = 3
        elif "32b" in model: 
            model_multiplier = 3.5
            capability_tier = 3
        elif "14b" in model or "13b" in model: 
            model_multiplier = 2.0
            capability_tier = 2
        elif "8b" in model or "7b" in model: 
            model_multiplier = 1.0
            capability_tier = 2
        elif "3b" in model:
            capability_tier = 1
        
        self.active_workers[worker_id] = {
            "name": data.get("name", "Unknown Worker"),
            "vram_gb": vram,
            "total_slots": data.get("total_slots", 1),
            "active_slots": 0,
            "model_name": data.get("model_name", "qwen2.5:7b"),
            "endpoint_url": data.get("endpoint_url"),
            "last_heartbeat": time.time(),
            "first_seen": time.time(),
            "status": "ready",
            "shards_completed": 0,
            "avg_completion_time": 0.0,
            "performance_score": 100.0,
            "hw_multiplier": hw_multiplier,
            "model_multiplier": model_multiplier,
            "capability_tier": capability_tier,
            "payout_history": [] # Timestamps of payouts
        }
        
        if worker_id not in self.payout_ledger:
            self.payout_ledger[worker_id] = 0
            
        print(f"[WorkerNexus] Registered {worker_id} ({data.get('name')}) | Tier: {capability_tier} | Multiplier: {hw_multiplier * model_multiplier}x")
        return worker_id

    def reserve_slot(self, worker_id):
        """Immediately take a slot to prevent over-allocation."""
        if worker_id in self.active_workers:
            w = self.active_workers[worker_id]
            if w["active_slots"] < w["total_slots"]:
                w["active_slots"] += 1
                w["status"] = "ready" if w["active_slots"] < w["total_slots"] else "busy"
                return True
        return False

    def release_slot(self, worker_id):
        """Release a slot after task completion."""
        if worker_id in self.active_workers:
            w = self.active_workers[worker_id]
            w["active_slots"] = max(0, w["active_slots"] - 1)
            w["status"] = "ready"
            return True
        return False

    def heartbeat(self, worker_id, active_slots=None):
        """Update last seen time and current load."""
        if worker_id in self.active_workers:
            w = self.active_workers[worker_id]
            w["last_heartbeat"] = time.time()
            if active_slots is not None:
                w["active_slots"] = active_slots
            
            w["status"] = "ready" if w["active_slots"] < w["total_slots"] else "busy"
            return True
        return False

    def get_available_workers(self):
        """Return list of workers with free slots and recent heartbeats."""
        now = time.time()
        available = []
        for wid, info in self.active_workers.items():
            if now - info["last_heartbeat"] < 60 and info["active_slots"] < info["total_slots"]:
                available.append({"id": wid, **info})
        return available

    def record_completion(self, worker_id, duration):
        """Record how long it took to complete a shard."""
        if worker_id in self.active_workers:
            w = self.active_workers[worker_id]
            if w["shards_completed"] == 0:
                w["avg_completion_time"] = duration
            else:
                w["avg_completion_time"] = (w["avg_completion_time"] * 0.7) + (duration * 0.3)
            
            w["shards_completed"] += 1
            
            # Speed scoring
            baseline = 30.0
            w["performance_score"] = (baseline / max(w["avg_completion_time"], 0.1)) * 100
            return True
        return False

    def record_pending_payout(self, worker_id, shard_id, base_credits=1.0):
        """Put credits in escrow pending audit."""
        if worker_id not in self.active_workers: return False
        w = self.active_workers[worker_id]
        
        # Calculate potential payout
        perf_mult = 1.0
        perf = w["performance_score"]
        if perf > 150: perf_mult = 1.5
        elif perf > 120: perf_mult = 1.2
        
        stack_mult = w["hw_multiplier"] * w["model_multiplier"]
        escrow_amount = base_credits * perf_mult * stack_mult
        
        self.pending_escrow[shard_id] = {
            "writer_id": worker_id,
            "amount": escrow_amount
        }
        print(f"[WorkerNexus] Shard {shard_id} escrowed: {escrow_amount:.2f} credits (Pending Audit)")
        return True

    def release_escrow(self, shard_id, audit_success=True, auditor_id=None):
        """Finalize payout after audit or reject if malicious."""
        if shard_id not in self.pending_escrow: return False
        
        data = self.pending_escrow.pop(shard_id)
        writer_id = data["writer_id"]
        amount = data["amount"]
        
        if audit_success:
            # 1. Pay the Writer
            if writer_id in self.payout_ledger:
                self.payout_ledger[writer_id] += amount
                if writer_id in self.active_workers:
                    self.active_workers[writer_id]["payout_history"].append(time.time())
                print(f"[WorkerNexus] Audit PASSED for {shard_id}. Released {amount:.2f} credits to {writer_id}.")
            
            # 2. Pay the Auditor (Mobile Critic Incentive)
            if auditor_id and auditor_id in self.payout_ledger:
                audit_fee = amount * 0.1 # 10% fee for auditing
                self.payout_ledger[auditor_id] += audit_fee
                if auditor_id in self.active_workers:
                    self.active_workers[auditor_id]["payout_history"].append(time.time())
                print(f"[WorkerNexus] Auditor {auditor_id} earned {audit_fee:.2f} credits.")
        else:
            print(f"[WorkerNexus] Audit FAILED for {shard_id}. Escrow burned.")
            
        return True

    def record_payout(self, worker_id, base_credits):
        # ... (Old method kept for direct non-audited payouts like shattering)
        if worker_id in self.payout_ledger:
            w = self.active_workers.get(worker_id)
            if not w: return False
            stack_mult = w["hw_multiplier"] * w["model_multiplier"]
            total_earning = base_credits * stack_mult
            self.payout_ledger[worker_id] += total_earning
            return True
        return False

    def get_status(self):
        now = time.time()
        available = self.get_available_workers()
        total_slots = sum(w["total_slots"] for w in self.active_workers.values())
        active_slots = sum(w["active_slots"] for w in self.active_workers.values())
        
        # Calculate Economy Stats
        total_credits = sum(self.payout_ledger.values())
        worker_stats = []
        for wid, w in self.active_workers.items():
            if now - w["last_heartbeat"] > 60: continue
            
            # Calculate Payout Frequency (credits per hour)
            life_span_hours = max((now - w["first_seen"]) / 3600, 0.1)
            total_earned = self.payout_ledger.get(wid, 0)
            avg_payout_per_hour = total_earned / life_span_hours
            
            # Recent Payout Frequency (last 1 hour)
            recent_payouts = [p for p in w["payout_history"] if now - p < 3600]
            frequency = len(recent_payouts)

            worker_stats.append({
                "id": wid,
                **w,
                "total_earned": total_earned,
                "hourly_rate": round(avg_payout_per_hour, 2),
                "frequency_rate": frequency # payouts in last hour
            })

        avg_hourly_net = sum(w["hourly_rate"] for w in worker_stats) / max(len(worker_stats), 1)

        return {
            "total_registered": len(self.active_workers),
            "active_now": len(available),
            "total_slots": total_slots,
            "active_slots": active_slots,
            "worker_details": worker_stats,
            "total_payout_pool": total_credits,
            "avg_hourly_net": round(avg_hourly_net, 2)
        }
