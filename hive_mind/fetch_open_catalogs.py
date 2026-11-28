"""Fetch real public astrophysics catalogs into memory/open_catalogs/ for Data-First science."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import requests

OUT_DIR = Path(__file__).resolve().parent / "memory" / "open_catalogs"
MANIFEST_PATH = OUT_DIR / "manifest.json"
UA = {"User-Agent": "SideQuestAI-ScienceBot/1.0"}


def fetch_exoplanets() -> dict:
    url = (
        "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?"
        "query=select+top+500+pl_name,pl_orbper,pl_rade,pl_bmasse,pl_eqt,st_teff,st_rad,st_mass,sy_dist+"
        "from+pscomppars+where+pl_bmasse+is+not+null+and+pl_rade+is+not+null+and+pl_orbper+is+not+null"
        "&format=json"
    )
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    out = OUT_DIR / "exoplanets.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {
        "file": str(out),
        "count": len(rows),
        "source": "NASA Exoplanet Archive (pscomppars)",
        "fields": ["pl_name", "pl_orbper", "pl_rade", "pl_bmasse", "pl_eqt", "st_teff", "st_rad", "st_mass", "sy_dist"],
    }


def fetch_pantheon_sne() -> dict:
    url = "https://raw.githubusercontent.com/PantheonPlusSH0ES/DataRelease/main/Pantheon%2B_Data/4_DISTANCES_AND_COVAR/Pantheon%2BSH0ES.dat"
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
    header = lines[0].split()
    idx = {k: i for i, k in enumerate(header)}
    rows = []
    for ln in lines[1:]:
        parts = ln.split()
        if len(parts) < len(header):
            continue
        try:
            rows.append({
                "cid": parts[idx["CID"]],
                "zhd": float(parts[idx["zHD"]]),
                "zhel": float(parts[idx["zHEL"]]),
                "m_b_corr": float(parts[idx["m_b_corr"]]),
                "mu_sh0es": float(parts[idx["MU_SH0ES"]]),
                "mu_err": float(parts[idx["MU_SH0ES_ERR_DIAG"]]),
            })
        except Exception:
            continue
    out = OUT_DIR / "pantheon_sne.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {
        "file": str(out),
        "count": len(rows),
        "source": "Pantheon+SH0ES Type Ia Supernovae",
        "fields": ["cid", "zhd", "zhel", "m_b_corr", "mu_sh0es", "mu_err"],
    }


def fetch_usgs_earthquakes() -> dict:
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=4.5&limit=1000"
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    feats = resp.json().get("features", [])
    rows = []
    for f in feats:
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        if p.get("mag") is None or coords[2] is None:
            continue
        rows.append({
            "id": f.get("id"),
            "mag": float(p["mag"]),
            "time_ms": p.get("time"),
            "lon": coords[0],
            "lat": coords[1],
            "depth_km": float(coords[2]),
            "place": p.get("place"),
        })
    out = OUT_DIR / "earthquakes.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {
        "file": str(out),
        "count": len(rows),
        "source": "USGS ComCat M4.5+ Global Earthquakes",
        "fields": ["id", "mag", "time_ms", "lon", "lat", "depth_km", "place"],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalogs = {}
    for name, fn in (
        ("exoplanets", fetch_exoplanets),
        ("pantheon_sne", fetch_pantheon_sne),
        ("earthquakes", fetch_usgs_earthquakes),
    ):
        try:
            catalogs[name] = fn()
            print(f"[OK] {name}: {catalogs[name]['count']} rows")
        except Exception as exc:
            print(f"[WARN] {name}: {exc}")
    MANIFEST_PATH.write_text(json.dumps({"catalogs": catalogs}, indent=2), encoding="utf-8")
    print(f"Manifest written: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
