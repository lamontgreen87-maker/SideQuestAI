"""Author lookup (INSPIRE-HEP) and email draft/omnibus builder for Empirical Leads."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

_INSPIRE_CACHE: Dict[str, Dict[str, Any]] = {}
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", re.IGNORECASE)


def extract_arxiv_id(source_url: str) -> str:
    m = _ARXIV_RE.search(source_url or "")
    return m.group(1) if m else ""


def lookup_inspire_authors(arxiv_id: str) -> Dict[str, Any]:
    if not arxiv_id:
        return {"authors": [], "primary_author": "", "primary_affiliation": "", "primary_email": "", "inspire_url": ""}
    if arxiv_id in _INSPIRE_CACHE:
        return _INSPIRE_CACHE[arxiv_id]

    info: Dict[str, Any] = {
        "authors": [],
        "primary_author": "",
        "primary_affiliation": "",
        "primary_email": "",
        "inspire_url": "",
    }
    try:
        resp = requests.get(
            f"https://inspirehep.net/api/literature?q=arxiv:{arxiv_id}",
            timeout=6,
        )
        if resp.ok:
            hits = resp.json().get("hits", {}).get("hits", [])
            if hits:
                meta = hits[0].get("metadata", {})
                ctrl = meta.get("control_number")
                if ctrl:
                    info["inspire_url"] = f"https://inspirehep.net/literature/{ctrl}"
                parsed_authors = []
                for a in meta.get("authors", [])[:6]:
                    name = str(a.get("full_name") or "").strip()
                    affs = a.get("raw_affiliations") or a.get("affiliations") or []
                    aff = ""
                    if affs and isinstance(affs[0], dict):
                        aff = str(affs[0].get("value") or "").strip()
                    emails = a.get("emails") or []
                    email = str(emails[0]).strip() if emails else ""
                    if name:
                        parsed_authors.append({"name": name, "affiliation": aff, "email": email})
                    if not info["primary_email"] and email:
                        info["primary_email"] = email
                info["authors"] = parsed_authors
                if parsed_authors:
                    info["primary_author"] = parsed_authors[0]["name"]
                    info["primary_affiliation"] = parsed_authors[0]["affiliation"]
    except Exception:
        pass

    _INSPIRE_CACHE[arxiv_id] = info
    return info


def _greeting_name(full_name: str) -> str:
    if not full_name:
        return "Author"
    if "," in full_name:
        last = full_name.split(",", 1)[0].strip()
        return f"Dr. {last}" if last else "Author"
    parts = full_name.strip().split()
    return f"Dr. {parts[-1]}" if parts else "Author"


def build_author_draft(article: Dict[str, Any]) -> Dict[str, Any]:
    source_url = str(article.get("source_url") or "")
    source_title = str(article.get("source_title") or "")
    arxiv_id = extract_arxiv_id(source_url)
    inspire = lookup_inspire_authors(arxiv_id)

    greeting = _greeting_name(inspire.get("primary_author", ""))
    lead_title = str(article.get("title") or "Automated Verification Note")
    insight = str(article.get("insight") or "").strip()
    output = str(article.get("experiment_output") or "").strip()[:900]
    code = str(article.get("experiment_code") or "").strip()[:1800]
    art_id = str(article.get("id") or "")
    wiki_link = f"https://sidequestai.org/#article-{art_id}" if art_id else "https://sidequestai.org"

    subject = f"Reproducible check on \"{source_title[:80]}\" ({arxiv_id or 'arXiv'})" if source_title else f"Reproducible check: {lead_title[:80]}"
    body_lines = [
        f"Dear {greeting},",
        "",
        f"I ran an automated numerical check inspired by your paper{f' \"{source_title}\"' if source_title else ''}{f' ({source_url})' if source_url else ''}.",
        "",
        f"Check: {lead_title}",
        f"Summary: {insight}",
        "",
        "Executed Output:",
        output or "(see link below)",
        "",
        f"Full reproducible Python script & details: {wiki_link}",
    ]
    if code:
        body_lines.extend(["", "--- Python Verification Script ---", code])
    body_lines.extend(["", "Best regards,", "SideQuestAI Automated Science Verification"])

    return {
        "id": art_id,
        "title": lead_title,
        "created_at": article.get("created_at", ""),
        "novelty_score": article.get("novelty_score", 0),
        "data_first": bool(article.get("data_first")),
        "source_title": source_title,
        "source_url": source_url,
        "arxiv_id": arxiv_id,
        "wiki_link": wiki_link,
        "primary_author": inspire.get("primary_author", ""),
        "primary_affiliation": inspire.get("primary_affiliation", ""),
        "primary_email": inspire.get("primary_email", ""),
        "inspire_url": inspire.get("inspire_url", ""),
        "authors": inspire.get("authors", []),
        "subject": subject,
        "body": "\n".join(body_lines),
    }


def build_author_omnibus(articles: List[Dict[str, Any]], hours: Optional[int] = 24) -> Dict[str, Any]:
    cutoff: Optional[datetime] = None
    if hours and hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    leads = [a for a in articles if a.get("is_unique")]
    selected: List[Dict[str, Any]] = []
    for a in leads:
        if cutoff is not None:
            raw_ts = str(a.get("created_at") or "")
            try:
                dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        selected.append(a)

    drafts = [build_author_draft(a) for a in selected[:40]]
    return {
        "hours": hours,
        "count": len(drafts),
        "drafts": drafts,
    }
