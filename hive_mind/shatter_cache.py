import json
import os
from typing import List


DEFAULT_CACHE_PATH = os.path.join("memory", "shatter_cache.jsonl")


def _score_post(post: dict) -> float:
    scores = post.get("scores", {}) if isinstance(post, dict) else {}
    consistency = float(scores.get("consistency_pass_rate", 0))
    audit = float(scores.get("audit_pass_rate", 0))
    recombine = 1.0 if scores.get("recombine_pass") else 0.0
    return (0.5 * consistency) + (0.4 * audit) + (0.1 * recombine)


def load_shatter_examples(cache_path: str = DEFAULT_CACHE_PATH, limit: int = 3) -> List[dict]:
    if not os.path.exists(cache_path):
        return []

    posts = []
    with open(cache_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                post = json.loads(line)
                if post.get("type") != "shatter_post":
                    continue
                posts.append(post)
            except json.JSONDecodeError:
                continue

    posts.sort(key=_score_post, reverse=True)
    return posts[:limit]


def format_examples_for_prompt(posts: List[dict]) -> str:
    formatted = []
    for post in posts:
        shards = post.get("shards", [])
        cleaned = []
        for shard in shards:
            if not isinstance(shard, dict):
                continue
            cleaned.append({
                "id": shard.get("id"),
                "task": shard.get("task"),
                "required_tier": shard.get("required_tier"),
                "depends_on": shard.get("depends_on", []),
                "inputs": shard.get("inputs", []),
                "outputs": shard.get("outputs", []),
                "success_criteria": shard.get("success_criteria", []),
            })
        formatted.append({
            "goal_summary": post.get("goal_summary"),
            "domain_tags": post.get("domain_tags", []),
            "shards": cleaned,
        })
    return json.dumps(formatted, ensure_ascii=True)
