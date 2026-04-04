"""
Streamlit Dashboard
===================
Live web dashboard for monitoring lead generation performance.
Deploy free on Streamlit Cloud - accessible from any browser/phone.

Run locally: streamlit run dashboard/app.py
Deploy: Push to GitHub, connect at share.streamlit.io
"""

import sys
import os

# Add parent directory to path so we can import config and core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from config import DATABASE_PATH
from core.database import LeadDatabase

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Lead Monitor - Advance AI Services",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# DATABASE CONNECTION
# =============================================================================
@st.cache_resource
def get_db():
    """Get database connection (cached across reruns)."""
    return LeadDatabase(DATABASE_PATH)


db = get_db()

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.title("🔍 Lead Monitor")
st.sidebar.markdown("**Advance AI Services**")
st.sidebar.markdown("---")

# Time range selector
time_range = st.sidebar.selectbox(
    "Time Range",
    options=[7, 14, 30, 60, 90],
    format_func=lambda x: f"Last {x} days",
    index=2,
)

# Category filter
category_filter = st.sidebar.selectbox(
    "Lead Category",
    options=["All", "HOT", "WARM", "COLD"],
    index=0,
)

# Platform filter
platform_filter = st.sidebar.selectbox(
    "Platform",
    options=["All", "reddit", "forum", "hackernews", "bluesky"],
    index=0,
)

# Refresh button
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_resource.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(
    "System runs every 30 mins via GitHub Actions. "
    "Dashboard auto-refreshes on page load."
)

# =============================================================================
# MAIN CONTENT
# =============================================================================

# ------ Overview Cards ------
st.title("📊 Lead Monitor Dashboard")

stats = db.get_stats_summary(days=time_range)
# Handle None values from empty database (SUM on empty set returns None)
for key in stats:
    if stats[key] is None:
        stats[key] = 0

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="🔥 HOT Leads",
        value=stats.get("today_hot", 0),
        delta=f"{stats.get('hot', 0)} total ({time_range}d)",
    )

with col2:
    st.metric(
        label="⚡ WARM Leads",
        value=stats.get("today_warm", 0),
        delta=f"{stats.get('warm', 0)} total ({time_range}d)",
    )

with col3:
    st.metric(
        label="❄️ COLD Filtered",
        value=stats.get("cold", 0),
    )

with col4:
    st.metric(
        label="✅ Replied",
        value=stats.get("replied", 0),
    )

with col5:
    st.metric(
        label="💰 Converted",
        value=stats.get("conversions", 0),
    )

# System status
last_scan = stats.get("last_scan", "Never")
if last_scan != "Never":
    st.success(f"✅ System running — Last scan: {last_scan}")
else:
    st.warning("⚠️ No scans recorded yet. System may not have run.")

st.markdown("---")

# ------ Tabs ------
tab_feed, tab_sources, tab_keywords, tab_funnel, tab_trends, tab_health = st.tabs([
    "📋 Lead Feed",
    "📡 Source Performance",
    "🔑 Keyword Performance",
    "📈 Conversion Funnel",
    "📊 Trends",
    "🏥 System Health",
])

# ------ TAB: Lead Feed ------
with tab_feed:
    st.subheader("Recent Leads")

    cat = category_filter if category_filter != "All" else None
    plat = platform_filter if platform_filter != "All" else None

    leads = db.get_leads(category=cat, platform=plat, days=time_range, limit=50)

    if not leads:
        st.info("No leads found for this filter. The system will populate this as it scans.")
    else:
        for lead in leads:
            category = lead.get("category", "COLD")
            icon = {"HOT": "🔥", "WARM": "⚡", "COLD": "❄️"}.get(category, "❓")
            score = lead.get("score", 0)

            with st.expander(
                f"{icon} [{category}] {lead.get('community', '')} — "
                f"Score: {score:.2f} — "
                f"{lead.get('title', lead.get('body', '')[:80])}",
                expanded=(category == "HOT"),
            ):
                col_a, col_b = st.columns([3, 1])

                with col_a:
                    if lead.get("title"):
                        st.markdown(f"**{lead['title']}**")
                    st.write(lead.get("body", "")[:500])
                    st.markdown(f"[View Post]({lead.get('url', '#')})")

                    if lead.get("suggested_reply"):
                        st.markdown("**Suggested Reply:**")
                        st.info(lead["suggested_reply"])

                    if lead.get("reasoning"):
                        st.caption(f"AI Reasoning: {lead['reasoning']}")

                with col_b:
                    st.markdown(f"**Platform:** {lead.get('platform', '')}")
                    st.markdown(f"**Author:** {lead.get('author', 'Unknown')}")
                    st.markdown(f"**Found:** {lead.get('discovered_at', '')[:16]}")
                    st.markdown(f"**Keyword:** {lead.get('keyword_matched', 'N/A')}")

                    lead_id = lead.get("id")
                    if lead_id:
                        # Action buttons
                        if not lead.get("replied"):
                            if st.button(f"✅ Mark Replied", key=f"reply_{lead_id}"):
                                db.mark_replied(lead_id)
                                st.rerun()
                        else:
                            st.success("Replied ✓")

                        if lead.get("replied") and not lead.get("response_received"):
                            if st.button(f"💬 Got Response", key=f"resp_{lead_id}"):
                                db.mark_response_received(lead_id)
                                st.rerun()
                        elif lead.get("response_received"):
                            st.success("Response received ✓")

                        if lead.get("response_received") and not lead.get("converted"):
                            if st.button(f"💰 Converted!", key=f"conv_{lead_id}"):
                                db.mark_converted(lead_id)
                                st.rerun()
                        elif lead.get("converted"):
                            st.success("🎉 Converted!")

# ------ TAB: Source Performance ------
with tab_sources:
    st.subheader("Lead Sources Performance")

    platform_stats = db.get_platform_stats(days=time_range)

    if platform_stats:
        df_sources = pd.DataFrame(platform_stats)
        df_sources = df_sources.sort_values("total", ascending=False)

        # Bar chart
        st.bar_chart(
            df_sources.set_index("community")[["hot", "warm", "total"]],
            color=["#ff4b4b", "#ffa500", "#4b8bff"],
        )

        # Table
        st.dataframe(
            df_sources[["platform", "community", "total", "hot", "warm"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No source data yet. Will populate after first scan.")

# ------ TAB: Keyword Performance ------
with tab_keywords:
    st.subheader("Top Keywords by Hits")

    keyword_stats = db.get_keyword_stats(days=time_range)

    if keyword_stats:
        df_kw = pd.DataFrame(keyword_stats)

        st.bar_chart(
            df_kw.set_index("keyword_matched")[["hits", "hot_hits"]],
            color=["#4b8bff", "#ff4b4b"],
        )

        st.dataframe(
            df_kw[["keyword_matched", "keyword_category", "hits", "hot_hits"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No keyword data yet. Will populate after first scan.")

# ------ TAB: Conversion Funnel ------
with tab_funnel:
    st.subheader("Conversion Funnel")

    funnel = db.get_conversion_funnel(days=time_range)
    # Handle None values from empty database
    if funnel:
        for key in funnel:
            if funnel[key] is None:
                funnel[key] = 0

    if funnel and funnel.get("total_leads", 0) > 0:
        total = funnel.get("total_leads", 0)
        qualified = funnel.get("qualified", 0)
        replied = funnel.get("replied", 0)
        responded = funnel.get("responded", 0)
        converted = funnel.get("converted", 0)

        # Funnel visualization
        funnel_data = pd.DataFrame({
            "Stage": ["Total Leads", "Qualified (HOT+WARM)", "Replied To", "Got Response", "Converted"],
            "Count": [total, qualified, replied, responded, converted],
        })

        st.bar_chart(funnel_data.set_index("Stage"))

        # Conversion rates
        col1, col2, col3 = st.columns(3)
        with col1:
            reply_rate = (replied / qualified * 100) if qualified > 0 else 0
            st.metric("Reply Rate", f"{reply_rate:.1f}%")
        with col2:
            response_rate = (responded / replied * 100) if replied > 0 else 0
            st.metric("Response Rate", f"{response_rate:.1f}%")
        with col3:
            conv_rate = (converted / total * 100) if total > 0 else 0
            st.metric("Overall Conversion", f"{conv_rate:.1f}%")
    else:
        st.info("No conversion data yet. Start replying to leads and mark their progress!")

# ------ TAB: Trends ------
with tab_trends:
    st.subheader(f"Daily Lead Trend (Last {time_range} Days)")

    trend_data = db.get_daily_trend(days=time_range)

    if trend_data:
        df_trend = pd.DataFrame(trend_data)
        df_trend["date"] = pd.to_datetime(df_trend["date"])

        st.line_chart(
            df_trend.set_index("date")[["hot", "warm", "cold"]],
            color=["#ff4b4b", "#ffa500", "#87ceeb"],
        )
    else:
        st.info("No trend data yet. Will populate over time.")

# ------ TAB: System Health ------
with tab_health:
    st.subheader("System Health (Last 24 Hours)")

    scan_logs = db.get_scan_health(hours=24)

    if scan_logs:
        total_scans = len(scan_logs)
        error_scans = sum(1 for s in scan_logs if s.get("errors"))
        total_posts = sum(s.get("posts_scanned", 0) for s in scan_logs)
        total_found = sum(s.get("leads_found", 0) for s in scan_logs)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Scans (24h)", total_scans)
        with col2:
            st.metric("Errors", error_scans)
        with col3:
            st.metric("Posts Scanned", total_posts)
        with col4:
            st.metric("Leads Found", total_found)

        # Scan log table
        df_logs = pd.DataFrame(scan_logs)
        st.dataframe(
            df_logs[["scan_time", "platform", "community", "posts_scanned",
                      "leads_found", "hot_leads", "errors", "duration_seconds"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No scan logs yet. System will populate this after first run.")
