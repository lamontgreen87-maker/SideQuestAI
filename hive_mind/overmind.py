import asyncio
import json
import os
import sys
from drone import DroneAgent
from consensus import ConsensusEngine
from runpod_orchestrator import RunPodOrchestrator
from dependency_resolver import DependencyResolver
from assembly_validator import AssemblyValidator
from success_checker import SuccessChecker
from worker_pool import WorkerPool
from project_memory import ProjectMemory
from shard_validator import ShardValidator
from shatter_cache import load_shatter_examples, format_examples_for_prompt
from shatter_export import export_shatter
from telemetry import TelemetryLogger, LoopGuard

class Overmind:
    """
    The Central Hub.
    Handles global decomposition, redundancy (Vantage Points), and consensus.
    Phase 2: Can ignite remote GPU brains via RunPod.
    """
    def __init__(self, redundancy_factor=3, phase=1, nexus=None, output_format=None, output_file=None):
        self.free_tier_mode = os.getenv(
            "FREE_TIER_MODE",
            "1" if os.getenv("BRAIN_PROVIDER", "custom").lower() != "custom" else "0",
        ) == "1"
        self.redundancy_factor = redundancy_factor
        self.consensus_engine = ConsensusEngine()
        self.runpod = RunPodOrchestrator()
        self.nexus = nexus
        self.worker_pool = WorkerPool(nexus) if nexus else None
        self.phase = phase # 1 = Local (8B), 2 = Remote (72B)
        self.shard_max_chars = int(os.getenv("SHARD_MAX_CHARS", 800))
        self.shard_max_words = int(os.getenv("SHARD_MAX_WORDS", 140))
        self.shard_refine_rounds = int(os.getenv("SHARD_REFINE_ROUNDS", 2))
        self.recombine_max_attempts = int(os.getenv("RECOMBINE_MAX_ATTEMPTS", 2))
        self.enable_success_check = os.getenv("ENABLE_SUCCESS_CHECK", "0") == "1"
        self.enable_consistency_critic = os.getenv("ENABLE_CONSISTENCY_CRITIC", "1") == "1"
        self.consistency_mode = os.getenv("CONSISTENCY_MODE", "shard").lower()
        self.enable_delegation = os.getenv("ENABLE_DELEGATION", "1") == "1"
        self.consistency_critic_count = int(os.getenv("CONSISTENCY_CRITIC_COUNT", 3))
        self.consistency_revise_attempts = int(os.getenv("CONSISTENCY_REVISE_ATTEMPTS", 2))
        self.audit_retry_attempts = int(os.getenv("AUDIT_RETRY_ATTEMPTS", 3))
        self.audit_response_retries = int(os.getenv("AUDIT_RESPONSE_RETRIES", 1))
        self.audit_use_heavy_fix = os.getenv("AUDIT_USE_HEAVY_FIX", "0") == "1"
        self.audit_required_tier = int(os.getenv("AUDIT_REQUIRED_TIER", "1"))
        self.audit_max_chars = int(os.getenv("AUDIT_MAX_CHARS", "8000"))
        self.audit_mode = os.getenv("AUDIT_MODE", "wave").lower()
        self.output_format = output_format or os.getenv("OUTPUT_FORMAT", "single_file")
        self.output_file = output_file or os.getenv("OUTPUT_FILE", "app.py")
        print(f"[Overmind] Initialized in Phase: {self.phase}", flush=True)
        self.status = "INITIALIZING"
        self.last_update = ""
        self.memory = ProjectMemory()
        self.telemetry = TelemetryLogger()
        self.run_guard = LoopGuard("overmind.run_swarm", self.telemetry)
        self.shatter_guard = LoopGuard("overmind.decompose_goal", self.telemetry)
        self.telemetry.log(
            "overmind_init",
            phase=self.phase,
            redundancy=self.redundancy_factor,
            shard_max_chars=self.shard_max_chars,
            shard_max_words=self.shard_max_words,
            consistency_critic=self.enable_consistency_critic,
            consistency_mode=self.consistency_mode,
            output_format=self.output_format,
            output_file=self.output_file,
        )

    def _parse_shatter_output(self, raw_output: str):
        start_idx = raw_output.find('[')
        end_idx = raw_output.rfind(']') + 1
        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON array found in output")
        json_str = raw_output[start_idx:end_idx]
        data = json.loads(json_str)
        if not isinstance(data, list):
            raise ValueError("Parsed JSON is not a list")
        return data

    @staticmethod
    def _language_from_filename(filename: str) -> str:
        lower = (filename or "").lower()
        if lower.endswith(".html") or lower.endswith(".htm"):
            return "html"
        if lower.endswith(".js"):
            return "javascript"
        if lower.endswith(".ts"):
            return "typescript"
        if lower.endswith(".css"):
            return "css"
        if lower.endswith(".py"):
            return "python"
        if lower.endswith(".json"):
            return "json"
        return ""

    def _normalize_shards(self, draft_tasks):
        def flatten_tasks(item):
            flat = []
            if isinstance(item, list):
                for sub in item:
                    flat.extend(flatten_tasks(sub))
            elif isinstance(item, dict) or isinstance(item, str):
                flat.append(item)
            return flat

        validated_tasks = []
        flat_tasks = flatten_tasks(draft_tasks)
        for i, t in enumerate(flat_tasks):
            if isinstance(t, str):
                t = {"id": chr(65 + i), "task": t}
            if isinstance(t, dict):
                t["id"] = t.get("id", chr(65 + i))
                t["task"] = t.get("task", "Unknown Task")
                t["required_tier"] = int(t.get("required_tier", 2))
                t["depends_on"] = t.get("depends_on", [])
                t["inputs"] = t.get("inputs", [])
                t["outputs"] = t.get("outputs", [])
                t["success_criteria"] = t.get("success_criteria", [])
                t["pass_conditions"] = t.get("pass_conditions", [])

                if not isinstance(t["depends_on"], list):
                    t["depends_on"] = [t["depends_on"]]
                if not isinstance(t["inputs"], list):
                    t["inputs"] = [str(t["inputs"])]
                if not isinstance(t["outputs"], list):
                    t["outputs"] = [str(t["outputs"])]
                if not isinstance(t["success_criteria"], list):
                    t["success_criteria"] = [str(t["success_criteria"])]
                if not isinstance(t["pass_conditions"], list):
                    t["pass_conditions"] = [str(t["pass_conditions"])]

                validated_tasks.append(t)

        if not validated_tasks:
            raise ValueError("No valid tasks found in parsed list")
        return validated_tasks

    def _build_shatter_prompt(self, goal, max_chars, max_words, prior=None, report=None, critic_notes=None):
        examples = load_shatter_examples()
        shard_range = "1-2" if self.output_format == "single_file" else "3-4"
        prompt = f"""
SHATTER THE FOLLOWING GOAL into a parallel execution plan with {shard_range} atomic mission shards sized for a 7B coder.

CONSTRAINTS:
1. Each shard must be a single, focused objective.
2. Each task must be <= {max_chars} characters AND <= {max_words} words.
3. Include inputs, outputs, and success_criteria as arrays.
4. Include depends_on (list of shard ids) and required_tier (1-3).
5. Include pass_conditions: explicit, testable acceptance checks tied to the world bible (no code snippets).
6. Prefer independent shards; only add dependencies when truly required.
7. OUTPUT FORMAT for all shards: SINGLE file only named {self.output_file}.

Return ONLY a JSON array with this schema:
[
  {{
    "id": "A",
    "task": "Do X",
    "required_tier": 2,
    "depends_on": [],
    "inputs": ["..."],
    "outputs": ["..."],
    "success_criteria": ["..."],
    "pass_conditions": ["explicit acceptance checks tied to the world bible"]
  }}
]

GOAL: {goal}
"""
        if examples:
            prompt += "\nREFERENCE_SHATTER_PATTERNS:\n" + format_examples_for_prompt(examples)
        if prior:
            prompt += "\nCURRENT_SHARDS:\n" + json.dumps(prior, ensure_ascii=True)
        if report:
            prompt += "\nVALIDATION_ISSUES:\n" + json.dumps(report, ensure_ascii=True)
        if critic_notes:
            prompt += f"\nCRITIC_FEEDBACK:\n{critic_notes}\n"
        return prompt

    async def _critique_shards(self, goal, shards, report):
        prompt = f"""
You are the SHARD CRITIC. Check if the shard plan is small enough for a 7B coder
and if shards are independent, well-scoped, and cover the goal.

GOAL: {goal}
SHARDS: {json.dumps(shards, ensure_ascii=True)}
VALIDATION_REPORT: {json.dumps(report, ensure_ascii=True)}

Respond with ONLY:
PASS
or
FAIL: <short reason and fix guidance>
"""
        critic = DroneAgent("Shatter-Hater", prompt, "audit", role="critic")
        result = await critic.run()
        verdict = result.get("output", "").strip().upper()
        return verdict

    async def _critique_recombine(self, goal, shard_results, final_output, assembly_report=None):
        prompt = f"""
You are the RECOMBINATION CRITIC. Verify the final synthesis is coherent, complete,
and consistent with shard outputs and audits.
Be strict: if the output would not run as a working product, fail it.
Check for internal contradictions (e.g., using item.width/item.height without defining them).
Verify goal requirements and pass conditions are present in the final output.

GOAL: {goal}
SHARD_RESULTS: {json.dumps(shard_results, ensure_ascii=True)}
ASSEMBLY_REPORT: {json.dumps(assembly_report or {}, ensure_ascii=True)}

FINAL_OUTPUT:
{final_output[:2000]}

Respond with ONLY:
PASS
or
FAIL: <short reason and gaps to fix>
"""
        critic = DroneAgent("Recombine-Critic", prompt, "audit", role="critic")
        result = await critic.run()
        verdict = result.get("output", "").strip().upper()
        return verdict

    async def _consistency_audit_shard(self, task_id, task_desc, outcome, task_meta):
        task_meta = task_meta or {}
        deps = task_meta.get("depends_on", [])
        inputs = task_meta.get("inputs", [])
        outputs = task_meta.get("outputs", [])
        success_criteria = task_meta.get("success_criteria", [])

        prompt = f"""
You are the CONSISTENCY CRITIC SWARM. Check whether this shard output fits the project.
You MUST explicitly identify the primary language and provide line-level fixes.
If there is no clear language, say UNKNOWN and still provide line-level guidance.
The output format for shards is a SINGLE file only: {self.output_file}. Do not require any other files.
You MUST follow the exact response template and include ALL fields below, even if UNKNOWN.
EVIDENCE must include file paths with line refs like {self.output_file}:L12 (use {self.output_file} only).
Do not add extra sections, headers, or prose outside the template.

SHARD ID: {task_id}
SHARD TASK: {task_desc}
DEPENDS_ON: {deps}
INPUTS: {inputs}
OUTPUTS: {outputs}
SUCCESS_CRITERIA: {success_criteria}

PROJECT MEMORY:
{self.memory.get_full_memory_prompt()}

SHARD OUTPUT (number lines in your analysis):
{outcome[:2000]}

Respond with ONLY one of the following formats:
OK:
- LANGUAGE: <explicit language or UNKNOWN>
- EVIDENCE: <brief evidence with file path and line reference like {self.output_file}:L12>
- MISSING: <what is missing to fit project or NONE>
- SUGGEST: <concise fix guidance (no edits), include file paths and line refs or NONE>
- NOTES: <any other inconsistencies or risks or NONE>
or
REVISE:
- LANGUAGE: <explicit language or UNKNOWN>
- EVIDENCE: <concrete problems with file paths and line references like {self.output_file}:L12>
- MISSING: <what is missing to fit project>
- SUGGEST: <concise fix guidance (no edits), include file paths and line refs>
- NOTES: <any other inconsistencies or risks>
"""
        critics = []
        for i in range(self.consistency_critic_count):
            critic = DroneAgent(f"Consistency-Critic-{task_id}-{i+1}", prompt, "audit", role="critic")
            critics.append(critic.run())

        results = await asyncio.gather(*critics)
        feedback = []
        ok_count = 0

        for res in results:
            verdict = res.get("output", "").strip()
            if self._is_consistency_ok(verdict):
                ok_count += 1
                continue
            feedback.append(verdict)

        passed = ok_count == self.consistency_critic_count
        if passed:
            return True, ""
        return False, self._merge_consistency_feedback(feedback)

    def _build_consistency_revise_prompt(self, task_desc, outcome, feedback):
        return f"""
[CONSISTENCY REVISION REQUEST]
The critic swarm found integration issues. Fix and return a revised shard output.
Only return a SINGLE file named {self.output_file}. Do NOT include or reference any other files.

ORIGINAL TASK:
{task_desc[:800]}

CURRENT OUTPUT:
{outcome[:800]}

CRITIC FEEDBACK:
{feedback[:800]}

        Respond with the corrected final output only.
        """

    def _build_audit_revise_prompt(self, task_desc, outcome, audit_feedback):
        return f"""
[AUDIT REVISION REQUEST]
The audit failed. Fix the issues and return a revised shard output.

ORIGINAL TASK:
{task_desc[:800]}

CURRENT OUTPUT:
{outcome[:800]}

AUDIT FAILURE:
{audit_feedback[:800]}

Respond with the corrected final output only.
"""

    @staticmethod
    def _is_consistency_ok(verdict: str) -> bool:
        normalized = verdict.strip().upper()
        if not normalized:
            return False
        if "REVISE" in normalized:
            return False
        if not normalized.startswith("OK"):
            return False
        # Require structured evidence even for OK (guards against weak critic output).
        if "EVIDENCE:" not in normalized or "LANGUAGE:" not in normalized:
            return False
        if not Overmind._evidence_has_path_line(normalized):
            return False
        return True

    @staticmethod
    def _merge_consistency_feedback(feedback_list):
        if not feedback_list:
            return "REVISE: No critic feedback available."

        sections = {"LANGUAGE": set(), "EVIDENCE": set(), "MISSING": set(), "SUGGEST": set(), "NOTES": set()}

        for item in feedback_list:
            upper = item.upper()
            for key in sections.keys():
                marker = f"- {key}:"
                if marker in upper:
                    start = upper.find(marker)
                    end = len(upper)
                    for other in sections.keys():
                        if other == key:
                            continue
                        next_marker = f"- {other}:"
                        next_pos = upper.find(next_marker, start + len(marker))
                        if next_pos != -1:
                            end = min(end, next_pos)
                    raw_section = item[start + len(marker):end].strip()
                    if raw_section:
                        sections[key].add(raw_section)

        # Fallback: include raw feedback if parsing missed everything
        if all(len(v) == 0 for v in sections.values()):
            merged = "\n".join([f for f in feedback_list if f])
            return f"REVISE:\n{merged}"

        def join_section(values):
            return "; ".join(sorted(values))

        language = join_section(sections["LANGUAGE"]) or "UNKNOWN"
        evidence = join_section(sections["EVIDENCE"]) or "No evidence provided."
        missing = join_section(sections["MISSING"]) or "Not specified."
        suggest = join_section(sections["SUGGEST"]) or "Provide fixes based on evidence."
        notes = join_section(sections["NOTES"]) or "None."

        # If evidence is missing file path + line ref, mark as revise with missing evidence.
        if "No evidence provided." in evidence or not Overmind._evidence_has_path_line(evidence):
            missing += " | Critic failed to provide file path and line references."

        return (
            "REVISE:\n"
            f"- LANGUAGE: {language}\n"
            f"- EVIDENCE: {evidence}\n"
            f"- MISSING: {missing}\n"
            f"- SUGGEST: {suggest}\n"
            f"- NOTES: {notes}"
        )

    @staticmethod
    def _evidence_has_path_line(text: str) -> bool:
        import re
        return re.search(r"[\w./-]+\.\w+:\s*L\d+", text) is not None

    @staticmethod
    def _interpret_audit_verdict(text: str):
        import re
        normalized = (text or "").strip()
        upper = normalized.upper()
        error_markers = [
            "ERROR:", "FAILED TO CONNECT", "READ TIMED OUT", "EXCEPTION",
            "TRACEBACK", "CONNECTIONPOOL", "HTTPCONNECTIONPOOL"
        ]
        if not normalized:
            return {"passed": False, "reason": "EMPTY", "normalized": normalized}
        if any(marker in upper for marker in error_markers):
            return {"passed": False, "reason": "ERROR_MARKER", "normalized": normalized}
        if re.match(r"^(PASS|OK)[.!]?$", upper):
            return {"passed": True, "reason": "PASS", "normalized": normalized}
        # Self-contradiction: claims failure but affirms success/achievement.
        if ("FAIL" in upper or "REJECT" in upper) and any(
            phrase in upper for phrase in ["GOAL ACHIEVED", "GOAL WAS ACHIEVED", "HAS BEEN ACHIEVED", "REQUIREMENTS MET"]
        ):
            return {"passed": True, "reason": "CONTRADICTION", "normalized": normalized}
        if ("FAIL" in upper or "REJECT" in upper) and any(
            phrase in upper for phrase in [
                "UNRELATED TO", "NOT RELEVANT", "DOES NOT AFFECT", "DOESN'T AFFECT", "PRIMARY FUNCTIONALITY"
            ]
        ):
            return {"passed": True, "reason": "CONTRADICTION", "normalized": normalized}
        if upper.startswith("FAIL") or upper.startswith("REJECT") or upper.startswith("REVISE"):
            return {"passed": False, "reason": "FAIL_MARKED", "normalized": normalized}
        return {"passed": False, "reason": "UNPARSEABLE", "normalized": normalized}
    async def decompose_goal(self, goal, depth=0):
        self.status = f"SHATTERING // PHASE: {self.phase} [DEPTH: {depth}]"
        self.shatter_guard.mark_progress("decompose_start", depth=depth)
        self.telemetry.log("shatter_start", goal=goal[:300], depth=depth, phase=self.phase)
        
        # Check for External API Provider (Together/OpenRouter/DeepInfra/Groq)
        brain_provider = os.getenv("BRAIN_PROVIDER", "custom")
        
        # Phase 2: Check for persistent remote brain or External API
        remote_ip = None
        if self.phase == 2:
            if brain_provider != "custom":
                print(f"[Overmind] Phase 2: Using EXTERNAL API BRAIN ({brain_provider})...")
                self.last_update = f"Connected to {brain_provider.upper()} API Brain."
                remote_ip = "EXTERNAL" # Flag for DroneAgent
            else:
                self.last_update = "Checking for remote 72B Brain via RunPod..."
                print("[Overmind] Phase 2: Checking for persistent brain pod...")
                remote_ip = self.runpod.get_persistent_brain_ip()
                
                if remote_ip:
                    print(f"[Overmind] REMOTE LINK ESTABLISHED: {remote_ip}")
                    self.last_update = "Remote 72B Brain connected!"
                else:
                    self.last_update = "Remote Brain offline. Run 'python start_brain.py' to enable 72B mode."
                    print("[Overmind] WARNING: No persistent brain found. Falling back to local Ollama.")
                    print("[Overmind] TIP: Run 'python start_brain.py' to launch the 72B brain")

        # Ensure the user sees the start of the actual work
        current_step = "Drafting initial mission shard map..."
        if remote_ip == "EXTERNAL":
            self.last_update = f"NEURAL LINK ACTIVE (API). {current_step} (via {brain_provider.upper()})"
        elif remote_ip:
            self.last_update = f"NEURAL LINK ACTIVE. {current_step} (via 72B Brain)"
        else:
            # If we were SUPPOSED to be in phase 2 but have no IP, prefix with fallback
            if self.phase == 2:
                self.last_update = f"FALLBACK ACTIVE. {current_step} (via Local Ollama)"
            else:
                self.last_update = f"{current_step} (via Local Ollama)"

        print(f"[Overmind] Initial Shatter Goal (Depth {depth}): {goal} | Remote IP: {remote_ip}", flush=True)
        
        max_chars = self.shard_max_chars
        max_words = self.shard_max_words

        async def run_shatter(prompt, drone_id):
            shatterer = DroneAgent(drone_id, goal, "architecture", role="writer", api_base_url=remote_ip)
            shatterer.task = prompt
            shatter_timeout = float(os.getenv("SHATTER_TIMEOUT", "120"))

            async def pulse_status():
                dots = ""
                while True:
                    dots = (dots + ".") if len(dots) < 3 else ""
                    self.last_update = f"{current_step} (Shattering logic{dots})"
                    await asyncio.sleep(1)

            pulse_task = asyncio.create_task(pulse_status())
            try:
                return await asyncio.wait_for(shatterer.run(), timeout=shatter_timeout)
            except asyncio.TimeoutError:
                self.telemetry.log(
                    "shatter_timeout",
                    timeout=shatter_timeout,
                    drone_id=drone_id,
                )
                return {"output": f"Error: Shatter timeout after {shatter_timeout}s"}
            finally:
                pulse_task.cancel()

        # Initial shatter
        shatter_prompt = self._build_shatter_prompt(goal, max_chars, max_words)
        shatter_result = await run_shatter(shatter_prompt, "Master-Shatterer")

        try:
            raw_output = shatter_result["output"]
            print(f"[Overmind] RAW SHATTER OUTPUT: {raw_output}")
            draft_tasks = self._parse_shatter_output(raw_output)
            draft_tasks = self._normalize_shards(draft_tasks)
        except Exception as e:
            print(f"[Overmind] SHATTER ERROR: Failed to parse or validate AI JSON. {e}")
            print(f"[Overmind] RAW OUTPUT: {shatter_result.get('output') if isinstance(shatter_result, dict) else shatter_result}")
            draft_tasks = [{"id": "A", "task": goal, "required_tier": 2, "depends_on": [], "inputs": [], "outputs": [], "success_criteria": []}]

        # Validate and refine for 7B-sized shards
        for attempt in range(self.shard_refine_rounds + 1):
            report = ShardValidator.validate(draft_tasks, max_chars=max_chars, max_words=max_words)
            self.telemetry.log(
                "shatter_validate",
                attempt=attempt,
                valid=report.get("valid"),
                oversized=len(report.get("oversized", [])),
                total=len(draft_tasks),
            )
            if report["valid"]:
                break

            critic_verdict = await self._critique_shards(goal, draft_tasks, report)
            if "PASS" in critic_verdict and "FAIL" not in critic_verdict:
                break

            refine_prompt = self._build_shatter_prompt(
                goal,
                max_chars,
                max_words,
                prior=draft_tasks,
                report=report,
                critic_notes=critic_verdict,
            )
            shatter_result = await run_shatter(refine_prompt, f"Shatter-Refiner-{attempt + 1}")
            try:
                raw_output = shatter_result["output"]
                draft_tasks = self._parse_shatter_output(raw_output)
                draft_tasks = self._normalize_shards(draft_tasks)
            except Exception as e:
                print(f"[Overmind] SHATTER REFINE ERROR: {e}")
                break
            self.shatter_guard.tick(
                "refine_loop",
                note="shatter_refine_attempt",
                attempt=attempt + 1,
            )

        # Final safeguard: split oversized shards deterministically
        final_report = ShardValidator.validate(draft_tasks, max_chars=max_chars, max_words=max_words)
        if final_report["oversized"]:
            print(f"[Overmind] Oversized shards detected: {final_report['oversized']}. Forcing split.")
            draft_tasks, split_info = ShardValidator.split_oversized_shards(
                draft_tasks, max_chars=max_chars, max_words=max_words
            )
            print(f"[Overmind] Forced split map: {split_info.get('split_map')}")
            self.telemetry.log(
                "shatter_forced_split",
                oversized=final_report.get("oversized"),
                split_map=split_info.get("split_map"),
            )

        print(f"[Overmind] SHATTERED INTO {len(draft_tasks)} tasks.")
        for t in draft_tasks:
            print(f"  - [{t.get('id')}] (Tier {t.get('required_tier')}): {t.get('task')[:60]}...")

        # 4. DEPENDENCY VALIDATION
        self.last_update = "Validating dependencies and building execution plan..."
        execution_plan = DependencyResolver.build_plan(draft_tasks)
        
        if not execution_plan['valid']:
            print(f"[Overmind] DEPENDENCY ERROR: {execution_plan['error']}")
            self.telemetry.log("dependency_error", error=execution_plan.get("error"))
            return {"tasks": draft_tasks, "execution_plan": None}
            
        return {"tasks": draft_tasks, "execution_plan": execution_plan}

    async def execute_task_with_redundancy(self, task_id, task_desc, required_tier=1, depth=0, max_depth=3, task_meta=None):
        """Dispatches tasks with Tiered Routing and supports Fractal Shattering (Delegation)."""
        print(f"[Overmind] Task {task_id}: Dispatching (Tier {required_tier})...")
        self.telemetry.log(
            "task_dispatch",
            task_id=task_id,
            required_tier=required_tier,
            depth=depth,
        )
        
        self.last_update = f"Task {task_id}: Waiting for Tier {required_tier} node..."
        
        # Add Delegation protocol to the task description for the worker
        delegation_msg = "\n\n[PROTOCOL] If this task is too complex, respond with 'DELEGATE: <new_goal_string>'"
        output_msg = (
            "\n\n[OUTPUT FORMAT]\n"
            "Return a SINGLE file only:\n"
            f"FILE: {self.output_file}\n"
            f"```{self._language_from_filename(self.output_file)}\n"
            "...\n"
            "```\n"
            "Use the appropriate language for the file type.\n"
            "Do not include any other files or extra prose.\n"
        )
        full_task = task_desc + (delegation_msg if self.enable_delegation else "") + output_msg

        if self.worker_pool and self.nexus:
            # RACING REDUNDANCY MODE
            self.status = "EXECUTING (COMMUNITY)"
            attempts = 0
            revised_task = full_task

            while True:
                result = await self.worker_pool.execute_shard(task_id, revised_task, required_tier=required_tier)
                if not result:
                    break

                outcome = result.get("output", "")

                # FRACTAL SHATTERING CHECK
                if self.enable_delegation and outcome.strip().startswith("DELEGATE:"):
                    sub_goal = outcome.replace("DELEGATE:", "").strip()
                    print(f"[Overmind] [RECURSION] FRACTAL SHATTER DETECTED for {task_id}. Re-shattering: {sub_goal}")
                    self.last_update = f"Task {task_id} delegated. Recursive Shatter in progress..."
                    self.telemetry.log(
                        "task_delegate",
                        task_id=task_id,
                        depth=depth,
                        sub_goal=sub_goal[:300],
                    )
                    
                    if depth < max_depth:
                        swarm_data = await self.run_swarm(sub_goal, depth=depth+1, max_depth=max_depth)
                        sub_shards = swarm_data.get("shards", [])
                        combined = "\n".join([f"- {r.get('outcome', 'No outcome')}" for r in sub_shards])
                        return {"id": task_id, "outcome": f"DELEGATED_COMPLETION:\n{combined}"}
                    else:
                        return {"id": task_id, "outcome": "ERROR: Max recursion depth reached."}

                # Consistency critic swarm
                if (
                    self.enable_consistency_critic
                    and self.consistency_mode == "shard"
                    and not str(task_id).startswith("AUDIT-")
                ):
                    passed, feedback = await self._consistency_audit_shard(task_id, task_desc, outcome, task_meta)
                    if not passed:
                        attempts += 1
                        self.telemetry.log(
                            "consistency_feedback",
                            task_id=task_id,
                            attempt=attempts,
                            feedback=(feedback or "")[:800],
                        )
                        if attempts <= self.consistency_revise_attempts:
                            revised_task = self._build_consistency_revise_prompt(task_desc, outcome, feedback)
                            self.last_update = f"Task {task_id}: Consistency revision requested (attempt {attempts})..."
                            self.telemetry.log(
                                "consistency_retry",
                                task_id=task_id,
                                attempt=attempts,
                            )
                            continue
                        self.telemetry.log(
                            "consistency_failed",
                            task_id=task_id,
                            attempts=attempts,
                        )
                        return {"id": task_id, "outcome": outcome, "status": "failed_consistency", "consistency_feedback": feedback}

                # Record pending payout in Escrow
                winner_id = result.get("worker_id", "Unknown")
                print(f"[Overmind] Task {task_id} completed by {winner_id}. Escrowing payout...", flush=True)
                if self.nexus:
                    self.nexus.record_pending_payout(winner_id, task_id, base_credits=2.0 if required_tier > 1 else 1.0)

                status = result.get("status", "success")
                self.telemetry.log(
                    "task_completed",
                    task_id=task_id,
                    status=status,
                    worker_id=winner_id,
                )
                return {"id": task_id, "outcome": outcome, "worker_id": winner_id, "status": status}
        
        # FALLBACK: Local Execution
        self.status = "BUILDING (LOCAL)"
        role = "critic" if str(task_id).startswith("AUDIT-") else "writer"
        builder = DroneAgent(f"{task_id}-Builder", task_desc, "action", role=role, depth=depth)
        attempts = 0
        revised_task = task_desc + output_msg
        while True:
            role = "critic" if str(task_id).startswith("AUDIT-") else "writer"
            builder = DroneAgent(f"{task_id}-Builder", revised_task, "action", role=role, depth=depth)
            res = await builder.run()
            output = res["output"]

            if (
                self.enable_consistency_critic
                and self.consistency_mode == "shard"
                and not str(task_id).startswith("AUDIT-")
            ):
                passed, feedback = await self._consistency_audit_shard(task_id, task_desc, output, task_meta)
                if not passed:
                    attempts += 1
                    self.telemetry.log(
                        "consistency_feedback",
                        task_id=task_id,
                        attempt=attempts,
                        feedback=(feedback or "")[:800],
                        mode="local",
                    )
                    if attempts <= self.consistency_revise_attempts:
                        revised_task = self._build_consistency_revise_prompt(task_desc, output, feedback)
                        self.telemetry.log(
                            "consistency_retry",
                            task_id=task_id,
                            attempt=attempts,
                            mode="local",
                        )
                        continue
                    self.telemetry.log(
                        "consistency_failed",
                        task_id=task_id,
                        attempts=attempts,
                        mode="local",
                    )
                    return {"id": task_id, "outcome": output, "status": "failed_consistency", "consistency_feedback": feedback}

            status = "failed" if isinstance(output, str) and output.startswith("Error:") else "success"
            return {"id": task_id, "outcome": output, "status": status}

    async def run_swarm(self, goal, depth=0, max_depth=3):
        self.memory.update_context("project_goal", goal)
        self.memory.update_context("output_format", self.output_format)
        self.memory.update_context("output_file", self.output_file)
        self.run_guard.mark_progress("swarm_start", depth=depth)
        self.telemetry.log("swarm_start", goal=goal[:300], depth=depth)
        result = await self.decompose_goal(goal, depth=depth)
        
        # Defensive check: Ensure result is a dict
        if not isinstance(result, dict):
            print(f"[Overmind] ERROR: decomposition returned {type(result)}. Falling back.")
            result = {"tasks": [{"id": "A", "task": goal, "required_tier": 2, "depends_on": []}], "execution_plan": None}

        tasks = result.get("tasks", [])
        task_map = {t.get("id"): t for t in tasks if isinstance(t, dict) and t.get("id")}
        plan = result.get("execution_plan")
        if not isinstance(plan, dict) or not plan.get('valid'):
            print(f"[Overmind] Falling back to sequential execution... (Plan Valid: {plan.get('valid') if isinstance(plan, dict) else 'None'})")
            self.telemetry.log("execution_fallback", reason="invalid_plan")
            execution_coros = []
            for t in tasks:
                if not isinstance(t, dict):
                    print(f"[Overmind] WARNING: Shard {t} is not a dict. Attempting recovery.")
                    t = {"id": "?", "task": str(t), "required_tier": 1}
                
                execution_coros.append(self.execute_task_with_redundancy(
                    t.get('id', '?'), 
                    t.get('task', 'Unknown'), 
                    t.get('required_tier', 1), 
                    depth=depth, 
                    max_depth=max_depth,
                    task_meta=t
                ))
            results = await asyncio.gather(*execution_coros)
            return {
                "shards": results, 
                "final_report": f"Successfully completed project goals through sequential execution (Fallback). Results consolidated."
            }

        # WAVE-BASED EXECUTION
        all_results = []
        for wave_idx, wave in enumerate(plan['waves']):
            self.status = f"EXECUTING WAVE {wave_idx + 1}/{plan['total_waves']}"
            await asyncio.sleep(0.5) # UX Breathing room
            print(f"\n[Overmind] STARTING WAVE {wave_idx + 1}: {wave}")
            self.telemetry.log(
                "wave_start",
                wave=wave_idx + 1,
                total_waves=plan.get("total_waves"),
                shard_ids=wave,
            )
            
            wave_coros = []
            for t_id in wave:
                # Use a safer lookup for the task object
                t_obj = next((t for t in tasks if isinstance(t, dict) and t.get('id') == t_id), None)
                if not t_obj:
                    print(f"[Overmind] ERROR: Wave referencing unknown task {t_id}")
                    continue
                    
                wave_coros.append(self.execute_task_with_redundancy(
                    t_id, 
                    t_obj.get('task', 'Unknown'), 
                    required_tier=t_obj.get('required_tier', 1), 
                    depth=depth, 
                    max_depth=max_depth,
                    task_meta=t_obj
                ))
            
            wave_results = await asyncio.gather(*wave_coros)
            all_results.extend(wave_results)
            
            # --- AUDIT WAVE (WORKER HATER PHASE) ---
            if self.audit_mode == "wave":
                self.status = f"AUDITING WAVE {wave_idx + 1}"
                await asyncio.sleep(0.5) # UX Breathing room
                for audit_attempt in range(self.audit_retry_attempts + 1):
                    print(f"[Overmind] IGNITING WORKER HATER AUDIT for Wave {wave_idx + 1} (Attempt {audit_attempt + 1})...", flush=True)
                    self.telemetry.log(
                        "audit_wave_start",
                        wave=wave_idx + 1,
                        attempt=audit_attempt + 1,
                    )
                    audit_coros = []
                    audit_prompts = {}
                    for res in wave_results:
                        task_id = res.get("id")
                        outcome = res.get("outcome")
                        # Record result in Project Memory for other drones to see
                        self.memory.record_shard(task_id, "Unknown (ID lookup needed)", outcome)
                        
                        # Assign a Worker Hater (Critic) to audit this outcome
                        audit_body = outcome or ""
                        if self.audit_max_chars > 0:
                            audit_body = audit_body[:self.audit_max_chars]
                        audit_prompt = (
                            "AUDIT THE FOLLOWING SHARD OUTCOME:\n"
                            f"{audit_body}\n\n"
                            "Check for bugs, logic holes, and security issues. Ensure it fits the global memory and world bible.\n"
                            "Only use evidence present in the output; do NOT speculate.\n"
                            "If output is incomplete or missing required parts, say that directly.\n"
                            f"{self.memory.get_full_memory_prompt()}\n\n"
                            "Respond with ONLY:\n"
                            "PASS\n"
                            "or\n"
                            "FAIL: <short reason grounded in the output>"
                        )
                        audit_prompts[task_id] = audit_prompt
                        
                        audit_coros.append(self.execute_task_with_redundancy(
                            f"AUDIT-{task_id}", 
                            audit_prompt, 
                            required_tier=self.audit_required_tier
                        ))
                    
                    audit_results = await asyncio.gather(*audit_coros)
                    failed_audits = []
                    for ar in audit_results:
                        audit_id = ar['id'].replace("AUDIT-", "")
                        auditor_id = ar.get('worker_id')
                        verdict = self._interpret_audit_verdict(ar.get("outcome", ""))
                        retry_attempts = 0
                        while (
                            not verdict["passed"]
                            and verdict["reason"] in {"EMPTY", "UNPARSEABLE", "ERROR_MARKER"}
                            and retry_attempts < self.audit_response_retries
                        ):
                            retry_attempts += 1
                            self.telemetry.log(
                                "audit_response_retry",
                                task_id=audit_id,
                                attempt=retry_attempts,
                                reason=verdict["reason"],
                            )
                            retry_result = await self.execute_task_with_redundancy(
                                f"AUDIT-{audit_id}",
                                audit_prompts.get(audit_id, ""),
                                required_tier=2,
                            )
                            ar = retry_result
                            auditor_id = ar.get("worker_id")
                            verdict = self._interpret_audit_verdict(ar.get("outcome", ""))
                        audit_passed = verdict["passed"]
                        reason = verdict["reason"]
                        raw_prefix = (ar.get("outcome") or "")[:160]

                        self.telemetry.log(
                            "audit_verdict",
                            task_id=audit_id,
                            auditor_id=auditor_id,
                            passed=audit_passed,
                            reason=reason,
                            raw_prefix=raw_prefix,
                        )
                        
                        print(
                            f"[Worker Hater] Audit for {audit_id} by {auditor_id}: "
                            f"{reason} | Raw: {raw_prefix}... Result: {'PASSED' if audit_passed else 'FAILED'}",
                            flush=True,
                        )
                        if not audit_passed:
                            failed_audits.append({
                                "task_id": audit_id,
                                "auditor_id": auditor_id,
                                "reason": reason,
                                "outcome": ar.get("outcome", "")
                            })
                        
                        if self.nexus:
                            self.nexus.release_escrow(audit_id, audit_success=audit_passed, auditor_id=auditor_id)
                        
                        all_results.append(ar)

                    if not failed_audits:
                        break

                    if audit_attempt >= self.audit_retry_attempts:
                        self.status = "AUDIT_FAILED"
                        self.last_update = "Audit failed; stopping before recombination."
                        self.telemetry.log(
                            "audit_failed",
                            wave=wave_idx + 1,
                            failures=len(failed_audits),
                        )
                        return {
                            "shards": all_results,
                            "final_report": f"AUDIT FAILED. Fix failed shards before recombination:\n{json.dumps(failed_audits, ensure_ascii=True, indent=2)}"
                        }

                    retry_coros = []
                    for failed in failed_audits:
                        task_id = failed["task_id"]
                        t_obj = task_map.get(task_id)
                        if not t_obj:
                            continue
                        revised_task = self._build_audit_revise_prompt(
                            t_obj.get("task", "Unknown"),
                            next((r.get("outcome", "") for r in wave_results if r.get("id") == task_id), ""),
                            failed.get("outcome", "")
                        )
                        if self.audit_use_heavy_fix:
                            retry_coros.append(self._repair_with_heavy(
                                task_id,
                                revised_task,
                                depth=depth,
                                task_meta=t_obj
                            ))
                        else:
                            retry_coros.append(self.execute_task_with_redundancy(
                                task_id,
                                revised_task,
                                required_tier=t_obj.get("required_tier", 1),
                                depth=depth,
                                max_depth=max_depth,
                                task_meta=t_obj
                            ))
                    if retry_coros:
                        retry_results = await asyncio.gather(*retry_coros)
                        for rr in retry_results:
                            all_results = [r for r in all_results if r.get("id") not in {rr.get("id"), f"AUDIT-{rr.get('id')}"}]
                        wave_results = retry_results
            
        # --- RECOMBINATION PHASE (JUDGE + CRITIC) ---
        self.status = "RECOMBINING PROJECT"
        print("\n[Overmind] IGNITING RECOMBINER (JUDGE)...", flush=True)
        self.telemetry.log("recombine_start")

        # Assembly validation for structural fit
        results_map = {}
        for res in all_results:
            t_id = res.get("id", "")
            if t_id.startswith("AUDIT-"):
                continue
            results_map[t_id] = {
                "status": res.get("status", "success"),
                "output": res.get("outcome", "")
            }

        assembly_report = AssemblyValidator.validate(tasks, results_map)

        success_report = None
        if self.enable_success_check:
            success_report = await SuccessChecker.check(tasks, results_map)

        recombine_results = all_results
        recombine_context_max = int(os.getenv("RECOMBINE_CONTEXT_MAX", "12000"))
        recombine_summary_max = int(os.getenv("RECOMBINE_SUMMARY_MAX", "1200"))
        if os.getenv("RECOMBINE_SUMMARIZE", "1") == "1":
            combined_len = sum(len((r.get("outcome") or "")) for r in all_results)
            if combined_len > recombine_context_max:
                recombine_results = await self._summarize_shard_outputs(
                    all_results,
                    tasks,
                    per_shard_max=recombine_summary_max,
                )
                self.telemetry.log(
                    "recombine_summarized",
                    original_len=combined_len,
                    summary_len=sum(len((r.get("outcome") or "")) for r in recombine_results),
                )

        recombine_feedback = None
        final_synthesis = None
        critic_verdict = None

        for attempt in range(max(1, self.recombine_max_attempts)):
            self.last_update = f"Judge is synthesizing audited shards into final project (attempt {attempt + 1})..."
            self.telemetry.log("recombine_attempt", attempt=attempt + 1)
            recombine_timeout = float(os.getenv("RECOMBINE_TIMEOUT", "180"))
            recomb_prompt = (
                f"FINAL PROJECT SYNTHESIS\n"
                f"MASTER GOAL: {goal}\n\n"
                f"CONSOLIDATE THE FOLLOWING AUDITED SHARDS INTO A SINGLE, FULLY FUNCTIONAL FINAL PROJECT:\n"
                f"YOU ARE ASSEMBLING A FRANKEN PROGRAM. Resolve conflicts, unify naming, and ensure consistency end-to-end.\n"
            )
            if self.output_format == "single_file":
                language = self._language_from_filename(self.output_file)
                recomb_prompt += (
                    f"\nOUTPUT FORMAT: SINGLE FILE ONLY\n"
                    f"Return only this file and nothing else:\n"
                    f"FILE: {self.output_file}\n"
                    f"```{language}\n"
                    "...\n"
                    "```\n"
                    "No extra prose, instructions, or additional files.\n"
                )

            recomb_prompt += f"\nASSEMBLY_REPORT: {json.dumps(assembly_report, ensure_ascii=True)}\n"
            if success_report:
                recomb_prompt += f"\nSUCCESS_REPORT: {json.dumps(success_report, ensure_ascii=True)}\n"
            if recombine_feedback:
                recomb_prompt += f"\nRECOMBINE_CRITIC_FEEDBACK: {recombine_feedback}\n"

            for res in recombine_results:
                t_id = res.get("id", "")
                if t_id.startswith("AUDIT-"):
                    original_id = t_id.replace("AUDIT-", "")
                    recomb_prompt += f"[CRITIC FEEDBACK FOR {original_id}]: {res.get('outcome')}\n"
                else:
                    recomb_prompt += f"--- Shard {t_id} ---\n{res.get('outcome')}\n"

            recomb_prompt += "\nRespond with the COMPLETE, FINAL, AND FUNCTIONAL project."

            recombiner = DroneAgent("Master-Judge", recomb_prompt, "architecture", role="judge")
            try:
                final_synthesis = await asyncio.wait_for(recombiner.run(), timeout=recombine_timeout)
            except asyncio.TimeoutError:
                critic_verdict = f"FAIL: RECOMBINE_TIMEOUT after {recombine_timeout}s"
                self.telemetry.log(
                    "recombine_timeout",
                    attempt=attempt + 1,
                    timeout=recombine_timeout,
                )
                final_synthesis = {"output": ""}
                recombine_feedback = critic_verdict
                continue

            critic_verdict = await self._critique_recombine(
                goal,
                shard_results=all_results,
                final_output=final_synthesis["output"],
                assembly_report=assembly_report,
            )
            sanity_issues = self._final_sanity_checks(final_synthesis["output"], goal, self.output_file)
            if sanity_issues:
                critic_verdict = f"FAIL: SANITY_CHECK: {'; '.join(sanity_issues)}"
                self.telemetry.log(
                    "final_sanity_fail",
                    issues=sanity_issues,
                )
            if "PASS" in critic_verdict and "FAIL" not in critic_verdict:
                break
            recombine_feedback = critic_verdict

        print("\n" + "!" * 60)
        print("MISSION COMPLETE: HIVE SYNTHESIS READY")
        print("!" * 60 + "\n")

        if final_synthesis is None:
            final_synthesis = {"output": ""}
            if not critic_verdict:
                critic_verdict = "FAIL: RECOMBINE_TIMEOUT"

        final_report = final_synthesis["output"]
        if self.output_format == "single_file":
            final_report = self._coerce_single_file_output(final_report, self.output_file)
        elif critic_verdict:
            final_report += f"\n\nRECOMBINE_CRITIC: {critic_verdict}"

        audit_total = 0
        audit_passed = 0
        consistency_total = 0
        consistency_passed = 0
        for res in all_results:
            res_id = res.get("id", "")
            if res_id.startswith("AUDIT-"):
                audit_total += 1
                verdict = self._interpret_audit_verdict(res.get("outcome", ""))
                if verdict["passed"]:
                    audit_passed += 1
            else:
                consistency_total += 1
                if res.get("status") == "success":
                    consistency_passed += 1

        audit_pass_rate = audit_passed / audit_total if audit_total else 0.0
        consistency_pass_rate = consistency_passed / consistency_total if consistency_total else 0.0
        recombine_pass = bool(critic_verdict and "PASS" in critic_verdict and "FAIL" not in critic_verdict)

        if recombine_pass and audit_pass_rate == 1.0 and consistency_pass_rate == 1.0:
            try:
                export_shatter(goal, tasks, scores={
                    "consistency_pass_rate": round(consistency_pass_rate, 2),
                    "audit_pass_rate": round(audit_pass_rate, 2),
                    "recombine_pass": True
                })
            except Exception as e:
                print(f"[Overmind] Shatter export failed: {e}")

        return {
            "shards": all_results,
            "final_report": final_report
        }

    async def _summarize_shard_outputs(self, results, tasks, per_shard_max=1200):
        task_map = {t.get("id"): t for t in tasks}
        summarized = []
        for res in results:
            outcome = res.get("outcome", "") or ""
            if len(outcome) <= per_shard_max:
                summarized.append(res)
                continue
            shard_id = res.get("id", "")
            task_desc = ""
            if shard_id and not shard_id.startswith("AUDIT-"):
                task_desc = task_map.get(shard_id, {}).get("task", "")
            prompt = (
                "Summarize the shard output for recombination.\n"
                f"Keep key APIs, state, required UI elements, and constraints. Do NOT invent details.\n"
                f"Keep under {per_shard_max} characters.\n\n"
                f"SHARD_ID: {shard_id}\n"
                f"TASK: {task_desc}\n"
                "OUTPUT:\n"
                f"{outcome[:4000]}\n"
            )
            summarizer = DroneAgent(f"Summarizer-{shard_id or 'X'}", prompt, "audit", role="scout")
            res_sum = await summarizer.run()
            summary = (res_sum.get("output") or "").strip()
            if not summary:
                summary = outcome[:per_shard_max]
            new_res = dict(res)
            new_res["outcome"] = summary
            summarized.append(new_res)
        return summarized

    async def _repair_with_heavy(self, task_id, task_desc, depth=0, task_meta=None):
        self.status = "REPAIRING (HEAVY)"
        self.last_update = f"Task {task_id}: Heavy model repair in progress..."
        self.telemetry.log(
            "audit_heavy_repair",
            task_id=task_id,
            depth=depth,
        )
        fix_prompt = (
            "[HEAVY REPAIR MODE]\n"
            "You must fully resolve ALL audit feedback and preserve required features.\n"
            "If the audit mentions missing controls or instructions, add them explicitly.\n"
            "Checklist before returning:\n"
            "- All HTML tags closed properly\n"
            "- Script block is complete and closed\n"
            "- All required controls and instructions are present\n"
            "- No unrelated error text\n"
            "Return only the corrected final output.\n\n"
            f"{task_desc}"
        )
        builder = DroneAgent(f"{task_id}-HeavyFix", fix_prompt, "action", role="writer", depth=depth)
        res = await builder.run()
        output = res.get("output", "")
        return {"id": task_id, "outcome": output, "status": "success", "worker_id": "HEAVY_LOCAL"}

    @staticmethod
    def _coerce_single_file_output(text: str, filename: str) -> str:
        if not text:
            return text
        fence = "```"
        if fence in text:
            parts = text.split(fence)
            if len(parts) >= 3:
                code = parts[1]
                if "\n" in code:
                    first_line, remainder = code.split("\n", 1)
                    if first_line.strip().startswith(("python", "html", "javascript", "typescript", "css", "json")):
                        code = remainder
                code = code.strip()
                language = Overmind._language_from_filename(filename)
                return f"FILE: {filename}\n```{language}\n{code}\n```"
        return text.strip()

    @staticmethod
    def _extract_code_block(text: str) -> str:
        if not text:
            return ""
        fence = "```"
        if fence in text:
            parts = text.split(fence)
            if len(parts) >= 3:
                code = parts[1]
                if "\n" in code:
                    first_line, remainder = code.split("\n", 1)
                    if first_line.strip().startswith(("python", "html", "javascript", "typescript", "css", "json")):
                        code = remainder
                return code.strip()
        return text.strip()

    def _final_sanity_checks(self, final_output: str, goal: str, output_file: str):
        issues = []
        goal_lower = (goal or "").lower()
        code = self._extract_code_block(final_output)
        code_lower = code.lower()

        if output_file.lower().endswith(".html"):
            if "<canvas" not in code_lower:
                issues.append("missing <canvas> element")
            if "arrow" in goal_lower and not any(k in code for k in ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]):
                issues.append("no arrow key handlers")
            if "win" in goal_lower and "win" not in code_lower:
                issues.append("no win message")
            if ("lose" in goal_lower or "loss" in goal_lower) and not ("lose" in code_lower or "game over" in code_lower):
                issues.append("no lose message")
            if "reset" in goal_lower:
                has_reset_button = "<button" in code_lower and "reset" in code_lower
                has_reset_handler = "addeventlistener" in code_lower and "click" in code_lower and "reset" in code_lower
                if not (has_reset_button and has_reset_handler):
                    issues.append("reset button or handler missing")
            if ("item.width" in code or "item.height" in code) and not ("width:" in code_lower and "height:" in code_lower):
                issues.append("collision uses item.width/item.height but items lack width/height")
            if "requestanimationframe" in code_lower and "gameloop(" not in code_lower:
                issues.append("game loop not started")
            if "no server" in goal_lower or "offline" in goal_lower:
                if "fetch(" in code_lower or "xmlhttprequest" in code_lower or "http://" in code_lower or "https://" in code_lower:
                    issues.append("network calls found despite offline requirement")

        return issues
