import json
import os
import random
import time
from typing import Dict, List, Tuple

import requests

MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Controls for the test sweep.
TRIALS_PER_SIZE = int(os.getenv("TRIALS_PER_SIZE", "2"))
REQUIREMENT_COUNTS = [
    int(x) for x in os.getenv("REQUIREMENT_COUNTS", "4,6,8,10,12").split(",") if x
]
TEMPERATURE = 0.2
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "600"))
TIMEOUT_SEC = int(os.getenv("TIMEOUT_SEC", "120"))


TASK_TYPES = [
    {
        "name": "parser",
        "title": "Build a log parser module",
        "description": (
            "Implement a Python module that parses lines of server logs and "
            "emits structured dicts. Include parsing and validation helpers."
        ),
        "required_symbols": ["parse_line", "parse_timestamp", "validate_record"],
    },
    {
        "name": "queue",
        "title": "Implement a task queue",
        "description": (
            "Implement a lightweight in-memory task queue with retry support "
            "and backoff. Provide enqueue and worker loop utilities."
        ),
        "required_symbols": ["enqueue", "dequeue", "worker_loop", "RetryPolicy"],
    },
    {
        "name": "cache",
        "title": "Build a TTL cache",
        "description": (
            "Implement a TTL cache with max size and eviction policy. "
            "Provide get/set methods and stats."
        ),
        "required_symbols": ["get", "set", "evict", "CacheStats"],
    },
]

TASK_FILTER = [t for t in os.getenv("TASK_FILTER", "").split(",") if t]
OUTPUT_LOG = os.getenv("OUTPUT_LOG", "")


def build_prompt(task: Dict, requirement_count: int) -> Tuple[str, List[str]]:
    base_reqs = [
        "Include type hints for public functions.",
        "Add basic input validation and raise ValueError on invalid input.",
        "Write a small usage example in a main guard.",
        "Keep functions short and focused (<= 30 lines).",
        "Avoid external dependencies.",
        "Return deterministic results.",
        "Add docstrings for public functions/classes.",
        "Use dataclasses where appropriate.",
        "Handle empty input gracefully.",
        "Include a simple unit-test-like function named run_smoke_tests.",
        "Do not use global state.",
        "Follow PEP8 naming conventions.",
        "Use a small helper function named _normalize.",
        "Avoid recursion.",
        "Use only built-in modules.",
        "Prefer iterators to building large lists.",
        "Provide clear error messages.",
        "Add a simple Stats class.",
        "Limit line length to 100 chars.",
        "Include a minimal README-style comment header.",
    ]

    required_symbols = list(task["required_symbols"])
    required_symbols.extend(["run_smoke_tests", "_normalize"])

    reqs = base_reqs[:requirement_count]
    reqs_text = "\n".join([f"- {r}" for r in reqs])

    symbols_text = ", ".join(required_symbols)
    prompt = (
        f"{task['title']}\n"
        f"{task['description']}\n\n"
        "Required symbols:\n"
        f"{symbols_text}\n\n"
        "Requirements:\n"
        f"{reqs_text}\n\n"
        "Keep the implementation minimal and compact while still correct.\n"
        "Output a single Python file. Include all required symbols and example usage.\n"
        "Do not include explanations outside the code."
    )
    return prompt, required_symbols


def call_ollama(prompt: str) -> str:
    body = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": TEMPERATURE, "num_predict": NUM_PREDICT},
    }
    resp = requests.post(OLLAMA_URL, json=body, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json().get("response", "")


def evaluate_output(output: str, required_symbols: List[str]) -> bool:
    if not output or len(output) < 200:
        return False
    lowered = output.lower()
    for sym in required_symbols:
        if sym.lower() not in lowered:
            return False
    return True


def run_trial(task: Dict, requirement_count: int) -> Dict:
    prompt, required_symbols = build_prompt(task, requirement_count)
    start = time.time()
    output = ""
    error = None
    try:
        output = call_ollama(prompt)
    except Exception as exc:
        error = str(exc)
    duration = time.time() - start
    passed = evaluate_output(output, required_symbols) if not error else False
    record = {
        "task": task["name"],
        "requirement_count": requirement_count,
        "prompt_chars": len(prompt),
        "prompt_words": len(prompt.split()),
        "duration_sec": round(duration, 2),
        "passed": passed,
        "error": error,
    }
    if OUTPUT_LOG:
        with open(OUTPUT_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "task": task["name"],
                "requirement_count": requirement_count,
                "prompt": prompt,
                "required_symbols": required_symbols,
                "passed": passed,
                "error": error,
                "output": output,
            }, ensure_ascii=True) + "\n")
    return record


def summarize(results: List[Dict]) -> List[Dict]:
    buckets = {}
    for r in results:
        key = (r["requirement_count"], r["prompt_chars"], r["prompt_words"])
        buckets.setdefault(key, []).append(r)

    summary = []
    for (req_count, chars, words), items in buckets.items():
        pass_rate = sum(1 for i in items if i["passed"]) / len(items)
        avg_time = sum(i["duration_sec"] for i in items) / len(items)
        errors = sum(1 for i in items if i.get("error"))
        summary.append({
            "requirements": req_count,
            "prompt_chars": chars,
            "prompt_words": words,
            "pass_rate": round(pass_rate, 2),
            "avg_time_sec": round(avg_time, 2),
            "trials": len(items),
            "errors": errors,
        })

    summary.sort(key=lambda x: x["requirements"])
    return summary


def recommend(summary: List[Dict], min_pass_rate: float = 0.8) -> Dict:
    candidates = [s for s in summary if s["pass_rate"] >= min_pass_rate]
    if not candidates:
        return {"max_chars": None, "max_words": None}

    best = max(candidates, key=lambda s: s["requirements"])
    return {"max_chars": best["prompt_chars"], "max_words": best["prompt_words"]}


def main():
    random.seed(7)
    results = []

    tasks = TASK_TYPES
    if TASK_FILTER:
        tasks = [t for t in TASK_TYPES if t["name"] in TASK_FILTER]

    for requirement_count in REQUIREMENT_COUNTS:
        for task in tasks:
            for _ in range(TRIALS_PER_SIZE):
                print(f"Running: reqs={requirement_count} task={task['name']}", flush=True)
                results.append(run_trial(task, requirement_count))

    summary = summarize(results)
    recommendation = recommend(summary, min_pass_rate=0.8)

    print("MODEL:", MODEL)
    print("RESULTS SUMMARY:")
    for row in summary:
        print(
            f"reqs={row['requirements']:2d} "
            f"chars={row['prompt_chars']:4d} "
            f"words={row['prompt_words']:3d} "
            f"pass={row['pass_rate']:.2f} "
            f"avg_time={row['avg_time_sec']:.2f}s "
            f"trials={row['trials']} "
            f"errors={row['errors']}"
        )

    print("\nRECOMMENDATION:")
    print(json.dumps(recommendation, indent=2))


if __name__ == "__main__":
    main()
