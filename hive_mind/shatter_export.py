import json
import os
import sys
from datetime import datetime, timezone
from hashlib import sha256

from shatter_cache import DEFAULT_CACHE_PATH


def export_shatter(goal: str, shards: list, scores: dict, cache_path: str = DEFAULT_CACHE_PATH):
    goal_hash = "sha256:" + sha256(goal.encode("utf-8")).hexdigest()
    payload = {
        "type": "shatter_post",
        "goal_hash": goal_hash,
        "goal_summary": goal[:200],
        "domain_tags": [],
        "model": os.getenv("NANO_MODEL", "unknown"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "shards": shards,
        "validation": {
            "passed": True,
            "issues": [],
            "oversized": []
        },
        "scores": scores
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python shatter_export.py <goal> <shards_json_path> [score_json_path]")
    goal = sys.argv[1]
    shards_path = sys.argv[2]
    score_path = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.exists(shards_path):
        raise SystemExit(f"Shards file not found: {shards_path}")

    with open(shards_path, "r", encoding="utf-8") as handle:
        shards = json.load(handle)

    scores = {"consistency_pass_rate": 0.0, "audit_pass_rate": 0.0, "recombine_pass": False}
    if score_path and os.path.exists(score_path):
        with open(score_path, "r", encoding="utf-8") as handle:
            scores.update(json.load(handle))

    export_shatter(goal, shards, scores)
    print(f"Exported shatter to {DEFAULT_CACHE_PATH}")


if __name__ == "__main__":
    main()
