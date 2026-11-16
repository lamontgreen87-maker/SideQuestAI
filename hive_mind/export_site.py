"""Export ScienceBot knowledge base into a static SideQuestAI Science Wiki."""

from __future__ import annotations

import json
import shutil
import subprocess
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
    .badge.data-first {
      border-color: rgba(167, 139, 250, 0.6);
      background: rgba(167, 139, 250, 0.16);
      color: #c4b5fd;
    }
    .badge.novel-strain {
      border-color: rgba(250, 204, 21, 0.8);
      background: linear-gradient(90deg, rgba(250, 204, 21, 0.22), rgba(45, 212, 191, 0.22));
      color: #fde047;
      font-weight: 700;
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
    .splash-section {
      margin-bottom: 1.75rem;
    }
    .splash-heading {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin: 0 0 0.85rem;
    }
    .splash-heading h2 {
      margin: 0;
      font-size: 1.15rem;
      color: #f0c36d;
      letter-spacing: -0.01em;
    }
    .splash-heading span {
      font-size: 0.82rem;
      color: var(--muted);
    }
    .splash-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
    }
    @media (max-width: 820px) {
      .splash-grid { grid-template-columns: 1fr; }
    }
    .splash-card {
      background: linear-gradient(160deg, #172033 0%, var(--surface) 100%);
      border: 1px solid rgba(210, 153, 34, 0.42);
      border-radius: 12px;
      padding: 1rem 1.1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 0.65rem;
    }
    .splash-card h3 {
      margin: 0;
      font-size: 1.02rem;
      color: var(--text);
    }
    .splash-excerpt {
      margin: 0;
      font-size: 0.88rem;
      color: #c9d5e8;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .splash-link {
      align-self: flex-start;
      font-size: 0.82rem;
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .splash-link:hover { text-decoration: underline; }
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
        <label class="chk"><input id="uniqueOnly" type="checkbox" /> ★ Empirical Lead</label>
        <label class="chk"><input id="realDataOnly" type="checkbox" /> Real Data (GWTC/EHT)</label>
        <label class="chk"><input id="dataFirstOnly" type="checkbox" /> Data-First (.hdf5)</label>
        <button class="btn" id="clearBtn" type="button">Clear</button>
      </div>
      <div class="domain-pills" id="domainPills"></div>
    </div>
  </header>

  <main>
    <section id="splashBox" class="splash-section container"></section>
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
        article.title,
        article.insight,
        article.hypothesis,
        article.mini_experiment,
        article.experiment_code,
        article.experiment_output,
        article.scout_angle,
        article.source_title,
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

    function isDataFirst(article) {
      if (Boolean(article.data_first)) return true;
      return !article.source_url && /h5py|gwosc_strain|\.hdf5/i.test(String(article.experiment_code || ""));
    }

    function isNovelStrainLead(article) {
      return isDataFirst(article) && isUnique(article);
    }

    function renderStats() {
      const s = state.data.status || {};
      const idx = state.data.index || {};
      const gen = (state.data.generated_at || "").slice(0, 19).replace("T", " ");
      document.getElementById("statsBar").innerHTML = [
        `<span class="stat-pill"><strong>${(state.data.articles || []).length}</strong> Articles</span>`,
        `<span class="stat-pill"><strong>${s.verified_count ?? 0}</strong> Verified</span>`,
        `<span class="stat-pill"><strong>${s.unique_count ?? 0}</strong> ★ Empirical Leads</span>`,
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
      const dataFirstOnly = document.getElementById("dataFirstOnly").checked;

      const filtered = (state.data.articles || []).filter((a) => {
        if (state.domain !== "all" && (a.domain || "general") !== state.domain) return false;
        if (verifiedOnly && !isVerified(a)) return false;
        if (uniqueOnly && !isUnique(a)) return false;
        if (realDataOnly && !isRealData(a)) return false;
        if (dataFirstOnly && !isDataFirst(a)) return false;
        if (q) {
          const hay = [
            a.title,
            a.domain,
            a.insight,
            a.hypothesis,
            a.mini_experiment,
            a.critic_takeaway,
            a.open_question,
            a.source_title,
            a.wiki_title,
            a.scout_angle,
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
            isNovelStrainLead(a)
              ? `<span class="badge novel-strain">★ Novel Strain Lead</span>`
              : (isUnique(a) ? `<span class="badge unique">★ Empirical Lead</span>` : ""),
            isDataFirst(a) ? `<span class="badge data-first">Data-First (.hdf5)</span>` : "",
            isRealData(a) ? `<span class="badge real-data">Real Data (GWTC/EHT)</span>` : "",
            a.novelty_score != null ? `<span class="badge">${escapeHtml(String(a.novelty_score))}% score</span>` : "",
            a.created_at ? `<span class="badge">${escapeHtml(String(a.created_at).slice(0, 10))}</span>` : "",
          ].join("");
          const bodyParts = [
            a.insight ? a.insight : "",
            a.hypothesis ? `Hypothesis: ${a.hypothesis}` : "",
            a.mini_experiment && a.mini_experiment !== "N/A" ? `Experiment: ${a.mini_experiment}` : "",
            a.open_question ? `Open Question: ${a.open_question}` : "",
          ].filter(Boolean);
          const body = bodyParts.join("\n\n");
          const codeBlock = a.experiment_code
            ? `<details><summary>Simulation / Verification Code${a.experiment_passed ? " (Passed)" : ""}</summary><pre><code>${escapeHtml(a.experiment_code)}</code></pre>${a.experiment_output ? `<pre><code>Output:\n${escapeHtml(a.experiment_output)}</code></pre>` : ""}</details>`
            : "";
          const sourceLink = a.source_url
            ? `<div><strong>Source:</strong> <a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" style="color:var(--accent)">${escapeHtml(a.source_title || a.source_url)}</a></div>`
            : "";
          const note = (a.critic_takeaway || sourceLink)
            ? `<div class="meta-note">${sourceLink}${a.critic_takeaway ? `<div><strong>Critic:</strong> ${escapeHtml(a.critic_takeaway)}</div>` : ""}</div>`
            : "";
          return `
            <article class="card" id="article-${escapeHtml(a.id || "")}">
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

    function importanceScore(a) {
      let score = 0;
      if (isVerified(a)) score += 3;
      if (isNovelStrainLead(a)) score += 6;
      else if (isUnique(a)) score += 3;
      if (isDataFirst(a)) score += 2;
      if (isRealData(a)) score += 2;
      score += Number(a.novelty_score || 0) / 100;
      return score;
    }

    function renderSplash() {
      const box = document.getElementById("splashBox");
      const q = document.getElementById("searchInput").value.trim();
      const filteredActive =
        q ||
        state.domain !== "all" ||
        document.getElementById("verifiedOnly").checked ||
        document.getElementById("uniqueOnly").checked ||
        document.getElementById("realDataOnly").checked ||
        document.getElementById("dataFirstOnly").checked;
      if (filteredActive) {
        box.style.display = "none";
        return;
      }
      box.style.display = "";

      const ranked = [...(state.data.articles || [])]
        .sort((a, b) => {
          const diff = importanceScore(b) - importanceScore(a);
          if (Math.abs(diff) > 1e-6) return diff;
          return String(b.created_at || "").localeCompare(String(a.created_at || ""));
        })
        .slice(0, 4);

      if (!ranked.length) {
        box.innerHTML = "";
        return;
      }

      const cards = ranked
        .map((a) => {
          const badges = [
            isVerified(a) ? `<span class="badge verified">✓ Verified</span>` : "",
            isNovelStrainLead(a)
              ? `<span class="badge novel-strain">★ Novel Strain Lead</span>`
              : (isUnique(a) ? `<span class="badge unique">★ Empirical Lead</span>` : ""),
            isDataFirst(a) ? `<span class="badge data-first">Data-First (.hdf5)</span>` : "",
            isRealData(a) ? `<span class="badge real-data">Real Data (GWTC/EHT)</span>` : "",
            a.novelty_score != null ? `<span class="badge">${escapeHtml(String(a.novelty_score))}% score</span>` : "",
          ].join("");
          const excerpt = a.insight || a.hypothesis || "";
          return `
            <div class="splash-card">
              <div>
                <h3>${escapeHtml(a.title || "Untitled Article")}</h3>
                <div class="badges">${badges}</div>
              </div>
              <p class="splash-excerpt">${escapeHtml(excerpt)}</p>
              <a class="splash-link" href="#article-${escapeHtml(a.id || "")}">Read full verification →</a>
            </div>
          `;
        })
        .join("");

      box.innerHTML = `
        <div class="splash-heading">
          <h2>★ Most Important &amp; Featured Discoveries</h2>
          <span>Top ranked by verification, novelty &amp; real GWTC/EHT data</span>
        </div>
        <div class="splash-grid">${cards}</div>
      `;

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
      renderSplash();
      renderArticles();

      ["searchInput", "verifiedOnly", "uniqueOnly", "realDataOnly", "dataFirstOnly"].forEach((id) => {
        document.getElementById(id).addEventListener("input", () => { renderSplash(); renderArticles(); });
        document.getElementById(id).addEventListener("change", () => { renderSplash(); renderArticles(); });
      });
      document.getElementById("clearBtn").onclick = () => {
        document.getElementById("searchInput").value = "";
        document.getElementById("verifiedOnly").checked = false;
        document.getElementById("uniqueOnly").checked = false;
        document.getElementById("realDataOnly").checked = false;
        document.getElementById("dataFirstOnly").checked = false;
        state.domain = "all";
        renderDomains();
        renderSplash();
        renderArticles();
      };
    }

    window.addEventListener("DOMContentLoaded", init);
  </script>
</body>
</html>
"""


import threading

_DEPLOY_LOCK = threading.Lock()


def export_site(output_dir: Path = SITE_DIR, bot: Any = None) -> Dict[str, Any]:
    """Export ScienceBot articles, dictionary index, and status into static site files."""
    if bot is None:
        bot = ScienceBot()
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": bot.get_status(),
        "index": bot.build_dictionary_index(),
        "articles": list(bot.feed),
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


def deploy_site(
    output_dir: Path = SITE_DIR,
    bot: Any = None,
    project_name: str = "sidequestai",
    branch: str = "main",
) -> Dict[str, Any]:
    """Export static site and publish to Cloudflare Pages via wrangler."""
    with _DEPLOY_LOCK:
        summary = export_site(output_dir=output_dir, bot=bot)
        npx_bin = shutil.which("npx")
        if not npx_bin:
            return {**summary, "deployed": False, "error": "npx not found on PATH"}
        cmd = [
            npx_bin,
            "wrangler",
            "pages",
            "deploy",
            str(output_dir),
            f"--project-name={project_name}",
            f"--branch={branch}",
            "--commit-dirty=true",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            **summary,
            "deployed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-600:] if proc.stdout else "",
            "stderr": proc.stderr[-600:] if proc.stderr else "",
        }


if __name__ == "__main__":
    summary = export_site()
    print(json.dumps(summary, indent=2))

