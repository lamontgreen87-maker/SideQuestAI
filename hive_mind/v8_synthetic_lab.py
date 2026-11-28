"""v8 Multi-Catalog Synthetic Lab & Novelty DPO Miner.

Generates:
  1. v8_lab_sft.jsonl: Verified multi-catalog Python experiments + Critic audits
     across NASA Exoplanets, Pantheon+SH0ES SNe Ia, and USGS Earthquakes.
  2. v8_lab_dpo.jsonl: Plain-string DPO pairs teaching:
     - Real statistical null controls / bootstrap p-values over toy/mock stubs
     - High-novelty (>=85) anomaly/tension hunting over low-novelty (<=55) repeats
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from export_training_data import CRITIC_SYSTEM, WRITER_SYSTEM  # noqa: E402

OPEN_MANIFEST = BASE_DIR / "memory" / "open_catalogs" / "manifest.json"
DB_FILE = BASE_DIR / "memory" / "science.db"
OUT_SFT = BASE_DIR / "memory" / "training" / "v8_lab_sft.jsonl"
OUT_DPO = BASE_DIR / "memory" / "training" / "v8_lab_dpo.jsonl"

_CATALOG_RECIPES: List[Dict[str, str]] = [
    {
        "catalog": "exoplanets",
        "title": "Exoplanet Mass-Radius Density Transition & Radius-Valley Permutation Test",
        "math_derivation": (
            "1) Governing Equation: Bulk density ratio relative to Earth is rho_rel = (M_p / M_earth) / (R_p / R_earth)^3, "
            "where M_p = pl_bmasse [M_earth] and R_p = pl_rade [R_earth], so rho_rel is dimensionless. "
            "2) Group Statistic: T_obs = median(rho_rel | R_p < 1.6) - median(rho_rel | 1.8 <= R_p <= 3.5). "
            "3) Null Hypothesis H0: Rocky and sub-Neptune densities are exchangeable; empirical one-sided p = (1 + count(T_perm >= T_obs)) / (1 + N_perm) with N_perm = 200."
        ),
        "hypothesis": "Confirmed exoplanets in the NASA Exoplanet Archive exhibit a statistically significant bulk-density break between rocky super-Earths (R < 1.6 R_earth) and sub-Neptunes (1.8 < R < 3.5 R_earth) that persists against 200 random label permutations (p < 0.01).",
        "code": '''import json, os
import numpy as np

cat = json.load(open(os.environ["OPEN_CATALOGS_MANIFEST"]))["catalogs"]["exoplanets"]
rows = json.load(open(cat["file"]))
rocky, subnep = [], []
for r in rows:
    rad, mass = r.get("pl_rade"), r.get("pl_bmasse")
    if rad is None or mass is None or rad <= 0 or mass <= 0:
        continue
    rho = mass / (rad ** 3)  # Earth-relative bulk density
    if rad < 1.6:
        rocky.append(rho)
    elif 1.8 <= rad <= 3.5:
        subnep.append(rho)

rocky = np.asarray(rocky, dtype=float)
subnep = np.asarray(subnep, dtype=float)
assert len(rocky) >= 10 and len(subnep) >= 10, "Insufficient planets in bins"
obs_diff = float(np.median(rocky) - np.median(subnep))
pooled = np.concatenate([rocky, subnep])
rng = np.random.default_rng(42)
n_perm = 200
ge = 0
for _ in range(n_perm):
    perm = rng.permutation(pooled)
    d = float(np.median(perm[:len(rocky)]) - np.median(perm[len(rocky):]))
    if d >= obs_diff:
        ge += 1
p_val = (ge + 1) / (n_perm + 1)
print(f"rocky_n={len(rocky)} subnep_n={len(subnep)} med_rho_diff={obs_diff:.4f} p={p_val:.4f}")
print("PASS" if (obs_diff > 0 and p_val < 0.05) else "FAIL")''',
        "bad_code": '''import json, os
print("Using mock exoplanet sample: rocky=10, subnep=10, diff=0.5")
print("PASS")''',
    },
    {
        "catalog": "pantheon_sne",
        "title": "Pantheon+SH0ES Low-z vs High-z Hubble Residual & Flat LCDM Chi2 Check",
        "math_derivation": (
            "1) Governing Equation (Flat LCDM): E(z) = sqrt(Omega_m*(1+z)^3 + Omega_L), "
            "d_C(z) = (c/H_0)*integral_0^z dz'/E(z') [Mpc], d_L(z) = (1+z)*d_C(z) [Mpc], "
            "mu_model(z) = 5*log10(d_L/Mpc) + 25 [mag], with c = 299792.458 km/s, H_0 = 73.04 km/s/Mpc, Omega_m = 0.315, Omega_L = 0.685. "
            "2) Goodness-of-Fit & Residual Split: chi2_red = mean(((mu_obs - mu_model)/sigma_mu)^2), "
            "Delta_mu = mean(res[z < 0.1]) - mean(res[z >= 0.1]) [mag], uncertainty via N_boot = 200 bootstrap resamples."
        ),
        "hypothesis": "Pantheon+SH0ES Type Ia supernovae show a tight Hubble diagram residual around flat LCDM (Omega_m=0.315, H0=73.04) with non-zero reduced chi2 and measurable low-z vs high-z residual offset tested via 200 bootstrap resamples.",
        "code": '''import json, os
import numpy as np

cat = json.load(open(os.environ["OPEN_CATALOGS_MANIFEST"]))["catalogs"]["pantheon_sne"]
rows = json.load(open(cat["file"]))
z = np.array([r["zhd"] for r in rows if r["zhd"] > 0.01 and r["mu_err"] > 0], dtype=float)
mu = np.array([r["mu_sh0es"] for r in rows if r["zhd"] > 0.01 and r["mu_err"] > 0], dtype=float)
err = np.array([r["mu_err"] for r in rows if r["zhd"] > 0.01 and r["mu_err"] > 0], dtype=float)

c_km_s = 299792.458
H0, Om, OL = 73.04, 0.315, 0.685
mu_model = np.empty_like(z)
for i, zi in enumerate(z):
    zs = np.linspace(0.0, zi, 128)
    ez = np.sqrt(Om * (1.0 + zs) ** 3 + OL)
    dc = (c_km_s / H0) * np.trapezoid(1.0 / ez, zs)
    dl_mpc = (1.0 + zi) * dc
    mu_model[i] = 5.0 * np.log10(dl_mpc) + 25.0

res = mu - mu_model
chi2_red = float(np.mean((res / err) ** 2))
low_mask = z < 0.1
high_mask = z >= 0.1
obs_shift = float(np.mean(res[low_mask]) - np.mean(res[high_mask]))
rng = np.random.default_rng(7)
boots = [
    float(np.mean(rng.choice(res[low_mask], size=int(np.sum(low_mask)), replace=True))
          - np.mean(rng.choice(res[high_mask], size=int(np.sum(high_mask)), replace=True)))
    for _ in range(200)
]
boot_std = float(np.std(boots))
print(f"n_sne={len(z)} chi2_red={chi2_red:.3f} low_high_shift={obs_shift:.4f}+/-{boot_std:.4f} mag")
print("PASS" if (len(z) > 1000 and 0.2 < chi2_red < 3.0) else "FAIL")''',
        "bad_code": '''import numpy as np
print("0 events checked; fallback to toy Hubble constant H0=70")
print("PASS")''',
    },
    {
        "catalog": "earthquakes",
        "title": "USGS ComCat M4.5+ Gutenberg-Richter b-Value MLE & Shallow-vs-Deep Magnitude Null Test",
        "math_derivation": (
            "1) Governing Equation (Aki-Utsu MLE): log10 N(>=M) = a - b*M => b_hat = log10(e) / (mean(M) - (M_min - Delta_M/2)) [dimensionless], "
            "with M_min = 4.5, bin width Delta_M = 0.1. "
            "2) Depth Comparison: T_obs = mean(M[depth >= 70 km]) - mean(M[depth < 70 km]). "
            "3) Null Hypothesis H0: Magnitude is independent of focal depth; two-sided p = (1 + count(|T_perm| >= |T_obs|)) / (1 + 200)."
        ),
        "hypothesis": "Global M4.5+ USGS earthquakes follow a Gutenberg-Richter b-value near 1.0 (Aki-Utsu MLE) and exhibit a testable magnitude distribution difference between shallow (<70 km) and deep (>=70 km) events evaluated against 200 random permutations.",
        "code": '''import json, os
import numpy as np

cat = json.load(open(os.environ["OPEN_CATALOGS_MANIFEST"]))["catalogs"]["earthquakes"]
rows = json.load(open(cat["file"]))
mags = np.array([r["mag"] for r in rows if r["mag"] >= 4.5], dtype=float)
depths = np.array([r["depth_km"] for r in rows if r["mag"] >= 4.5], dtype=float)
assert len(mags) >= 50, "Insufficient earthquake rows"

m_min = 4.5
b_mle = float(np.log10(np.e) / (np.mean(mags) - (m_min - 0.05)))
shallow = mags[depths < 70.0]
deep = mags[depths >= 70.0]
obs_diff = float(np.mean(deep) - np.mean(shallow)) if len(deep) > 5 else 0.0
rng = np.random.default_rng(11)
n_perm = 200
ge = 0
for _ in range(n_perm):
    perm = rng.permutation(mags)
    d = float(np.mean(perm[:len(deep)]) - np.mean(perm[len(deep):])) if len(deep) > 5 else 0.0
    if abs(d) >= abs(obs_diff):
        ge += 1
p_val = (ge + 1) / (n_perm + 1)
print(f"n_eq={len(mags)} b_mle={b_mle:.3f} deep_n={len(deep)} diff={obs_diff:.4f} p={p_val:.4f}")
print("PASS" if (0.5 <= b_mle <= 2.0 and len(mags) >= 50) else "FAIL")''',
        "bad_code": '''import json, os
print("placeholder seismic b-value = 1.0")
print("PASS")''',
    },
]


def _prompt_str(system_txt: str, user_txt: str) -> str:
    return f"{system_txt}\n\n{user_txt}"


def build_v8_lab_datasets() -> Dict[str, int]:
    OUT_SFT.parent.mkdir(parents=True, exist_ok=True)
    sft_rows: List[Dict[str, Any]] = []
    dpo_rows: List[Dict[str, Any]] = []

    if OPEN_MANIFEST.exists():
        for rec in _CATALOG_RECIPES:
            user_prompt = (
                f"DATA-FIRST REAL OBSERVATIONAL MODE (NO ARXIV PAPER).\n"
                f"Target Title: {rec['title']}\n"
                f"Hypothesis: {rec['hypothesis']}\n"
                f"Catalog: {rec['catalog']} via `os.environ['OPEN_CATALOGS_MANIFEST']`.\n"
                "MATH-FIRST RULE: Explicitly derive the governing equation, units/dimensions, and null-hypothesis test statistic in `math_derivation` BEFORE `experiment_code`.\n"
                "Output ONLY valid JSON with keys: title, domain, math_derivation, hypothesis, mini_experiment, experiment_code, expected_result."
            )
            good_json = json.dumps({
                "title": rec["title"],
                "domain": "Observational Astrophysics & Statistical Physics",
                "math_derivation": rec["math_derivation"],
                "hypothesis": rec["hypothesis"],
                "mini_experiment": f"Load {rec['catalog']} from OPEN_CATALOGS_MANIFEST, compute real statistic, and run >=200 permutation/bootstrap null trials.",
                "experiment_code": rec["code"],
                "expected_result": "Quantitative metric + empirical p-value + PASS/FAIL.",
            })
            bad_json = json.dumps({
                "title": rec["title"],
                "domain": "Observational Astrophysics & Statistical Physics",
                "math_derivation": "Skipped explicit equations and units.",
                "hypothesis": rec["hypothesis"],
                "mini_experiment": "Placeholder toy check.",
                "experiment_code": rec["bad_code"],
                "expected_result": "PASS",
            })
            sft_rows.append({
                "messages": [
                    {"role": "system", "content": WRITER_SYSTEM},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": good_json},
                ],
                "source": f"v8_lab_{rec['catalog']}",
            })
            dpo_rows.append({
                "prompt": _prompt_str(WRITER_SYSTEM, user_prompt),
                "chosen": good_json,
                "rejected": bad_json,
                "failure_mode": "v8_stub_vs_real_catalog",
            })

    # Mine high-novelty (>=85) vs low-novelty (<=55) DPO pairs from science.db
    novelty_pairs = 0
    if DB_FILE.exists():
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                high = conn.execute(
                    "SELECT title, domain, hypothesis, mini_experiment, experiment_code, insight, novelty_score "
                    "FROM articles WHERE verified=1 AND novelty_score >= 85 AND length(experiment_code) > 120 "
                    "ORDER BY novelty_score DESC, rowid DESC LIMIT 120"
                ).fetchall()
                low = conn.execute(
                    "SELECT title, domain, hypothesis, mini_experiment, experiment_code, insight, novelty_score "
                    "FROM articles WHERE verified=1 AND novelty_score <= 55 AND length(experiment_code) > 120 "
                    "ORDER BY rowid DESC LIMIT 120"
                ).fetchall()
                for hi, lo in zip(high, low):
                    p = _prompt_str(
                        WRITER_SYSTEM,
                        f"Domain: {hi['domain']}\nDesign a HIGH-NOVELTY quantitative experiment that tests a real tension, anomaly, or residual rather than a routine textbook check.",
                    )
                    chosen = json.dumps({
                        "title": hi["title"],
                        "domain": hi["domain"],
                        "hypothesis": hi["hypothesis"],
                        "mini_experiment": hi["mini_experiment"],
                        "experiment_code": hi["experiment_code"],
                        "expected_result": hi["insight"][:220] if hi["insight"] else "Quantitative anomaly test",
                    })
                    rejected = json.dumps({
                        "title": lo["title"],
                        "domain": lo["domain"],
                        "hypothesis": lo["hypothesis"],
                        "mini_experiment": lo["mini_experiment"],
                        "experiment_code": lo["experiment_code"],
                        "expected_result": lo["insight"][:220] if lo["insight"] else "Routine check",
                    })
                    dpo_rows.append({
                        "prompt": p,
                        "chosen": chosen,
                        "rejected": rejected,
                        "failure_mode": "v8_novelty_upgrade",
                    })
                    novelty_pairs += 1
        except Exception:
            pass

    OUT_SFT.write_text("\n".join(json.dumps(r) for r in sft_rows) + ("\n" if sft_rows else ""), encoding="utf-8")
    OUT_DPO.write_text("\n".join(json.dumps(r) for r in dpo_rows) + ("\n" if dpo_rows else ""), encoding="utf-8")
    return {"v8_lab_sft": len(sft_rows), "v8_lab_dpo": len(dpo_rows), "novelty_pairs": novelty_pairs}


EXAM_FILE = BASE_DIR / "memory" / "training" / "v8_phd_exam.json"


def run_v8_phd_exam(ollama_base: str = "http://127.0.0.1:11434", model: str = "v7-8b", max_repairs: int = 0) -> Dict[str, Any]:
    """Grade a model on the 4-part Math-First Multi-Catalog v8 PhD Exam."""
    import os
    import requests
    from datetime import datetime, timezone
    from science_bot import _extract_json_obj, _run_experiment_code

    os.environ["OPEN_CATALOGS_MANIFEST"] = str(OPEN_MANIFEST)
    tests = [
        ("gwosc_signal", "MATH-FIRST EXAM (GW190814 - Signal): First derive `math_derivation` (whitening, H1-L1 cross-correlation equation, units, time-slide p-value), then in `experiment_code` load GW190814 H1 & L1 from GWOSC_STRAIN_MANIFEST, inject a 180 Hz damped sinusoid (3.5*std) in BOTH off-source windows, run >=50 time-shifts, and print verdict=DETECTION + PASS."),
        ("gwosc_null", "MATH-FIRST EXAM (GW190814 - Pure Noise): First derive `math_derivation` (null statistic & p-value formula), then in `experiment_code` load GW190814 H1 & L1 off-source noise (ZERO injection), run >=50 time-shifts, and print verdict=NULL_NO_SIGNAL + PASS."),
        ("exoplanets_density", "MATH-FIRST EXAM (Exoplanets): First derive `math_derivation` (rho_rel = M_p / R_p^3, units, permutation test), then in `experiment_code` load `exoplanets` from OPEN_CATALOGS_MANIFEST, test rocky (R<1.6) vs sub-Neptune (1.8<=R<=3.5) density with >=200 permutations, and print p-value + PASS."),
        ("pantheon_lcdm", "MATH-FIRST EXAM (Pantheon+ SNe Ia): First derive `math_derivation` (flat LCDM luminosity distance d_L(z) & distance modulus mu(z), chi2_red), then in `experiment_code` load `pantheon_sne` from OPEN_CATALOGS_MANIFEST, compute chi2_red and low-z vs high-z bootstrap shift, and print PASS."),
    ]
    results: Dict[str, Any] = {}
    passed_count = 0
    total_repairs = 0
    for key, prompt in tests:
        ok = False
        detail = ""
        repairs_used = 0
        messages = [{"role": "system", "content": WRITER_SYSTEM}, {"role": "user", "content": prompt}]
        try:
            for attempt in range(max_repairs + 1):
                r = requests.post(
                    f"{ollama_base.rstrip('/')}/api/chat",
                    json={"model": model, "messages": messages, "stream": False, "think": False, "options": {"temperature": 0.3, "num_predict": 2500}},
                    timeout=(15, 180),
                )
                r.raise_for_status()
                raw = str((r.json().get("message") or {}).get("content") or "")
                parsed = _extract_json_obj(raw) or {}
                has_math = len(str(parsed.get("math_derivation") or "").strip()) >= 20
                code = str(parsed.get("experiment_code") or "")
                exp = _run_experiment_code(code, timeout_s=25)
                out = str(exp.get("output") or "")
                up = out.upper()
                if exp.get("passed") and has_math:
                    if key == "gwosc_signal":
                        ok = "DETECTION" in up and "NULL" not in up
                    elif key == "gwosc_null":
                        ok = "NULL" in up and "DETECTION" not in up
                    elif key == "exoplanets_density":
                        ok = "EXOPLANET" in code.upper() or "OPEN_CATALOGS_MANIFEST" in code.upper()
                    else:
                        ok = "PANTHEON" in code.upper() or "OPEN_CATALOGS_MANIFEST" in code.upper()
                detail = f"math={'ok' if has_math else 'missing'} | " + out[:200].replace("\n", " | ")
                if ok or attempt >= max_repairs:
                    break
                repairs_used += 1
                total_repairs += 1
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"Failed check (math={'ok' if has_math else 'missing'}):\n{out[:700]}\nReturn valid JSON with `math_derivation` and `experiment_code`."})
        except Exception as e:
            detail = str(e)[:160]
        if ok:
            passed_count += 1
        results[key] = {"passed": ok, "repairs_used": repairs_used, "detail": detail}

    payload = {
        "model": model,
        "exam_version": "v8_math_first_multi_catalog",
        "score": passed_count,
        "total": len(tests),
        "invalidated_by_corrections": max_repairs > 0,
        "total_repairs": total_repairs,
        "tests": results,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
    EXAM_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXAM_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "exam":
        url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:11434"
        mdl = sys.argv[3] if len(sys.argv) > 3 else "v7-8b"
        rep = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        print(json.dumps(run_v8_phd_exam(url, mdl, max_repairs=rep), indent=2))
    else:
        print(json.dumps(build_v8_lab_datasets(), indent=2))
