import json
import os
import threading
import time


class TelemetryLogger:
    def __init__(self, path=None, enabled=None):
        if enabled is None:
            enabled = os.getenv("HIVE_LOG_ENABLED", "1") == "1"
        self.enabled = enabled
        self.path = path or os.getenv("HIVE_LOG_PATH", os.path.join("memory", "telemetry.jsonl"))
        self._lock = threading.Lock()
        if self.enabled:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)

    def log(self, event, **fields):
        if not self.enabled:
            return
        record = {"ts": time.time(), "event": event}
        record.update(fields)
        line = json.dumps(record, ensure_ascii=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")


class LoopGuard:
    def __init__(self, name, logger, max_repeats=None, stall_seconds=None, warn_cooldown=None):
        self.name = name
        self.logger = logger
        self.max_repeats = max_repeats if max_repeats is not None else int(os.getenv("HIVE_LOOP_MAX_REPEATS", "20"))
        self.stall_seconds = stall_seconds if stall_seconds is not None else int(os.getenv("HIVE_LOOP_STALL_SECONDS", "120"))
        self.warn_cooldown = warn_cooldown if warn_cooldown is not None else int(os.getenv("HIVE_LOOP_WARN_COOLDOWN", "60"))
        self._last_key = None
        self._repeat_count = 0
        self._last_warn_ts = 0.0
        now = time.time()
        self._last_progress_ts = now
        self._last_tick_ts = now

    def mark_progress(self, note=None, **fields):
        self._last_progress_ts = time.time()
        if note:
            self.logger.log(
                "progress",
                guard=self.name,
                note=note,
                **fields,
            )

    def tick(self, key, note=None, **fields):
        now = time.time()
        if key == self._last_key:
            self._repeat_count += 1
        else:
            self._last_key = key
            self._repeat_count = 1
            self._last_progress_ts = now

        self._last_tick_ts = now
        if note:
            self.logger.log(
                "tick",
                guard=self.name,
                key=key,
                note=note,
                **fields,
            )

        stalled = (now - self._last_progress_ts) >= self.stall_seconds
        repeating = self._repeat_count >= self.max_repeats
        if (stalled or repeating) and (now - self._last_warn_ts) >= self.warn_cooldown:
            self._last_warn_ts = now
            self.logger.log(
                "loop_warning",
                guard=self.name,
                key=key,
                repeats=self._repeat_count,
                stalled_seconds=round(now - self._last_progress_ts, 2),
                **fields,
            )
