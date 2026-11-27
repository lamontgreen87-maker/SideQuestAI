import asyncio
import json
import os
from pathlib import Path
import requests
import random
import threading
import time as _time


def _load_dotenv_if_needed():
    """Load key=value pairs from local .env without overriding existing env vars."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_PROVIDER_CONFIG = {
    "together": ("https://api.together.xyz/v1/chat/completions", "qwen/qwen-2.5-72b-instruct", "TOGETHER_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "nvidia/nemotron-3.5-lightning:free", "OPENROUTER_API_KEY"),
    "deepinfra": ("https://api.deepinfra.com/v1/openai/chat/completions", "qwen/qwen-2.5-72b-instruct", "DEEPINFRA_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash", "GEMINI_API_KEY"),
}


_PROVIDER_COOLDOWNS: dict[str, float] = {}
_LAST_SUCCESS_PROVIDER: str | None = None


def _mark_provider_cooldown(prov: str, seconds: float = 1800.0):
    _PROVIDER_COOLDOWNS[prov] = _time.time() + seconds


def _is_provider_cooling(prov: str) -> bool:
    until = _PROVIDER_COOLDOWNS.get(prov, 0.0)
    if until and _time.time() >= until:
        _PROVIDER_COOLDOWNS.pop(prov, None)
        return False
    return _time.time() < until


def get_available_providers() -> list[str]:
    _load_dotenv_if_needed()
    avail = ["ollama"]
    if os.getenv("GROQ_API_KEY"):
        avail.append("hybrid")
    for prov, (_, _, key_env) in _PROVIDER_CONFIG.items():
        if os.getenv(key_env) or (os.getenv("BRAIN_PROVIDER", "").lower() == prov and os.getenv("BRAIN_API_KEY")):
            avail.append(prov)
    if os.getenv("RUNPOD_ENDPOINT_ID", "").strip() and os.getenv("RUNPOD_API_KEY"):
        avail.append("runpod_serverless")
    return avail


def set_active_provider(provider: str) -> dict:
    global _LAST_SUCCESS_PROVIDER
    prov = (provider or "").strip().lower()
    if prov:
        os.environ["BRAIN_PROVIDER"] = prov
        _PROVIDER_COOLDOWNS.pop(prov, None)
        _LAST_SUCCESS_PROVIDER = prov
    return get_active_provider_info()


def get_active_provider_info() -> dict:
    _load_dotenv_if_needed()
    primary = os.getenv("BRAIN_PROVIDER", "custom").lower()
    chain = _resolve_provider_chain(primary, "EXTERNAL" if primary != "custom" else None)
    if primary == "hybrid":
        active = "hybrid"
    else:
        active = _LAST_SUCCESS_PROVIDER if (_LAST_SUCCESS_PROVIDER and not _is_provider_cooling(_LAST_SUCCESS_PROVIDER)) else (chain[0][0] if chain else primary)
    if active == "hybrid":
        local_m = os.getenv("LOCAL_HYPOTHESIS_MODEL") or os.getenv("NANO_MODEL") or "qwen2.5-coder:14b"
        groq_m = os.getenv("BRAIN_MODEL") or "openai/gpt-oss-120b"
        active_model = f"{local_m} -> {groq_m}"
    elif active in ("ollama", "custom"):
        active_model = os.getenv("HEAVY_MODEL") or "qwen2.5-coder:14b"
    else:
        active_model = next((m for p, _, m, _ in chain if p == active), os.getenv("BRAIN_MODEL") or "default")
    cooling = [p for p in list(_PROVIDER_COOLDOWNS) if _is_provider_cooling(p)]
    return {
        "provider": active,
        "model": active_model,
        "cooling_down": cooling,
        "available_providers": get_available_providers(),
    }


def _resolve_provider_chain(primary: str, api_base_url: str | None):
    """Build ordered list of (provider, api_url, model, api_key), cycling away from exhausted providers."""
    chain = []
    seen = set()
    fallbacks = [
        x.strip().lower()
        for x in os.getenv("BRAIN_FALLBACK_PROVIDERS", "groq,gemini,openrouter").split(",")
        if x.strip()
    ]
    candidates = [primary] + [fb for fb in fallbacks if fb != primary]

    for idx, prov in enumerate(candidates):
        if prov in seen:
            continue
        seen.add(prov)
        if prov in _PROVIDER_CONFIG:
            url, default_model, key_env = _PROVIDER_CONFIG[prov]
            key = os.getenv(key_env) or (os.getenv("BRAIN_API_KEY") if idx == 0 else None)
            if not key and idx > 0:
                continue
            model = (os.getenv("BRAIN_MODEL") if idx == 0 else None) or default_model
            chain.append((prov, url, model, key))
        elif prov == "runpod_serverless":
            endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "").strip()
            rp_key = os.getenv("RUNPOD_API_KEY") or (os.getenv("BRAIN_API_KEY") if idx == 0 else None)
            if not endpoint_id or not rp_key:
                continue
            url = f"https://api.runpod.ai/v2/{endpoint_id}/openai/v1/chat/completions"
            model = os.getenv("RUNPOD_SERVERLESS_MODEL") or os.getenv("BRAIN_MODEL") or "Qwen/Qwen2.5-32B-Instruct-AWQ"
            chain.append((prov, url, model, rp_key))
        elif idx == 0 and api_base_url and api_base_url != "EXTERNAL":
            url = f"http://{api_base_url}:8000/v1/chat/completions"
            model = os.getenv("BRAIN_MODEL") or "qwen/qwen-2.5-72b-instruct"
            chain.append((prov, url, model, os.getenv("BRAIN_API_KEY")))

    # Put healthy (non-cooling) providers first so exhausted services stay cycled out
    healthy = [item for item in chain if not _is_provider_cooling(item[0])]
    cooling = [item for item in chain if _is_provider_cooling(item[0])]
    return healthy + cooling


_PACE_LOCK: asyncio.Lock | None = None
_LAST_REMOTE_CALL_AT: float = 0.0


async def _pace_remote_call():
    """Enforce minimum spacing between remote API calls in free-tier mode."""
    global _PACE_LOCK, _LAST_REMOTE_CALL_AT
    free_mode = os.getenv(
        "FREE_TIER_MODE",
        "1" if os.getenv("BRAIN_PROVIDER", "custom").lower() != "custom" else "0",
    ) == "1"
    min_interval = float(os.getenv("BRAIN_MIN_CALL_INTERVAL_S", "3.0" if free_mode else "0"))
    if min_interval <= 0:
        return
    if _PACE_LOCK is None:
        _PACE_LOCK = asyncio.Lock()
    async with _PACE_LOCK:
        elapsed = _time.monotonic() - _LAST_REMOTE_CALL_AT
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        _LAST_REMOTE_CALL_AT = _time.monotonic()


_OLLAMA_LOCAL_LOCK = threading.Lock()


class DroneAgent:
    """
    The Specialized 'Little AI'.
    Handles search, education, action, and testing using real local AI (Ollama).
    """
    OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
    HEAVY_MODEL = os.getenv("HEAVY_MODEL", "qwen2.5-coder:7b")
    LIGHT_MODEL = os.getenv("LIGHT_MODEL", "qwen2.5-coder:7b") # Fast mobile-class audit
    NANO_MODEL = os.getenv("NANO_MODEL", "qwen2.5:14b")  # Fast mobile-class shatter
    SHATTER_MODEL = os.getenv("SHATTER_MODEL")
    RECOMBINE_MODEL = os.getenv("RECOMBINE_MODEL")

    def __init__(self, drone_id, task, task_type, role="general", depth=0, max_depth=3, overmind_callback=None, model_size="3B", api_base_url=None, provider_override=None):
        self.drone_id = drone_id
        self.task = task
        self.task_type = task_type
        self.role = role
        self.depth = depth
        self.max_depth = max_depth
        self.overmind_callback = overmind_callback
        self.model_size = model_size
        self.api_base_url = api_base_url # For remote 72B Brains
        self.provider_override = provider_override
        self.log = []
        
        
        # Smart model routing based on task complexity
        if self.role == "judge" and self.RECOMBINE_MODEL:
            # Allow a dedicated model for recombination/synthesis
            self.model = self.RECOMBINE_MODEL
        elif self.task_type == "architecture" and self.role == "writer" and self.SHATTER_MODEL:
            # Allow a dedicated model for shattering
            self.model = self.SHATTER_MODEL
        elif self.role in ["scout", "mouth", "judge"] or self.task_type == "architecture":
            # Ultra-fast for simple queries, shattering, and high-speed synthesis
            self.model = self.NANO_MODEL
        elif self.task_type == "action":
            # Complex tasks need the heavy model (7B)
            self.model = self.HEAVY_MODEL
        else:
            # Simple tasks (research, audit, critic) can use light model (3B)
            self.model = self.LIGHT_MODEL
        
        # Personas for different roles
        self.personas = {
            "writer": "You are a world-class technical writer and builder. Your goal is to provide a comprehensive, functional solution to the following task. Follow the Master Spec strictly.",
            "critic": "You are the 'WORKER HATER'. You are a ruthless code auditor and bug hunter. Your only job is to find logic holes, security flaws, and bugs. You MUST test the provided code conceptually and reject anything that isn't robust. Be precise and aggressive.",
            "judge": "You are the RECOMBINER. Your role is to synthesize individual shard outcomes and audits into a coherent, fully functional final project. Ensure all pieces fit together perfectly.",
            "scout": "You are a high-speed Nano-Drone. Your job is to perform a quick syntax and logical sanity check of the provided mission goal.",
            "mouth": "You are the communication interface. Be professional, technical, and reassuring. Acknowledge the user's mission and status.",
            "general": "You are a specialized Hive Drone. Think through the task deeply and provide a precise outcome."
        }

    def log_step(self, message):
        print(f"[Drone-{self.drone_id} ({self.role.upper()})] {message}")
        self.log.append(message)

    async def generate_ai_response(self, prompt, system_prompt=None):
        """Calls either the local Ollama API or a remote OpenAI-compatible brain (vLLM)."""
        if system_prompt is None:
            system_prompt = self.personas.get(self.role, self.personas["general"])
        if os.getenv("DISABLE_THINK", "0") == "1" and self.model.startswith("qwen3:"):
            prompt = f"{prompt} /no_think"

        _load_dotenv_if_needed()
        brain_provider = (self.provider_override or os.getenv("BRAIN_PROVIDER", "custom")).lower()

        # Phase 2: Remote Bridge (vLLM/OpenAI or External Free API Provider with Fallback)
        if brain_provider not in ("ollama", "custom") or (self.api_base_url and self.api_base_url != "EXTERNAL"):
            chain = _resolve_provider_chain(brain_provider, self.api_base_url)
            if not chain:
                return "Error: No API provider/key configured. Set BRAIN_PROVIDER and BRAIN_API_KEY in .env."

            max_tokens_env = os.getenv("BRAIN_MAX_TOKENS")
            loop = asyncio.get_event_loop()
            last_error = "No provider succeeded"

            for prov, api_url, brain_model, brain_api_key in chain:
                self.log_step(f"Bridging to {prov.upper()} ({brain_model})...")
                headers = {"Content-Type": "application/json"}
                if brain_api_key:
                    headers["Authorization"] = f"Bearer {brain_api_key}"

                payload = {
                    "model": brain_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                }
                if max_tokens_env:
                    payload["max_tokens"] = int(max_tokens_env)

                has_next_healthy = any(not _is_provider_cooling(p2) for p2, _, _, _ in chain if p2 != prov)
                max_attempts = 1 if has_next_healthy else 4

                for attempt in range(max_attempts):
                    try:
                        if prov != "runpod_serverless":
                            await _pace_remote_call()
                        response = await loop.run_in_executor(
                            None,
                            lambda u=api_url, h=headers, p=payload: requests.post(u, headers=h, json=p, timeout=25),
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if "error" in data or not data.get("choices"):
                                last_error = f"Remote Brain ({prov}) error payload: {str(data.get('error') or data)[:250]}"
                                break
                            global _LAST_SUCCESS_PROVIDER
                            if not self.provider_override and os.getenv("BRAIN_PROVIDER", "").lower() != "hybrid":
                                _LAST_SUCCESS_PROVIDER = prov
                            _PROVIDER_COOLDOWNS.pop(prov, None)
                            return data["choices"][0]["message"]["content"]
                        if response.status_code in (429, 502, 503, 504) and attempt < max_attempts - 1:
                            retry_after = response.headers.get("Retry-After")
                            wait_s = (
                                float(retry_after)
                                if retry_after and retry_after.replace(".", "", 1).isdigit()
                                else (5.0 if response.status_code >= 500 else (2 ** (attempt + 1)) * 3.0)
                            )
                            wait_s = min(wait_s, 45.0)
                            self.log_step(f"Transient {response.status_code} on {prov}; waiting {wait_s:.1f}s...")
                            await asyncio.sleep(wait_s)
                            continue
                        body = response.text.strip()
                        if body.startswith("<"):
                            body = f"HTTP {response.status_code} upstream gateway error"
                        last_error = f"Remote Brain ({prov}) returned {response.status_code}: {body[:250]}"
                        break
                    except Exception as e:
                        last_error = f"Failed to reach {prov}: {str(e)}"
                        break

                cooldown_s = 3600.0 if "402" in last_error else (120.0 if "upstream gateway error" in last_error or "returned 50" in last_error else 1800.0)
                _mark_provider_cooldown(prov, cooldown_s)
                self.log_step(f"Provider {prov} exhausted/failed ({last_error[:80]}), cycling to next free service...")

            return f"Error: {last_error}"

        # Phase 1: Local Ollama
        self.model = os.getenv("HEAVY_MODEL", self.model) if self.task_type == "action" else (
            os.getenv("NANO_MODEL", self.model) if (self.role in ["scout", "mouth", "judge"] or self.task_type == "architecture") else os.getenv("LIGHT_MODEL", self.model)
        )
        full_prompt = f"System: {system_prompt}\n\nTask: {prompt}"
        
        try:
            print(f"[DroneAgent] Calling Ollama at {self.OLLAMA_URL} with model {self.model} (Streaming)...", flush=True)
            # We use loop.run_in_executor for the blocking requests call
            loop = asyncio.get_event_loop()
            
            stream_enabled = os.getenv("OLLAMA_STREAM", "1") == "1"
            timeout_sec = int(os.getenv("OLLAMA_TIMEOUT", "45"))
            default_predict = "400" if self.role == "scout" else "2000"
            num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", default_predict))
            if self.role == "scout":
                num_predict = min(num_predict, 500)
            def stream_request():
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": stream_enabled,
                    "keep_alive": "15m",
                    "options": {"temperature": 0.7, "num_predict": num_predict},
                }
                model_low = (self.model or "").lower()
                if "qwen3" in model_low or "sciencebot" in model_low:
                    payload["think"] = False
                with _OLLAMA_LOCAL_LOCK:
                    response = requests.post(
                        self.OLLAMA_URL,
                        json=payload,
                        timeout=(10, timeout_sec),
                        stream=stream_enabled
                    )
                    if response.status_code != 200:
                        return f"Error: Ollama API returned {response.status_code}"

                    if not stream_enabled:
                        return str((response.json().get("message") or {}).get("content") or "")
                    
                    full_response = ""
                    for line in response.iter_lines():
                        if line:
                            chunk = json.loads(line)
                            content = str((chunk.get("message") or {}).get("content") or chunk.get("response") or "")
                            full_response += content
                            print(".", end="", flush=True) # Token pulse
                    return full_response

            output = await loop.run_in_executor(None, stream_request)
            print(f"\n[DroneAgent] AI Response received (Length: {len(output)})", flush=True)
            return output
        except Exception as e:
            print(f"[DroneAgent] Ollama Exception: {e}", flush=True)
            return f"Error: Failed to connect to Ollama ({str(e)})"

    async def run(self):
        print(f"[DroneAgent] [{self.drone_id}] EXECUTION START. Role: {self.role}, Task Type: {self.task_type}")
        # Complexity check: If the task is too broad, request a sub-shatter
        if len(self.task) > 2000 and self.depth < self.max_depth and self.overmind_callback:
            self.log_step(f"CRITICAL: Task too broad at depth {self.depth}. Requesting Fractal Shatter...")
            sub_results = await self.overmind_callback(self.task, self.depth + 1)
            
            if isinstance(sub_results, list):
                combined_output = "\n".join([f"Sub-Task {r.get('id', '?')}: {r.get('outcome', 'No outcome')}" if isinstance(r, dict) else str(r) for r in sub_results])
            else:
                combined_output = str(sub_results)
            return {
                "id": self.drone_id,
                "status": "COMPLETED_VIA_SHATTER",
                "output": f"Shatter Outcome:\n{combined_output}",
                "log": self.log
            }

        self.log_step(f"Initializing Phase: {self.role.upper()} Drone waking up...")
        print(f"[DroneAgent] [{self.drone_id}] Calling generate_ai_response using model {self.model}...")
        
        # Real AI Processing
        if self.role == "scout":
            self.log_step("Performing NANO-AUDIT on mission parameters...")
            ai_output = await self.generate_ai_response(f"Audit this goal for syntax and logic: {self.task}")
            self.log_step("Audit Complete.")
            # We wrap the output with NANO_AUDIT_PASS if it looks good
            result = f"NANO_AUDIT_PASS: {ai_output}"
        elif self.role == "mouth":
            self.log_step("Syncing with user intent...")
            ai_output = await self.generate_ai_response(f"Acknowledge this mission to the user professionally: {self.task}")
            result = f"SYNC_OK: {ai_output}"
        elif self.role == "critic":
            self.log_step("Searching for logic holes and vulnerabilities...")
            result = await self.generate_ai_response(f"Audit the following work for vulnerabilities and flaws: {self.task}")
        elif self.role == "judge":
            self.log_step("Commencing final project synthesis...")
            result = await self.generate_ai_response(self.task)
        else:
            self.log_step("Synthesizing solution...")
            result = await self.generate_ai_response(self.task)
            
        self.log_step("Finalizing session...")
        return {
            "id": self.drone_id,
            "status": "COMPLETED",
            "output": result,
            "log": self.log
        }
