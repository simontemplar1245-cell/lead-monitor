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

    # Sort: HOT first (by score desc), then WARM (by score desc)
    hot_warm.sort(key=lambda x: (
        0 if x.get("category") == "HOT" else 1,
        -float(x.get("score", 0))
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

    cards_html = "\n".join(lead_rows) if lead_rows else '<p class="empty">No leads found yet. The scanner runs every 30 minutes — check back soon.</p>'

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

<div class="filters">
  <button class="filter-btn active" onclick="filterLeads('all')">All</button>
  <button class="filter-btn" onclick="filterLeads('hot')">HOT Only</button>
  <button class="filter-btn" onclick="filterLeads('warm')">WARM Only</button>
  <button class="filter-btn" onclick="filterLeads('direct')">Direct Contact</button>
  <button class="filter-btn" onclick="filterLeads('research')">Research Needed</button>
  <button class="filter-btn" onclick="filterLeads('jobs')">Indeed/LinkedIn</button>
  <button class="filter-btn" onclick="filterLeads('reddit')">Reddit</button>
</div>

<div class="container" id="leads">
{cards_html}
</div>

<div class="footer">
  Advance AI Services Lead Monitor &middot; Auto-updates every 30 minutes<br>
  <strong style="color:#86efac;">Direct contact (reply/DM on platform):</strong> Reddit (80+ subreddits), Hacker News, Bluesky, 8 industry forums<br>
  <strong style="color:#fcd34d;">Research needed (apply-only, cold-call the business):</strong> Indeed, LinkedIn Jobs
</div>

<script>
function filterLeads(type) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.card').forEach(card => {{
    const p = card.dataset.platform;
    if (type === 'all') {{
      card.style.display = '';
    }} else if (type === 'hot') {{
      card.style.display = card.dataset.category === 'HOT' ? '' : 'none';
    }} else if (type === 'warm') {{
      card.style.display = card.dataset.category === 'WARM' ? '' : 'none';
    }} else if (type === 'direct') {{
      // Direct-contact platforms: Reddit, HN, Bluesky, forums
      const isDirect = (p === 'reddit' || p === 'reddit_search' ||
                        p === 'hackernews' || p === 'bluesky' || p === 'forum');
      card.style.display = isDirect ? '' : 'none';
    }} else if (type === 'research') {{
      // Research-needed: job postings
      card.style.display = p === 'jobs' ? '' : 'none';
    }} else if (type === 'jobs') {{
      card.style.display = p === 'jobs' ? '' : 'none';
    }} else if (type === 'reddit') {{
      card.style.display = (p === 'reddit' || p === 'reddit_search') ? '' : 'none';
    }} else {{
      card.style.display = p === type ? '' : 'none';
    }}
  }});
}}
</script>

</body>
</html>"""
    return html


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

    # Time ago
    time_str = ""
    try:
        dt = datetime.fromisoformat(str(discovered).replace("Z", "+00:00"))
        diff = datetime.utcnow() - dt.replace(tzinfo=None)
        if diff.days > 0:
            time_str = f"{diff.days}d ago"
        else:
            hours = int(diff.total_seconds() / 3600)
            time_str = f"{hours}h ago" if hours > 0 else "just now"
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

    if platform == "jobs":
        # Jobs are apply-only on Indeed/LinkedIn. You cannot message the employer
        # through the job board itself. But the business almost always has a
        # Google Business listing, LinkedIn page, and/or Facebook page — and
        # those DO allow direct contact. Generate links to all of them.
        contact_badge = '<span class="badge badge-research" title="Use Maps / LinkedIn / Facebook to reach the business directly">RESEARCH</span>'

        from urllib.parse import quote_plus
        company_name = lead.get("author") or ""
        q = quote_plus(company_name)

        # Google Maps: gets the phone number immediately for local businesses.
        # This is the fastest path to an actual conversation.
        maps_url = f"https://www.google.com/maps/search/?api=1&query={q}"
        # LinkedIn company search: find the owner/HR and send a connection
        # request with a note (free, no Premium needed).
        linkedin_url = f"https://www.linkedin.com/search/results/companies/?keywords={q}"
        # Facebook Pages search: small businesses often read Page DMs daily.
        facebook_url = f"https://www.facebook.com/search/pages/?q={q}"
        # Regular Google (fallback for website/email discovery)
        google_url = f"https://www.google.com/search?q={quote_plus(company_name + ' contact')}"

        primary_link = f'<a class="card-link card-link-primary" href="{maps_url}" target="_blank" rel="noopener">📞 Call via Google Maps</a>'
        linkedin_link = f'<a class="card-link" href="{linkedin_url}" target="_blank" rel="noopener">LinkedIn</a>'
        facebook_link = f'<a class="card-link" href="{facebook_url}" target="_blank" rel="noopener">Facebook</a>'
        google_link = f'<a class="card-link" href="{google_url}" target="_blank" rel="noopener">Website</a>'

        secondary_link = ""
        if url and url != "N/A":
            secondary_link = f'<a class="card-link" href="{escape(url)}" target="_blank" rel="noopener">Job posting</a>{url_indicator}'

        link_html = primary_link + linkedin_link + facebook_link + google_link + secondary_link

        contact_hint = (
            '<div class="contact-hint">'
            '<strong>How to contact:</strong> Indeed and LinkedIn job postings are '
            '<em>apply-only</em> — you cannot message the employer through the job board. '
            'But you can reach the business directly through other channels:<br>'
            '&nbsp;&nbsp;• <strong>Google Maps</strong> — fastest; local businesses list their phone number, tap to call<br>'
            '&nbsp;&nbsp;• <strong>LinkedIn</strong> — find the owner/HR, send a connection request with a short note (free, no Premium)<br>'
            '&nbsp;&nbsp;• <strong>Facebook</strong> — small businesses often read Page DMs daily<br>'
            '&nbsp;&nbsp;• <strong>Website</strong> — fallback; look for a contact form or email'
            '</div>'
        )
    else:
        # Direct-contact platforms: Reddit, HN, Bluesky, forums
        contact_badge = '<span class="badge badge-direct" title="You can reply or DM directly on this platform">DIRECT</span>'

        if url and url != "N/A":
            link_html = f'<a class="card-link card-link-primary" href="{escape(url)}" target="_blank" rel="noopener">Open post & reply &rarr;</a>{url_indicator}'

        if platform in ("reddit", "reddit_search"):
            contact_hint = (
                '<div class="contact-hint">'
                '<strong>How to contact:</strong> Click the link to open the Reddit post, '
                'then reply publicly (helpful first, pitch last) or DM the author directly. '
                'Check their post history first — long-time users spot spam instantly.'
                '</div>'
            )
        elif platform == "hackernews":
            contact_hint = (
                '<div class="contact-hint">'
                '<strong>How to contact:</strong> Reply in the HN thread, or click the author\'s '
                'username on HN — their profile often lists an email address.'
                '</div>'
            )
        elif platform == "bluesky":
            contact_hint = (
                '<div class="contact-hint">'
                '<strong>How to contact:</strong> Reply publicly on Bluesky. '
                'DMs only work if they follow you back.'
                '</div>'
            )
        elif platform == "forum":
            contact_hint = (
                '<div class="contact-hint">'
                '<strong>How to contact:</strong> Reply in the forum thread, '
                'or create a free account and PM the user directly.'
                '</div>'
            )

    # For job postings, show company + role clearly
    role_html = ""
    if platform == "jobs":
        company_line = author
        title_line = ""
        role_html = f'<div class="card-role">Role: {title}</div>'
    else:
        company_line = f"{community}"
        title_line = title

    # Suggested reply
    suggested_html = ""
    if suggested:
        suggested_html = f"""
    <div class="suggested">
      <strong>Suggested outreach:</strong>
      {suggested}
    </div>"""

    # Summary / reasoning
    body = lead.get("body", "")
    summary = ""
    if reasoning:
        summary = reasoning
    elif body:
        summary = escape(body[:200]) + ("..." if len(body) > 200 else "")

    # Source label — show the ACTUAL board (Indeed vs LinkedIn vs r/sub etc.)
    source_map = {
        "jobs": "Job Board",
        "reddit": "Reddit",
        "reddit_search": "Reddit",
        "hackernews": "Hacker News",
        "bluesky": "Bluesky",
        "forum": "Forum",
    }
    source_label = source_map.get(platform, platform)
    if platform == "jobs" and community:
        # community is stored like "indeed (United States)" — extract the board name
        board = community.split(" (")[0].strip().title()
        if board:
            source_label = board
    elif platform in ("reddit", "reddit_search") and community:
        source_label = f"r/{community}"
    elif platform == "forum" and community:
        source_label = community

    score_pct = int(score * 100)

    return f"""
  <div class="card {card_class}" data-category="{category}" data-platform="{platform}">
    <div class="card-top">
      <div>
        <div class="card-company">{company_line}</div>
        {role_html}
        <div class="card-title">{title_line}</div>
      </div>
      <div style="text-align:right;white-space:nowrap;">
        <span class="badge {badge_class}">{category}</span>
        <span class="badge badge-source">{source_label}</span>
        {contact_badge}
      </div>
    </div>
    <div class="card-summary">{summary}</div>
    <div class="card-meta">
      <span>Score: {score:.0%} <span class="score-bar"><span class="score-fill {score_class}" style="width:{score_pct}%"></span></span></span>
      <span>{time_str}</span>
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
