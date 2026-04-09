#!/usr/bin/env python3
"""
Lead CRM — Free Outreach Tracker
==================================
Track every message you send, follow-ups needed, and your conversion pipeline.
Runs 100% locally on your Mac — no accounts, no subscriptions.

Usage:
  python crm.py                        Show pipeline dashboard
  python crm.py leads                  List all HOT/WARM leads
  python crm.py leads --new            Only uncontacted leads
  python crm.py leads --contacted      Only contacted leads
  python crm.py view 5                 View lead #5 with full details + outreach history
  python crm.py contact 5              Log outreach to lead #5 (interactive)
  python crm.py reply 5                Log that lead #5 replied back
  python crm.py convert 5              Mark lead #5 as converted (paying client)
  python crm.py note 5 "talked to mgr" Add a note to lead #5
  python crm.py followup               Show leads needing follow-up (3+ days, no reply)
  python crm.py stats                  Outreach stats and conversion funnel
"""

import sys
import os
import argparse
import textwrap
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATABASE_PATH
from core.database import LeadDatabase


# =========================================================================
# FORMATTING HELPERS
# =========================================================================

def _bold(text):
    return f"\033[1m{text}\033[0m"

def _red(text):
    return f"\033[91m{text}\033[0m"

def _yellow(text):
    return f"\033[93m{text}\033[0m"

def _green(text):
    return f"\033[92m{text}\033[0m"

def _cyan(text):
    return f"\033[96m{text}\033[0m"

def _dim(text):
    return f"\033[2m{text}\033[0m"

def _category_color(category):
    if category == "HOT":
        return _red(category)
    elif category == "WARM":
        return _yellow(category)
    return _dim(category)

def _status_label(lead):
    if lead.get("converted"):
        return _green("CONVERTED")
    if lead.get("response_received"):
        return _cyan("IN CONVERSATION")
    if lead.get("replied"):
        return _yellow("CONTACTED")
    return _dim("NEW")

def _time_ago(iso_str):
    if not iso_str:
        return "never"
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        diff = datetime.utcnow() - dt.replace(tzinfo=None)
        days = diff.days
        hours = int(diff.total_seconds() / 3600)
        if days > 0:
            return f"{days}d ago"
        if hours > 0:
            return f"{hours}h ago"
        return "just now"
    except (ValueError, TypeError):
        return "?"

def _bar(count, total, width=20):
    if total == 0:
        return " " * width
    filled = int(width * count / total)
    return "=" * filled + "-" * (width - filled)


# =========================================================================
# COMMANDS
# =========================================================================

def cmd_dashboard(db):
    """Show the pipeline dashboard."""
    pipeline = db.get_pipeline_counts()
    total = pipeline.get("total", 0) or 0
    new = pipeline.get("new_leads", 0) or 0
    contacted = pipeline.get("contacted", 0) or 0
    talking = pipeline.get("in_conversation", 0) or 0
    converted = pipeline.get("converted", 0) or 0

    print()
    print(_bold("  ADVANCE AI SERVICES — LEAD PIPELINE"))
    print(_bold("  " + "=" * 45))
    print()
    print(f"  {_dim('NEW LEADS')}        [{_bar(new, total)}] {new}")
    print(f"  {_yellow('CONTACTED')}       [{_bar(contacted, total)}] {contacted}")
    print(f"  {_cyan('IN CONVERSATION')} [{_bar(talking, total)}] {talking}")
    print(f"  {_green('CONVERTED')}       [{_bar(converted, total)}] {converted}")
    print()
    print(f"  Total qualified leads: {total}")
    print()

    # Show leads needing follow-up
    followups = db.get_leads_needing_followup(days_since_contact=3)
    if followups:
        print(_bold(f"  NEEDS FOLLOW-UP ({len(followups)}):"))
        for lead in followups[:5]:
            company = lead.get("author") or "Unknown"
            title = lead.get("title", "")[:40]
            last = _time_ago(lead.get("last_contacted"))
            msgs = lead.get("messages_sent", 0)
            print(f"    #{lead['id']:>4}  {company[:25]:<25} {title:<40} {msgs} msgs, last {last}")
        if len(followups) > 5:
            print(f"    ... and {len(followups) - 5} more (run: python crm.py followup)")
        print()

    # Quick stats
    stats = db.get_stats_summary(days=7)
    print(_dim(f"  Last 7 days: {stats.get('total', 0)} leads found, "
               f"{stats.get('hot', 0)} HOT, {stats.get('warm', 0)} WARM"))
    print(_dim(f"  Last scan: {stats.get('last_scan', 'never')}"))
    print()


def cmd_leads(db, filter_type=None, platform=None):
    """List leads."""
    if filter_type == "new":
        leads = db.get_leads(days=30, limit=200)
        leads = [l for l in leads if l.get("category") in ("HOT", "WARM") and not l.get("replied")]
        label = "NEW (uncontacted)"
    elif filter_type == "contacted":
        leads = db.get_leads(days=30, limit=200)
        leads = [l for l in leads if l.get("replied") and not l.get("converted")]
        label = "CONTACTED"
    elif filter_type == "converted":
        leads = db.get_leads(days=90, limit=200)
        leads = [l for l in leads if l.get("converted")]
        label = "CONVERTED"
    else:
        leads = db.get_leads(days=30, limit=100)
        leads = [l for l in leads if l.get("category") in ("HOT", "WARM")]
        label = "ALL HOT/WARM"

    if platform:
        leads = [l for l in leads if l.get("platform", "").lower() == platform.lower()]

    if not leads:
        print(f"\n  No {label.lower()} leads found.\n")
        return

    print()
    print(_bold(f"  {label} LEADS ({len(leads)})"))
    print(f"  {'ID':>4}  {'Cat':>4}  {'Status':<17}  {'Source':<12}  {'Company/Author':<25}  {'Title':<40}  {'Found':<8}")
    print(f"  {'—'*4}  {'—'*4}  {'—'*17}  {'—'*12}  {'—'*25}  {'—'*40}  {'—'*8}")

    for lead in leads:
        lid = lead["id"]
        cat = _category_color(lead.get("category", ""))
        status = _status_label(lead)
        source = lead.get("platform", "")[:12]
        company = (lead.get("author") or "?")[:25]
        title = (lead.get("title") or "")[:40]
        found = _time_ago(lead.get("discovered_at"))

        print(f"  {lid:>4}  {cat:>13}  {status:<26}  {source:<12}  {company:<25}  {title:<40}  {found:<8}")

    print()
    print(_dim("  View details: python crm.py view <ID>"))
    print(_dim("  Log outreach: python crm.py contact <ID>"))
    print()


def cmd_view(db, lead_id):
    """View full details of a lead + outreach history."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        print(f"\n  Lead #{lead_id} not found.\n")
        return

    print()
    print(_bold(f"  LEAD #{lead['id']}"))
    print(f"  {'=' * 50}")
    print(f"  Category:    {_category_color(lead.get('category', ''))}")
    print(f"  Score:       {lead.get('score', 0):.2f}")
    print(f"  Status:      {_status_label(lead)}")
    print(f"  Platform:    {lead.get('platform', '')}")
    print(f"  Community:   {lead.get('community', '')}")
    print(f"  Company:     {lead.get('author', 'Unknown')}")
    print(f"  Title:       {lead.get('title', '')}")
    print(f"  URL:         {lead.get('url', 'N/A')}")
    print(f"  Found:       {lead.get('discovered_at', '')}")

    if lead.get("notes"):
        print(f"  Notes:       {lead['notes']}")

    # Post body
    body = lead.get("body", "")
    if body:
        print()
        print(_bold("  POST CONTENT:"))
        wrapped = textwrap.fill(body[:500], width=70, initial_indent="    ", subsequent_indent="    ")
        print(wrapped)
        if len(body) > 500:
            print(_dim(f"    ... ({len(body)} chars total)"))

    # Reasoning
    reasoning = lead.get("reasoning", "")
    if reasoning:
        print()
        print(_bold("  WHY THIS IS A LEAD:"))
        print(f"    {reasoning}")

    # Suggested reply
    suggested = lead.get("suggested_reply", "")
    if suggested:
        print()
        print(_bold("  SUGGESTED REPLY:"))
        wrapped = textwrap.fill(suggested, width=70, initial_indent="    ", subsequent_indent="    ")
        print(wrapped)

    # Outreach history
    history = db.get_outreach_history(lead_id)
    if history:
        print()
        print(_bold(f"  OUTREACH HISTORY ({len(history)} messages):"))
        for msg in history:
            seq = msg.get("sequence_number", "?")
            channel = msg.get("channel", "?")
            sent = msg.get("sent_at", "?")
            status = msg.get("status", "sent")
            replied = "REPLIED" if msg.get("reply_received") else ""

            print(f"    #{seq}  {channel:<15}  {sent}  {status}  {_green(replied) if replied else ''}")

            if msg.get("subject"):
                print(f"         Subject: {msg['subject']}")
            if msg.get("message_text"):
                preview = msg["message_text"][:120].replace("\n", " ")
                print(f"         {_dim(preview)}")
            if msg.get("reply_text"):
                print(f"         {_cyan('Reply: ' + msg['reply_text'][:120])}")
            if msg.get("notes"):
                print(f"         Note: {msg['notes']}")
    else:
        print()
        print(_dim("  No outreach yet. Run: python crm.py contact " + str(lead_id)))

    print()


def cmd_contact(db, lead_id):
    """Log outreach to a lead (interactive)."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        print(f"\n  Lead #{lead_id} not found.\n")
        return

    company = lead.get("author") or "Unknown"
    title = lead.get("title", "")[:50]
    print()
    print(_bold(f"  LOG OUTREACH — Lead #{lead_id}: {company}"))
    print(f"  {title}")
    print()

    # Channel
    print("  Channel:")
    print("    1. Email")
    print("    2. Reddit DM")
    print("    3. Reddit comment")
    print("    4. LinkedIn")
    print("    5. Phone call")
    print("    6. Other")

    try:
        choice = input("\n  Pick channel (1-6): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.\n")
        return

    channels = {"1": "email", "2": "reddit_dm", "3": "reddit_comment",
                "4": "linkedin", "5": "phone", "6": "other"}
    channel = channels.get(choice, "other")

    # Subject (for email)
    subject = ""
    if channel == "email":
        try:
            subject = input("  Subject line: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.\n")
            return

    # Message
    try:
        print("  Message sent (paste it, then press Enter on empty line):")
        lines = []
        while True:
            line = input("  ")
            if line == "":
                break
            lines.append(line)
        message = "\n".join(lines)
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.\n")
        return

    # Notes
    try:
        notes = input("  Notes (optional): ").strip()
    except (EOFError, KeyboardInterrupt):
        notes = ""

    outreach_id = db.log_outreach(
        lead_id=lead_id,
        channel=channel,
        message_text=message,
        subject=subject,
        notes=notes,
    )

    print()
    print(_green(f"  Outreach logged (#{outreach_id}) — {channel} to {company}"))
    print(_dim(f"  Lead #{lead_id} marked as CONTACTED"))
    print()


def cmd_reply(db, lead_id):
    """Log that a lead replied."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        print(f"\n  Lead #{lead_id} not found.\n")
        return

    company = lead.get("author") or "Unknown"

    try:
        reply_text = input(f"  What did {company} say? (brief summary): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.\n")
        return

    db.log_reply_received(lead_id, reply_text)

    print()
    print(_green(f"  Reply logged for lead #{lead_id} ({company})"))
    print(_dim("  Lead moved to IN CONVERSATION stage"))
    print()


def cmd_convert(db, lead_id):
    """Mark a lead as converted."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        print(f"\n  Lead #{lead_id} not found.\n")
        return

    company = lead.get("author") or "Unknown"
    db.mark_converted(lead_id)

    print()
    print(_green(f"  Lead #{lead_id} ({company}) marked as CONVERTED!"))
    print()


def cmd_note(db, lead_id, note_text):
    """Add a note to a lead."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        print(f"\n  Lead #{lead_id} not found.\n")
        return

    # Append to existing notes
    existing = lead.get("notes") or ""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    new_note = f"[{timestamp}] {note_text}"
    combined = f"{existing}\n{new_note}".strip() if existing else new_note

    db.add_note(lead_id, combined)
    print(f"\n  Note added to lead #{lead_id}.\n")


def cmd_followup(db):
    """Show leads that need follow-up."""
    leads = db.get_leads_needing_followup(days_since_contact=3)

    if not leads:
        print("\n  No leads need follow-up right now.\n")
        return

    print()
    print(_bold(f"  FOLLOW-UP NEEDED ({len(leads)} leads)"))
    print(f"  These leads were contacted 3+ days ago with no reply.\n")
    print(f"  {'ID':>4}  {'Company':<25}  {'Title':<35}  {'Msgs':>4}  {'Last Contact':<12}")
    print(f"  {'—'*4}  {'—'*25}  {'—'*35}  {'—'*4}  {'—'*12}")

    for lead in leads:
        lid = lead["id"]
        company = (lead.get("author") or "?")[:25]
        title = (lead.get("title") or "")[:35]
        msgs = lead.get("messages_sent", 0)
        last = _time_ago(lead.get("last_contacted"))

        print(f"  {lid:>4}  {company:<25}  {title:<35}  {msgs:>4}  {last:<12}")

    print()
    print(_dim("  Send follow-up: python crm.py contact <ID>"))
    print()


def cmd_stats(db):
    """Show outreach statistics."""
    pipeline = db.get_pipeline_counts()
    outreach = db.get_outreach_stats()

    total_leads = pipeline.get("total", 0) or 0
    contacted = (pipeline.get("contacted", 0) or 0) + (pipeline.get("in_conversation", 0) or 0) + (pipeline.get("converted", 0) or 0)
    replied = (pipeline.get("in_conversation", 0) or 0) + (pipeline.get("converted", 0) or 0)
    converted = pipeline.get("converted", 0) or 0

    print()
    print(_bold("  OUTREACH STATISTICS"))
    print(f"  {'=' * 45}")
    print()

    # Funnel
    print(_bold("  CONVERSION FUNNEL:"))
    print(f"    Qualified leads found:  {total_leads}")
    print(f"    Contacted:              {contacted}  ({_pct(contacted, total_leads)})")
    print(f"    Got a reply:            {replied}  ({_pct(replied, contacted)})")
    print(f"    Converted to client:    {converted}  ({_pct(converted, replied)})")
    print()

    # Messages
    total_msgs = outreach.get("total_messages", 0) or 0
    leads_contacted = outreach.get("leads_contacted", 0) or 0
    replies_rcvd = outreach.get("replies_received", 0) or 0

    print(_bold("  MESSAGE STATS:"))
    print(f"    Total messages sent:    {total_msgs}")
    print(f"    Unique leads contacted: {leads_contacted}")
    print(f"    Replies received:       {replies_rcvd}  ({_pct(replies_rcvd, total_msgs)})")
    print()

    # Per channel
    by_channel = outreach.get("by_channel", [])
    if by_channel:
        print(_bold("  BY CHANNEL:"))
        for ch in by_channel:
            name = ch.get("channel", "?")
            msgs = ch.get("messages", 0)
            reps = ch.get("replies", 0)
            print(f"    {name:<20}  {msgs} sent, {reps} replies ({_pct(reps, msgs)})")
        print()


def _pct(part, whole):
    if not whole:
        return "0%"
    return f"{part / whole * 100:.0f}%"


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Lead CRM — Free Outreach Tracker for Advance AI Services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python crm.py                  Pipeline dashboard
              python crm.py leads --new      Uncontacted leads
              python crm.py view 5           Full details for lead #5
              python crm.py contact 5        Log that you messaged lead #5
              python crm.py reply 5          Log that lead #5 replied
              python crm.py convert 5        Mark as paying client
              python crm.py followup         Leads needing follow-up
              python crm.py stats            Conversion funnel
        """),
    )
    sub = parser.add_subparsers(dest="command")

    # leads
    p_leads = sub.add_parser("leads", help="List leads")
    p_leads.add_argument("--new", action="store_true", help="Only uncontacted")
    p_leads.add_argument("--contacted", action="store_true", help="Only contacted")
    p_leads.add_argument("--converted", action="store_true", help="Only converted")
    p_leads.add_argument("--platform", help="Filter by platform (reddit, jobs, etc.)")

    # view
    p_view = sub.add_parser("view", help="View lead details")
    p_view.add_argument("id", type=int, help="Lead ID")

    # contact
    p_contact = sub.add_parser("contact", help="Log outreach to a lead")
    p_contact.add_argument("id", type=int, help="Lead ID")

    # reply
    p_reply = sub.add_parser("reply", help="Log that a lead replied")
    p_reply.add_argument("id", type=int, help="Lead ID")

    # convert
    p_convert = sub.add_parser("convert", help="Mark lead as converted")
    p_convert.add_argument("id", type=int, help="Lead ID")

    # note
    p_note = sub.add_parser("note", help="Add a note to a lead")
    p_note.add_argument("id", type=int, help="Lead ID")
    p_note.add_argument("text", help="Note text")

    # followup
    sub.add_parser("followup", help="Show leads needing follow-up")

    # stats
    sub.add_parser("stats", help="Outreach stats and conversion funnel")

    args = parser.parse_args()

    # Initialize DB (will create outreach table if missing)
    db = LeadDatabase(DATABASE_PATH)

    if args.command is None:
        cmd_dashboard(db)
    elif args.command == "leads":
        filter_type = None
        if args.new:
            filter_type = "new"
        elif args.contacted:
            filter_type = "contacted"
        elif args.converted:
            filter_type = "converted"
        cmd_leads(db, filter_type=filter_type, platform=args.platform)
    elif args.command == "view":
        cmd_view(db, args.id)
    elif args.command == "contact":
        cmd_contact(db, args.id)
    elif args.command == "reply":
        cmd_reply(db, args.id)
    elif args.command == "convert":
        cmd_convert(db, args.id)
    elif args.command == "note":
        cmd_note(db, args.id, args.text)
    elif args.command == "followup":
        cmd_followup(db)
    elif args.command == "stats":
        cmd_stats(db)


if __name__ == "__main__":
    main()
