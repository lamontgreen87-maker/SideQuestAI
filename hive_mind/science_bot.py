import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from drone import (
    DroneAgent,
    _load_dotenv_if_needed,
    get_active_provider_info,
    set_active_provider,
)

SCIENCE_DOMAINS = [
    ("Black Hole Event Horizons & General Relativity", "cat:gr-qc+AND+all:black+hole"),
    ("Hawking Radiation & Black Hole Thermodynamics", "(cat:gr-qc+OR+cat:hep-th)+AND+all:Hawking+radiation+entropy"),
    ("Kerr Black Holes, Frame Dragging & Penrose Process", "(cat:gr-qc+OR+cat:astro-ph.HE)+AND+all:Kerr+black+hole"),
    ("Gravitational Waves & Quasinormal Mode Ringdown", "(cat:gr-qc+OR+cat:astro-ph.HE)+AND+all:ringdown+quasinormal"),
    ("Black Hole Shadows, Photon Spheres & Lensing", "(cat:gr-qc+OR+cat:astro-ph.HE)+AND+all:black+hole+shadow+lensing"),
    ("Relativistic Jets & Accretion Disks", "cat:astro-ph.HE+AND+all:black+hole+accretion"),
    ("Black Hole Information Paradox & Page Curve", "(cat:hep-th+OR+cat:gr-qc)+AND+all:Page+curve+entropy"),
]

BASE_DIR = Path(__file__).resolve().parent
FEED_FILE = BASE_DIR / "memory" / "science_feed.json"
DB_FILE = BASE_DIR / "memory" / "science.db"
GWTC_CATALOG_FILE = BASE_DIR / "memory" / "gwtc_catalog.json"
MAX_FEED_ITEMS = 200
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

_INDEX_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "using", "based",
    "which", "their", "these", "those", "have", "been", "will", "would", "could",
    "should", "about", "between", "through", "under", "over", "after", "before",
    "when", "where", "what", "why", "how", "more", "most", "some", "such", "than",
    "then", "only", "also", "other", "both", "each", "your", "they", "them", "were",
    "being", "make", "made", "study", "model", "system", "systems", "high",
    "new", "novel", "via", "can", "are", "was", "its", "not", "but", "all", "one",
}


def _strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _extract_json_obj(raw: str) -> Optional[Dict[str, Any]]:
    cleaned = _strip_json_fences(raw)
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _fetch_arxiv_papers(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Fetch recent papers from arXiv's free Atom API without extra dependencies."""
    encoded = urllib.parse.quote(query, safe=":+")
    url = (
        f"https://export.arxiv.org/api/query?search_query={encoded}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "HiveScienceBot/1.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        papers = []
        for entry in root.findall("atom:entry", ATOM_NS):
            title = " ".join((entry.findtext("atom:title", "", ATOM_NS) or "").split())
            summary = " ".join((entry.findtext("atom:summary", "", ATOM_NS) or "").split())
            link = (entry.findtext("atom:id", "", ATOM_NS) or "").strip()
            if title:
                papers.append({"title": title, "summary": summary[:450], "url": link})
        return papers
    except Exception:
        return []


def _fetch_wikipedia_summary(query: str) -> Optional[Dict[str, str]]:
    """Fetch a matching Wikipedia article summary via Wikipedia's free public API."""
    headers = {"User-Agent": "HiveScienceBot/1.0 (https://localhost)"}
    try:
        search_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            headers=headers,
            timeout=8,
        )
        if search_resp.status_code != 200:
            return None
        hits = search_resp.json().get("query", {}).get("search", [])
        if not hits:
            return None
        title = hits[0].get("title", "").strip()
        if not title:
            return None
        slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
        sum_resp = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
            headers=headers,
            timeout=8,
        )
        if sum_resp.status_code != 200:
            return None
        data = sum_resp.json()
        extract = (data.get("extract") or "").strip()
        page_url = (
            data.get("content_urls", {}).get("desktop", {}).get("page")
            or f"https://en.wikipedia.org/wiki/{slug}"
        )
        return {
            "title": data.get("title") or title,
            "extract": extract[:600],
            "url": page_url,
        }
    except Exception:
        return None


def _run_experiment_code(code: str, timeout_s: int = 25) -> Dict[str, Any]:
    """Execute a self-contained Python experiment script in an isolated subprocess."""
    clean_code = _strip_json_fences(code or "").strip()
    if not clean_code:
        return {"passed": False, "output": "No experiment code provided.", "code": ""}

    # Basic safety guard against destructive OS/network calls in generated experiment scripts
    blocked = ("shutil.rmtree", "os.remove", "os.unlink", "subprocess.", "socket.")
    for bad in blocked:
        if bad in clean_code:
            return {
                "passed": False,
                "output": f"Blocked unsafe call '{bad}' in experiment script.",
                "code": clean_code,
            }

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(clean_code)
            tmp_path = tmp.name
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if GWTC_CATALOG_FILE.exists():
            env["GWTC_CATALOG_PATH"] = str(GWTC_CATALOG_FILE)
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_s,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = "\n".join(part for part in (out, f"STDERR: {err}" if err else "") if part)
        upper_out = out.upper()
        explicit_fail = "FAIL" in upper_out and "PASS" not in upper_out
        passed = proc.returncode == 0 and bool(out) and not explicit_fail
        return {
            "passed": passed,
            "output": (combined or "(no output)")[:1500],
            "code": clean_code[:3000],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": f"Experiment timed out after {timeout_s}s.", "code": clean_code[:3000]}
    except Exception as e:
        return {"passed": False, "output": f"Execution error: {e}", "code": clean_code[:3000]}
    finally:
        try:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _has_any_api_key() -> bool:
    if os.getenv("BRAIN_PROVIDER", "").lower() in ("ollama", "custom", "hybrid"):
        return True
    return any(
        os.getenv(k)
        for k in (
            "BRAIN_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "OPENROUTER_API_KEY",
            "RUNPOD_ENDPOINT_ID",
        )
    )


class ScienceBot:
    """
    Scheduled AI Science Bot powered by the Hive Mind DroneAgent stack.
    Runs computational experiments in Python, audits results with Critic & Judge,
    and stores verified articles in SQLite (memory/science.db).
    """

    def __init__(self):
        _load_dotenv_if_needed()
        self.enabled: bool = True
        self.interval_minutes: int = int(os.getenv("SCIENCE_INTERVAL_MINUTES", "30"))
        self.topic_focus: str = os.getenv("SCIENCE_TOPIC_FOCUS", "").strip()
        self.mode: str = os.getenv("SCIENCE_MODE", "full").lower()
        self.research_phase: str = os.getenv("SCIENCE_RESEARCH_PHASE", "foundation").lower()
        if self.research_phase not in ("foundation", "frontier"):
            self.research_phase = "foundation"
        self.arxiv_grounding: bool = os.getenv("SCIENCE_ARXIV_GROUNDING", "1") == "1"
        self.strict_publish: bool = os.getenv("SCIENCE_STRICT_PUBLISH", "1") == "1"
        self.inter_call_delay_s: float = float(os.getenv("SCIENCE_DRONE_DELAY_S", "4.0"))
        default_workers = "3" if os.getenv("BRAIN_PROVIDER", "").lower() == "runpod_serverless" else "1"
        self.workers_per_run: int = max(1, min(5, int(os.getenv("SCIENCE_WORKERS_PER_RUN", default_workers))))

        self.running: bool = False
        self.current_stage: str = "Initializing..."
        self.current_run_details: Dict[str, Any] = {}
        self.next_run_epoch: Optional[float] = None
        self.total_runs: int = 0
        self.last_error: Optional[str] = None
        self.feed: List[Dict[str, Any]] = []

        self._subscribers: List[asyncio.Queue] = []
        self._wake_event = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self._prefetch_task: Optional[asyncio.Task] = None
        self._init_db()
        self._load_state()

    def _init_db(self) -> None:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    title TEXT,
                    domain TEXT,
                    insight TEXT,
                    hypothesis TEXT,
                    mini_experiment TEXT,
                    experiment_code TEXT,
                    experiment_output TEXT,
                    experiment_passed INTEGER DEFAULT 0,
                    open_question TEXT,
                    critic_takeaway TEXT,
                    confidence TEXT,
                    verified INTEGER DEFAULT 0,
                    published INTEGER DEFAULT 1,
                    scout_angle TEXT,
                    source_title TEXT,
                    source_url TEXT,
                    wiki_title TEXT,
                    wiki_extract TEXT,
                    wiki_url TEXT
                )
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
            if "published" not in cols:
                conn.execute("ALTER TABLE articles ADD COLUMN published INTEGER DEFAULT 1")
            if "is_unique" not in cols:
                conn.execute("ALTER TABLE articles ADD COLUMN is_unique INTEGER DEFAULT 0")
            if "novelty_score" not in cols:
                conn.execute("ALTER TABLE articles ADD COLUMN novelty_score INTEGER DEFAULT 0")
            conn.commit()

    def _count_rejected_db(self) -> int:
        with sqlite3.connect(DB_FILE) as conn:
            row = conn.execute("SELECT COUNT(*) FROM articles WHERE published = 0").fetchone()
            return int(row[0]) if row else 0

    def _upsert_article_db(self, entry: Dict[str, Any]) -> None:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO articles (
                    id, created_at, title, domain, insight, hypothesis, mini_experiment,
                    experiment_code, experiment_output, experiment_passed,
                    open_question, critic_takeaway, confidence, verified, published,
                    is_unique, novelty_score,
                    scout_angle, source_title, source_url, wiki_title, wiki_extract, wiki_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("id", ""),
                    entry.get("created_at", ""),
                    entry.get("title", ""),
                    entry.get("domain", ""),
                    entry.get("insight", ""),
                    entry.get("hypothesis", ""),
                    entry.get("mini_experiment", ""),
                    entry.get("experiment_code", ""),
                    entry.get("experiment_output", ""),
                    1 if entry.get("experiment_passed") else 0,
                    entry.get("open_question", ""),
                    entry.get("critic_takeaway", ""),
                    entry.get("confidence", "Exploratory"),
                    1 if entry.get("verified") else 0,
                    1 if entry.get("published", True) else 0,
                    1 if entry.get("is_unique") else 0,
                    int(entry.get("novelty_score", 0) or 0),
                    entry.get("scout_angle", ""),
                    entry.get("source_title", ""),
                    entry.get("source_url", ""),
                    entry.get("wiki_title", ""),
                    entry.get("wiki_extract", ""),
                    entry.get("wiki_url", ""),
                ),
            )
            conn.commit()

    @staticmethod
    def _novelty_tokens(item: Dict[str, Any]) -> set:
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "into", "using",
            "test", "testing", "check", "checks", "verify", "verification",
            "empirical", "consistency", "consistent", "sub", "extremal", "black",
            "hole", "holes", "units", "physics", "general", "relativity", "bounds",
            "bound", "relation", "identity", "every", "all", "are", "was", "were",
        }
        text = " ".join([
            str(item.get("title") or ""),
            str(item.get("hypothesis") or ""),
            str(item.get("insight") or "")[:240],
        ]).lower()
        return {w for w in re.findall(r"[a-z]{3,}", text) if w not in stop}

    @staticmethod
    def _concept_family(item: Dict[str, Any]) -> str:
        t = f"{item.get('title', '')} {item.get('hypothesis', '')}".lower()
        if any(k in t for k in ("smarr", "irreducible", "horizon sum", "horizon difference", "horizon ratio", "horizon product", "horizon‑sum", "horizon‑area", "horizon-area", "horizon‑radius", "horizon-radius", "kerr horizon", "outer‑horizon", "outer-horizon", "angular velocity", "linear velocity", "surface gravity", "surface‑gravity", "quadrupole‑moment", "quadrupole-moment")):
            return "textbook_kerr_horizon"
        if "schwarzschild" in t and any(k in t for k in ("hawking temperature", "bekenstein", "entropy", "area theorem", "schwarzschild radius", "photon sphere", "photon‑sphere", "critical impact")):
            return "textbook_schwarzschild"
        return ""

    def _score_uniqueness(self, entry: Dict[str, Any], prior_items: List[Dict[str, Any]]) -> tuple[int, bool, str]:
        tokens = self._novelty_tokens(entry)
        if not tokens:
            return 0, False, ""
        max_sim = 0.0
        closest_title = ""
        fam = self._concept_family(entry)
        fam_seen = False
        for other in prior_items:
            if other.get("id") == entry.get("id"):
                continue
            if fam and self._concept_family(other) == fam:
                fam_seen = True
            otoks = self._novelty_tokens(other)
            if not otoks:
                continue
            union = len(tokens | otoks)
            sim = (len(tokens & otoks) / union) if union else 0.0
            if sim > max_sim:
                max_sim = sim
                closest_title = str(other.get("title") or "")
        novelty_score = max(0, min(100, round((1.0 - max_sim) * 100)))
        if fam_seen:
            novelty_score = min(novelty_score, 55)
        is_unique = bool(entry.get("verified")) and novelty_score >= 80 and not fam_seen
        return novelty_score, is_unique, closest_title

    def _load_articles_from_db(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM articles WHERE published = 1 ORDER BY created_at DESC LIMIT ?",
                (MAX_FEED_ITEMS,),
            ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["experiment_passed"] = bool(d.get("experiment_passed"))
            d["verified"] = bool(d.get("verified"))
            d["published"] = bool(d.get("published", 1))
            d["is_unique"] = bool(d.get("is_unique", 0))
            d["novelty_score"] = int(d.get("novelty_score", 0) or 0)
            items.append(d)
        # Score novelty_score/is_unique chronologically with tightened concept-family rules
        seen_chron: List[Dict[str, Any]] = []
        for it in reversed(items):
            score, uniq, _ = self._score_uniqueness(it, seen_chron)
            it["novelty_score"] = score
            it["is_unique"] = uniq
            seen_chron.append(it)
        return items

    def load_recent_runs(self, limit: int = 25) -> List[Dict[str, Any]]:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["experiment_passed"] = bool(d.get("experiment_passed"))
            d["verified"] = bool(d.get("verified"))
            d["published"] = bool(d.get("published", 1))
            d["is_unique"] = bool(d.get("is_unique", 0))
            d["novelty_score"] = int(d.get("novelty_score", 0) or 0)
            items.append(d)
        # Score novelty_score/is_unique chronologically with tightened concept-family rules
        seen_chron: List[Dict[str, Any]] = []
        for it in reversed(items):
            score, uniq, _ = self._score_uniqueness(it, seen_chron)
            it["novelty_score"] = score
            it["is_unique"] = uniq
            seen_chron.append(it)
        return items

    def _load_state(self) -> None:
        if FEED_FILE.exists():
            try:
                data = json.loads(FEED_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cfg = data.get("config", {})
                    self.interval_minutes = int(cfg.get("interval_minutes", self.interval_minutes))
                    self.topic_focus = str(cfg.get("topic_focus", self.topic_focus))
                    self.enabled = bool(cfg.get("enabled", self.enabled))
                    self.mode = str(cfg.get("mode", self.mode))
                    if cfg.get("research_phase") in ("foundation", "frontier"):
                        self.research_phase = str(cfg["research_phase"])
                    self.arxiv_grounding = bool(cfg.get("arxiv_grounding", self.arxiv_grounding))
                    self.total_runs = int(cfg.get("total_runs", 0))
                    if cfg.get("workers_per_run") is not None:
                        self.workers_per_run = max(1, min(5, int(cfg["workers_per_run"])))
                    if cfg.get("provider"):
                        set_active_provider(str(cfg["provider"]))
                    for old_item in data.get("feed", []):
                        if isinstance(old_item, dict) and old_item.get("id"):
                            self._upsert_article_db(old_item)
            except (OSError, ValueError, TypeError):
                pass
        self.feed = self._load_articles_from_db()
        if self.total_runs < len(self.feed):
            self.total_runs = len(self.feed)

    def _save_state(self) -> None:
        try:
            FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "config": {
                    "interval_minutes": self.interval_minutes,
                    "topic_focus": self.topic_focus,
                    "enabled": self.enabled,
                    "mode": self.mode,
            "research_phase": self.research_phase,
                    "research_phase": self.research_phase,
                    "arxiv_grounding": self.arxiv_grounding,
                    "total_runs": self.total_runs,
                    "workers_per_run": self.workers_per_run,
                    "provider": get_active_provider_info()["provider"],
                },
                "feed": self.feed[:MAX_FEED_ITEMS],
            }
            FEED_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def get_status(self) -> Dict[str, Any]:
        info = get_active_provider_info()
        seconds_until_next = (
            max(0, int(self.next_run_epoch - time.time()))
            if self.next_run_epoch and self.enabled
            else None
        )
        verified_count = sum(1 for item in self.feed if item.get("verified"))
        unique_items = [item for item in self.feed if item.get("is_unique")]
        latest_unique = (
            {
                "id": unique_items[0].get("id"),
                "title": unique_items[0].get("title"),
                "domain": unique_items[0].get("domain"),
                "novelty_score": unique_items[0].get("novelty_score", 0),
                "created_at": unique_items[0].get("created_at"),
            }
            if unique_items
            else None
        )
        return {
            "enabled": self.enabled,
            "running": self.running,
            "current_stage": self.current_stage,
            "interval_minutes": self.interval_minutes,
            "topic_focus": self.topic_focus,
            "mode": self.mode,
            "research_phase": self.research_phase,
            "workers_per_run": self.workers_per_run,
            "calls_per_cycle": 2 if self.mode == "eco" else (2 + 2 * self.workers_per_run),
            "arxiv_grounding": self.arxiv_grounding,
            "total_runs": self.total_runs,
            "verified_count": verified_count,
            "unique_count": len(unique_items),
            "latest_unique": latest_unique,
            "strict_publish": self.strict_publish,
            "rejected_count": self._count_rejected_db(),
            "seconds_until_next": seconds_until_next,
            "last_error": self.last_error,
            "provider": info["provider"],
            "model": info["model"],
            "cooling_down": info.get("cooling_down", []),
            "available_providers": info.get("available_providers", []),
            "api_key_configured": _has_any_api_key(),
            "current_run": self.current_run_details,
        }

    def backfill_wiki_for_feed(self) -> int:
        """Populate Wikipedia summaries for past articles that don't have wiki_url yet."""
        updated = 0
        for item in self.feed:
            if item.get("wiki_url"):
                continue
            q = item.get("domain") or item.get("title") or ""
            if not q:
                continue
            wiki = _fetch_wikipedia_summary(q)
            if not wiki and item.get("title"):
                wiki = _fetch_wikipedia_summary(item["title"])
            if wiki:
                item["wiki_title"] = wiki["title"]
                item["wiki_extract"] = wiki["extract"]
                item["wiki_url"] = wiki["url"]
                self._upsert_article_db(item)
                updated += 1
        if updated:
            self._save_state()
        return updated

    def build_dictionary_index(self) -> Dict[str, Any]:
        """Build an A-Z keyword & Wikipedia dictionary index across article titles and descriptions."""
        term_map: Dict[str, List[Dict[str, str]]] = {}
        wiki_map: Dict[str, Dict[str, Any]] = {}

        for item in self.feed:
            ref = {
                "id": item.get("id", ""),
                "title": item.get("title", "Untitled"),
                "domain": item.get("domain", ""),
            }
            if item.get("wiki_title"):
                wt = item["wiki_title"]
                w_entry = wiki_map.setdefault(
                    wt, {"title": wt, "url": item.get("wiki_url", ""), "articles": []}
                )
                if ref not in w_entry["articles"]:
                    w_entry["articles"].append(ref)

            blob = " ".join(str(item.get(k, "")) for k in ("title", "insight"))
            tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", blob))
            for tok in tokens:
                low = tok.lower()
                if low in _INDEX_STOPWORDS or len(low) < 4:
                    continue
                bucket = term_map.setdefault(low, [])
                if all(a["id"] != ref["id"] for a in bucket):
                    bucket.append(ref)

        terms = [
            {"term": term, "count": len(refs), "articles": refs}
            for term, refs in term_map.items()
        ]
        terms.sort(key=lambda x: (-x["count"], x["term"]))

        by_letter: Dict[str, List[Dict[str, Any]]] = {}
        for t in terms[:120]:
            ch = t["term"][0].upper()
            by_letter.setdefault(ch, []).append(t)

        return {
            "total_articles": len(self.feed),
            "total_terms": len(terms),
            "top_terms": terms[:40],
            "by_letter": dict(sorted(by_letter.items())),
            "wiki_pages": sorted(wiki_map.values(), key=lambda w: -len(w["articles"])),
        }

    def search_articles(self, query: str = "", domain: str = "") -> List[Dict[str, Any]]:
        q = (query or "").strip().lower()
        d = (domain or "").strip().lower()
        results = []
        for item in self.feed:
            if d and d not in (item.get("domain") or "").lower():
                continue
            if q:
                haystack = " ".join(
                    str(item.get(k, ""))
                    for k in ("id", "title", "domain", "insight", "hypothesis", "mini_experiment", "wiki_title", "source_title")
                ).lower()
                if q not in haystack:
                    continue
            results.append(item)
        return results

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        message = {"type": event_type, "data": data}
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

    def _set_stage(self, stage: str) -> None:
        self.current_stage = stage
        self._emit("status", self.get_status())

    def _log_run_step(self, message: str, **updates: Any) -> None:
        if not isinstance(self.current_run_details, dict):
            self.current_run_details = {}
        events = list(self.current_run_details.get("events", []))
        ts = datetime.now().strftime("%H:%M:%S")
        events.append(f"{ts} · {message}")
        self.current_run_details.update(updates)
        self.current_run_details["events"] = events[-25:]
        self._emit("status", self.get_status())

    def update_config(
        self,
        enabled: Optional[bool] = None,
        interval_minutes: Optional[int] = None,
        topic_focus: Optional[str] = None,
        mode: Optional[str] = None,
        arxiv_grounding: Optional[bool] = None,
        provider: Optional[str] = None,
        workers_per_run: Optional[int] = None,
        research_phase: Optional[str] = None,
    ) -> Dict[str, Any]:
        if enabled is not None:
            self.enabled = bool(enabled)
            if not self.enabled and self._prefetch_task and not self._prefetch_task.done():
                self._prefetch_task.cancel()
                self._prefetch_task = None
        if interval_minutes is not None:
            self.interval_minutes = max(0, min(1440, int(interval_minutes)))
            if self.enabled and not self.running:
                self.next_run_epoch = time.time() + self.interval_minutes * 60
        if topic_focus is not None:
            self.topic_focus = topic_focus.strip()
            if self._prefetch_task and not self._prefetch_task.done():
                self._prefetch_task.cancel()
                self._prefetch_task = None
        if mode in ("eco", "full"):
            self.mode = mode
        if arxiv_grounding is not None:
            self.arxiv_grounding = bool(arxiv_grounding)
        if provider:
            set_active_provider(provider)
            self.last_error = None
            if self._prefetch_task and not self._prefetch_task.done():
                self._prefetch_task.cancel()
                self._prefetch_task = None
            if not self.running:
                self.current_stage = f"Switched to {provider.upper()} — ready"
        if workers_per_run is not None:
            self.workers_per_run = max(1, min(5, int(workers_per_run)))
        if research_phase in ("foundation", "frontier"):
            self.research_phase = research_phase
            if self._prefetch_task and not self._prefetch_task.done():
                self._prefetch_task.cancel()
                self._prefetch_task = None
        self._save_state()
        self._emit("status", self.get_status())
        self._wake_event.set()
        return self.get_status()

    async def trigger_now(self) -> bool:
        if self.running:
            return False
        asyncio.create_task(self.run_cycle())
        return True

    async def _call_drone(
        self, drone_id: str, role: str, task_type: str, prompt: str, provider_override: Optional[str] = None
    ) -> str:
        eff_prov = (provider_override or get_active_provider_info()["provider"]).lower()
        drone = DroneAgent(
            drone_id=drone_id,
            task=prompt[:120],
            task_type=task_type,
            role=role,
            api_base_url=None if eff_prov in ("ollama", "custom") else "EXTERNAL",
            provider_override=provider_override,
        )
        result = await drone.generate_ai_response(prompt)
        if isinstance(result, str) and result.startswith("Error:"):
            raise RuntimeError(result)
        return result

    def _build_prior_digest(self, domain: str) -> tuple[str, int]:
        prior_digest = ""
        is_frontier = self.research_phase == "frontier"
        feed_pool = [it for it in self.feed if not (is_frontier and self._concept_family(it))]
        if feed_pool:
            past_lines = [
                f"- {it.get('title')} ({it.get('domain')}): {it.get('hypothesis', '')[:120]}"
                for it in feed_pool[:5]
            ]
            prior_digest += "\nScienceBot Past Findings (build on or connect if relevant, do not repeat):\n" + "\n".join(past_lines) + "\n"

        recent_all = self.load_recent_runs(25)
        if is_frontier:
            recent_all = [r for r in recent_all if not self._concept_family(r)]
        passing_runs = [r for r in recent_all if r.get("experiment_passed") and r.get("experiment_output")]
        same_dom_pass = [r for r in passing_runs if (r.get("domain") or "").lower() == domain.lower()]
        other_dom_pass = [r for r in passing_runs if r not in same_dom_pass]
        useful_exp_runs = (same_dom_pass + other_dom_pass)[:4]
        if useful_exp_runs:
            exp_lines = []
            for r in useful_exp_runs:
                out_snip = (r.get("experiment_output") or "").replace("\n", " | ")[:240]
                method_snip = (r.get("mini_experiment") or "").replace("\n", " ")[:120]
                exp_lines.append(
                    f"- {r.get('title')} ({r.get('domain')}): Method: {method_snip} | Measured Output: {out_snip}"
                )
            prior_digest += (
                "\nUseful Passing Experiments (verified numerical baselines & working checks you can build on):\n"
                + "\n".join(exp_lines)
                + "\n"
            )

        rejected_runs = [r for r in recent_all if not r.get("published")]
        same_dom = [r for r in rejected_runs if (r.get("domain") or "").lower() == domain.lower()]
        other_dom = [r for r in rejected_runs if r not in same_dom]
        evidence_runs = (same_dom + other_dom)[:5]
        if evidence_runs:
            rej_lines = []
            for r in evidence_runs:
                exp_state = "Python PASS" if r.get("experiment_passed") else "Python FAIL"
                reason = (r.get("critic_takeaway") or r.get("experiment_output") or "").replace("\n", " ")[:180]
                rej_lines.append(
                    f"- [{exp_state} | {r.get('confidence', 'Exploratory')}] {r.get('title')} ({r.get('domain')}): "
                    f"Hypothesis: {(r.get('hypothesis') or '')[:120]} | Evidence/Audit: {reason}"
                )
            prior_digest += (
                "\nFalsified / Rejected Prior Runs (use as negative evidence; DO NOT repeat disproved claims—refine or test a corrected mechanism):\n"
                + "\n".join(rej_lines)
                + "\n"
            )
        return prior_digest, len(evidence_runs)

    def _scout_phase_instruction(self) -> str:
        if self.research_phase == "frontier":
            return (
                "FRONTIER MODE (PAPER-GROUNDED, NO PURE SPECULATION): Strictly FORBIDDEN to re-verify textbook Kerr/Schwarzschild "
                "horizon identities (r₊±r₋, Smarr, M_irr, A=4π(r₊²+a²), b_crit=3√3M, or basic Hawking temperature scaling). "
                "Anchor your hypothesis DIRECTLY in the Live arXiv Paper Reference above—do NOT invent disconnected speculative formulas. "
                "Extract ONE specific quantitative claim, scaling law, or numerical comparison from that arXiv paper and design a "
                "self-contained Python check that tests, bounds, or compares it against a known GR/thermodynamic control."
            )
        return (
            "FOUNDATION MODE: Build a verified baseline—test a fundamental, dimensionally consistent Black Hole Physics "
            "relation or numerical solver (not yet in recent topics) that future frontier tests can use as a control."
        )

    async def _prepare_scout_hypothesis(
        self,
        run_idx: int,
        recent_titles: List[str],
        recent_urls: set,
        hyp_prov: Optional[str],
    ) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        if self.topic_focus:
            domain = self.topic_focus
            arxiv_query = f"all:{self.topic_focus.replace(' ', '+')}"
        else:
            domain, arxiv_query = SCIENCE_DOMAINS[run_idx % len(SCIENCE_DOMAINS)]

        paper = None
        if self.arxiv_grounding:
            papers = await loop.run_in_executor(None, _fetch_arxiv_papers, arxiv_query, 4)
            fresh = [p for p in papers if p.get("url") not in recent_urls]
            paper = fresh[0] if fresh else (papers[0] if papers else None)

        wiki_query = self.topic_focus or (paper["title"] if paper else domain)
        wiki = await loop.run_in_executor(None, _fetch_wikipedia_summary, wiki_query)
        wiki_ctx = f"\nWikipedia Reference ({wiki['title']}):\n{wiki['extract']}\n" if wiki else ""
        prior_digest, rej_count = self._build_prior_digest(domain)
        paper_ctx = (
            f"\nLive arXiv Paper Reference:\nTitle: {paper['title']}\nAbstract: {paper['summary']}\n"
            if paper
            else ""
        ) + wiki_ctx + prior_digest

        scout_prompt = (
            f"Domain: {domain}\n"
            f"Recent topics (DO NOT repeat or re-test these same identities): {json.dumps(recent_titles)}"
            f"{paper_ctx}\n"
            f"{self._scout_phase_instruction()}\n"
            "Available tools in the Python sandbox: `numpy`, `scipy`, and a real 282-event LIGO/Virgo/KAGRA GWTC + EHT JSON catalog at `os.environ['GWTC_CATALOG_PATH']`. "
            "Propose ONE genuinely NEW, dimensionally consistent, testable Black Hole Physics hypothesis "
            "(distinct from the recent topics above) and an exact self-contained Python numerical check "
            "(using SI or geometric units) that directly tests it (against real GWTC/EHT data when relevant). Reply in 2-4 concise sentences."
        )
        scout_angle = await self._call_drone(
            "Sci-Scout", "scout", "research", scout_prompt, provider_override=hyp_prov
        )
        if hyp_prov == "ollama" and (not scout_angle or scout_angle.startswith("Error:")):
            scout_angle = await self._call_drone(
                "Sci-Scout", "scout", "research", scout_prompt, provider_override="groq"
            )
        return {
            "domain": domain,
            "paper": paper,
            "wiki": wiki,
            "paper_ctx": paper_ctx,
            "scout_angle": scout_angle,
            "rej_count": rej_count,
        }

    async def run_cycle(self) -> Optional[Dict[str, Any]]:
        if self._run_lock.locked():
            return None

        async with self._run_lock:
            self.running = True
            self.last_error = None
            run_started = time.time()
            active_info = get_active_provider_info()
            self.current_run_details = {
                "run_number": self.total_runs + 1,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "provider": active_info["provider"],
                "model": active_info["model"],
                "mode": self.mode,
            "research_phase": self.research_phase,
                "workers_count": 1 if self.mode == "eco" else self.workers_per_run,
                "events": [f"{datetime.now().strftime('%H:%M:%S')} · Starting Run #{self.total_runs + 1} ({active_info['provider']} · {active_info['model']})"],
            }
            recent_all_titles = [r.get("title", "") for r in self.load_recent_runs(15) if r.get("title")]
            recent_titles = list(dict.fromkeys([item.get("title", "") for item in self.feed[:8] if item.get("title")] + recent_all_titles))[:14]
            recent_urls = {item.get("source_url") for item in self.feed[:12] if item.get("source_url")}

            if self.topic_focus:
                domain = self.topic_focus
                arxiv_query = f"all:{self.topic_focus.replace(' ', '+')}"
            else:
                domain, arxiv_query = SCIENCE_DOMAINS[self.total_runs % len(SCIENCE_DOMAINS)]
            self.current_run_details["domain"] = domain

            try:
                loop = asyncio.get_event_loop()
                paper = None
                if self.arxiv_grounding:
                    self._set_stage(f"Fetching latest arXiv papers in {domain}...")
                    papers = await loop.run_in_executor(None, _fetch_arxiv_papers, arxiv_query, 4)
                    fresh = [p for p in papers if p.get("url") not in recent_urls]
                    paper = fresh[0] if fresh else (papers[0] if papers else None)
                    if paper:
                        self._log_run_step(
                            f"arXiv paper selected: {paper['title'][:110]}",
                            arxiv_title=paper["title"],
                            arxiv_url=paper["url"],
                        )

                self._set_stage(f"Fetching Wikipedia context for {domain}...")
                wiki_query = self.topic_focus or (paper["title"] if paper else domain)
                wiki = await loop.run_in_executor(None, _fetch_wikipedia_summary, wiki_query)
                if wiki:
                    self._log_run_step(
                        f"Wikipedia context loaded: {wiki['title']}",
                        wiki_title=wiki["title"],
                        wiki_url=wiki["url"],
                    )

                wiki_ctx = (
                    f"\nWikipedia Reference ({wiki['title']}):\n{wiki['extract']}\n"
                    if wiki
                    else ""
                )
                prior_digest, rej_count = self._build_prior_digest(domain)
                if rej_count:
                    self._log_run_step(f"Loaded {rej_count} falsified/rejected run(s) + passing baselines as prior evidence")

                paper_ctx = (
                    f"\nLive arXiv Paper Reference:\nTitle: {paper['title']}\nAbstract: {paper['summary']}\n"
                    if paper
                    else ""
                ) + wiki_ctx + prior_digest

                exp_schema_note = (
                    '- "experiment_code": a self-contained Python 3 script (`math`, `cmath`, `random`, `statistics`, `numpy`, `scipy`, `json`, `os`) '
                    "that runs a quantitative Black Hole Physics check using real constants "
                    "(G=6.67430e-11, c=2.99792458e8, hbar=1.054571817e-34, k_B=1.380649e-23, M_sun=1.98847e30). "
                    "When testing gravitational-wave mergers, ringdowns, radiated mass/energy, spins, or shadows, you may load the real LIGO/Virgo/KAGRA GWTC + EHT catalog from "
                    "`json.load(open(os.environ['GWTC_CATALOG_PATH']))` (`events`: 282 mergers with `event`, `mass_1_source`, `mass_2_source`, `final_mass_source`, `chi_eff`, `luminosity_distance`, `redshift`, `network_matched_filter_snr`; `eht_targets`: `M87*`, `SgrA*`). "
                    "Always filter out `None` values when reading catalog fields. "
                    "It MUST compute real numerical values, assert physical consistency, and print clear metrics plus PASS or FAIL."
                )

                active_prov = get_active_provider_info()["provider"]
                is_hybrid = active_prov == "hybrid"
                hyp_prov = "ollama" if is_hybrid else None
                heavy_prov = "groq" if is_hybrid else None

                if self.mode == "eco":
                    self._set_stage(f"Writer drafting {domain} + Python experiment (Eco 1/2)...")
                    writer_prompt = (
                        f"Domain: {domain}\n"
                        f"Recent titles (DO NOT repeat): {json.dumps(recent_titles)}"
                        f"{paper_ctx}\n"
                        "Draft a rigorous science update as JSON with keys:\n"
                        '"title" (max 10 words), "domain" (1-3 words), "insight" (2-3 sentences), '
                        '"hypothesis" (1-2 testable sentences), "mini_experiment" (2-3 sentences), '
                        f'"open_question" (1 question), and:\n{exp_schema_note}\nReturn ONLY valid JSON.'
                    )
                    writer_raw = await self._call_drone("Sci-Writer", "writer", "action", writer_prompt, provider_override=heavy_prov)
                    parsed_w = _extract_json_obj(writer_raw) or {}
                    self._log_run_step(
                        f"Eco Writer drafted: {parsed_w.get('title') or domain}",
                        worker_titles=[parsed_w.get("title") or domain],
                    )

                    self._set_stage("Running Python experiment...")
                    exp_res = await loop.run_in_executor(
                        None, _run_experiment_code, parsed_w.get("experiment_code", "")
                    )
                    self._log_run_step(
                        f"Python experiment {'PASSED' if exp_res.get('passed') else 'FAILED'}",
                        experiment_passed=bool(exp_res.get("passed")),
                        experiment_output=exp_res.get("output", ""),
                        experiment_code=exp_res.get("code", ""),
                    )
                    await asyncio.sleep(self.inter_call_delay_s)

                    self._set_stage("Critic & Judge auditing real experiment output (Eco 2/2)...")
                    judge_prompt = (
                        f"Draft:\n{writer_raw}\n\n"
                        f"Actual Python Experiment Result (passed={exp_res['passed']}):\n{exp_res['output']}\n\n"
                        "Audit the draft against the actual measured experiment output, tighten any overclaims, "
                        "and output ONLY valid JSON with keys: "
                        '"title", "domain", "insight", "hypothesis", "mini_experiment", '
                        '"open_question", "critic_takeaway" (1-2 sentences), '
                        '"confidence" ("High", "Exploratory", or "Speculative").'
                    )
                    judge_raw = await self._call_drone("Sci-Judge", "judge", "architecture", judge_prompt, provider_override=heavy_prov)
                    critic_notes = ""
                    scout_angle = paper["title"] if paper else ""
                else:
                    if is_hybrid and self._prefetch_task is not None:
                        self._set_stage(f"Receiving parallel Local Ollama hypothesis for Run #{self.total_runs + 1} (1/5)...")
                        try:
                            prefetched = await self._prefetch_task
                        except (Exception, asyncio.CancelledError):
                            prefetched = None
                        finally:
                            self._prefetch_task = None
                    else:
                        prefetched = None

                    if prefetched:
                        domain = prefetched["domain"]
                        paper = prefetched["paper"]
                        wiki = prefetched["wiki"]
                        paper_ctx = prefetched["paper_ctx"]
                        scout_angle = prefetched["scout_angle"]
                        self.current_run_details["domain"] = domain
                        if paper:
                            self.current_run_details["arxiv_title"] = paper["title"]
                            self.current_run_details["arxiv_url"] = paper["url"]
                        if wiki:
                            self.current_run_details["wiki_title"] = wiki["title"]
                            self.current_run_details["wiki_url"] = wiki["url"]
                        self._log_run_step(
                            f"Parallel Local Ollama hypothesis ready ({domain})",
                            scout_hypothesis=scout_angle,
                        )
                    else:
                        self._set_stage(
                            f"Local Ollama generating hypotheses in {domain} (1/5)..."
                            if is_hybrid
                            else f"Scout selecting angle in {domain} (1/5)..."
                        )
                        scout_prompt = (
                            f"Domain: {domain}\n"
                            f"Recent topics (DO NOT repeat or re-test these same identities): {json.dumps(recent_titles)}"
                            f"{paper_ctx}\n"
                            f"{self._scout_phase_instruction()}\n"
                            "Available tools in the Python sandbox: `numpy`, `scipy`, and a real 282-event LIGO/Virgo/KAGRA GWTC + EHT JSON catalog at `os.environ['GWTC_CATALOG_PATH']`. "
                            "Propose ONE genuinely NEW, dimensionally consistent, testable Black Hole Physics hypothesis "
                            "(distinct from the recent topics above) and an exact self-contained Python numerical check "
                            "(using SI or geometric units) that directly tests it (against real GWTC/EHT data when relevant). Reply in 2-4 concise sentences."
                        )
                        scout_angle = await self._call_drone(
                            "Sci-Scout", "scout", "research", scout_prompt, provider_override=hyp_prov
                        )
                        if hyp_prov == "ollama" and (not scout_angle or scout_angle.startswith("Error:")):
                            self._log_run_step("Ollama timed out/errored — falling back to Groq for Scout")
                            scout_angle = await self._call_drone(
                                "Sci-Scout", "scout", "research", scout_prompt, provider_override="groq"
                            )
                        self._log_run_step(
                            f"{'Local Ollama' if is_hybrid else 'Scout'} hypothesis ready",
                            scout_hypothesis=scout_angle,
                        )
                        if not is_hybrid:
                            await asyncio.sleep(self.inter_call_delay_s)

                    # In Hybrid mode, immediately start Local Ollama generating Run #(N+1) in parallel with Groq!
                    if is_hybrid and self.enabled and (self._prefetch_task is None or self._prefetch_task.done()):
                        next_titles = list(recent_titles)
                        if paper and paper.get("title"):
                            next_titles = [paper["title"]] + next_titles[:7]
                        self._prefetch_task = asyncio.create_task(
                            self._prepare_scout_hypothesis(
                                self.total_runs + 1, next_titles, recent_urls, "ollama"
                            )
                        )
                        self._log_run_step(
                            f"Parallel: Local Ollama generating Run #{self.total_runs + 2} hypothesis while Groq tests Run #{self.total_runs + 1}"
                        )

                    w_count = self.workers_per_run
                    lenses = [
                        "Mechanistic & Theoretical Physics/Biology",
                        "Experimental & Empirical Falsification",
                        "Cross-Disciplinary Systems & Applications",
                        "Mathematical & Quantitative Modeling",
                        "Edge-Case & Failure-Mode Analysis",
                    ]
                    self._set_stage(f"Groq testing hypothesis with {w_count} parallel Writer(s) (2/5)..." if is_hybrid else f"Running {w_count} parallel Writer worker(s) (2/5)...")
                    writer_tasks = [
                        self._call_drone(
                            f"Sci-Writer-{i+1}",
                            "writer",
                            "action",
                            (
                                f"Perspective: {lenses[i % len(lenses)]}\n"
                                f"Scout brief:\n{scout_angle}\n{paper_ctx}\n"
                                "Produce a JSON object with keys: "
                                '"title", "domain", "insight", "hypothesis", "mini_experiment", "open_question", '
                                f"and:\n{exp_schema_note}\nReturn ONLY valid JSON."
                            ),
                            provider_override=heavy_prov,
                        )
                        for i in range(w_count)
                    ]
                    writer_outputs = await asyncio.gather(*writer_tasks)

                    # Extract and execute ALL writers' experiment scripts in parallel
                    parsed_writers = [_extract_json_obj(w_out) or {} for w_out in writer_outputs]
                    worker_titles = [
                        f"W{i+1}: {obj['title']}"
                        for i, obj in enumerate(parsed_writers)
                        if obj.get("title")
                    ]
                    self._log_run_step(
                        f"{w_count} parallel Writer(s) completed",
                        worker_titles=worker_titles,
                    )

                    self._set_stage(f"Executing {w_count} computational Python experiment(s) in parallel (3/5)...")
                    exp_results = await asyncio.gather(*[
                        loop.run_in_executor(None, _run_experiment_code, str(obj.get("experiment_code") or ""))
                        for obj in parsed_writers
                    ])
                    # Prefer passing experiments, then falsification/modeling lenses (indices 1, 3), then richer output
                    lens_bonus = {1: 200, 3: 150, 4: 100, 0: 50, 2: 25}
                    best_idx = max(
                        range(len(exp_results)),
                        key=lambda idx: (
                            1 if exp_results[idx].get("passed") else 0,
                            lens_bonus.get(idx % 5, 0) + min(len(exp_results[idx].get("output") or ""), 800),
                        ),
                    )
                    passed_count = sum(1 for r in exp_results if r.get("passed"))
                    exp_res = exp_results[best_idx]
                    writer_raw = writer_outputs[best_idx]
                    self._log_run_step(
                        f"Python experiments: {passed_count}/{len(exp_results)} PASSED (selected Writer-{best_idx + 1})",
                        experiment_passed=bool(exp_res.get("passed")),
                        experiment_output=exp_res.get("output", ""),
                        experiment_code=exp_res.get("code", ""),
                    )

                    if get_active_provider_info()["provider"] != "runpod_serverless":
                        await asyncio.sleep(self.inter_call_delay_s)

                    self._set_stage(f"Groq auditing Writer-{best_idx + 1} with {w_count} parallel Critic(s) (4/5)..." if is_hybrid else f"Running {w_count} parallel Critic worker(s) on Writer-{best_idx + 1} (4/5)...")
                    critic_tasks = [
                        self._call_drone(
                            f"Sci-Critic-{i+1}",
                            "critic",
                            "audit",
                            (
                                f"Audit the selected Writer-{best_idx + 1} Draft against its ACTUAL measured experiment output below "
                                f"from the lens of {lenses[i % len(lenses)]}.\n"
                                f"Draft:\n{writer_raw}\n\n"
                                f"Experiment Passed: {exp_res['passed']}\nMeasured Output:\n{exp_res['output']}\n\n"
                                "Start with 'VERDICT: VALID' if the math, units, and code are physically sound within the stated regime (even if minor scope caveats apply), "
                                "or 'VERDICT: FATAL_ERROR' ONLY if there is an actual formula/unit/code error or the script failed to test the hypothesis. "
                                "Then give 2-3 sharp bullets on scientific accuracy, math/simulation validity, and scope caveats."
                            ),
                            provider_override=heavy_prov,
                        )
                        for i in range(w_count)
                    ]
                    critic_outputs = await asyncio.gather(*critic_tasks)
                    critic_notes = "\n---\n".join(critic_outputs)
                    self._log_run_step(
                        f"{w_count} parallel Critic(s) completed",
                        critic_notes=critic_notes[:1800],
                    )
                    if get_active_provider_info()["provider"] != "runpod_serverless":
                        await asyncio.sleep(self.inter_call_delay_s)

                    self._set_stage("Judge synthesizing verified consensus (5/5)...")
                    judge_prompt = (
                        f"Selected Draft (Writer-{best_idx + 1}):\n{writer_raw}\n\n"
                        f"Actual Python Experiment Result (passed={exp_res['passed']}, {passed_count}/{len(exp_results)} writers passed):\n{exp_res['output']}\n\n"
                        f"Critic Audits:\n{critic_notes}\n\n"
                        "Synthesize the empirically grounded result as a single JSON object with keys: "
                        '"title", "domain", "insight", "hypothesis", "mini_experiment", '
                        '"open_question", "critic_takeaway", '
                        '"confidence" (set "High" if experiment passed, directly tested the hypothesis, and a majority of critics returned VERDICT: VALID with no fatal physics/math/unit error; record any minor scope caveats in critic_takeaway/open_question; otherwise set "Exploratory" or "Speculative"). '
                        "Return ONLY valid JSON."
                    )
                    judge_raw = await self._call_drone("Sci-Judge", "judge", "architecture", judge_prompt, provider_override=heavy_prov)

                parsed = _extract_json_obj(judge_raw) or _extract_json_obj(writer_raw) or {}
                confidence = parsed.get("confidence") or "Exploratory"
                verified = bool(exp_res.get("passed")) and confidence == "High"
                published = verified if self.strict_publish else True

                entry = {
                    "id": str(uuid.uuid4())[:8],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "title": parsed.get("title") or f"{domain} Brief #{self.total_runs + 1}",
                    "domain": parsed.get("domain") or domain,
                    "insight": parsed.get("insight") or judge_raw[:600],
                    "hypothesis": parsed.get("hypothesis") or "See insight synthesis above.",
                    "mini_experiment": parsed.get("mini_experiment") or "N/A",
                    "experiment_code": exp_res.get("code", ""),
                    "experiment_output": exp_res.get("output", ""),
                    "experiment_passed": bool(exp_res.get("passed")),
                    "open_question": parsed.get("open_question") or "",
                    "critic_takeaway": parsed.get("critic_takeaway") or critic_notes[:1200],
                    "confidence": confidence,
                    "verified": verified,
                    "published": published,
                    "scout_angle": scout_angle[:2000],
                    "source_title": paper["title"] if paper else "",
                    "source_url": paper["url"] if paper else "",
                    "wiki_title": wiki["title"] if wiki else "",
                    "wiki_extract": wiki["extract"] if wiki else "",
                    "wiki_url": wiki["url"] if wiki else "",
                }

                novelty_score, is_unique, closest_title = self._score_uniqueness(entry, self.feed)
                entry["novelty_score"] = novelty_score
                entry["is_unique"] = is_unique

                elapsed_s = round(time.time() - run_started, 1)
                self._log_run_step(
                    f"Judge verdict: {confidence} · {'Verified & Published' if published else 'Rejected'} · {novelty_score}% novel{' · UNIQUE DISCOVERY!' if is_unique else ''} ({elapsed_s}s)",
                    elapsed_s=elapsed_s,
                    judge_verdict=f"{confidence} ({'Verified & Published' if published else 'Rejected'})",
                )

                self._upsert_article_db(entry)
                self.feed = self._load_articles_from_db()
                self.total_runs += 1
                self._save_state()
                self._emit("run_complete", entry)
                if published:
                    self._emit("update", entry)
                    if is_unique:
                        self._emit("unique_discovery", {**entry, "closest_match_title": closest_title})
                        self._set_stage(f"UNIQUE DISCOVERY ({novelty_score}% novel) published! Waiting for next cycle")
                    else:
                        self._set_stage("Verified & published! Waiting for next cycle")
                else:
                    self._set_stage("Hypothesis failed verification — not published")
                return entry

            except Exception as e:
                self.last_error = str(e)
                self._set_stage(f"Paused on error: {str(e)[:120]}")
                return None
            finally:
                self.running = False
                self.next_run_epoch = time.time() + self.interval_minutes * 60
                self._emit("status", self.get_status())

    async def run_loop(self) -> None:
        """Background scheduler loop that runs every interval_minutes when enabled."""
        await asyncio.sleep(2.0)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.backfill_wiki_for_feed)

        if self.enabled and not self.feed and _has_any_api_key():
            await self.run_cycle()
        else:
            self.next_run_epoch = time.time() + self.interval_minutes * 60
            self._set_stage(
                "Idle — waiting for next free cycle"
                if _has_any_api_key()
                else "Waiting for API key in .env"
            )

        while True:
            self._wake_event.clear()
            wait_s = (
                max(0.5 if self.interval_minutes == 0 else 5.0, self.next_run_epoch - time.time())
                if (self.enabled and self.next_run_epoch)
                else 60.0
            )
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                pass

            if self.enabled and self.next_run_epoch and time.time() >= self.next_run_epoch:
                if _has_any_api_key():
                    try:
                        await self.run_cycle()
                    except (Exception, asyncio.CancelledError) as e:
                        self.running = False
                        self.last_error = f"Cycle interrupted: {e}"
                        self.next_run_epoch = time.time() + 2.0
                        self._set_stage("Recovered from interruption — retrying")
                else:
                    self.next_run_epoch = time.time() + 60.0
                    self._set_stage("Waiting for API key in .env")
