"""Export ScienceBot's science.db into validated, deduplicated multi-role SFT & DPO JSONL datasets."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "memory" / "science.db"
OUT_DIR = BASE_DIR / "memory" / "training"

WRITER_SYSTEM = (
    "You are a computational physics & astrophysics verification agent. "
    "Given an arXiv paper or research angle, output ONLY a valid JSON object with \"experiment_code\" FIRST, "
    'followed by "title", "domain", "insight", "hypothesis", "mini_experiment", "open_question". '
    "The experiment_code must be self-contained Python (numpy/scipy/sympy/math/h5py) that executes cleanly "
    "and prints quantitative verification results plus PASS or FAIL."
)

CRITIC_SYSTEM = (
    "You are a strict computational physics Critic. Audit the draft, Python code, and measured output. "
    "Start with 'VERDICT: VALID' if math, units, and code are physically sound within the stated regime, "
    "or 'VERDICT: FATAL_ERROR' if there is an actual formula/unit/code error or trivial stub."
)

JUDGE_SYSTEM = (
    "You are the ScienceBot Judge. Synthesize the draft, measured Python output, and Critic audit into a single JSON object "
    'with keys: "title", "domain", "insight", "hypothesis", "mini_experiment", "open_question", "critic_takeaway", "confidence" '
    '("High" if experiment passed and Critic returned VERDICT: VALID, else "Exploratory").'
)

SCOUT_SYSTEM = (
    "You are a computational astrophysics Scout. Given a domain and arXiv paper, propose ONE sharp, "
    "falsifiable hypothesis testable in a short Python (numpy/scipy/sympy/h5py) verification script."
)


def _valid_python(code: str) -> bool:
    code = (code or "").strip()
    if not code or len(code) < 40:
        return False
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _format_user_prompt(row: Dict[str, Any]) -> str:
    parts = []
    if row.get("domain"):
        parts.append(f"Domain: {row['domain']}")
    if row.get("scout_angle"):
        parts.append(f"Scout brief:\n{row['scout_angle']}")
    if row.get("source_title") or row.get("source_url"):
        parts.append(f"Source paper: {row.get('source_title', '')} ({row.get('source_url', '')})")
    if not parts:
        parts.append(f"Topic: {row.get('title', 'Computational physics verification')}")
    return "\n".join(parts)


def _format_writer_json(row: Dict[str, Any]) -> str:
    # Put experiment_code first to match ScienceBot's inference schema
    obj = {
        "experiment_code": row.get("experiment_code") or "",
        "title": row.get("title") or "",
        "domain": row.get("domain") or "",
        "insight": row.get("insight") or "",
        "hypothesis": row.get("hypothesis") or "",
        "mini_experiment": row.get("mini_experiment") or "",
        "open_question": row.get("open_question") or "",
    }
    return json.dumps(obj, ensure_ascii=False)


def export_datasets() -> Dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM articles ORDER BY created_at DESC").fetchall()]

    seen_titles = set()
    verified_passing: List[Dict[str, Any]] = []
    syntax_dropped = 0
    dedup_dropped = 0

    for r in rows:
        if not (r.get("verified") and r.get("experiment_passed")):
            continue
        code = str(r.get("experiment_code") or "").strip()
        if not _valid_python(code):
            syntax_dropped += 1
            continue
        nt = _norm_title(str(r.get("title") or ""))
        if nt and nt in seen_titles:
            dedup_dropped += 1
            continue
        if nt:
            seen_titles.add(nt)
        verified_passing.append(r)

    rejected = [
        r for r in rows
        if (not r.get("verified") or not r.get("experiment_passed"))
        and str(r.get("experiment_code") or "").strip()
    ]

    sft_path = OUT_DIR / "sft_train.jsonl"
    dpo_path = OUT_DIR / "dpo_pairs.jsonl"

    total_chars = 0
    writer_count = 0
    critic_count = 0
    judge_count = 0
    scout_count = 0
    repair_count = 0

    with sft_path.open("w", encoding="utf-8") as f:
        for r in verified_passing:
            # 0. Scout SFT (arXiv -> testable angle)
            if r.get("scout_angle") and r.get("source_title"):
                s_rec = {
                    "messages": [
                        {"role": "system", "content": SCOUT_SYSTEM},
                        {"role": "user", "content": f"Domain: {r.get('domain', '')}\nPaper: {r.get('source_title', '')} ({r.get('source_url', '')})"},
                        {"role": "assistant", "content": str(r["scout_angle"])[:1200]},
                    ]
                }
                s_line = json.dumps(s_rec, ensure_ascii=False)
                total_chars += len(s_line)
                f.write(s_line + "\n")
                scout_count += 1

            # 1. Writer SFT
            w_rec = {
                "messages": [
                    {"role": "system", "content": WRITER_SYSTEM},
                    {"role": "user", "content": _format_user_prompt(r)},
                    {"role": "assistant", "content": _format_writer_json(r)},
                ]
            }
            line = json.dumps(w_rec, ensure_ascii=False)
            total_chars += len(line)
            f.write(line + "\n")
            writer_count += 1

            # 2. Critic SFT (VALID)
            if r.get("critic_takeaway"):
                c_rec = {
                    "messages": [
                        {"role": "system", "content": CRITIC_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"Title: {r.get('title', '')}\n"
                                f"Code:\n```python\n{str(r.get('experiment_code') or '')[:1800]}\n```\n"
                                f"Measured Output:\n{str(r.get('experiment_output') or '')[:800]}"
                            ),
                        },
                        {"role": "assistant", "content": f"VERDICT: VALID\n{r['critic_takeaway']}"},
                    ]
                }
                c_line = json.dumps(c_rec, ensure_ascii=False)
                total_chars += len(c_line)
                f.write(c_line + "\n")
                critic_count += 1

            # 3. Judge SFT
            j_obj = {
                "title": r.get("title") or "",
                "domain": r.get("domain") or "",
                "insight": r.get("insight") or "",
                "hypothesis": r.get("hypothesis") or "",
                "mini_experiment": r.get("mini_experiment") or "",
                "open_question": r.get("open_question") or "",
                "critic_takeaway": r.get("critic_takeaway") or "",
                "confidence": "High",
            }
            j_rec = {
                "messages": [
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Draft: {r.get('title', '')} — {r.get('insight', '')}\n"
                            f"Experiment (passed=True): {str(r.get('experiment_output') or '')[:700]}\n"
                            f"Critic: VERDICT: VALID\n{str(r.get('critic_takeaway') or '')[:600]}"
                        ),
                    },
                    {"role": "assistant", "content": json.dumps(j_obj, ensure_ascii=False)},
                ]
            }
            j_line = json.dumps(j_rec, ensure_ascii=False)
            total_chars += len(j_line)
            f.write(j_line + "\n")
            judge_count += 1

        # Add negative Critic examples (FATAL_ERROR) up to 25% of positive count
        for r in rejected[: max(20, len(verified_passing) // 4)]:
            if not r.get("critic_takeaway"):
                continue
            c_neg = {
                "messages": [
                    {"role": "system", "content": CRITIC_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Title: {r.get('title', '')}\n"
                            f"Code:\n```python\n{str(r.get('experiment_code') or '')[:1500]}\n```\n"
                            f"Measured Output:\n{str(r.get('experiment_output') or '')[:600]}"
                        ),
                    },
                    {"role": "assistant", "content": f"VERDICT: FATAL_ERROR\n{r['critic_takeaway']}"},
                ]
            }
            n_line = json.dumps(c_neg, ensure_ascii=False)
            total_chars += len(n_line)
            f.write(n_line + "\n")
            critic_count += 1

        # Merge captured Self-Repair trajectories
        repair_path = OUT_DIR / "self_repair_sft.jsonl"
        if repair_path.exists():
            for line in repair_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                total_chars += len(line)
                f.write(line.strip() + "\n")
                repair_count += 1

    # DPO preference pairs: prioritize sciencebot-4b v2 mistakes, then stock 4B mistakes, then domain rejections
    dpo_count = 0
    seen_dpo_prompts = set()
    with dpo_path.open("w", encoding="utf-8") as f:
        for onpolicy_path in (
            OUT_DIR / "onpolicy_dpo_pairs_v3.jsonl",
            OUT_DIR / "onpolicy_dpo_pairs_4b_runpod.jsonl",
            OUT_DIR / "onpolicy_dpo_pairs_v2.jsonl",
            OUT_DIR / "onpolicy_dpo_pairs.jsonl",
        ):
            if not onpolicy_path.exists():
                continue
            for line in onpolicy_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    op = json.loads(line)
                    if op.get("prompt") and op.get("chosen") and op.get("rejected") and op["prompt"] not in seen_dpo_prompts:
                        rec = {"prompt": op["prompt"], "chosen": op["chosen"], "rejected": op["rejected"]}
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        seen_dpo_prompts.add(op["prompt"])
                        dpo_count += 1
                except Exception:
                    pass

        rej_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for r in rejected:
            rej_by_domain.setdefault(str(r.get("domain") or "general"), []).append(r)

        for idx, pos in enumerate(verified_passing):
            prompt_txt = f"{WRITER_SYSTEM}\n\n{_format_user_prompt(pos)}"
            if prompt_txt in seen_dpo_prompts:
                continue
            dom = str(pos.get("domain") or "general")
            pool = rej_by_domain.get(dom) or rejected
            if not pool:
                continue
            neg = pool[idx % len(pool)]
            rec = {
                "prompt": prompt_txt,
                "chosen": _format_writer_json(pos),
                "rejected": _format_writer_json(neg),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            dpo_count += 1

    return {
        "total_db_rows": len(rows),
        "scout_sft": scout_count,
        "writer_sft": writer_count,
        "repair_sft": repair_count,
        "critic_sft": critic_count,
        "judge_sft": judge_count,
        "total_sft_examples": scout_count + writer_count + repair_count + critic_count + judge_count,
        "dpo_pairs": dpo_count,
        "syntax_dropped": syntax_dropped,
        "dedup_dropped": dedup_dropped,
        "approx_sft_tokens": total_chars // 4,
        "sft_path": str(sft_path),
        "dpo_path": str(dpo_path),
    }


if __name__ == "__main__":
    print(json.dumps(export_datasets(), indent=2))
