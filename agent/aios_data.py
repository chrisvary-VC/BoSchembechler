"""The only file that touches data.

Demo mode reads seed/*.json. Live mode queries the real workspace and falls
back to the same seed whenever a query fails or comes back empty, so a panel is
never blank on camera.

To wire live data, fill in the _live_* functions. Each one must return the same
shape as its seed file, or return None to fall back.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional

from services import dropbox_client, google_credentials, google_service

logger = logging.getLogger("aios.data")

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

# Short name -> real filename. The brief lives in daily_brief.json, not
# brief.json; if you rename a seed file, update this map.
SEED_FILES = {
    "brief": "daily_brief.json",
    "metrics": "metrics.json",
    "pipeline": "pipeline.json",
    "intel": "intel.json",
    "actions": "actions.json",
}


def demo_mode() -> bool:
    return os.getenv("AIOS_DEMO_MODE", "1").strip() != "0"


def load_seed(name: str) -> dict:
    filename = SEED_FILES.get(name)
    if filename is None:
        raise KeyError(f"no seed mapped for {name!r}; known: {sorted(SEED_FILES)}")
    path = SEED_DIR / filename
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _resolve(name: str, live: Callable[[], Optional[dict]]) -> dict:
    """Use seed data only in demo mode; never leak demo names into live mode."""
    if demo_mode():
        return load_seed(name)
    try:
        data = live()
        if data:
            return data
        logger.warning("live %s was empty", name)
    except Exception:
        logger.exception("live %s failed", name)
    empty = {
        "brief": {"title": "Daily Brief", "summary": "Connect your services to build today's brief.", "signals": [], "sections": []},
        "metrics": {"default": "active_users", "series": {}},
        "pipeline": {"title": "Pipeline", "stages": [], "deals": []},
        "intel": {"items": []},
        "actions": {"title": "Today · ranked", "items": []},
    }
    return empty[name]


# --------------------------------------------------------------------------
# Live sources. Stubs on purpose — return None until you wire your workspace.
# --------------------------------------------------------------------------

def _live_brief() -> Optional[dict]:
    now = datetime.now(timezone.utc)
    calendar = google_service("calendar", "v3")
    events = calendar.events().list(
        calendarId="primary", timeMin=now.isoformat(),
        timeMax=(now + timedelta(days=1)).isoformat(), singleEvents=True,
        orderBy="startTime", maxResults=10,
    ).execute().get("items", [])
    gmail = google_service("gmail", "v1")
    unread_result = gmail.users().messages().list(
        userId="me", q="is:unread newer_than:7d", maxResults=10
    ).execute()
    unread = unread_result.get("messages", [])
    important_result = gmail.users().messages().list(
        userId="me", q="is:important newer_than:7d", maxResults=10
    ).execute()
    important = important_result.get("messages", [])
    unread_count = unread_result.get("resultSizeEstimate", len(unread))
    important_count = important_result.get("resultSizeEstimate", len(important))
    event_lines = []
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
        event_lines.append(f"{_friendly_time(start)} — {event.get('summary', 'Untitled event')}")
    mail_lines = [_gmail_summary(gmail, m["id"]) for m in important[:5]]
    signals = [
        {"label": "Calendar", "value": f"{len(events)} today", "delta": "next 24 hours"},
        {"label": "Unread email", "value": str(unread_count), "delta": "last 7 days", "alert": unread_count > 10},
        {"label": "Important", "value": str(important_count), "delta": "last 7 days", "alert": important_count > 0},
    ]
    sections = []
    if event_lines:
        sections.append({"heading": "Calendar", "lines": event_lines})
    if mail_lines:
        sections.append({"heading": "Important email", "lines": mail_lines})
    return {
        "title": f"Daily Brief · {datetime.now().strftime('%A')}",
        "spoken": f"Your brief is ready. You have {len(events)} calendar items and {important_count} important emails in the last week.",
        "summary": f"{len(events)} calendar items today, {unread_count} unread messages, and {important_count} important messages this week.",
        "signals": signals,
        "sections": sections,
    }


def _live_metrics(metric: str, days: int) -> Optional[dict]:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest

    raw_ids = os.getenv("GA4_PROPERTY_IDS") or os.getenv("GA4_PROPERTY_ID", "")
    property_ids = [p.strip().removeprefix("properties/") for p in raw_ids.split(",") if p.strip()]
    if not property_ids:
        raise RuntimeError("Set GA4_PROPERTY_IDS in .env")
    aliases = {
        "users": "activeUsers", "active_users": "activeUsers",
        "sessions": "sessions", "views": "screenPageViews",
        "pageviews": "screenPageViews", "engagement": "engagementRate",
    }
    api_metric = aliases.get(metric.lower(), "activeUsers")
    client = BetaAnalyticsDataClient(credentials=google_credentials())
    totals = {}
    for property_id in property_ids:
        response = client.run_report(RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=f"{days - 1}daysAgo", end_date="today")],
            dimensions=[{"name": "date"}], metrics=[Metric(name=api_metric)],
            order_bys=[{"dimension": {"dimension_name": "date"}}],
        ))
        for row in response.rows:
            date = datetime.strptime(row.dimension_values[0].value, "%Y%m%d").strftime("%Y-%m-%d")
            totals[date] = totals.get(date, 0.0) + float(row.metric_values[0].value)
    points = [{"date": date, "value": value} for date, value in sorted(totals.items())]
    labels = {"activeUsers": "Active users", "sessions": "Sessions", "screenPageViews": "Page views", "engagementRate": "Engagement rate"}
    units = {"engagementRate": "%"}
    key = metric.lower()
    summary = f"Live Google Analytics 4 data across {len(property_ids)} website properties."
    return {"default": key, "series": {key: {"label": labels[api_metric], "unit": units.get(api_metric, ""), "summary": summary, "points": points}}}


def _live_pipeline() -> Optional[dict]:
    return {"title": "Pipeline · connect a CRM", "stages": [], "deals": []}


def _live_intel(query: str) -> Optional[dict]:
    items = []
    gmail = google_service("gmail", "v1")
    for hit in gmail.users().messages().list(userId="me", q=query, maxResults=6).execute().get("messages", []):
        msg = gmail.users().messages().get(userId="me", id=hit["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = _headers(msg)
        items.append({"when": _email_when(headers.get("date", "")), "source": f"Email · {headers.get('subject', 'No subject')}", "who": headers.get("from", "Unknown"), "quote": msg.get("snippet", ""), "tags": [query.lower()]})
    drive = google_service("drive", "v3")
    safe = query.replace("'", "\\'")
    files = drive.files().list(q=f"fullText contains '{safe}' and trashed = false", pageSize=6, fields="files(name,mimeType,modifiedTime,webViewLink)").execute().get("files", [])
    for f in files:
        items.append({"when": _friendly_time(f.get("modifiedTime", "")), "source": "Google Drive", "who": "Drive", "quote": f.get("name", "Untitled file"), "tags": [query.lower()]})
    try:
        dbx = dropbox_client()
        for match in dbx.files_search_v2(query, max_results=6).matches:
            meta = match.metadata.get_metadata()
            items.append({"when": "Dropbox", "source": "Dropbox", "who": "Dropbox", "quote": getattr(meta, "name", str(meta)), "tags": [query.lower()]})
    except Exception:
        logger.info("Dropbox search unavailable", exc_info=True)
    return {"items": items}


def get_recent_emails(hours: int = 3, unread_only: bool = False, topic: str = "") -> dict:
    """Return inbox messages received inside an exact rolling time window."""
    hours = max(1, min(int(hours), 168))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query_parts = ["in:inbox", f"after:{int(cutoff.timestamp())}"]
    if unread_only:
        query_parts.append("is:unread")
    if topic.strip():
        query_parts.append(topic.strip())

    gmail = google_service("gmail", "v1")
    hits = gmail.users().messages().list(
        userId="me", q=" ".join(query_parts), maxResults=50
    ).execute().get("messages", [])
    emails = []
    for hit in hits:
        msg = gmail.users().messages().get(
            userId="me", id=hit["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        # Enforce the cutoff ourselves; Gmail's search result is not trusted as
        # the final authority for a relative-time request.
        if received < cutoff:
            continue
        headers = _headers(msg)
        emails.append({
            "received_at": received.isoformat(),
            "when": received.astimezone().strftime("%a %-I:%M %p"),
            "source": f"Email · {headers.get('subject', 'No subject')}",
            "who": headers.get("from", "Unknown sender"),
            "quote": msg.get("snippet", ""),
            "tags": ["email", "recent"] + (["unread"] if "UNREAD" in msg.get("labelIds", []) else []),
        })
    emails.sort(key=lambda item: item["received_at"], reverse=True)
    return {"hours": hours, "unread_only": unread_only, "topic": topic, "items": emails[:12]}


def _live_actions() -> Optional[dict]:
    brief = _live_brief() or {}
    lines = []
    for section in brief.get("sections", []):
        for line in section.get("lines", []):
            lines.append({"rank": len(lines) + 1, "title": line, "why": section["heading"], "effort": ""})
    return {"title": "Today · ranked", "items": lines[:8]}


def _headers(message: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}


def _gmail_summary(service, message_id: str) -> str:
    msg = service.users().messages().get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject"]).execute()
    headers = _headers(msg)
    return f"{headers.get('subject', 'No subject')} — {headers.get('from', 'Unknown sender')}"


def _friendly_time(value: str) -> str:
    if not value:
        return "Recently"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%a %-I:%M %p")
    except ValueError:
        return value


def _email_when(value: str) -> str:
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%a %-I:%M %p")
    except Exception:
        return "Recently"


# --------------------------------------------------------------------------
# What the tools call.
# --------------------------------------------------------------------------

def get_brief() -> dict:
    return _resolve("brief", _live_brief)


def get_metrics(metric: str = "active_users", days: int = 30) -> dict:
    data = _resolve("metrics", lambda: _live_metrics(metric, days))
    series = data.get("series", {})
    chosen = series.get(metric) or series.get(data.get("default", ""))
    if chosen is None and series:
        metric, chosen = next(iter(series.items()))
    if chosen is None:
        return {"metric": metric, "unit": "", "points": [], "summary": "", "delta_pct": 0}
    points = chosen.get("points", [])[-days:]
    first = points[0]["value"] if points else 0
    last = points[-1]["value"] if points else 0
    delta_pct = round(((last - first) / first) * 100, 1) if first else 0.0
    return {
        "metric": chosen.get("label", metric),
        "unit": chosen.get("unit", ""),
        "points": points,
        "summary": chosen.get("summary", ""),
        "delta_pct": delta_pct,
    }


def get_pipeline() -> dict:
    return _resolve("pipeline", _live_pipeline)


def search_intel(query: str) -> dict:
    data = _resolve("intel", lambda: _live_intel(query))
    items = data.get("items", [])
    q = (query or "").lower().strip()
    if q:
        hits = [
            i for i in items
            if q in i.get("quote", "").lower()
            or q in i.get("who", "").lower()
            or q in i.get("source", "").lower()
            or any(q in t.lower() for t in i.get("tags", []))
        ]
        if hits:
            items = hits
    return {"query": query, "items": items[:6]}


def get_actions() -> dict:
    return _resolve("actions", _live_actions)
