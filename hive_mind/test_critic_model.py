import json
import os
import time

import requests

MODEL = os.getenv("CRITIC_MODEL", "qwen2.5:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
TIMEOUT_SEC = int(os.getenv("TIMEOUT_SEC", "90"))


def call_model(prompt: str) -> str:
    body = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 180},
    }
    resp = requests.post(OLLAMA_URL, json=body, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json().get("response", "")


def build_prompt(case):
    return f"""
You are the CONSISTENCY CRITIC SWARM. Check whether this shard output fits the project.
You MUST explicitly identify the primary language and provide line-level fixes.
If there is no clear language, say UNKNOWN and still provide line-level guidance.

SHARD ID: {case['id']}
SHARD TASK: {case['task']}
DEPENDS_ON: {case['depends_on']}
INPUTS: {case['inputs']}
OUTPUTS: {case['outputs']}
SUCCESS_CRITERIA: {case['success_criteria']}

PROJECT MEMORY:
{case['project_memory']}

SHARD OUTPUT (number lines in your analysis):
{case['output']}

Respond with ONLY one of:
OK
or
REVISE:
- LANGUAGE: <explicit language or UNKNOWN>
- EVIDENCE: <concrete problems with file paths and line references like src/app.py:L12; if unknown, provide best-guess target path>
- MISSING: <what is missing to fit project>
- SUGGEST: <concise fix guidance (no edits), include file paths and line refs>
- NOTES: <any other inconsistencies or risks>
""".strip()


def run_case(case):
    prompt = build_prompt(case)
    start = time.time()
    response = call_model(prompt)
    elapsed = time.time() - start
    return response, round(elapsed, 2)


def main():
    project_memory = (
        "### PROJECT MEMORY ###\n"
        "Primary Goal: Build a small Python library for task queuing.\n"
        "Architecture: {\"modules\": [\"queue.py\", \"retry.py\"]}\n"
        "Previous Shard Outcomes:\n"
        "- Shard A: Implemented enqueue/dequeue API for TaskQueue.\n"
    )

    cases = [
        {
            "id": "B",
            "task": "Add retry policy and worker loop in queue.py",
            "depends_on": ["A"],
            "inputs": ["TaskQueue"],
            "outputs": ["RetryPolicy", "worker_loop"],
            "success_criteria": ["RetryPolicy exists", "worker_loop uses backoff"],
            "project_memory": project_memory,
            "output": (
                "def worker_loop(queue):\n"
                "    while True:\n"
                "        task = queue.dequeue()\n"
                "        task()\n"
                "class RetryPolicy:\n"
                "    def __init__(self, max_retries=3):\n"
                "        self.max_retries = max_retries\n"
            ),
            "expect": "REVISE",
            "reason": "No backoff, missing file path guidance, no input validation.",
        },
        {
            "id": "C",
            "task": "Add TTL cache utility in cache.py",
            "depends_on": [],
            "inputs": [],
            "outputs": ["TTLCache"],
            "success_criteria": ["TTLCache supports get/set", "eviction policy noted"],
            "project_memory": project_memory,
            "output": (
                "class TTLCache:\n"
                "    def __init__(self):\n"
                "        self.data = {}\n"
                "    def get(self, key):\n"
                "        return self.data[key]\n"
                "    def set(self, key, value):\n"
                "        self.data[key] = value\n"
            ),
            "expect": "REVISE",
            "reason": "No TTL/eviction policy, missing constraints.",
        },
        {
            "id": "D",
            "task": "Add a README snippet in docs/README.md",
            "depends_on": [],
            "inputs": [],
            "outputs": ["README"],
            "success_criteria": ["Usage example included"],
            "project_memory": project_memory,
            "output": (
                "# Task Queue Library\n"
                "Usage:\n"
                "from queue import TaskQueue\n"
                "q = TaskQueue()\n"
            ),
            "expect": "REVISE",
            "reason": "Missing usage example details and file path refs.",
        },
    ]

    results = []
    for case in cases:
        response, elapsed = run_case(case)
        verdict = "OK" if response.strip().upper().startswith("OK") else "REVISE"
        results.append({
            "id": case["id"],
            "expected": case["expect"],
            "verdict": verdict,
            "elapsed_sec": elapsed,
            "response": response.strip(),
        })

    print(f"MODEL: {MODEL}")
    for r in results:
        print(f"[{r['id']}] expected={r['expected']} got={r['verdict']} time={r['elapsed_sec']}s")
        print(r["response"])
        print("-" * 40)

    print("RAW_RESULTS_JSON:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
