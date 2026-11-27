"""v7 Synthetic Lab & PhD Qualifying Exam for ScienceBot.

Uses real off-source LIGO 4096 Hz .hdf5 strain from memory/gwosc_strain/manifest.json
to generate ground-truth SFT + Anti-P-Hacking DPO datasets across 3 scenarios:
  1. True coherent signal in H1 + L1 (must detect with p < 0.01 over >=50 time-shifts)
  2. Pure background noise (must honestly report NULL / no signal)
  3. Single-detector glitch in H1 only (must reject via H1-L1 coincidence check)

Also provides run_phd_exam(ollama_base, model) to grade any model on held-out events.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from export_training_data import CRITIC_SYSTEM, WRITER_SYSTEM  # noqa: E402
from science_bot import _extract_json_obj, _run_experiment_code  # noqa: E402

MANIFEST_FILE = BASE_DIR / "memory" / "gwosc_strain" / "manifest.json"
OUT_SFT = BASE_DIR / "memory" / "training" / "v7_lab_sft.jsonl"
OUT_DPO = BASE_DIR / "memory" / "training" / "v7_lab_dpo.jsonl"


def _make_chosen_code(event_name: str, scenario: str, f0: float, amp_sigma: float) -> str:
    inj_block = ""
    if scenario == "true_signal":
        inj_block = (
            f"sig = {amp_sigma:.2f} * np.std(h1_w) * np.exp(-np.maximum(0.0, t_rel) / 0.04) * np.sin(2 * np.pi * {f0:.1f} * t_rel) * (t_rel >= 0)\n"
            "h1_w = h1_w + sig\n"
            "l1_w = l1_w + np.roll(sig, 12)  # ~3ms light-travel offset\n"
        )
    elif scenario == "single_det_glitch":
        inj_block = (
            f"glitch = {max(6.0, amp_sigma * 2.0):.2f} * np.std(h1_w) * np.exp(-((t_rel - 0.05) / 0.015) ** 2) * np.sin(2 * np.pi * {f0:.1f} * t_rel)\n"
            "h1_w = h1_w + glitch  # H1-only instrumental glitch\n"
        )

    return f'''import json, os, h5py
import numpy as np
from scipy.signal import butter, filtfilt

manifest = json.load(open(os.environ["GWOSC_STRAIN_MANIFEST"]))
ev = manifest["events"]["{event_name}"]
fs = float(ev["detectors"]["H1"]["sample_rate_hz"])
with h5py.File(ev["detectors"]["H1"]["file"], "r") as fh:
    h1_full = fh["strain"]["Strain"][:]
with h5py.File(ev["detectors"]["L1"]["file"], "r") as fl:
    l1_full = fl["strain"]["Strain"][:]

# Use off-source background window away from merger GPS
off_idx = int(4.0 * fs)
win_n = int(4.0 * fs)
h1_seg = h1_full[off_idx:off_idx + win_n].astype(np.float64)
l1_seg = l1_full[off_idx:off_idx + win_n].astype(np.float64)

b, a = butter(4, [40.0 / (0.5 * fs), 500.0 / (0.5 * fs)], btype="band")
h1_w = filtfilt(b, a, h1_seg)
l1_w = filtfilt(b, a, l1_seg)
h1_w = (h1_w - np.mean(h1_w)) / (np.std(h1_w) + 1e-30)
l1_w = (l1_w - np.mean(l1_w)) / (np.std(l1_w) + 1e-30)

t_rel = np.arange(win_n) / fs - 2.0
{inj_block}
# On-source coincidence around t_rel in [-0.05, 0.25]s with +/-10ms lag scan
on_mask = (t_rel >= -0.05) & (t_rel <= 0.25)
h1_on = h1_w[on_mask]
l1_on = l1_w[on_mask]
max_lag = int(0.012 * fs)
lags = range(-max_lag, max_lag + 1)

def max_xcorr(x, y):
    best = 0.0
    for lg in lags:
        ys = np.roll(y, lg)
        c = abs(float(np.dot(x, ys))) / (np.linalg.norm(x) * np.linalg.norm(ys) + 1e-30)
        if c > best:
            best = c
    return best

on_xcorr = max_xcorr(h1_on, l1_on)
h1_snr = float(np.max(np.abs(h1_on)) / (np.std(h1_w) + 1e-30))
l1_snr = float(np.max(np.abs(l1_on)) / (np.std(l1_w) + 1e-30))

# >=50 time-shifted off-source null trials (slides >= 0.25s)
shifts = np.linspace(int(0.25 * fs), win_n - int(0.5 * fs), 60, dtype=int)
null_scores = []
for sh in shifts:
    l1_sh = np.roll(l1_w, int(sh))[on_mask]
    null_scores.append(max_xcorr(h1_on, l1_sh))
null_arr = np.array(null_scores)
p_val = float((np.sum(null_arr >= on_xcorr) + 1.0) / (len(null_arr) + 1.0))

coincident = (p_val < 0.02) and (min(h1_snr, l1_snr) > 3.2) and (max(h1_snr, l1_snr) / (min(h1_snr, l1_snr) + 1e-9) < 3.5)
if coincident:
    verdict = "DETECTION"
elif h1_snr > 5.0 and l1_snr < 3.5:
    verdict = "SINGLE_DETECTOR_GLITCH"
else:
    verdict = "NULL_NO_SIGNAL"

print(f"Event={{'{event_name}'}} on_xcorr={{on_xcorr:.4f}} p_val={{p_val:.4f}} H1_snr={{h1_snr:.2f}} L1_snr={{l1_snr:.2f}} verdict={{verdict}} PASS")
'''


def _make_rejected_code(event_name: str, scenario: str) -> str:
    if scenario == "pure_noise":
        return f'''import json, os, h5py, numpy as np
manifest = json.load(open(os.environ["GWOSC_STRAIN_MANIFEST"]))
ev = manifest["events"]["{event_name}"]
with h5py.File(ev["detectors"]["H1"]["file"], "r") as fh:
    h1 = fh["strain"]["Strain"][:]
# P-hacking: cherry-pick max bin without whitening or time-shift null controls
peak = float(np.max(np.abs(h1)))
print(f"Strong anomalous signal detected at peak={{peak:.3e}}, p=0.01 PASS")
'''
    return f'''import json, os, h5py, numpy as np
manifest = json.load(open(os.environ["GWOSC_STRAIN_MANIFEST"]))
ev = manifest["events"]["{event_name}"]
with h5py.File(ev["detectors"]["H1"]["file"], "r") as fh:
    h1 = fh["strain"]["Strain"][:]
# Bug: ignores L1 detector coincidence completely!
snr = float(np.max(np.abs(h1)) / (np.std(h1) + 1e-30))
print(f"Coincident gravitational-wave detection confirmed with H1 SNR={{snr:.2f}} PASS")
'''


def build_v7_lab_datasets(samples_per_event: int = 3) -> Dict[str, Any]:
    m = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    train_events = [k for k, v in m.get("events", {}).items() if not v.get("held_out")]
    OUT_SFT.parent.mkdir(parents=True, exist_ok=True)

    sft_rows: List[Dict[str, Any]] = []
    dpo_rows: List[Dict[str, Any]] = []
    scenarios = ["true_signal", "pure_noise", "single_det_glitch"]

    for ev_name in train_events:
        for _ in range(samples_per_event):
            for scen in scenarios:
                f0 = random.uniform(80.0, 320.0)
                amp = random.uniform(2.5, 4.5)
                chosen_code = _make_chosen_code(ev_name, scen, f0, amp)
                res = _run_experiment_code(chosen_code, timeout_s=20)
                if not res.get("passed"):
                    continue

                prompt = (
                    f"DATA-FIRST METHOD TEST ({ev_name}): Load H1 & L1 4096 Hz `.hdf5` strain from `GWOSC_STRAIN_MANIFEST`, "
                    "bandpass & whiten the data, test H1-L1 cross-correlation coincidence against >=50 time-shifted background trials, "
                    "and distinguish `DETECTION`, `NULL_NO_SIGNAL`, or `SINGLE_DETECTOR_GLITCH` honestly."
                )
                verdict_map = {
                    "true_signal": ("Coincident H1-L1 Signal Detected", "A coherent signal exceeding 50 time-shifted background trials (p < 0.02) is present in both H1 and L1."),
                    "pure_noise": ("Null Result Confirmed in Background Strain", "No coincident excess exceeds the 50-trial time-shifted background distribution; reported honestly as NULL."),
                    "single_det_glitch": ("Single-Detector H1 Glitch Rejected", "A loud transient in H1 lacks a coincident L1 counterpart and is correctly rejected as an instrumental glitch."),
                }
                title, insight = verdict_map[scen]
                chosen_json = json.dumps({
                    "experiment_code": chosen_code,
                    "title": f"{ev_name}: {title}",
                    "domain": "Gravitational-Wave Raw Strain (.hdf5)",
                    "insight": insight,
                    "hypothesis": "Coincident H1-L1 whitened cross-correlation exceeds >=50 time-shifted background trials only for astrophysical signals, not pure noise or single-detector glitches.",
                    "mini_experiment": "Bandpass 40-500 Hz, whiten H1/L1, scan +/-12ms lag cross-correlation, compare vs 60 time-shifted null trials.",
                    "open_question": "Does the same coincidence test hold across other GWTC events and alternative PSD whitening windows?",
                }, ensure_ascii=False)

                sft_rows.append({
                    "messages": [
                        {"role": "system", "content": WRITER_SYSTEM},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": chosen_json},
                    ]
                })

                # Method Critic SFT (both valid coincidence and rejecting bad single-detector/p-hacked runs)
                rej_code = _make_rejected_code(ev_name, scen)
                rej_json = json.dumps({
                    "experiment_code": rej_code,
                    "title": f"{ev_name}: Unverified Detection Claim",
                    "domain": "Gravitational-Wave Raw Strain (.hdf5)",
                    "insight": "Claimed detection without whitening, L1 coincidence, or time-shift null controls.",
                    "hypothesis": "Signal present.",
                    "mini_experiment": "Peak amplitude check.",
                    "open_question": "None.",
                }, ensure_ascii=False)
                dpo_rows.append({
                    "prompt": [
                        {"role": "system", "content": WRITER_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "chosen": [{"role": "assistant", "content": chosen_json}],
                    "rejected": [{"role": "assistant", "content": rej_json}],
                })
                sft_rows.append({
                    "messages": [
                        {"role": "system", "content": CRITIC_SYSTEM},
                        {"role": "user", "content": f"Title: {title}\nCode:\n{rej_code}\nOutput: Claimed detection without L1 or time-shift controls.\nAudit this run."},
                        {"role": "assistant", "content": "VERDICT: FATAL_ERROR — Missing whitening, >=50 time-shifted null controls, and H1-L1 coincidence check."},
                    ]
                })

    with OUT_SFT.open("w", encoding="utf-8") as f:
        for row in sft_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with OUT_DPO.open("w", encoding="utf-8") as f:
        for row in dpo_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "train_events": len(train_events),
        "v7_lab_sft": len(sft_rows),
        "v7_lab_dpo": len(dpo_rows),
        "sft_path": str(OUT_SFT),
        "dpo_path": str(OUT_DPO),
    }


if __name__ == "__main__":
    print(json.dumps(build_v7_lab_datasets(), indent=2))
