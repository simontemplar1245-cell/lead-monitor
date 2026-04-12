#!/usr/bin/env python3
"""
Lead Report — Static HTML Dashboard
=====================================
Generates a single HTML page with all leads, clickable links, summaries,
and importance badges. Deployed to GitHub Pages after every scan.

Usage:
  python report.py                  # Generate to _site/index.html
  python report.py --output dir/    # Custom output directory
  python report.py --validate       # Also check that lead URLs are reachable
"""

import sys
import os
import re
import argparse
import logging
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATABASE_PATH
from core.database import LeadDatabase

logger = logging.getLogger(__name__)

# =========================================================================
# URL VALIDATION
# =========================================================================

def validate_url(url: str, timeout: int = 8) -> dict:
    """Check if a URL is reachable. Returns {valid, status, reason}."""
    if not url or url == "N/A":
        return {"valid": False, "status": 0, "reason": "No URL"}
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"valid": False, "status": 0, "reason": "Not HTTP"}
    except Exception:
        return {"valid": False, "status": 0, "reason": "Bad URL"}

    try:
        import requests
        resp = requests.head(url, timeout=timeout, allow_redirects=True,
                             headers={"User-Agent": "LeadMonitor/1.0"})
        if resp.status_code < 400:
            return {"valid": True, "status": resp.status_code, "reason": "OK"}
        # Some sites block HEAD, try GET
        resp = requests.get(url, timeout=timeout, allow_redirects=True,
                            headers={"User-Agent": "LeadMonitor/1.0"},
                            stream=True)
        resp.close()
        if resp.status_code < 400:
            return {"valid": True, "status": resp.status_code, "reason": "OK"}
        return {"valid": False, "status": resp.status_code,
                "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "status": 0, "reason": str(e)[:60]}


# =========================================================================
# HTML GENERATION
# =========================================================================

def generate_html(db: LeadDatabase, validate: bool = False) -> str:
    """Generate the full HTML report."""
    # Fetch ALL leads ever collected
    all_leads = db.get_leads(days=9999, limit=5000)
    hot_warm = [l for l in all_leads if l.get("category") in ("HOT", "WARM")]

    # Sort: newest first, then by category (HOT before WARM at same time)
    hot_warm.sort(key=lambda x: (
        -(datetime.fromisoformat(str(x.get("discovered_at", "2000-01-01")).replace("Z", "+00:00")).replace(tzinfo=None).timestamp() if x.get("discovered_at") else 0),
        0 if x.get("category") == "HOT" else 1,
    ))

    hot = [l for l in hot_warm if l.get("category") == "HOT"]
    warm = [l for l in hot_warm if l.get("category") == "WARM"]

    # Validate URLs if requested
    url_status = {}
    if validate:
        logger.info(f"Validating {len(hot_warm)} URLs...")
        for lead in hot_warm:
            url = lead.get("url", "")
            if url and url != "N/A" and url not in url_status:
                url_status[url] = validate_url(url)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Pipeline stats
    pipeline = db.get_pipeline_counts()

    lead_rows = []
    for lead in hot_warm:
        lead_rows.append(_render_lead_card(lead, url_status))

    cards_html = "\n".join(lead_rows) if lead_rows else '<p class="empty">No leads found yet. The scanner runs every hour — check back soon.</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Advance AI Services — Lead Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    line-height: 1.5;
    padding: 0;
  }}
  .header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #334155;
    padding: 24px 20px;
    text-align: center;
  }}
  .header h1 {{
    font-size: 1.5rem;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 4px;
  }}
  .header .subtitle {{
    font-size: 0.85rem;
    color: #94a3b8;
  }}
  .pipeline {{
    display: flex;
    gap: 12px;
    padding: 16px 20px;
    justify-content: center;
    flex-wrap: wrap;
    background: #1e293b;
    border-bottom: 1px solid #334155;
  }}
  .pipe-box {{
    text-align: center;
    padding: 12px 20px;
    border-radius: 8px;
    min-width: 120px;
  }}
  .pipe-box .num {{
    font-size: 1.8rem;
    font-weight: 700;
  }}
  .pipe-box .label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    opacity: 0.8;
  }}
  .pipe-new {{ background: #1e3a5f; color: #60a5fa; }}
  .pipe-contacted {{ background: #3b2f0a; color: #fbbf24; }}
  .pipe-talking {{ background: #0a3b3b; color: #2dd4bf; }}
  .pipe-converted {{ background: #14532d; color: #4ade80; }}
  .filters {{
    padding: 16px 20px;
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
  }}
  .filter-btn {{
    padding: 6px 16px;
    border-radius: 20px;
    border: 1px solid #475569;
    background: transparent;
    color: #94a3b8;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
  }}
  .filter-btn:hover, .filter-btn.active {{
    background: #334155;
    color: #f8fafc;
    border-color: #60a5fa;
  }}
  .container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
  }}
  .section-title {{
    font-size: 1.1rem;
    font-weight: 600;
    margin: 24px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid #334155;
  }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
  }}
  .card:hover {{
    border-color: #475569;
  }}
  .card-hot {{
    border-left: 4px solid #ef4444;
  }}
  .card-warm {{
    border-left: 4px solid #f59e0b;
  }}
  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 8px;
  }}
  .card-company {{
    font-size: 1.05rem;
    font-weight: 600;
    color: #f8fafc;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    white-space: nowrap;
  }}
  .badge-hot {{
    background: #991b1b;
    color: #fca5a5;
  }}
  .badge-warm {{
    background: #78350f;
    color: #fcd34d;
  }}
  .badge-source {{
    background: #1e3a5f;
    color: #93c5fd;
    margin-left: 6px;
  }}
  .badge-direct {{
    background: #14532d;
    color: #86efac;
    margin-left: 6px;
  }}
  .badge-research {{
    background: #78350f;
    color: #fcd34d;
    margin-left: 6px;
  }}
  .card-title {{
    font-size: 0.9rem;
    color: #cbd5e1;
    margin-bottom: 6px;
  }}
  .card-summary {{
    font-size: 0.85rem;
    color: #94a3b8;
    margin-bottom: 10px;
    line-height: 1.6;
  }}
  .card-meta {{
    display: flex;
    gap: 16px;
    font-size: 0.78rem;
    color: #64748b;
    flex-wrap: wrap;
    align-items: center;
  }}
  .card-link {{
    display: inline-block;
    padding: 6px 14px;
    background: #1e3a5f;
    color: #60a5fa;
    text-decoration: none;
    font-weight: 600;
    border-radius: 6px;
    font-size: 0.85rem;
    transition: background 0.2s;
    margin-right: 6px;
  }}
  .card-link:hover {{
    background: #2563eb;
    color: #fff;
  }}
  .card-link-primary {{
    background: #14532d;
    color: #86efac;
  }}
  .card-link-primary:hover {{
    background: #16a34a;
    color: #fff;
  }}
  .contact-hint {{
    font-size: 0.78rem;
    color: #94a3b8;
    margin-top: 8px;
    padding: 8px 10px;
    background: #0f172a;
    border-radius: 6px;
    border-left: 3px solid #475569;
  }}
  .contact-hint strong {{
    color: #cbd5e1;
  }}
  .card-role {{
    font-size: 0.88rem;
    color: #93c5fd;
    margin-bottom: 4px;
    font-weight: 500;
  }}
  .url-ok {{ color: #4ade80; }}
  .url-bad {{ color: #f87171; }}
  .suggested {{
    margin-top: 10px;
    padding: 10px 12px;
    background: #0f172a;
    border-radius: 6px;
    font-size: 0.82rem;
    color: #94a3b8;
    border: 1px solid #1e293b;
  }}
  .suggested strong {{
    color: #cbd5e1;
    font-size: 0.75rem;
    display: block;
    margin-bottom: 4px;
  }}
  .score-bar {{
    width: 50px;
    height: 6px;
    background: #334155;
    border-radius: 3px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
    margin-left: 4px;
  }}
  .score-fill {{
    height: 100%;
    border-radius: 3px;
  }}
  .score-hot {{ background: #ef4444; }}
  .score-warm {{ background: #f59e0b; }}
  .empty {{
    text-align: center;
    padding: 60px 20px;
    color: #64748b;
    font-size: 0.95rem;
  }}
  .footer {{
    text-align: center;
    padding: 30px 20px;
    font-size: 0.78rem;
    color: #475569;
    border-top: 1px solid #1e293b;
    margin-top: 30px;
  }}
  /* Setup section (collapsible signup links) */
  .setup-wrap {{
    max-width: 900px;
    margin: 16px auto 0;
    padding: 0 20px;
  }}
  .setup-toggle {{
    width: 100%;
    background: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
    transition: background 0.2s;
  }}
  .setup-toggle:hover {{ background: #334155; }}
  .setup-toggle::after {{ content: ' ▼'; float: right; opacity: 0.6; }}
  .setup-toggle.open::after {{ content: ' ▲'; }}
  .setup-body {{
    display: none;
    background: #1e293b;
    border: 1px solid #334155;
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 16px;
    margin-top: -8px;
  }}
  .setup-body.open {{ display: block; }}
  .setup-body p {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 12px; }}
  .signup-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 8px;
    margin-top: 8px;
  }}
  .signup-item {{
    display: block;
    padding: 10px 14px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    text-decoration: none;
    font-size: 0.85rem;
    transition: all 0.2s;
  }}
  .signup-item:hover {{
    border-color: #60a5fa;
    background: #1e3a5f;
  }}
  .signup-item strong {{ display: block; color: #f8fafc; margin-bottom: 2px; }}
  .signup-item span {{ color: #64748b; font-size: 0.78rem; }}
  /* Copy button + contacted state */
  .copy-btn {{
    display: inline-block;
    padding: 5px 12px;
    background: #1e3a5f;
    color: #93c5fd;
    border: 1px solid #334155;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    margin-left: 6px;
    transition: all 0.2s;
  }}
  .copy-btn:hover {{ background: #2563eb; color: #fff; }}
  .copy-btn.copied {{ background: #14532d; color: #86efac; border-color: #14532d; }}
  .mark-btn {{
    display: inline-block;
    padding: 5px 12px;
    background: transparent;
    color: #94a3b8;
    border: 1px solid #475569;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    margin-left: 6px;
    transition: all 0.2s;
  }}
  .mark-btn:hover {{ background: #334155; color: #f8fafc; }}
  .card.contacted {{ opacity: 0.45; }}
  .card.contacted .mark-btn {{
    background: #14532d;
    color: #86efac;
    border-color: #14532d;
  }}
  .hidden-msg {{ position: absolute; left: -9999px; top: -9999px; }}
  .suggested-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
  }}
  @media (max-width: 600px) {{
    .pipeline {{ gap: 8px; }}
    .pipe-box {{ min-width: 80px; padding: 10px 12px; }}
    .pipe-box .num {{ font-size: 1.3rem; }}
    .card-top {{ flex-direction: column; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Advance AI Services — Lead Dashboard</h1>
  <div class="subtitle">Updated {now} &middot; {len(hot)} HOT &middot; {len(warm)} WARM &middot; {len(hot_warm)} total</div>
</div>

<div class="pipeline">
  <div class="pipe-box pipe-new">
    <div class="num">{pipeline.get('new_leads', 0) or 0}</div>
    <div class="label">New Leads</div>
  </div>
  <div class="pipe-box pipe-contacted">
    <div class="num">{pipeline.get('contacted', 0) or 0}</div>
    <div class="label">Contacted</div>
  </div>
  <div class="pipe-box pipe-talking">
    <div class="num">{pipeline.get('in_conversation', 0) or 0}</div>
    <div class="label">In Conversation</div>
  </div>
  <div class="pipe-box pipe-converted">
    <div class="num">{pipeline.get('converted', 0) or 0}</div>
    <div class="label">Converted</div>
  </div>
</div>

<div class="setup-wrap">
  <button class="setup-toggle" onclick="toggleSetup()">⚙️  One-time setup — accounts you need to create</button>
  <div class="setup-body" id="setup-body">
    <p>To actually contact leads you need accounts on these platforms. All free. Create them once and you're set.</p>
    <div class="signup-grid">
      <a class="signup-item" href="https://accounts.google.com/signup" target="_blank" rel="noopener">
        <strong>Google / Gmail</strong>
        <span>For Maps, cold email, signing up everywhere else</span>
      </a>
      <a class="signup-item" href="https://www.linkedin.com/signup" target="_blank" rel="noopener">
        <strong>LinkedIn</strong>
        <span>Connection requests with notes (free, no Premium)</span>
      </a>
      <a class="signup-item" href="https://www.facebook.com/r.php" target="_blank" rel="noopener">
        <strong>Facebook</strong>
        <span>DM business pages directly</span>
      </a>
      <a class="signup-item" href="https://www.reddit.com/register" target="_blank" rel="noopener">
        <strong>Reddit</strong>
        <span>Reply to posts and DM users (age account 1+ week first)</span>
      </a>
      <a class="signup-item" href="https://news.ycombinator.com/login" target="_blank" rel="noopener">
        <strong>Hacker News</strong>
        <span>Reply in threads, see profile emails</span>
      </a>
      <a class="signup-item" href="https://bsky.app" target="_blank" rel="noopener">
        <strong>Bluesky</strong>
        <span>Public replies (DMs need follow-back)</span>
      </a>
      <a class="signup-item" href="https://hunter.io/users/sign_up" target="_blank" rel="noopener">
        <strong>Hunter.io (optional)</strong>
        <span>25 free email lookups/mo for cold email</span>
      </a>
      <a class="signup-item" href="https://wa.me/" target="_blank" rel="noopener">
        <strong>WhatsApp Business</strong>
        <span>Many SMBs use WhatsApp — message them once you have their phone</span>
      </a>
    </div>
    <p style="margin-top:14px;font-size:0.78rem;">
      <strong style="color:#cbd5e1;">Workflow:</strong> open a lead → click <em>Copy pitch</em> → click the platform button (LinkedIn / Facebook / Maps) → paste &amp; send → click <em>Mark contacted</em>.
    </p>
  </div>
</div>

<div class="filters">
  <button class="filter-btn active" onclick="filterLeads('all')">All</button>
  <button class="filter-btn" onclick="filterLeads('hot')">HOT Only</button>
  <button class="filter-btn" onclick="filterLeads('warm')">WARM Only</button>
  <button class="filter-btn" onclick="filterLeads('direct')">Direct Contact</button>
  <button class="filter-btn" onclick="filterLeads('research')">Research Needed</button>
  <button class="filter-btn" onclick="filterLeads('jobs')">Indeed/LinkedIn</button>
  <button class="filter-btn" onclick="filterLeads('reddit')">Reddit</button>
  <button class="filter-btn" onclick="filterLeads('uncontacted')">Hide Contacted</button>
</div>

<div class="container" id="leads">
{cards_html}
</div>

<div class="footer">
  Advance AI Services — Lead Dashboard &middot; Auto-updates every hour<br>
  <strong style="color:#86efac;">Direct contact (reply/DM on platform):</strong> Reddit (80+ subreddits), Hacker News, Bluesky, 8 industry forums<br>
  <strong style="color:#fcd34d;">Research needed (apply-only, cold-call the business):</strong> Indeed, LinkedIn Jobs
</div>

<script>
// ----- Setup section toggle -----
function toggleSetup() {{
  const body = document.getElementById('setup-body');
  const btn = document.querySelector('.setup-toggle');
  body.classList.toggle('open');
  btn.classList.toggle('open');
}}

// ----- Copy pitch to clipboard -----
function copyPitch(leadId, btn) {{
  const ta = document.getElementById('msg-' + leadId);
  if (!ta) return;
  // Decode HTML entities by reading textarea value
  const text = ta.value.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#x27;/g, "'");
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(() => flashCopied(btn));
  }} else {{
    // Fallback for older browsers
    ta.style.position = 'fixed';
    ta.style.left = '0';
    ta.style.top = '0';
    ta.select();
    try {{ document.execCommand('copy'); flashCopied(btn); }} catch (e) {{}}
    ta.style.position = 'absolute';
    ta.style.left = '-9999px';
    ta.style.top = '-9999px';
  }}
}}
function flashCopied(btn) {{
  const orig = btn.innerHTML;
  btn.innerHTML = '✓ Copied!';
  btn.classList.add('copied');
  setTimeout(() => {{
    btn.innerHTML = orig;
    btn.classList.remove('copied');
  }}, 1800);
}}

// ----- Mark contacted (persisted in localStorage) -----
const CONTACTED_KEY = 'leadmonitor_contacted_v1';
function getContacted() {{
  try {{
    return new Set(JSON.parse(localStorage.getItem(CONTACTED_KEY) || '[]'));
  }} catch (e) {{ return new Set(); }}
}}
function saveContacted(set) {{
  localStorage.setItem(CONTACTED_KEY, JSON.stringify([...set]));
}}
function toggleContacted(leadId, btn) {{
  const set = getContacted();
  const card = btn.closest('.card');
  if (set.has(leadId)) {{
    set.delete(leadId);
    card.classList.remove('contacted');
    btn.innerHTML = '✓ Mark contacted';
  }} else {{
    set.add(leadId);
    card.classList.add('contacted');
    btn.innerHTML = '✓ Contacted';
  }}
  saveContacted(set);
}}
function initContacted() {{
  const set = getContacted();
  document.querySelectorAll('.card').forEach(card => {{
    const id = parseInt(card.dataset.id, 10);
    if (set.has(id)) {{
      card.classList.add('contacted');
      const btn = card.querySelector('.mark-btn');
      if (btn) btn.innerHTML = '✓ Contacted';
    }}
  }});
}}

// ----- Filter leads -----
let currentFilter = 'all';
function filterLeads(type) {{
  currentFilter = type;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const set = getContacted();
  document.querySelectorAll('.card').forEach(card => {{
    const p = card.dataset.platform;
    const id = parseInt(card.dataset.id, 10);
    let show = true;
    if (type === 'hot')         show = card.dataset.category === 'HOT';
    else if (type === 'warm')   show = card.dataset.category === 'WARM';
    else if (type === 'direct') show = (p === 'reddit' || p === 'reddit_search' || p === 'hackernews' || p === 'bluesky' || p === 'forum');
    else if (type === 'research') show = p === 'jobs';
    else if (type === 'jobs')   show = p === 'jobs';
    else if (type === 'reddit') show = (p === 'reddit' || p === 'reddit_search');
    else if (type === 'uncontacted') show = !set.has(id);
    card.style.display = show ? '' : 'none';
  }});
}}

document.addEventListener('DOMContentLoaded', initContacted);
</script>

</body>
</html>"""
    return html


def _fallback_pitch(lead: dict) -> str:
    """
    Generate a short cold-outreach pitch when the classifier didn't supply one.
    Kept under ~100 words (the sweet spot for cold message reply rates).
    """
    platform = lead.get("platform", "")
    company = (lead.get("author") or "there").strip()
    role = (lead.get("title") or "").strip()
    community = (lead.get("community") or "").strip()

    if platform == "jobs":
        # Cold outreach to a business posting a phone/reception role
        role_line = f"a {role}" if role else "a phone/reception role"
        return (
            f"Hi {company} team,\n\n"
            f"Saw you're hiring for {role_line}. Before locking in a "
            f"full-time hire, you might want to look at our AI receptionist "
            f"— it answers calls 24/7, books appointments, and never misses "
            f"a lead. Most clients spend ~$200/mo vs. paying a salary.\n\n"
            f"Worth a 5-minute look? Happy to send a 30-second demo.\n\n"
            f"— Advance AI Services"
        )

    # Social platforms (Reddit / HN / Bluesky / forums) — reply, not cold pitch
    topic_hint = ""
    body = (lead.get("body") or "").strip()
    if "missed call" in body.lower() or "phone" in body.lower():
        topic_hint = "missed calls and phone overflow"
    elif "after hours" in body.lower() or "after-hours" in body.lower():
        topic_hint = "after-hours coverage"
    elif "receptionist" in body.lower():
        topic_hint = "reception/front-desk workload"
    elif "chatbot" in body.lower() or "chat bot" in body.lower():
        topic_hint = "website chat / lead capture"
    else:
        topic_hint = "what you're describing"

    return (
        f"Hey — saw your post about {topic_hint}. We build AI receptionists "
        f"and chatbots that handle exactly this: 24/7 call answering, "
        f"appointment booking, and lead capture from your website. Most "
        f"clients save 15+ hours/week on phone admin.\n\n"
        f"Happy to show you a 2-min demo if you want to see how it works "
        f"— no pressure either way.\n\n"
        f"— Advance AI Services"
    )


def _render_lead_card(lead: dict, url_status: dict) -> str:
    """Render a single lead as an HTML card."""
    category = lead.get("category", "WARM")
    platform = lead.get("platform", "")
    community = lead.get("community", "")
    author = escape(lead.get("author") or "Unknown")
    title = escape(lead.get("title") or "(no title)")
    url = lead.get("url", "")
    score = float(lead.get("score", 0))
    reasoning = escape(lead.get("reasoning") or "")
    suggested = escape(lead.get("suggested_reply") or "")
    discovered = lead.get("discovered_at", "")

    # Time ago + actual timestamp
    time_str = ""
    try:
        dt = datetime.fromisoformat(str(discovered).replace("Z", "+00:00"))
        dt_naive = dt.replace(tzinfo=None)
        diff = datetime.utcnow() - dt_naive
        # Readable date: "Apr 12, 2026 at 3:45 PM"
        date_str = dt_naive.strftime("%b %d, %Y at %I:%M %p UTC")
        if diff.days > 0:
            time_str = f"{diff.days}d ago &middot; {date_str}"
        else:
            hours = int(diff.total_seconds() / 3600)
            relative = f"{hours}h ago" if hours > 0 else "just now"
            time_str = f"{relative} &middot; {date_str}"
    except (ValueError, TypeError):
        time_str = ""

    # Card CSS class
    card_class = "card-hot" if category == "HOT" else "card-warm"
    badge_class = "badge-hot" if category == "HOT" else "badge-warm"
    score_class = "score-hot" if category == "HOT" else "score-warm"

    # URL validation indicator
    url_indicator = ""
    if url and url in url_status:
        vs = url_status[url]
        if vs["valid"]:
            url_indicator = ' <span class="url-ok" title="Link verified">&#10003;</span>'
        else:
            url_indicator = f' <span class="url-bad" title="{escape(vs["reason"])}">&#10007;</span>'

    # ========================================================================
    # CONTACT STRATEGY per platform — critical for actually reaching the lead
    # ========================================================================
    # Direct-contact platforms: Reddit, HN, Bluesky, forums (comment/DM free)
    # Research-needed platforms: Indeed/LinkedIn jobs (apply-only, no employer DM)
    # ========================================================================
    link_html = ""
    contact_badge = ""
    contact_hint = ""

    # Contact info pulled in by core/enricher.py (may be empty strings)
    contact_email = (lead.get("contact_email") or "").strip()
    contact_phone = (lead.get("contact_phone") or "").strip()
    contact_website = (lead.get("contact_website") or "").strip()

    # ================================================================
    # CONTACT BUTTONS — ALWAYS in this order:
    #   1. ✉️  Email (pre-filled mailto: with pitch in body)
    #   2. 💬  LinkedIn DM / Facebook DM (messaging platforms)
    #   3. 🌐  Website (contact form)
    #   4. 📞  Phone (secondary — user prefers messaging)
    #   5. 📍  Maps (last resort — only useful to look up more info)
    #   6. Post link / job posting (reference, not a contact action)
    # ================================================================
    from urllib.parse import quote_plus
    company_name = lead.get("author") or ""
    q = quote_plus(company_name) if company_name else ""

    # Build ordered button list
    buttons = []

    # 1. Email — always the top action when we have one
    if contact_email:
        subj = quote_plus(f"Quick question — {company_name}" if company_name else "Quick question")
        body = quote_plus(_fallback_pitch(lead))
        mailto = f"mailto:{contact_email}?subject={subj}&body={body}"
        buttons.append(f'<a class="card-link card-link-primary" href="{mailto}">✉️ Email {escape(contact_email)}</a>')

    # 2. LinkedIn DM (for businesses — search by company name)
    if platform in ("jobs", "complaints", "craigslist") and q:
        li_url = f"https://www.linkedin.com/search/results/companies/?keywords={q}"
        buttons.append(f'<a class="card-link" href="{li_url}" target="_blank" rel="noopener">💬 LinkedIn</a>')

    # 3. Facebook DM (for businesses — search pages)
    if platform in ("jobs", "complaints", "craigslist") and q:
        fb_url = f"https://www.facebook.com/search/pages/?q={q}"
        buttons.append(f'<a class="card-link" href="{fb_url}" target="_blank" rel="noopener">💬 Facebook</a>')

    # 4. Website
    if contact_website:
        buttons.append(f'<a class="card-link" href="{escape(contact_website)}" target="_blank" rel="noopener">🌐 Website</a>')
    elif platform in ("jobs", "complaints") and q:
        google_url = f"https://www.google.com/search?q={quote_plus(company_name + ' contact email')}"
        buttons.append(f'<a class="card-link" href="{google_url}" target="_blank" rel="noopener">🔍 Find email</a>')

    # 5. Phone (shown but not primary — user prefers messaging)
    if contact_phone:
        tel_url = f"tel:{re.sub(r'[^0-9+]', '', contact_phone)}"
        buttons.append(f'<a class="card-link" href="{tel_url}">📞 {escape(contact_phone)}</a>')

    # 6. Maps (backup — useful to look up phone/address when enrichment is empty)
    if platform in ("jobs", "complaints", "craigslist") and q:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={q}"
        buttons.append(f'<a class="card-link" href="{maps_url}" target="_blank" rel="noopener">📍 Maps</a>')

    # 7. Post link (for social leads: the original post to reply to)
    if url and url != "N/A":
        if platform in ("jobs",):
            buttons.append(f'<a class="card-link" href="{escape(url)}" target="_blank" rel="noopener">📄 Job posting</a>{url_indicator}')
        elif platform in ("complaints",):
            buttons.append(f'<a class="card-link" href="{escape(url)}" target="_blank" rel="noopener">📄 Review</a>{url_indicator}')
        elif platform in ("craigslist",):
            buttons.append(f'<a class="card-link" href="{escape(url)}" target="_blank" rel="noopener">📄 CL post</a>{url_indicator}')
        elif platform in ("quora",):
            buttons.append(f'<a class="card-link" href="{escape(url)}" target="_blank" rel="noopener">📄 Quora thread</a>{url_indicator}')
        else:
            # Reddit, HN, Bluesky, forums — replying IS the contact method
            is_primary = not contact_email  # only make it green if no email available
            cls = "card-link card-link-primary" if is_primary else "card-link"
            buttons.append(f'<a class="{cls}" href="{escape(url)}" target="_blank" rel="noopener">💬 Reply on platform</a>{url_indicator}')

    # If no email was found, make the first button primary
    if buttons and not contact_email:
        buttons[0] = buttons[0].replace('class="card-link"', 'class="card-link card-link-primary"', 1)

    link_html = "".join(buttons)

    # Contact hint — simple, one-liner per platform type
    if platform in ("jobs", "complaints", "craigslist"):
        if contact_email:
            contact_hint = '<div class="contact-hint">✉️ Email found — click to send with the pitch pre-filled.</div>'
        else:
            contact_hint = '<div class="contact-hint">No email found yet. Try LinkedIn or Facebook DM, or click <em>Find email</em> to search.</div>'
    elif platform in ("reddit", "reddit_search"):
        contact_hint = '<div class="contact-hint">Reply publicly first (helpful, not salesy), then DM the author.</div>'
    elif platform == "hackernews":
        contact_hint = '<div class="contact-hint">Reply in the HN thread, or click the author\'s username — their profile often lists an email.</div>'
    elif platform == "bluesky":
        contact_hint = '<div class="contact-hint">Reply publicly on Bluesky. DMs only work if they follow you back.</div>'
    elif platform == "forum":
        contact_hint = '<div class="contact-hint">Reply in the forum thread or PM the user directly.</div>'
    elif platform == "quora":
        contact_hint = '<div class="contact-hint">Answer the Quora question — helpful answers rank on Google for years.</div>'
    else:
        contact_hint = ""

    # For job postings / complaints, show the business name prominently
    role_html = ""
    if platform == "jobs":
        company_line = author
        title_line = ""
        role_html = f'<div class="card-role">Role: {title}</div>'
    elif platform in ("complaints", "craigslist"):
        company_line = author if author and author != "Unknown" else title
        title_line = title if company_line != title else ""
    else:
        company_line = f"{community}"
        title_line = title

    # Suggested outreach — use Claude's if available, otherwise generate a
    # sensible fallback based on lead type. We need a real pitch on EVERY card
    # so the Copy button always has something to copy.
    pitch_text = lead.get("suggested_reply") or ""
    if not pitch_text:
        pitch_text = _fallback_pitch(lead)

    # The version we display (HTML-escaped) and the version we copy (raw text
    # held in a hidden textarea so navigator.clipboard.writeText gets the
    # original characters with newlines intact).
    pitch_display = escape(pitch_text).replace("\n", "<br>")
    lead_id = lead.get("id", 0)

    suggested_html = f"""
    <div class="suggested">
      <strong>Suggested outreach:</strong><br>
      {pitch_display}
      <div class="suggested-row">
        <button class="copy-btn" onclick="copyPitch({lead_id}, this)">📋 Copy pitch</button>
        <button class="mark-btn" onclick="toggleContacted({lead_id}, this)">✓ Mark contacted</button>
      </div>
      <textarea class="hidden-msg" id="msg-{lead_id}" readonly>{escape(pitch_text)}</textarea>
    </div>"""

    # Summary / reasoning
    body = lead.get("body", "")
    summary = ""
    if reasoning:
        summary = reasoning
    elif body:
        summary = escape(body[:200]) + ("..." if len(body) > 200 else "")

    # ================================================================
    # SOURCE LABEL — ONE clear, specific label per lead.
    # Show exactly where this lead was found so the user never has to
    # guess. Examples: "Indeed", "Reddit r/HVAC", "Yelp Review",
    # "Craigslist NYC", "Quora", "Hacker News".
    # ================================================================
    if platform == "jobs" and community:
        board = community.split(" (")[0].strip().title()
        source_label = board if board else "Job Board"
    elif platform in ("reddit", "reddit_search") and community:
        # community can be "HVAC" or "r/HVAC (search: virtual rec...)"
        sub = community.split(" (")[0].strip()
        if not sub.startswith("r/"):
            sub = f"r/{sub}"
        source_label = f"Reddit {sub}"
    elif platform == "forum" and community:
        source_label = community
    elif platform == "hackernews":
        source_label = "Hacker News"
    elif platform == "bluesky":
        source_label = "Bluesky"
    elif platform == "complaints" and community:
        # community is the review site name: yelp, bbb, trustpilot, etc.
        site_nice = {"yelp": "Yelp Review", "bbb": "BBB Complaint",
                     "trustpilot": "Trustpilot", "google_maps": "Google Maps"}
        source_label = site_nice.get(community, community.title())
    elif platform == "craigslist" and community:
        city = community.split("/")[0].title()
        source_label = f"Craigslist {city}"
    elif platform == "quora":
        source_label = "Quora"
    else:
        source_label = platform.replace("_", " ").title() if platform else "Unknown"

    score_pct = int(score * 100)

    return f"""
  <div class="card {card_class}" data-category="{category}" data-platform="{platform}" data-id="{lead_id}">
    <div class="card-top">
      <div>
        <div class="card-company">{company_line}</div>
        {role_html}
        <div class="card-title">{title_line}</div>
      </div>
      <div style="text-align:right;white-space:nowrap;">
        <span class="badge {badge_class}">{category}</span>
        <span class="badge badge-source">{source_label}</span>
      </div>
    </div>
    <div class="card-summary">{summary}</div>
    <div class="card-meta">
      <span>Score: {score:.0%} <span class="score-bar"><span class="score-fill {score_class}" style="width:{score_pct}%"></span></span></span>
      <span>🕐 {time_str}</span>
    </div>
    <div style="margin-top:10px;">{link_html}</div>
    {contact_hint}{suggested_html}
  </div>"""


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate lead dashboard HTML")
    parser.add_argument("--output", default="_site",
                        help="Output directory (default: _site)")
    parser.add_argument("--validate", action="store_true",
                        help="Validate that lead URLs are reachable")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    db = LeadDatabase(DATABASE_PATH)
    html = generate_html(db, validate=args.validate)

    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Dashboard written to {out_path}")


if __name__ == "__main__":
    main()
