"""Export ScienceBot knowledge base into a static SideQuestAI Science Wiki."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from science_bot import ScienceBot  # noqa: E402

SITE_DIR = BASE_DIR / "site"


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SideQuestAI Science Wiki</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" />
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
  <style>
    :root {
      --bg: #0b0f17;
      --surface: #131a26;
      --surface-2: #1a2333;
      --border: #263248;
      --text: #e6edf7;
      --muted: #93a4bd;
      --accent: #58a6ff;
      --green: #3fb950;
      --gold: #d29922;
      --teal: #2dd4bf;
      --code-bg: #0d131d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }
    header {
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, #111827 0%, var(--bg) 100%);
      padding: 1.5rem 1.25rem 1.25rem;
    }
    .container {
      max-width: 1240px;
      margin: 0 auto;
    }
    .header-top {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-end;
      gap: 1rem;
    }
    h1 {
      margin: 0;
      font-size: 1.65rem;
      letter-spacing: -0.02em;
    }
    .subtitle {
      margin: 0.25rem 0 0;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .stats-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem;
    }
    .stat-pill {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 0.3rem 0.75rem;
      font-size: 0.82rem;
      color: var(--muted);
    }
    .stat-pill strong { color: var(--text); }
    .controls {
      margin-top: 1.1rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    input[type="search"] {
      flex: 1 1 280px;
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 8px;
      padding: 0.55rem 0.85rem;
      font-size: 0.95rem;
    }
    input[type="search"]:focus {
      outline: 2px solid var(--accent);
      border-color: transparent;
    }
    label.chk {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--surface);
      border: 1px solid var(--border);
      padding: 0.42rem 0.75rem;
      border-radius: 8px;
      font-size: 0.86rem;
      cursor: pointer;
      user-select: none;
    }
    button.btn {
      background: var(--surface-2);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.45rem 0.8rem;
      border-radius: 8px;
      font-size: 0.85rem;
      cursor: pointer;
    }
    button.btn:hover { border-color: var(--accent); }
    .domain-pills {
      margin-top: 0.75rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
    }
    .domain-pill {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      font-size: 0.8rem;
      cursor: pointer;
    }
    .domain-pill.active {
      background: rgba(88, 166, 255, 0.16);
      border-color: var(--accent);
      color: var(--text);
    }
    main {
      padding: 1.5rem 1.25rem 3rem;
    }
    .layout {
      display: grid;
      grid-template-columns: 290px minmax(0, 1fr);
      gap: 1.5rem;
      align-items: start;
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
    }
    .sidebar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem;
      position: sticky;
      top: 1rem;
      max-height: calc(100vh - 2rem);
      overflow-y: auto;
    }
    .sidebar h2 {
      margin: 0 0 0.75rem;
      font-size: 1rem;
    }
    .letter-group {
      margin-bottom: 0.75rem;
    }
    .letter-title {
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--accent);
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.15rem;
      margin-bottom: 0.35rem;
    }
    .term-chip {
      display: inline-block;
      margin: 0.15rem 0.2rem 0.15rem 0;
      padding: 0.15rem 0.45rem;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.78rem;
      color: var(--text);
      cursor: pointer;
    }
    .term-chip:hover { border-color: var(--accent); }
    .articles {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.15rem 1.25rem;
    }
    .card-header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.5rem;
    }
    .card-title {
      margin: 0;
      font-size: 1.15rem;
      color: var(--text);
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.45rem;
    }
    .badge {
      font-size: 0.75rem;
      padding: 0.16rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      color: var(--muted);
    }
    .badge.verified {
      border-color: rgba(63, 185, 80, 0.5);
      background: rgba(63, 185, 80, 0.14);
      color: var(--green);
    }
    .badge.unique {
      border-color: rgba(210, 153, 34, 0.55);
      background: rgba(210, 153, 34, 0.15);
      color: #f0c36d;
    }
    .badge.real-data {
      border-color: rgba(45, 212, 191, 0.55);
      background: rgba(45, 212, 191, 0.14);
      color: var(--teal);
    }
    .card-body {
      margin-top: 0.85rem;
      color: #d6e0ef;
      font-size: 0.94rem;
      white-space: pre-wrap;
    }
    details {
      margin-top: 0.85rem;
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.55rem 0.8rem;
    }
    summary {
      cursor: pointer;
      font-size: 0.85rem;
      color: var(--accent);
      font-weight: 600;
    }
    pre {
      margin: 0.6rem 0 0;
      overflow-x: auto;
      font-size: 0.82rem;
      line-height: 1.45;
      color: #cbd5e1;
    }
    .meta-note {
      margin-top: 0.7rem;
      font-size: 0.82rem;
      color: var(--muted);
      border-top: 1px solid var(--border);
      padding-top: 0.55rem;
    }
    .empty {
      text-align: center;
      padding: 2.5rem 1rem;
      color: var(--muted);
      background: var(--surface);
      border: 1px dashed var(--border);
      border-radius: 12px;
    }
  </style>
</head>
<body>
  <header>
    <div class="container">
      <div class="header-top">
        <div>
          <h1>SideQuestAI Science Wiki</h1>
          <p class="subtitle">Autonomous computational physics &amp; astrophysics encyclopedia</p>
        </div>
        <div class="stats-bar" id="statsBar"></div>
      </div>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="Search articles, equations, terms, or arXiv IDs..." />
        <label class="chk"><input id="verifiedOnly" type="checkbox" /> Verified</label>
        <label class="chk"><input id="uniqueOnly" type="checkbox" /> ★ Unique</label>
        <label class="chk"><input id="realDataOnly" type="checkbox" /> Real Data (GWTC/EHT)</label>
        <button class="btn" id="clearBtn" type="button">Clear</button>
      </div>
      <div class="domain-pills" id="domainPills"></div>
    </div>
  </header>

  <main>
    <div class="container layout">
      <aside class="sidebar">
        <h2>A–Z Dictionary Index</h2>
        <div id="indexBox"></div>
      </aside>
      <section class="articles" id="articlesBox"></section>
    </div>
  </main>

  <script>
    const EMBEDDED_DATA = __EMBEDDED_DATA__;

    const state = {
      data: null,
      domain: "all",
    };

    function escapeHtml(str) {
      return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function isRealData(article) {
      const hay = [
        article.data_source,
        article.verification_note,
        article.title,
        article.summary,
        article.content,
        article.code,
      ].join(" ").toLowerCase();
      return (
        hay.includes("gwtc") ||
        hay.includes("eht") ||
        hay.includes("gwtc_catalog.json") ||
        hay.includes("ligo/virgo/kagra")
      );
    }

    function isUnique(article) {
      return Boolean(article.is_unique) || Number(article.uniqueness_score || 0) >= 0.7;
    }

    function isVerified(article) {
      return Boolean(article.verified);
    }

    function renderStats() {
      const s = state.data.status || {};
      const idx = state.data.index || {};
      const gen = (state.data.generated_at || "").slice(0, 19).replace("T", " ");
      document.getElementById("statsBar").innerHTML = [
        `<span class="stat-pill"><strong>${(state.data.articles || []).length}</strong> Articles</span>`,
        `<span class="stat-pill"><strong>${s.verified_count ?? 0}</strong> Verified</span>`,
        `<span class="stat-pill"><strong>${s.unique_count ?? 0}</strong> ★ Unique</span>`,
        `<span class="stat-pill"><strong>${idx.total_terms ?? 0}</strong> Terms</span>`,
        gen ? `<span class="stat-pill">Updated <strong>${escapeHtml(gen)} UTC</strong></span>` : "",
      ].join("");
    }

    function renderDomains() {
      const articles = state.data.articles || [];
      const counts = {};
      for (const a of articles) {
        const d = a.domain || "general";
        counts[d] = (counts[d] || 0) + 1;
      }
      const domains = ["all", ...Object.keys(counts).sort()];
      const box = document.getElementById("domainPills");
      box.innerHTML = domains
        .map((d) => {
          const label = d === "all" ? `All (${articles.length})` : `${d} (${counts[d]})`;
          const active = state.domain === d ? "active" : "";
          return `<button class="domain-pill ${active}" data-domain="${escapeHtml(d)}">${escapeHtml(label)}</button>`;
        })
        .join("");
      box.querySelectorAll(".domain-pill").forEach((btn) => {
        btn.onclick = () => {
          state.domain = btn.dataset.domain;
          renderDomains();
          renderArticles();
        };
      });
    }

    function renderIndex() {
      const byLetter = (state.data.index && state.data.index.by_letter) || {};
      const letters = Object.keys(byLetter).sort();
      const box = document.getElementById("indexBox");
      if (!letters.length) {
        box.innerHTML = `<div class="subtitle">No indexed terms yet.</div>`;
        return;
      }
      box.innerHTML = letters
        .map((letter) => {
          const terms = (byLetter[letter] || []).slice(0, 20);
          const chips = terms
            .map((item) => {
              const term = typeof item === "string" ? item : (item.term || item.name || "");
              const count = typeof item === "object" && item.count ? ` (${item.count})` : "";
              return `<span class="term-chip" data-term="${escapeHtml(term)}">${escapeHtml(term)}${escapeHtml(count)}</span>`;
            })
            .join("");
          return `<div class="letter-group"><div class="letter-title">${escapeHtml(letter)}</div>${chips}</div>`;
        })
        .join("");

      box.querySelectorAll(".term-chip").forEach((chip) => {
        chip.onclick = () => {
          document.getElementById("searchInput").value = chip.dataset.term;
          renderArticles();
        };
      });
    }

    function renderArticles() {
      const q = document.getElementById("searchInput").value.trim().toLowerCase();
      const verifiedOnly = document.getElementById("verifiedOnly").checked;
      const uniqueOnly = document.getElementById("uniqueOnly").checked;
      const realDataOnly = document.getElementById("realDataOnly").checked;

      const filtered = (state.data.articles || []).filter((a) => {
        if (state.domain !== "all" && (a.domain || "general") !== state.domain) return false;
        if (verifiedOnly && !isVerified(a)) return false;
        if (uniqueOnly && !isUnique(a)) return false;
        if (realDataOnly && !isRealData(a)) return false;
        if (q) {
          const hay = [
            a.title,
            a.domain,
            a.summary,
            a.content,
            a.verification_note,
            a.arxiv_id,
            (a.terms || []).join(" "),
          ].join(" ").toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      const box = document.getElementById("articlesBox");
      if (!filtered.length) {
        box.innerHTML = `<div class="empty">No articles match the current filters.</div>`;
        return;
      }

      box.innerHTML = filtered
        .map((a) => {
          const badges = [
            a.domain ? `<span class="badge">${escapeHtml(a.domain)}</span>` : "",
            isVerified(a) ? `<span class="badge verified">✓ Verified</span>` : "",
            isUnique(a) ? `<span class="badge unique">★ Unique</span>` : "",
            isRealData(a) ? `<span class="badge real-data">Real Data (GWTC/EHT)</span>` : "",
            a.created_at ? `<span class="badge">${escapeHtml(String(a.created_at).slice(0, 10))}</span>` : "",
          ].join("");
          const body = a.content || a.summary || "";
          const codeBlock = a.code
            ? `<details><summary>Simulation / Verification Code</summary><pre><code>${escapeHtml(a.code)}</code></pre></details>`
            : "";
          const note = a.verification_note
            ? `<div class="meta-note"><strong>Verification:</strong> ${escapeHtml(a.verification_note)}</div>`
            : "";
          return `
            <article class="card">
              <div class="card-header">
                <h3 class="card-title">${escapeHtml(a.title || "Untitled Article")}</h3>
              </div>
              <div class="badges">${badges}</div>
              <div class="card-body">${escapeHtml(body)}</div>
              ${codeBlock}
              ${note}
            </article>
          `;
        })
        .join("");

      if (typeof renderMathInElement === "function") {
        renderMathInElement(box, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "\\[", right: "\\]", display: true },
            { left: "$", right: "$", display: false },
            { left: "\\(", right: "\\)", display: false },
          ],
          throwOnError: false,
        });
      }
    }

    async function init() {
      try {
        const res = await fetch("./data.json", { cache: "no-store" });
        state.data = res.ok ? await res.json() : EMBEDDED_DATA;
      } catch (_) {
        state.data = EMBEDDED_DATA;
      }

      renderStats();
      renderDomains();
      renderIndex();
      renderArticles();

      ["searchInput", "verifiedOnly", "uniqueOnly", "realDataOnly"].forEach((id) => {
        document.getElementById(id).addEventListener("input", renderArticles);
        document.getElementById(id).addEventListener("change", renderArticles);
      });
      document.getElementById("clearBtn").onclick = () => {
        document.getElementById("searchInput").value = "";
        document.getElementById("verifiedOnly").checked = false;
        document.getElementById("uniqueOnly").checked = false;
        document.getElementById("realDataOnly").checked = false;
        state.domain = "all";
        renderDomains();
        renderArticles();
      };
    }

    window.addEventListener("DOMContentLoaded", init);
  </script>
</body>
</html>
"""


def export_site(output_dir: Path = SITE_DIR) -> Dict[str, Any]:
    """Export ScienceBot articles, dictionary index, and status into static site files."""
    bot = ScienceBot()
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": bot.get_status(),
        "index": bot.build_dictionary_index(),
        "articles": bot.feed,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "data.json"
    html_path = output_dir / "index.html"

    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    data_path.write_text(json_text, encoding="utf-8")

    # Escape '</' so embedded JSON cannot prematurely close the <script> tag.
    embedded_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html_text = HTML_TEMPLATE.replace("__EMBEDDED_DATA__", embedded_json)
    html_path.write_text(html_text, encoding="utf-8")

    return {
        "data_path": str(data_path),
        "html_path": str(html_path),
        "article_count": len(payload["articles"]),
        "total_terms": payload["index"].get("total_terms", 0),
    }


if __name__ == "__main__":
    summary = export_site()
    print(json.dumps(summary, indent=2))

