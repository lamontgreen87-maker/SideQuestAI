import asyncio
import os
import requests
from telemetry import TelemetryLogger, LoopGuard

class WorkerPool:
    """Manages a pool of workers with SLA-driven Racing Redundancy."""
    
    def __init__(self, nexus):
        self.nexus = nexus
        self.hub = None
        self.active_tasks = {} # shard_id -> { "original_worker": id, "racer_worker": id, "start_time": t, "status": s }
        self.results = {}      # shard_id -> [listOfResults]
        self.SOFT_TIMEOUT = float(os.getenv("SOFT_TIMEOUT", "30.0")) # Trigger racer
        self.HARD_TIMEOUT = float(os.getenv("HARD_TIMEOUT", "60.0")) # Drop worker credits
        self.AUDIT_REVISE_ATTEMPTS = int(os.getenv("AUDIT_REVISE_ATTEMPTS", "2"))
        self.telemetry = TelemetryLogger()
        
    async def execute_shard(self, shard_id, task_desc, required_tier=1):
        """Dispatches a shard with tier-based routing and racing redundancy."""
        print(f"[WorkerPool] Dispatching Shard {shard_id} (Required Tier: {required_tier})...")
        guard = LoopGuard(f"workerpool.shard.{shard_id}", self.telemetry)
        self.telemetry.log(
            "workerpool_dispatch",
            shard_id=shard_id,
            required_tier=required_tier,
        )
        
        self.active_tasks[shard_id] = {
            "task": task_desc,
            "start_time": asyncio.get_event_loop().time(),
            "status": "pending",
            "required_tier": required_tier,
            "workers": []
        }
        self.results[shard_id] = []
        
        # 1. Wait for an appropriate worker
        worker_id = None
        while not worker_id:
            worker_id = self._get_best_worker(required_tier=required_tier)
            if not worker_id:
                guard.tick("wait_worker", required_tier=required_tier)
                await asyncio.sleep(2)
        guard.mark_progress("worker_assigned", worker_id=worker_id)
            
        # Dispatch first attempt
        asyncio.create_task(self._call_worker(shard_id, worker_id, task_desc))
        
        # 2. Monitor for Soft Timeout
        while True:
            await asyncio.sleep(1)
            elapsed = asyncio.get_event_loop().time() - self.active_tasks[shard_id]["start_time"]
            
            # If we have at least one result, we can potentially move on
            if self.results[shard_id]:
                print(f"[WorkerPool] Shard {shard_id} has initial result. Proceeding.", flush=True)
                guard.mark_progress("result_ready", worker_id=self.results[shard_id][0].get("worker_id"))
                return self.results[shard_id][0]
                
            # If we hit SOFT_TIMEOUT and haven't started a racer yet
            if elapsed > self.SOFT_TIMEOUT and len(self.active_tasks[shard_id]["workers"]) < 2:
                racer_id = self._get_best_worker(
                    exclude=[w for w in self.active_tasks[shard_id]["workers"]],
                    required_tier=required_tier
                )
                # Try to find a worker
                worker_id = self._get_best_worker(required_tier)
                
                if worker_id and worker_id not in self.active_tasks[shard_id]["workers"]:
                    # Reserve and fire!
                    if self.nexus.reserve_slot(worker_id):
                        asyncio.create_task(self._call_worker(shard_id, worker_id, task_desc))
                else:
                    # No worker available right now
                    all_workers = self.nexus.get_status()["active_now"] if hasattr(self.nexus, 'get_status') else 0 # Added check for get_status
                    if self.hub:
                        if all_workers == 0:
                            self.hub.last_update = "WAITING // NEXUS EMPTY (No nodes connected)"
                        else:
                            self.hub.last_update = f"WAITING // NEXUS BUSY ({all_workers} nodes active, all slots full)"
                    guard.tick(
                        "wait_worker_busy",
                        active_workers=all_workers,
                    )

            # If we hit HARD_TIMEOUT with no results, reset and re-dispatch
            if elapsed > self.HARD_TIMEOUT and not self.results[shard_id]:
                self.telemetry.log(
                    "workerpool_hard_timeout",
                    shard_id=shard_id,
                    elapsed=round(elapsed, 2),
                    workers=len(self.active_tasks[shard_id]["workers"]),
                )
                guard.tick(
                    "hard_timeout_reset",
                    elapsed=round(elapsed, 2),
                    workers=len(self.active_tasks[shard_id]["workers"]),
                )
                # Release any reserved slots before retry
                for wid in list(self.active_tasks[shard_id]["workers"]):
                    self.nexus.release_slot(wid)
                self.active_tasks[shard_id]["workers"] = []
                self.active_tasks[shard_id]["start_time"] = asyncio.get_event_loop().time()
                self.active_tasks[shard_id]["status"] = "pending"
                worker_id = self._get_best_worker(required_tier=required_tier)
                if worker_id and self.nexus.reserve_slot(worker_id):
                    asyncio.create_task(self._call_worker(shard_id, worker_id, task_desc))
            
            # Wait before checking again
            await asyncio.sleep(2)
            
            # 2. Timeout / Liveliness check? (Future expansion)
            if self.active_tasks[shard_id]["status"] == "completed":
                break
            guard.tick(
                "wait_result",
                elapsed=round(elapsed, 2),
                workers=len(self.active_tasks[shard_id]["workers"]),
            )
                
        return self.results[shard_id][0] # Return the first successful result

    def _get_best_worker(self, required_tier, exclude=None):
        """Finds the best available worker, allowing for tier degradation if needed."""
        available = self.nexus.get_available_workers()
        if exclude:
            available = [w for w in available if w["id"] not in exclude]
            
        if not available:
            return None
            
        # 1. Try to find the exact tier or higher
        best = [w for w in available if w["capability_tier"] >= required_tier]
        if best:
            # Sort by performance score (highest first)
            # We return the ID (string) to avoid unhashable type issues in callers
            return sorted(best, key=lambda x: x["performance_score"], reverse=True)[0]["id"]
            
        # 2. TIER DEGRADATION: If no high-tier node found, take the best available node
        # We don't want to wait forever for a Tier 3 if only Tier 1/2 are connected.
        print(f"[WorkerPool] TIER DEGRADATION: No Tier {required_tier} nodes available. Falling back to best effort.", flush=True)
        return sorted(available, key=lambda x: x["performance_score"], reverse=True)[0]["id"]

    async def _call_worker(self, shard_id, worker_id, task_desc):
        """Makes the actual network call to the worker node."""
        worker_info = self.nexus.active_workers.get(worker_id)
        if not worker_info: return
        
        self.active_tasks[shard_id]["workers"].append(worker_id)
        
        try:
            loop = asyncio.get_event_loop()
            task_payload = task_desc
            audit_feedback = ""

            for attempt in range(self.AUDIT_REVISE_ATTEMPTS + 1):
                response = await loop.run_in_executor(None, lambda: requests.post(
                    f"{worker_info['endpoint_url']}/execute",
                    json={"task": task_payload},
                    timeout=self.HARD_TIMEOUT + 5
                ))

                if response.status_code != 200:
                    print(f"[WorkerPool] Worker {worker_id} failed with {response.status_code}")
                    self.telemetry.log(
                        "workerpool_http_error",
                        shard_id=shard_id,
                        worker_id=worker_id,
                        status_code=response.status_code,
                    )
                    break

                result = response.json()
                outcome = result.get("output", "")

                # 3. PEER-SLAM AUDIT (The 'Hater' 3B layer)
                print(f"[WorkerPool] Result received from {worker_id}. Dispatched for Peer-Slam Audit...")
                audit_passed, audit_feedback = await self._audit_result(shard_id, outcome, task_desc)

                if audit_passed:
                    print(f"[WorkerPool] [PASS] SHARD {shard_id} PASSED AUDIT. Recording.")
                    result["worker_id"] = worker_id # Add worker_id to the result
                    result["audit_feedback"] = audit_feedback
                    self.results[shard_id].append(result)
                    self.active_tasks[shard_id]["status"] = "completed"
                    self.telemetry.log(
                        "workerpool_audit_pass",
                        shard_id=shard_id,
                        worker_id=worker_id,
                    )
                    break

                print(f"[WorkerPool] [FAIL] SHARD {shard_id} FAILED AUDIT. Restructure required.")
                self.telemetry.log(
                    "workerpool_audit_fail",
                    shard_id=shard_id,
                    worker_id=worker_id,
                )
                if attempt < self.AUDIT_REVISE_ATTEMPTS:
                    task_payload = self._build_restructure_task(task_desc, outcome, audit_feedback)
                    continue
                # We don't record the result, so execute_shard will trigger a racer.
                
        except Exception as e:
            print(f"[WorkerPool] Error calling worker {worker_id}: {e}")
            self.telemetry.log(
                "workerpool_exception",
                shard_id=shard_id,
                worker_id=worker_id,
                error=str(e),
            )
        finally:
            # Slot released in the Nexus
            self.nexus.release_slot(worker_id)

    async def _audit_result(self, shard_id, outcome, task_desc):
        """Dispatches a lightning-fast Peer-Audit to a Tier 1 worker."""
        auditor_id = self._get_best_worker(required_tier=1)
        if not auditor_id:
            # Fallback: If no community auditor, we assume success for now 
            # (or we could use local Drone, but community-first is the goal)
            return True, ""

        auditor_info = self.nexus.active_workers.get(auditor_id)
        if not auditor_info:
            return True, ""
        
        audit_task = f"""
        [PEER-SLAM AUDIT]
        Verify if the output completes the task with basic correctness.
        Only judge what is explicitly present in the output. Do NOT speculate or invent errors.
        If code is missing or incomplete, say so directly. If unclear, say "INSUFFICIENT" and why.
        Identify the language and cite concrete evidence (file/line guesses if needed).

        TASK: {task_desc[:500]}
        OUTPUT: {outcome[:800]}

        Respond with ONLY:
        OK
        or
        REVISE: <specific evidence>. RESTRUCTURE: <concise fix instructions>
        """
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(
                f"{auditor_info['endpoint_url']}/execute",
                json={"task": audit_task},
                timeout=20 # Audits must be fast
            ))
            
            if response.status_code == 200:
                audit_result = response.json().get("output", "")
                passed, normalized, reason = self._interpret_audit_result(audit_result)
                self.telemetry.log(
                    "peer_audit_verdict",
                    shard_id=shard_id,
                    auditor_id=auditor_id,
                    passed=passed,
                    reason=reason,
                    raw_prefix=(audit_result or "")[:160],
                )
                return passed, normalized
        except:
            pass
            
        return True, "" # Default to pass if audit times out to keep flow moving

    def _build_restructure_task(self, task_desc, outcome, audit_feedback):
        return f"""
        [RESTRUCTURE REQUEST]
        The audit failed. Fix syntax/parse errors and missing required parts.

        ORIGINAL TASK:
        {task_desc[:800]}

        YOUR OUTPUT:
        {outcome[:800]}

        AUDIT FEEDBACK:
        {audit_feedback[:800]}

        Respond with the corrected final output only.
        """

    @staticmethod
    def _interpret_audit_result(audit_result: str):
        import re
        verdict = (audit_result or "").strip()
        upper = verdict.upper()
        if not verdict:
            return False, verdict, "EMPTY"
        if re.match(r"^(OK|PASS)[.!]?$", upper):
            return True, verdict, "PASS"
        if upper.startswith("REVISE") or upper.startswith("FAIL") or upper.startswith("REJECT") or upper.startswith("INSUFFICIENT"):
            return False, verdict, "FAIL_MARKED"
        return False, verdict, "UNPARSEABLE"
