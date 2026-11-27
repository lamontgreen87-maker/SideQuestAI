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
  <title>SideQuestAI — Autonomous Science Dispatch</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,500&display=swap" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" />
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
  <style>
    :root {
      --bg: #0a0e16;
      --surface: #111824;
      --surface-2: #182131;
      --border: #253146;
      --text: #edf2fa;
      --muted: #93a4bd;
      --accent: #60a5fa;
      --green: #3fb950;
      --gold: #eab308;
      --teal: #2dd4bf;
      --code-bg: #0b1019;
      --serif: "Newsreader", Georgia, "Times New Roman", serif;
      --sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.62;
    }
    header {
      border-bottom: 2px solid var(--border);
      background: radial-gradient(circle at top right, rgba(96, 165, 250, 0.08), transparent 45%), #0d131f;
      padding: 1.35rem 1.25rem 1.15rem;
    }
    .container {
      max-width: 1260px;
      margin: 0 auto;
    }
    .masthead-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.74rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      padding-bottom: 0.65rem;
      margin-bottom: 0.85rem;
      border-bottom: 1px solid var(--border);
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
      font-family: var(--serif);
      font-size: 2.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.1;
    }
    .subtitle {
      margin: 0.3rem 0 0;
      color: var(--muted);
      font-size: 0.94rem;
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
      max-height: 5.2rem;
      overflow-y: auto;
      padding-right: 0.25rem;
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
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 1.5rem;
      align-items: start;
    }
    .articles { order: 1; }
    .sidebar {
      order: 2;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem;
      position: sticky;
      top: 1rem;
      max-height: calc(100vh - 2rem);
      overflow-y: auto;
    }
    .sidebar-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.65rem;
    }
    .sidebar h2 {
      margin: 0;
      font-size: 0.96rem;
    }
    .layout.hide-index {
      grid-template-columns: minmax(0, 1fr);
    }
    .layout.hide-index .sidebar {
      display: none;
    }
    @media (max-width: 960px) {
      .layout { grid-template-columns: 1fr; }
      .articles { order: 1; }
      .sidebar {
        order: 2;
        position: static;
        max-height: 360px;
      }
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
      padding: 1.25rem 1.35rem;
      transition: border-color 0.15s ease;
    }
    .card:hover { border-color: rgba(96, 165, 250, 0.55); }
    .kicker {
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 0.3rem;
    }
    .card-header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.65rem;
    }
    .card-title {
      margin: 0;
      font-family: var(--serif);
      font-size: 1.32rem;
      font-weight: 600;
      line-height: 1.28;
      color: var(--text);
      flex: 1 1 320px;
    }
    .card-excerpt {
      margin: 0.75rem 0 0;
      color: #cbd5e6;
      font-size: 0.95rem;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-footer {
      margin-top: 0.85rem;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }
    .card-hypothesis {
      margin: 0.65rem 0 0;
      padding: 0.55rem 0.8rem;
      border-left: 3px solid var(--accent);
      background: rgba(96, 165, 250, 0.07);
      border-radius: 0 8px 8px 0;
      font-size: 0.88rem;
      color: #d6e2f5;
    }
    .output-box {
      margin-top: 0.65rem;
      background: var(--code-bg);
      border: 1px solid rgba(63, 185, 80, 0.35);
      border-radius: 8px;
      padding: 0.6rem 0.8rem;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.8rem;
      line-height: 1.45;
      color: #c9f7d5;
      white-space: pre-wrap;
      overflow-x: auto;
    }
    .detail-section {
      margin-top: 1rem;
      padding-top: 0.85rem;
      border-top: 1px solid var(--border);
    }
    .detail-label {
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 0.35rem;
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
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
    }
    @media (max-width: 900px) {
      .splash-grid { grid-template-columns: 1fr; }
    }
    .splash-lead {
      background: linear-gradient(135deg, #162134 0%, #101725 100%);
      border: 1px solid rgba(96, 165, 250, 0.45);
      border-left: 4px solid var(--gold);
      border-radius: 12px;
      padding: 1.35rem 1.5rem;
      margin-bottom: 1rem;
      cursor: pointer;
      transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .splash-lead:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .splash-lead h3 {
      margin: 0.25rem 0 0.5rem;
      font-family: var(--serif);
      font-size: 1.65rem;
      line-height: 1.22;
      color: var(--text);
    }
    .splash-lead .splash-excerpt {
      font-size: 0.98rem;
      -webkit-line-clamp: 3;
      margin-bottom: 0.75rem;
    }
    .splash-card {
      background: linear-gradient(160deg, #151e2f 0%, var(--surface) 100%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem 1.1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 0.65rem;
      cursor: pointer;
      transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .splash-card:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .card-title { cursor: pointer; }
    .card-title:hover { color: var(--accent); }
    .modal-box.article-modal { max-width: 860px; }
    .splash-card h3 {
      margin: 0;
      font-family: var(--serif);
      font-size: 1.12rem;
      line-height: 1.28;
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
    .claim-btn {
      background: rgba(210, 153, 34, 0.14);
      border: 1px solid rgba(210, 153, 34, 0.5);
      color: #fde047;
      border-radius: 7px;
      padding: 0.35rem 0.7rem;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }
    .claim-btn:hover { background: rgba(210, 153, 34, 0.25); }
    .modal-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(5, 8, 15, 0.78);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .modal-backdrop.open { display: flex; }
    .modal-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      max-width: 680px;
      width: 100%;
      max-height: 90vh;
      overflow-y: auto;
      padding: 1.25rem;
    }
    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      margin-bottom: 0.75rem;
    }
    .modal-head h3 { margin: 0; font-size: 1.05rem; }
    .modal-meta {
      font-size: 0.86rem;
      color: var(--muted);
      margin-bottom: 0.75rem;
      line-height: 1.5;
    }
    .modal-meta a { color: var(--accent); }
    .modal-textarea {
      width: 100%;
      min-height: 220px;
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 0.75rem;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.82rem;
      line-height: 1.45;
      resize: vertical;
    }
    .modal-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem;
      margin-top: 0.85rem;
      align-items: center;
    }
    .btn-primary {
      background: var(--accent);
      color: #08101c;
      border: none;
      border-radius: 8px;
      padding: 0.5rem 0.9rem;
      font-weight: 700;
      font-size: 0.88rem;
      text-decoration: none;
      cursor: pointer;
    }
    .model-banner {
      background: linear-gradient(135deg, #131c2e 0%, #0e1522 100%);
      border: 1px solid rgba(96, 165, 250, 0.35);
      border-radius: 12px;
      padding: 1.05rem 1.25rem;
      margin-bottom: 1.4rem;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }
    .model-banner h2 {
      margin: 0 0 0.25rem;
      font-family: var(--serif);
      font-size: 1.18rem;
      color: var(--text);
    }
    .model-specs {
      font-size: 0.86rem;
      color: #c5d2e6;
      line-height: 1.55;
      max-width: 780px;
    }
    .model-specs strong { color: var(--text); }
    .model-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.55rem;
      align-items: center;
    }
  </style>
</head>
<body>
  <header>
    <div class="container">
      <div class="masthead-bar">
        <span>SideQuestAI Science Dispatch</span>
        <span>Machine-Verified Physics &amp; Astrophysics</span>
      </div>
      <div class="header-top">
        <div>
          <h1>SideQuestAI Science</h1>
          <p class="subtitle">Independent numerical &amp; analytical verifications of frontier arXiv research</p>
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
        <button class="btn" id="toggleIndexBtn" type="button">Hide Index</button>
      </div>
      <div class="domain-pills" id="domainPills"></div>
    </div>
  </header>

  <main>
    <section class="container model-banner">
      <div>
        <div class="kicker" style="margin-bottom:0.15rem;">Open Weights · Local Autonomous Scientist</div>
        <h2>Run <code>sciencebot-4b</code> Locally (2.50 GB GGUF)</h2>
        <div class="model-specs">
          <div><strong>Model Size:</strong> <code>2.50 GB</code> (<code>Q4_K_M</code> GGUF · Qwen3-4B fine-tuned via SFT + On-Policy DPO) · <code>~3.73 GB</code> VRAM loaded in Ollama.</div>
          <div><strong>Minimum Hardware:</strong> <code>6 GB+</code> VRAM GPU (RTX 2060/3060/4060 or Apple Silicon <code>8 GB+</code> unified RAM) or <code>16 GB</code> system RAM for CPU/iGPU fallback.</div>
          <div><strong>Recommended:</strong> <code>8–16 GB+</code> VRAM GPU (<code>~15 cycles/hr</code> in local Eco mode) or <code>RTX 4090</code> (<code>~100+ cycles/hr</code> parallel) + Python <code>3.10+</code> (<code>numpy</code>, <code>scipy</code>, <code>sympy</code>) &amp; Ollama.</div>
          <div><strong>Quick Run:</strong> <code>ollama run hf.co/lamonster87/sciencebot-4b-gguf</code> (or load <code>unsloth.Q4_K_M.gguf</code> in PocketPal AI on <code>8 GB+</code> RAM phones).</div>
        </div>
      </div>
      <div class="model-actions">
        <a class="btn-primary" href="https://huggingface.co/lamonster87/sciencebot-4b-gguf/resolve/main/unsloth.Q4_K_M.gguf" target="_blank" rel="noopener">Download GGUF (2.50 GB) ↗</a>
        <a class="btn" href="https://huggingface.co/lamonster87/sciencebot-4b-gguf" target="_blank" rel="noopener" style="text-decoration:none;">Hugging Face ↗</a>
        <a class="btn" href="mailto:lamontgreen87@gmail.com?subject=SideQuestAI%20ScienceBot%204B%20Model%20Inquiry&body=Hi%20Lamont%2C%0A%0AI%20downloaded%20sciencebot-4b%20from%20SideQuestAI%20and%20wanted%20to%20reach%20out.%0A%0AThanks!">Email Lamont</a>
        <a class="btn" href="https://github.com/lamontgreen87-maker/SideQuestAI" target="_blank" rel="noopener" style="text-decoration:none;">GitHub ↗</a>
      </div>
    </section>
    <section id="splashBox" class="splash-section container"></section>
    <div class="container layout" id="mainLayout">
      <section class="articles" id="articlesBox"></section>
      <aside class="sidebar">
        <div class="sidebar-head">
          <h2>A–Z Dictionary Index</h2>
          <button class="btn" type="button" onclick="toggleIndex(false)" style="padding:0.2rem 0.5rem;font-size:0.75rem;">Hide</button>
        </div>
        <div id="indexBox"></div>
      </aside>
    </div>
  </main>

  <div class="modal-backdrop" id="articleModal" onclick="if(event.target===this)closeArticleModal()">
    <div class="modal-box article-modal">
      <div class="modal-head">
        <h3 id="articleModalTitle">Article</h3>
        <button class="btn" type="button" onclick="closeArticleModal()">Close</button>
      </div>
      <div class="badges" id="articleModalBadges" style="margin-bottom:0.75rem;"></div>
      <div id="articleModalContent"></div>
      <div class="modal-actions" id="articleModalActions"></div>
    </div>
  </div>

  <div class="modal-backdrop" id="outreachModal" onclick="if(event.target===this)closeOutreachModal()">
    <div class="modal-box">
      <div class="modal-head">
        <h3>Email Paper Author &amp; Claim Verified Title</h3>
        <button class="btn" type="button" onclick="closeOutreachModal()">Close</button>
      </div>
      <div class="modal-meta" id="outreachMeta"></div>
      <textarea class="modal-textarea" id="outreachBody" readonly></textarea>
      <div class="modal-actions">
        <a class="btn-primary" id="outreachMailto" href="#">Open in Email App</a>
        <button class="btn" id="outreachCopyBtn" type="button" onclick="copyOutreachText()">Copy Email Text</button>
      </div>
    </div>
  </div>

  <div class="modal-backdrop" id="claimModal" onclick="if(event.target===this)closeClaimModal()">
    <div class="modal-box">
      <div class="modal-head">
        <h3>Claim Your Verified Title</h3>
        <button class="btn" type="button" onclick="closeClaimModal()">Close</button>
      </div>
      <div class="modal-meta" id="claimMeta"></div>
      <label style="display:block;font-size:0.85rem;color:var(--muted);margin-bottom:0.35rem;">Your Name / Affiliation (for attribution badge)</label>
      <input id="claimAuthorInput" type="text" placeholder="e.g. Dr. Jane Doe (MIT)" style="width:100%;background:var(--code-bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:0.55rem 0.75rem;margin-bottom:0.85rem;" />
      <div class="modal-actions">
        <button class="btn-primary" type="button" onclick="submitAuthorClaim()">Confirm Claim &amp; Verify Receipt</button>
      </div>
    </div>
  </div>

  <script>
    const EMBEDDED_DATA = __EMBEDDED_DATA__;

    const state = {
      data: null,
      domain: "all",
      visibleCount: 40,
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
        `<span class="stat-pill"><strong>${s.runs_per_hour ?? 0}</strong> Runs/hr</span>`,
        `<span class="stat-pill"><strong>${s.training_examples ?? 0}/${s.training_goal ?? 1000}</strong> Lesson 1 (${s.training_pct ?? 0}%)</span>`,
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

      const visible = filtered.slice(0, state.visibleCount);
      box.innerHTML = visible
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
          const claimBtn = (isVerified(a) && a.source_url)
            ? (a.claimed_by
                ? `<a class="claim-btn" href="${escapeHtml(a.claim_url || "#")}" target="_blank" rel="noopener" style="border-color:rgba(63,185,80,0.6);color:#4ade80;text-decoration:none;">✓ Claimed by ${escapeHtml(a.claimed_by)}</a>`
                : `<button class="claim-btn" type="button" onclick="openOutreachModal('${escapeHtml(a.id || "")}')">Email Author &amp; Claim Title</button>`)
            : "";
          const insightTxt = a.insight || "";
          const hypTxt = a.hypothesis ? `<div class="card-hypothesis"><strong>Hypothesis:</strong> ${escapeHtml(a.hypothesis)}</div>` : "";
          const outLines = (a.experiment_output || "").trim().split("\n").slice(0, 6).join("\n");
          const outPreview = outLines
            ? `<div class="output-box"><div style="font-family:var(--sans);font-size:0.72rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:var(--green);margin-bottom:0.25rem;">Measured Output${a.experiment_passed ? " · PASS" : ""}</div>${escapeHtml(outLines)}</div>`
            : "";
          const criticSnippet = a.critic_takeaway
            ? `<div class="meta-note"><strong>Critic Audit:</strong> ${escapeHtml(a.critic_takeaway.slice(0, 260))}${a.critic_takeaway.length > 260 ? "…" : ""}</div>`
            : "";
          const kicker = escapeHtml(a.domain || "Physics & Astrophysics");
          return `
            <article class="card" id="article-${escapeHtml(a.id || "")}">
              <div class="kicker">${kicker}</div>
              <div class="card-header">
                <h3 class="card-title" onclick="openArticleModal('${escapeHtml(a.id || "")}')">${escapeHtml(a.title || "Untitled Article")}</h3>
                ${claimBtn}
              </div>
              <div class="badges">${badges}</div>
              ${insightTxt ? `<div class="card-body" style="margin-top:0.75rem;">${escapeHtml(insightTxt)}</div>` : ""}
              ${hypTxt}
              ${outPreview}
              ${criticSnippet}
              <div class="card-footer">
                <a class="splash-link" href="#article-${escapeHtml(a.id || "")}" onclick="event.preventDefault();openArticleModal('${escapeHtml(a.id || "")}')">Read full dispatch &amp; verification code →</a>
                ${a.source_url ? `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" style="font-size:0.8rem;color:var(--muted);text-decoration:none;">arXiv Paper ↗</a>` : ""}
              </div>
            </article>
          `;
        })
        .join("") + (filtered.length > visible.length
          ? `<div style="text-align:center;margin-top:0.5rem;"><button class="btn-primary" type="button" onclick="state.visibleCount+=40;renderArticles();">Load More Articles (Showing ${visible.length} of ${filtered.length})</button></div>`
          : "");

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

      const lead = ranked[0];
      const subCards = ranked.slice(1)
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
            <div class="splash-card" onclick="openArticleModal('${escapeHtml(a.id || "")}')">
              <div>
                <div class="kicker">${escapeHtml(a.domain || "Dispatch")}</div>
                <h3>${escapeHtml(a.title || "Untitled Article")}</h3>
                <div class="badges">${badges}</div>
              </div>
              <p class="splash-excerpt">${escapeHtml(excerpt)}</p>
              <a class="splash-link" href="#article-${escapeHtml(a.id || "")}" onclick="event.preventDefault();event.stopPropagation();openArticleModal('${escapeHtml(a.id || "")}')">Read full dispatch →</a>
            </div>
          `;
        })
        .join("");

      const leadBadges = [
        isVerified(lead) ? `<span class="badge verified">✓ Verified</span>` : "",
        isNovelStrainLead(lead)
          ? `<span class="badge novel-strain">★ Novel Strain Lead</span>`
          : (isUnique(lead) ? `<span class="badge unique">★ Empirical Lead</span>` : ""),
        isDataFirst(lead) ? `<span class="badge data-first">Data-First (.hdf5)</span>` : "",
        isRealData(lead) ? `<span class="badge real-data">Real Data (GWTC/EHT)</span>` : "",
        lead.novelty_score != null ? `<span class="badge">${escapeHtml(String(lead.novelty_score))}% score</span>` : "",
      ].join("");

      box.innerHTML = `
        <div class="splash-heading">
          <h2>★ Lead Dispatch &amp; Featured Research</h2>
          <span>Top ranked by verification, novelty &amp; real GWTC/EHT data</span>
        </div>
        <div class="splash-lead" onclick="openArticleModal('${escapeHtml(lead.id || "")}')">
          <div class="kicker" style="color:var(--gold);">Lead Story · ${escapeHtml(lead.domain || "Physics")}</div>
          <h3>${escapeHtml(lead.title || "Untitled Article")}</h3>
          <div class="badges" style="margin-bottom:0.65rem;">${leadBadges}</div>
          <p class="splash-excerpt">${escapeHtml(lead.insight || lead.hypothesis || "")}</p>
          <a class="splash-link" href="#article-${escapeHtml(lead.id || "")}" onclick="event.preventDefault();event.stopPropagation();openArticleModal('${escapeHtml(lead.id || "")}')">Read full dispatch →</a>
        </div>
        ${subCards ? `<div class="splash-grid">${subCards}</div>` : ""}
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
        document.getElementById(id).addEventListener("input", () => { state.visibleCount = 40; renderSplash(); renderArticles(); });
        document.getElementById(id).addEventListener("change", () => { state.visibleCount = 40; renderSplash(); renderArticles(); });
      });
      document.getElementById("clearBtn").onclick = () => {
        document.getElementById("searchInput").value = "";
        document.getElementById("verifiedOnly").checked = false;
        document.getElementById("uniqueOnly").checked = false;
        document.getElementById("realDataOnly").checked = false;
        document.getElementById("dataFirstOnly").checked = false;
        state.domain = "all";
        state.visibleCount = 40;
        renderDomains();
        renderSplash();
        renderArticles();
      };
      document.getElementById("toggleIndexBtn").onclick = () => toggleIndex();
    }

    function toggleIndex(force) {
      const layout = document.getElementById("mainLayout");
      const btn = document.getElementById("toggleIndexBtn");
      const hide = typeof force === "boolean" ? !force : !layout.classList.contains("hide-index");
      layout.classList.toggle("hide-index", hide);
      if (btn) btn.textContent = hide ? "Show Index" : "Hide Index";
    }

    function openOutreachModal(articleId) {
      const articles = (state.data && state.data.articles) || [];
      const a = articles.find((x) => String(x.id || "") === String(articleId));
      if (!a) return;
      const authorName = a.author_name || "Author";
      const aff = a.author_affiliation ? ` (${a.author_affiliation})` : "";
      const email = a.author_email || "";
      const wikiLink = `https://sidequestai.org/#article-${a.id || ""}`;
      const claimLink = `https://sidequestai.org/?claim=${encodeURIComponent(a.id || "")}&token=${encodeURIComponent(a.claim_token || "")}#article-${a.id || ""}`;
      const subject = `Verified Check & Title Claim: "${a.source_title || a.title || "Your Paper"}"${a.arxiv_id ? ` (${a.arxiv_id})` : ""}`;
      const greeting = authorName && authorName !== "Author"
        ? `Dr. ${(authorName.includes(",") ? authorName.split(",")[0] : authorName.split(" ").slice(-1)[0]).trim()}`
        : "Author";
      const bodyLines = [
        `Dear ${greeting},`,
        "",
        `I'm sharing an independent numerical/analytical verification of your paper${a.source_title ? ` "${a.source_title}"` : ""}${a.source_url ? ` (${a.source_url})` : ""}.`,
        "",
        `Verified Title: ${a.title || "Automated Verification"}`,
        `Summary: ${a.insight || a.summary || ""}`,
        "",
        "Executed Verification Output:",
        (a.experiment_output || "(see full script at link below)").slice(0, 900),
        "",
        `CLICK TO CLAIM YOUR VERIFIED TITLE & CONFIRM RECEIPT:`,
        claimLink,
        "",
        `Article page: ${wikiLink}`,
        "",
        "Best regards,",
        "A SideQuestAI Science Wiki Reader"
      ].join("\n");

      const metaParts = [
        `<div><strong>Writer:</strong> ${escapeHtml(authorName)}${escapeHtml(aff)}</div>`,
        `<div><strong>Email:</strong> ${email ? escapeHtml(email) : "Not listed on INSPIRE-HEP — check paper PDF or INSPIRE link"}</div>`,
        `<div>${a.source_url ? `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener">arXiv Paper ↗</a>` : ""}${a.inspire_url ? ` · <a href="${escapeHtml(a.inspire_url)}" target="_blank" rel="noopener">INSPIRE-HEP ↗</a>` : ""}</div>`
      ];
      document.getElementById("outreachMeta").innerHTML = metaParts.join("");
      document.getElementById("outreachBody").value = `Subject: ${subject}\n\n${bodyLines}`;
      document.getElementById("outreachMailto").href =
        `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyLines)}`;
      document.getElementById("outreachCopyBtn").textContent = "Copy Email Text";
      document.getElementById("outreachModal").classList.add("open");
    }

    function closeOutreachModal() {
      document.getElementById("outreachModal").classList.remove("open");
    }

    async function copyOutreachText() {
      const txt = document.getElementById("outreachBody").value || "";
      try {
        await navigator.clipboard.writeText(txt);
        document.getElementById("outreachCopyBtn").textContent = "Copied!";
      } catch (_) {
        document.getElementById("outreachBody").select();
        document.execCommand("copy");
        document.getElementById("outreachCopyBtn").textContent = "Copied!";
      }
    }

    let _activeClaim = null;

    function openClaimModalFromQuery() {
      const params = new URLSearchParams(window.location.search);
      const claimId = params.get("claim");
      const token = params.get("token");
      if (!claimId || !token) return;
      const articles = (state.data && state.data.articles) || [];
      const a = articles.find((x) => String(x.id || "") === String(claimId));
      if (!a || String(a.claim_token || "") !== String(token)) return;
      _activeClaim = a;
      document.getElementById("claimMeta").innerHTML =
        `<div><strong>Verified Title:</strong> ${escapeHtml(a.title || "")}</div>` +
        `<div><strong>Paper:</strong> ${escapeHtml(a.source_title || a.source_url || "")}</div>` +
        `<div><strong>Claim Token:</strong> <code>${escapeHtml(token)}</code> (verified)</div>`;
      document.getElementById("claimAuthorInput").value = a.author_name || "";
      document.getElementById("claimModal").classList.add("open");
    }

    function closeClaimModal() {
      document.getElementById("claimModal").classList.remove("open");
    }

    function submitAuthorClaim() {
      if (!_activeClaim) return;
      const a = _activeClaim;
      const claimedBy = (document.getElementById("claimAuthorInput").value || a.author_name || "Verified Author").trim();
      const title = `Claim Title: ${a.title || a.id}`;
      const body = [
        `Article ID: ${a.id || ""}`,
        `arXiv ID: ${a.arxiv_id || "N/A"}`,
        `Claim Token: ${a.claim_token || ""}`,
        `Claimed By: ${claimedBy}`,
        `Article URL: https://sidequestai.org/#article-${a.id || ""}`,
        "",
        "I confirm receipt of this verification email and claim authorship attribution for this verified title."
      ].join("\n");
      const url = `https://github.com/lamontgreen87-maker/SideQuestAI/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
      window.open(url, "_blank", "noopener");
      closeClaimModal();
    }

    let _activeArticleId = null;

    function openArticleModal(articleId) {
      const articles = (state.data && state.data.articles) || [];
      const a = articles.find((x) => String(x.id || "") === String(articleId));
      if (!a) return;
      _activeArticleId = String(a.id || "");
      if (window.location.hash !== `#article-${_activeArticleId}`) {
        history.replaceState(null, "", `#article-${_activeArticleId}`);
      }
      document.getElementById("articleModalTitle").textContent = a.title || "Untitled Article";
      document.getElementById("articleModalBadges").innerHTML = [
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

      const sections = [];
      if (a.insight) {
        sections.push(`<div class="detail-section" style="margin-top:0;padding-top:0;border-top:none;"><div class="detail-label">Key Finding</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.insight)}</div></div>`);
      }
      if (a.hypothesis) {
        sections.push(`<div class="detail-section"><div class="detail-label">Hypothesis Tested</div><div class="card-hypothesis" style="margin-top:0;">${escapeHtml(a.hypothesis)}</div></div>`);
      }
      if (a.experiment_output) {
        sections.push(`<div class="detail-section"><div class="detail-label" style="color:var(--green);">Measured Verification Output${a.experiment_passed ? " · PASSED" : ""}</div><div class="output-box" style="margin-top:0;">${escapeHtml(a.experiment_output)}</div></div>`);
      }
      if (a.mini_experiment && a.mini_experiment !== "N/A") {
        sections.push(`<div class="detail-section"><div class="detail-label">Experimental Methodology</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.mini_experiment)}</div></div>`);
      }
      if (a.critic_takeaway) {
        sections.push(`<div class="detail-section"><div class="detail-label">Independent Critic Audit${a.confidence ? ` · Confidence: ${escapeHtml(a.confidence)}` : ""}</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.critic_takeaway)}</div></div>`);
      }
      if (a.scout_angle) {
        sections.push(`<div class="detail-section"><div class="detail-label">Research Angle (Scout)</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.scout_angle)}</div></div>`);
      }
      if (a.open_question) {
        sections.push(`<div class="detail-section"><div class="detail-label">Suggested Next Directions &amp; Open Questions</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.open_question)}</div></div>`);
      }
      if (a.wiki_extract) {
        const wLink = a.wiki_url ? ` <a href="${escapeHtml(a.wiki_url)}" target="_blank" rel="noopener" style="color:var(--accent)">Wikipedia ↗</a>` : "";
        sections.push(`<div class="detail-section"><div class="detail-label">Background Context${a.wiki_title ? ` · ${escapeHtml(a.wiki_title)}` : ""}</div><div class="card-body" style="margin-top:0;">${escapeHtml(a.wiki_extract)}${wLink}</div></div>`);
      }
      if (a.experiment_code) {
        const linesCount = String(a.experiment_code).split("\n").length;
        sections.push(`<div class="detail-section"><details><summary>Reproducible Python Verification Script (${linesCount} lines${a.experiment_passed ? " · Passed" : ""})</summary><pre><code>${escapeHtml(a.experiment_code)}</code></pre></details></div>`);
      }
      if (a.source_url || a.author_name || a.inspire_url) {
        const refParts = [];
        if (a.source_url) refParts.push(`<div><strong>Source Paper:</strong> <a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" style="color:var(--accent)">${escapeHtml(a.source_title || a.source_url)}</a></div>`);
        if (a.author_name) refParts.push(`<div><strong>Author:</strong> ${escapeHtml(a.author_name)}${a.author_affiliation ? ` (${escapeHtml(a.author_affiliation)})` : ""}</div>`);
        if (a.inspire_url) refParts.push(`<div><strong>INSPIRE-HEP:</strong> <a href="${escapeHtml(a.inspire_url)}" target="_blank" rel="noopener" style="color:var(--accent)">${escapeHtml(a.inspire_url)}</a></div>`);
        sections.push(`<div class="detail-section"><div class="detail-label">Source &amp; Attribution</div><div class="meta-note" style="margin-top:0;">${refParts.join("")}</div></div>`);
      }

      const contentEl = document.getElementById("articleModalContent");
      contentEl.innerHTML = sections.join("");
      if (typeof renderMathInElement === "function") {
        renderMathInElement(contentEl, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "\\[", right: "\\]", display: true },
            { left: "$", right: "$", display: false },
            { left: "\\(", right: "\\)", display: false },
          ],
          throwOnError: false,
        });
      }

      const actions = [
        `<button class="btn" id="copyArticleLinkBtn" type="button" onclick="copyArticleLink()">Copy Article Link</button>`,
      ];
      if (isVerified(a) && a.source_url && !a.claimed_by) {
        actions.push(`<button class="claim-btn" type="button" onclick="closeArticleModal();openOutreachModal('${escapeHtml(_activeArticleId)}')">Email Author &amp; Claim Title</button>`);
      }
      if (a.source_url) {
        actions.push(`<a class="btn" href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" style="text-decoration:none;">Open Paper ↗</a>`);
      }
      document.getElementById("articleModalActions").innerHTML = actions.join("");
      document.getElementById("articleModal").classList.add("open");
    }

    function closeArticleModal() {
      document.getElementById("articleModal").classList.remove("open");
      if (window.location.hash.startsWith("#article-")) {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }

    async function copyArticleLink() {
      if (!_activeArticleId) return;
      const url = `https://sidequestai.org/#article-${_activeArticleId}`;
      try {
        await navigator.clipboard.writeText(url);
        document.getElementById("copyArticleLinkBtn").textContent = "Copied Link!";
      } catch (_) {}
    }

    function openArticleFromHash() {
      const m = window.location.hash.match(/^#article-(.+)$/);
      if (m && m[1]) openArticleModal(decodeURIComponent(m[1]));
    }

    window.addEventListener("hashchange", openArticleFromHash);
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeArticleModal();
        closeOutreachModal();
        closeClaimModal();
      }
    });

    window.addEventListener("DOMContentLoaded", () => {
      init().then(() => {
        openArticleFromHash();
        setTimeout(openClaimModalFromQuery, 150);
      });
    });
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
    from author_outreach import enrich_articles_with_authors
    all_published = bot._load_articles_from_db(limit=5000)
    enriched_articles = enrich_articles_with_authors(list(all_published), max_lookups=25)
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": bot.get_status(),
        "index": bot.build_dictionary_index(),
        "articles": enriched_articles,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "data.json"
    html_path = output_dir / "index.html"

    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    data_path.write_text(json_text, encoding="utf-8")

    # Keep inline fallback compact so index.html loads fast while data.json serves all articles.
    embedded_payload = {**payload, "articles": enriched_articles[:100]}
    embedded_json = json.dumps(embedded_payload, ensure_ascii=False).replace("</", "<\\/")
    html_text = HTML_TEMPLATE.replace("__EMBEDDED_DATA__", embedded_json)
    html_path.write_text(html_text, encoding="utf-8")

    return {
        "data_path": str(data_path),
        "html_path": str(html_path),
        "article_count": len(payload["articles"]),
        "total_terms": payload["index"].get("total_terms", 0),
    }


def _merge_remote_feed(bot: Any) -> int:
    """Pull origin/main feed and merge any unseen article IDs into local ScienceBot DB."""
    repo_root = BASE_DIR.parent
    git_bin = shutil.which("git")
    if not git_bin:
        return 0
    try:
        subprocess.run(
            [git_bin, "-C", str(repo_root), "fetch", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        show = subprocess.run(
            [git_bin, "-C", str(repo_root), "show", "origin/main:hive_mind/memory/science_feed.json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if show.returncode != 0 or not show.stdout.strip():
            return 0
        remote_data = json.loads(show.stdout)
        remote_feed = remote_data.get("feed", []) if isinstance(remote_data, dict) else []
        local_ids = {a.get("id") for a in bot.feed}
        added = 0
        for item in remote_feed:
            if isinstance(item, dict) and item.get("id") and item["id"] not in local_ids:
                bot._upsert_article_db(item)
                added += 1
        if added:
            bot.feed = bot._load_articles_from_db()
            bot._save_state()
        return added
    except Exception:
        return 0


def _push_git_sync() -> bool:
    """Commit and push merged science_feed.json + site/ to origin/main (best-effort)."""
    repo_root = BASE_DIR.parent
    git_bin = shutil.which("git")
    if not git_bin:
        return False
    try:
        subprocess.run(
            [git_bin, "-C", str(repo_root), "add", "hive_mind/memory/science_feed.json", "hive_mind/site/"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        diff = subprocess.run(
            [git_bin, "-C", str(repo_root), "diff", "--cached", "--quiet"],
            timeout=10,
        )
        if diff.returncode != 0:
            subprocess.run(
                [git_bin, "-C", str(repo_root), "commit", "-m", "Auto-sync ScienceBot articles"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        subprocess.run(
            [git_bin, "-C", str(repo_root), "pull", "--no-rebase", "-X", "ours", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        push = subprocess.run(
            [git_bin, "-C", str(repo_root), "push", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return push.returncode == 0
    except Exception:
        return False


def deploy_site(
    output_dir: Path = SITE_DIR,
    bot: Any = None,
    project_name: str = "sidequestai",
    branch: str = "main",
) -> Dict[str, Any]:
    """Merge remote GitHub feed, export static site, push Git sync, and deploy to Cloudflare Pages."""
    with _DEPLOY_LOCK:
        if bot is None:
            bot = ScienceBot()
        merged = _merge_remote_feed(bot)
        bot._save_state()
        summary = export_site(output_dir=output_dir, bot=bot)
        git_synced = _push_git_sync()

        wrangler_bin = shutil.which("wrangler")
        npx_bin = shutil.which("npx")
        if wrangler_bin:
            base_cmd = [wrangler_bin]
        elif npx_bin:
            base_cmd = [npx_bin, "--yes", "wrangler"]
        else:
            return {**summary, "merged_from_remote": merged, "git_synced": git_synced, "deployed": False, "error": "wrangler/npx not found on PATH"}
        cmd = base_cmd + [
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
            "merged_from_remote": merged,
            "git_synced": git_synced,
            "deployed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-600:] if proc.stdout else "",
            "stderr": proc.stderr[-600:] if proc.stderr else "",
        }


if __name__ == "__main__":
    summary = export_site()
    print(json.dumps(summary, indent=2))

