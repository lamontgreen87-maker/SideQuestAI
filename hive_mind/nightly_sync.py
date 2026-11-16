import json
import os
import sys
from hashlib import sha256

from shatter_cache import DEFAULT_CACHE_PATH


def load_existing_hashes(cache_path: str) -> set:
    hashes = set()
    if not os.path.exists(cache_path):
        return hashes
    with open(cache_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            hashes.add(sha256(line.encode("utf-8")).hexdigest())
    return hashes


def append_unique(cache_path: str, incoming_path: str) -> int:
    added = 0
    existing = load_existing_hashes(cache_path)

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as out_handle:
        with open(incoming_path, "r", encoding="utf-8") as in_handle:
            for line in in_handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") != "shatter_post":
                    continue
                line_hash = sha256(line.encode("utf-8")).hexdigest()
                if line_hash in existing:
                    continue
                out_handle.write(line + "\n")
                existing.add(line_hash)
                added += 1

    return added


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python nightly_sync.py <incoming_jsonl> [cache_path]")
    incoming = sys.argv[1]
    cache_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CACHE_PATH

    if not os.path.exists(incoming):
        raise SystemExit(f"Incoming file not found: {incoming}")

    added = append_unique(cache_path, incoming)
    print(f"Added {added} shatter posts to {cache_path}")


if __name__ == "__main__":
    main()
