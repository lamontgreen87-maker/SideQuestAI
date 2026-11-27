"""Generate On-Policy DPO pairs by having stock qwen3:4b (e.g. on Beelink SER5) attempt verified prompts.

Usage (from main PC pointing at SER5 over Tailscale):
    python ser5_onpolicy_dpo.py http://100.x.x.x:11434

Or copy science.db / training/ onto SER5 and run locally on SER5:
    python ser5_onpolicy_dpo.py http://127.0.0.1:11434
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, Set

import requests

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from export_training_data import WRITER_SYSTEM, _format_user_prompt, _format_writer_json, _valid_python  # noqa: E402
from science_bot import DB_FILE, _extract_json_obj, _run_experiment_code  # noqa: E402

OUT_FILE = Path(os.getenv("ONPOLICY_OUT_FILE") or str(BASE_DIR / "memory" / "training" / "onpolicy_dpo_pairs.jsonl"))
DEFAULT_OLLAMA = os.getenv("SER5_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("SER5_MODEL", "qwen3:4b")


def _load_seen_ids() -> Set[str]:
    seen: Set[str] = set()
    if not OUT_FILE.exists():
        return seen
    for line in OUT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if obj.get("article_id"):
                seen.add(str(obj["article_id"]))
        except Exception:
            pass
    return seen


def _ask_4b(ollama_base: str, prompt: str) -> str:
    url = f"{ollama_base.rstrip('/')}/api/chat"
    r = requests.post(
        url,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": WRITER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "options": {"temperature": 0.7, "num_predict": 2500},
        },
        timeout=(10, 300),
    )
    r.raise_for_status()
    return str((r.json().get("message") or {}).get("content") or "").strip()


def main() -> None:
    ollama_base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OLLAMA
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    seen = _load_seen_ids()

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM articles WHERE verified=1 AND experiment_passed=1 ORDER BY created_at DESC").fetchall()]

    candidates = [r for r in rows if str(r.get("id") or "") not in seen and _valid_python(str(r.get("experiment_code") or ""))][:limit]
    print(f"[OnPolicy-DPO] Target={ollama_base} ({MODEL}) | {len(candidates)} new verified prompts (already seen={len(seen)})", flush=True)

    pairs_added = 0
    passed_4b = 0
    with OUT_FILE.open("a", encoding="utf-8") as f:
        for idx, row in enumerate(candidates, 1):
            user_prompt = _format_user_prompt(row)
            try:
                raw_4b = _ask_4b(ollama_base, user_prompt)
            except Exception as e:
                print(f"[OnPolicy-DPO] Request error at {idx}: {e}", flush=True)
                time.sleep(2)
                continue

            obj_4b = _extract_json_obj(raw_4b) or {}
            code_4b = str(obj_4b.get("experiment_code") or "").strip()
            res_4b = _run_experiment_code(code_4b) if code_4b else {"passed": False, "output": "No experiment code provided."}

            if res_4b.get("passed"):
                passed_4b += 1
            else:
                rec = {
                    "article_id": str(row.get("id") or ""),
                    "prompt": f"{WRITER_SYSTEM}\n\n{user_prompt}",
                    "chosen": _format_writer_json(row),
                    "rejected": raw_4b or '{"error": "empty response"}',
                    "failure_reason": str(res_4b.get("output") or "")[:300],
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                pairs_added += 1

            if idx % 10 == 0 or idx == len(candidates):
                print(f"[OnPolicy-DPO] {idx}/{len(candidates)} | 4B passed={passed_4b} | DPO mistake pairs={pairs_added}", flush=True)


if __name__ == "__main__":
    main()

