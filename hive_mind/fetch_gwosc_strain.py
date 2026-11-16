"""Download public LIGO/Virgo 4096 Hz HDF5 strain snippets from GWOSC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import gwosc.datasets
import gwosc.locate
import h5py
import requests

STRAIN_DIR = Path(__file__).resolve().parent / "memory" / "gwosc_strain"
TARGET_EVENTS = ["GW150914", "GW170817", "GW190521"]


def _pick_32s_4khz_url(urls: List[str]) -> str | None:
    """Prefer 32-second 4096 Hz HDF5 strain files (small, fast, standard)."""
    hdf5_urls = [u for u in urls if u.endswith(".hdf5") or ".hdf5?" in u]
    for u in hdf5_urls:
        if "4KHZ" in u.upper() and "32SEC" in u.upper():
            return u
    for u in hdf5_urls:
        if "4KHZ" in u.upper():
            return u
    return hdf5_urls[0] if hdf5_urls else None


def fetch_strain_catalog() -> Dict[str, Any]:
    STRAIN_DIR.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {"events": {}}

    for event_name in TARGET_EVENTS:
        try:
            gps = float(gwosc.datasets.event_gps(event_name))
        except Exception as exc:
            print(f"[GWOSC] Could not resolve GPS for {event_name}: {exc}")
            continue

        event_entry: Dict[str, Any] = {"gps": gps, "detectors": {}}
        for det in ("H1", "L1"):
            try:
                urls = gwosc.locate.get_event_urls(
                    event_name,
                    detector=det,
                    sample_rate=4096,
                    format="hdf5",
                )
            except Exception:
                urls = []

            url = _pick_32s_4khz_url(urls)
            if not url:
                continue

            out_path = STRAIN_DIR / f"{event_name}_{det}_4K_32s.hdf5"
            if not out_path.exists() or out_path.stat().st_size < 1024:
                head = requests.head(url, allow_redirects=True, timeout=15)
                size_bytes = int(head.headers.get("Content-Length", "0") or 0)
                if size_bytes > 25 * 1024 * 1024:
                    print(f"[GWOSC] Skipping {event_name} {det}: file too large ({size_bytes // (1024*1024)} MB)")
                    continue
                print(f"[GWOSC] Downloading {event_name} {det} ({size_bytes // 1024} KB) -> {out_path.name}")
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                out_path.write_bytes(resp.content)

            with h5py.File(out_path, "r") as f:
                strain = f["strain"]["Strain"]
                dt = float(strain.attrs.get("Xspacing", 1.0 / 4096.0))
                t0 = float(strain.attrs.get("Xstart", gps - 16.0))
                n_samples = int(strain.shape[0])

            event_entry["detectors"][det] = {
                "file": str(out_path),
                "sample_rate_hz": round(1.0 / dt, 3),
                "t0_gps": t0,
                "n_samples": n_samples,
            }

        if event_entry["detectors"]:
            manifest["events"][event_name] = event_entry

    manifest_path = STRAIN_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = fetch_strain_catalog()
    print(json.dumps(result, indent=2))
