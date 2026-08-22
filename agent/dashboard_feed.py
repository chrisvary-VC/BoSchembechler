"""Cached, read-only data feed for the JARVIS command-center dashboard.

Upstream services are refreshed independently in background workers. HTTP
requests only read the in-memory snapshot, so a slow Google or Dropbox call
can never stall the dashboard. Every module keeps its last successful value
and exposes freshness metadata alongside the legacy top-level fields.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import lifestyle
import operations
import productivity
from services import SECRETS, dropbox_client, google_credentials, google_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aios.dashboard_feed")

PORT = int(os.getenv("AIOS_DASHBOARD_FEED_PORT", "8788"))
WEB_PORT = int(os.getenv("AIOS_WEB_PORT", "4310"))
CACHE_VERSION = 3
CACHE_FILE = SECRETS / "dashboard-cache.json"
CACHE_WRITE_SECONDS = 30
MAX_WORKERS = max(4, min(int(os.getenv("AIOS_DASHBOARD_WORKERS", "8")), 12))

_lock = threading.RLock()
_google_lock = threading.Lock()
_cache_write_lock = threading.Lock()
_gmail_bundle_lock = threading.Lock()
_ga4_bundle_lock = threading.Lock()
_doctor_bundle_lock = threading.Lock()
_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None
_executor: ThreadPoolExecutor | None = None
_cache_dirty = False
_last_cache_write = 0.0
_snapshot: dict[str, Any] = {}
_snapshot_bytes = b"{}"
_etag = ""
_gmail_bundle_cache: tuple[float, dict] | None = None
_ga4_bundle_cache: tuple[float, dict] | None = None
_doctor_bundle_cache: tuple[float, dict] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


def _interval(env_name: str, default: int, minimum: int = 2) -> int:
    try:
        return max(minimum, int(os.getenv(env_name, str(default))))
    except ValueError:
        return default


def _monitor_interval_seconds() -> int:
    return operations.MONITOR_INTERVAL_SECONDS


@dataclass(frozen=True)
class Collected:
    """A usable value with an optional partial-failure warning."""

    data: Any
    warning: str = ""


@dataclass(frozen=True)
class ModuleSpec:
    interval: int
    stale_after: int
    default: Any
    collector: Callable[[], Any]
    cache: bool = True


def _clean_error(exc: BaseException | str) -> str:
    """Return a short UI-safe error without tokens, URLs, or response bodies."""
    raw = str(exc).replace("\n", " ").strip()
    low = raw.lower()
    if "invalid_grant" in low or "token has been expired" in low:
        return "Authorization expired; reconnect this service."
    if "insufficient" in low or "permission" in low or "forbidden" in low:
        return "Connected account does not grant the required permission."
    if "timed out" in low or "timeout" in low:
        return "Service timed out."
    if "connection refused" in low:
        return "Local service is not running."
    # Avoid exposing query strings, OAuth details, or large upstream bodies.
    words = [word for word in raw.split() if not word.startswith(("http://", "https://"))]
    return " ".join(words)[:160] or type(exc).__name__


def _headers(message: dict) -> dict[str, str]:
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in message.get("payload", {}).get("headers", [])
    }


def _friendly_email_time(value: str) -> str:
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%a %-I:%M %p")
    except Exception:
        return "Recently"


_SENSITIVE_DASHBOARD_TERMS = (
    "password", "credential", "recovery code", "secret key", "api key",
    "login and password", "authentication token",
)


def _safe_dashboard_reference(title: str, text: str = "") -> bool:
    """Keep likely credential stores out of ambient/on-screen surfaces."""
    sample = f"{title} {text[:240]}".lower()
    return not any(term in sample for term in _SENSITIVE_DASHBOARD_TERMS)


def _gmail_priority_flags(
    headers: dict[str, str], labels: set[str], message_id: str, priority_ids: set[str]
) -> tuple[bool, bool, bool]:
    bulk_labels = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
    bulk_header = bool(
        headers.get("list-id")
        or headers.get("list-unsubscribe")
        or headers.get("precedence", "").lower() in {"bulk", "list", "junk"}
        or headers.get("auto-submitted", "").lower() not in {"", "no"}
    )
    bulk = bool(labels & bulk_labels) or bulk_header
    important = "IMPORTANT" in labels
    starred = "STARRED" in labels
    unread = "UNREAD" in labels
    priority_eligible = message_id in priority_ids and not bulk and (important or starred)
    queue_eligible = priority_eligible and (starred or (important and unread))
    return bulk, priority_eligible, queue_eligible


def _get_gmail_bundle() -> dict:
    """Share one bounded Gmail fetch across the legacy and intelligence modules."""
    global _gmail_bundle_cache
    with _gmail_bundle_lock:
        if _gmail_bundle_cache and time.monotonic() - _gmail_bundle_cache[0] < 30:
            return copy.deepcopy(_gmail_bundle_cache[1])
        cutoff = _utc_now() - timedelta(hours=24)
        with _google_lock:
            gmail = google_service("gmail", "v1")
            recent_result = gmail.users().messages().list(
                userId="me", q=f"in:inbox after:{int(cutoff.timestamp())}", maxResults=12
            ).execute()
            # Unread alone is not a useful proxy for priority: promotional mail can
            # otherwise crowd out actual work. Ask Gmail for its important/starred
            # signal separately and exclude the bulk-message categories.
            priority_result = gmail.users().messages().list(
                userId="me",
                q=(
                    "in:inbox newer_than:1d {is:important is:starred} "
                    "-category:promotions -category:social -category:forums"
                ),
                maxResults=12,
            ).execute()
            priority_ids = {
                hit.get("id", "") for hit in priority_result.get("messages", [])
                if hit.get("id")
            }
            count_queries = {
                "unread_estimate": "in:inbox is:unread",
                "unread_24h_estimate": "in:inbox is:unread newer_than:1d",
                "important_24h_estimate": "in:inbox is:important newer_than:1d",
                "starred_estimate": "in:inbox is:starred",
            }
            counts = {}
            for key, query in count_queries.items():
                result = gmail.users().messages().list(
                    userId="me", q=query, maxResults=1
                ).execute()
                counts[key] = int(result.get("resultSizeEstimate", 0))

            # Merge the recent stream with the bounded priority query so a useful
            # message is not lost merely because several newsletters arrived later.
            hits = []
            seen_ids = set()
            for hit in recent_result.get("messages", []) + priority_result.get("messages", []):
                if hit.get("id") and hit["id"] not in seen_ids:
                    seen_ids.add(hit["id"])
                    hits.append(hit)

            emails = []
            for hit in hits:
                msg = gmail.users().messages().get(
                    userId="me",
                    id=hit["id"],
                    format="metadata",
                    metadataHeaders=[
                        "From", "Subject", "Date", "List-Id", "List-Unsubscribe",
                        "Precedence", "Auto-Submitted",
                    ],
                ).execute()
                received = datetime.fromtimestamp(
                    int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc
                )
                if received < cutoff:
                    continue
                headers = _headers(msg)
                labels = set(msg.get("labelIds", []))
                important = "IMPORTANT" in labels
                starred = "STARRED" in labels
                unread = "UNREAD" in labels
                bulk, priority_eligible, queue_eligible = _gmail_priority_flags(
                    headers, labels, msg.get("id", ""), priority_ids
                )
                priority_score = (
                    (5 if starred else 0) + (3 if important else 0) + (1 if unread else 0)
                )
                category_label = next(
                    (label for label in labels if label.startswith("CATEGORY_")), ""
                )
                emails.append({
                    "id": msg.get("id", ""),
                    "thread_id": msg.get("threadId", ""),
                    "received_at": received.isoformat(),
                    "when": received.astimezone().strftime("%a %-I:%M %p")
                    if received.timestamp() else _friendly_email_time(headers.get("date", "")),
                    "source": f"Email · {headers.get('subject', 'No subject')}",
                    "subject": headers.get("subject", "No subject"),
                    "who": headers.get("from", "Unknown sender"),
                    "quote": msg.get("snippet", "")[:320],
                    "unread": unread,
                    "important": important,
                    "starred": starred,
                    "category": category_label.removeprefix("CATEGORY_").lower(),
                    "bulk": bulk,
                    "priority_eligible": priority_eligible,
                    "queue_eligible": queue_eligible,
                    "priority": "high" if priority_eligible else "attention" if unread else "normal",
                    "priority_score": priority_score,
                })
        emails.sort(key=lambda item: item.get("received_at", ""), reverse=True)
        priority_candidates = sorted(
            (item for item in emails if item["priority_eligible"]),
            key=lambda item: (item["priority_score"], item["received_at"]),
            reverse=True,
        )
        # A conversation is one actionable unit even when several replies landed.
        # Keep the newest/highest-scored message for display and queueing.
        priority_by_thread = {}
        for item in priority_candidates:
            thread_key = item.get("thread_id") or item.get("id")
            if thread_key not in priority_by_thread:
                priority_by_thread[thread_key] = item
        priority = list(priority_by_thread.values())
        bundle = {
            "recent": emails,
            "recent_24h_estimate": int(recent_result.get("resultSizeEstimate", len(emails))),
            **counts,
            "priority_count": len(priority),
            "priority_message_count_estimate": int(
                priority_result.get("resultSizeEstimate", len(priority_candidates))
            ),
            "priority_recent_count": len(priority),
            "priority_window": "important or starred inbox mail from the last 24 hours, excluding bulk categories",
            "priority": priority[:8],
            "last_received_at": emails[0]["received_at"] if emails else "",
            "counts_are_estimates": True,
        }
        _gmail_bundle_cache = (time.monotonic(), bundle)
        return copy.deepcopy(bundle)


def _collect_emails() -> list[dict]:
    """Backward-compatible recent inbox list for the existing rail."""
    return _get_gmail_bundle()["recent"][:6]


def _collect_inbox_intelligence() -> dict:
    bundle = _get_gmail_bundle()
    return {key: value for key, value in bundle.items() if key != "recent"}


def _collect_tasks() -> list[dict]:
    with _google_lock:
        tasks = productivity.list_google_tasks(8)
    return [{
        "id": item.get("id", ""),
        "title": item.get("title", "Untitled task"),
        "due": item.get("due", ""),
        "status": item.get("status", "needsAction"),
        "updated": item.get("updated", ""),
    } for item in tasks]


def _collect_calendar() -> list[dict]:
    # Use the user's local calendar day instead of a UTC rolling 24-hour range.
    local_now = datetime.now().astimezone()
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    with _google_lock:
        service = google_service("calendar", "v3")
        events = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=8,
        ).execute().get("items", [])
    return [{
        "id": item.get("id", ""),
        "title": item.get("summary", "Untitled event"),
        "start": item.get("start", {}).get("dateTime")
        or item.get("start", {}).get("date", ""),
        "end": item.get("end", {}).get("dateTime")
        or item.get("end", {}).get("date", ""),
        "all_day": "date" in item.get("start", {}),
        "location": item.get("location", ""),
    } for item in events]


def _event_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _event_meeting_url(item: dict) -> str:
    meeting_url = item.get("hangoutLink", "")
    if not meeting_url:
        for point in item.get("conferenceData", {}).get("entryPoints", []):
            if point.get("entryPointType") == "video" and point.get("uri"):
                meeting_url = point["uri"]
                break
    if not meeting_url:
        # Imported Outlook/Teams invitations often put the join link only in
        # the description instead of Calendar's structured conference data.
        match = re.search(
            r"https://teams\.microsoft\.com/(?:meet|l/meetup-join)/[^\s<>]+",
            item.get("description", ""),
            flags=re.IGNORECASE,
        )
        if match:
            meeting_url = match.group(0).rstrip(").,;")
    return meeting_url


def _select_meeting_candidate(events: list[dict], allow_solo: bool = False) -> dict | None:
    for candidate in events:
        attendees = candidate.get("attendees", [])
        self_declined = any(
            attendee.get("self") and attendee.get("responseStatus") == "declined"
            for attendee in attendees
        )
        non_self_attendees = any(
            not attendee.get("self") and attendee.get("responseStatus") != "declined"
            for attendee in attendees
        )
        timed = bool(
            candidate.get("start", {}).get("dateTime")
            and candidate.get("end", {}).get("dateTime")
        )
        real_meeting = bool(non_self_attendees or _event_meeting_url(candidate))
        if (
            candidate.get("status") != "cancelled"
            and candidate.get("eventType", "default") == "default"
            and timed
            and not self_declined
            and (real_meeting or allow_solo)
        ):
            return candidate
    return None


def _meeting_queue_due(event: dict, now: datetime | None = None) -> bool:
    if not event or not event.get("queue_eligible"):
        return False
    now = now or _utc_now()
    minutes = event.get("starts_in_minutes")
    event_end = _event_datetime(event.get("end", ""))
    upcoming = (
        event.get("phase") == "upcoming"
        and isinstance(minutes, int)
        and 0 <= minutes <= 180
    )
    in_progress = (
        event.get("phase") == "in_progress"
        and event_end is not None
        and event_end > now
    )
    return upcoming or in_progress


def _collect_meeting_prep() -> Collected:
    now = _utc_now()
    with _google_lock:
        calendar = google_service("calendar", "v3")
        events = calendar.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=7)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute().get("items", [])
    # Meeting prep should focus on timed appointments. All-day birthdays and
    # observances still belong in the calendar module, but not in the command queue.
    allow_solo = os.getenv("AIOS_INCLUDE_SOLO_CALENDAR_BLOCKS", "").lower() in {
        "1", "true", "yes", "on",
    }
    item = _select_meeting_candidate(events, allow_solo)
    if not item:
        return Collected({"status": "none", "event": None, "related": [], "prepared_at": _iso()})
    start_value = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
    end_value = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", "")
    start = _event_datetime(start_value)
    end = _event_datetime(end_value)
    minutes = int((start - now).total_seconds() // 60) if start else None
    phase = "in_progress" if start and end and start <= now < end else "upcoming"
    meeting_url = _event_meeting_url(item)
    attendees = [{
        "name": attendee.get("displayName", ""),
        "email": attendee.get("email", ""),
        "response_status": attendee.get("responseStatus", ""),
        "self": bool(attendee.get("self")),
        "organizer": bool(attendee.get("organizer")),
    } for attendee in item.get("attendees", [])[:20]]
    event = {
        "id": item.get("id", ""),
        "title": item.get("summary", "Untitled event"),
        "start": start_value,
        "end": end_value,
        "all_day": "date" in item.get("start", {}),
        "starts_in_minutes": minutes,
        "phase": phase,
        "location": item.get("location", ""),
        "description": item.get("description", "")[:1200],
        "calendar_url": item.get("htmlLink", ""),
        "meeting_url": meeting_url,
        "organizer": item.get("organizer", {}),
        "attendees": attendees,
        "attendee_count": len(item.get("attendees", [])),
        "status": item.get("status", "confirmed"),
        "queue_eligible": True,
    }

    related = []
    warning = ""
    query_parts = [event["title"]]
    query_parts.extend(
        attendee.get("name") or attendee.get("email", "").split("@", 1)[0]
        for attendee in attendees if not attendee.get("self")
    )
    query = " ".join(part for part in query_parts if part).strip()[:500]
    if query and productivity.memory_count():
        try:
            hits = productivity.search_memory(query, limit=4)
            try:
                minimum_score = float(os.getenv("AIOS_MEETING_MEMORY_MIN_SCORE", "0.55"))
            except ValueError:
                minimum_score = 0.55
            minimum_score = max(0.0, min(minimum_score, 1.0))
            related = [{
                "id": hit.get("id", ""),
                "source": hit.get("source", "Private memory"),
                "title": hit.get("title", "Untitled item"),
                "snippet": hit.get("text", "")[:320],
                "updated_at": hit.get("updated_at", ""),
                "relevance": round(float(hit.get("score", 0)), 3),
            } for hit in hits if (
                float(hit.get("score", 0)) >= minimum_score
                and _safe_dashboard_reference(hit.get("title", ""), hit.get("text", ""))
            )]
        except Exception as exc:
            warning = f"Private memory context: {_clean_error(exc)}"
    return Collected({
        "status": phase,
        "event": event,
        "related": related,
        "prepared_at": _iso(),
    }, warning)


def _metric_payload(label: str, points: list[dict], property_count: int) -> dict:
    first = points[0]["value"] if points else 0
    last = points[-1]["value"] if points else 0
    delta = round(((last - first) / first) * 100, 1) if first else 0.0
    return {
        "metric": label,
        "unit": "",
        "summary": f"Google Analytics 4 across {property_count} website properties.",
        "delta_pct": delta,
        "points": points,
    }


def _ga4_properties() -> list[dict]:
    raw_ids = os.getenv("GA4_PROPERTY_IDS") or os.getenv("GA4_PROPERTY_ID", "")
    property_ids = [
        value.strip().removeprefix("properties/")
        for value in raw_ids.split(",") if value.strip()
    ]
    if not property_ids:
        raise RuntimeError("Google Analytics properties are not configured.")
    names: dict[str, str] = {}
    configured = os.getenv("GA4_PROPERTY_NAMES", "").strip()
    if configured:
        try:
            value = json.loads(configured)
            if isinstance(value, dict):
                names = {str(key).removeprefix("properties/"): str(name) for key, name in value.items()}
        except json.JSONDecodeError:
            parts = [part.strip() for part in configured.split(",")]
            if any("=" in part for part in parts):
                names = {
                    key.strip().removeprefix("properties/"): name.strip()
                    for part in parts if "=" in part
                    for key, name in [part.split("=", 1)]
                }
            else:
                names = {
                    property_id: parts[index]
                    for index, property_id in enumerate(property_ids)
                    if index < len(parts) and parts[index]
                }
    return [{
        "id": property_id,
        "name": names.get(property_id, f"GA4 {property_id}"),
        "name_configured": property_id in names,
    } for property_id in property_ids]


def _get_ga4_bundle() -> dict:
    """Collect one shared historical portfolio for legacy and rich modules."""
    global _ga4_bundle_cache
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Metric, MetricAggregation, RunReportRequest,
    )

    with _ga4_bundle_lock:
        if _ga4_bundle_cache and time.monotonic() - _ga4_bundle_cache[0] < 600:
            return copy.deepcopy(_ga4_bundle_cache[1])
        configured = _ga4_properties()
        aggregate_days: dict[str, dict[str, float]] = {}
        aggregate_totals = {"active_users": 0.0, "sessions": 0.0, "views": 0.0, "key_events": 0.0}
        properties = []
        warnings: list[str] = []
        successes = 0
        with _google_lock:
            client = BetaAnalyticsDataClient(credentials=google_credentials())
            for config in configured:
                property_id = config["id"]
                property_warnings: list[str] = []
                metric_names = ["activeUsers", "sessions", "screenPageViews", "keyEvents"]
                key_events_supported = True
                try:
                    try:
                        trend_report = client.run_report(RunReportRequest(
                            property=f"properties/{property_id}",
                            date_ranges=[DateRange(start_date="13daysAgo", end_date="today")],
                            dimensions=[{"name": "date"}],
                            metrics=[Metric(name=name) for name in metric_names],
                            metric_aggregations=[MetricAggregation.TOTAL],
                            order_bys=[{"dimension": {"dimension_name": "date"}}],
                        ))
                    except Exception as key_event_exc:
                        # Some properties/API revisions do not expose keyEvents.
                        metric_names = metric_names[:3]
                        key_events_supported = False
                        property_warnings.append(f"key events unavailable: {_clean_error(key_event_exc)}")
                        trend_report = client.run_report(RunReportRequest(
                            property=f"properties/{property_id}",
                            date_ranges=[DateRange(start_date="13daysAgo", end_date="today")],
                            dimensions=[{"name": "date"}],
                            metrics=[Metric(name=name) for name in metric_names],
                            metric_aggregations=[MetricAggregation.TOTAL],
                            order_bys=[{"dimension": {"dimension_name": "date"}}],
                        ))
                except Exception as exc:
                    message = _clean_error(exc)
                    warnings.append(f"{config['name']}: {message}")
                    properties.append({
                        **config,
                        "status": "error",
                        "error": message,
                        "totals": {},
                        "trend": [],
                        "top_pages": [],
                        "key_events": [],
                        "key_events_supported": False,
                    })
                    continue

                successes += 1
                trend = []
                for row in trend_report.rows:
                    day = datetime.strptime(row.dimension_values[0].value, "%Y%m%d").strftime("%Y-%m-%d")
                    values = [float(item.value or 0) for item in row.metric_values]
                    point = {
                        "date": day,
                        "active_users": values[0],
                        "sessions": values[1],
                        "views": values[2],
                        "key_events": values[3] if len(values) > 3 else None,
                    }
                    trend.append(point)
                    bucket = aggregate_days.setdefault(day, {"active_users": 0, "sessions": 0, "views": 0, "key_events": 0})
                    for key in ("active_users", "sessions", "views"):
                        bucket[key] += point[key]
                    if point["key_events"] is not None:
                        bucket["key_events"] += point["key_events"]
                total_values = (
                    [float(item.value or 0) for item in trend_report.totals[0].metric_values]
                    if trend_report.totals else []
                )
                totals = {
                    "active_users": total_values[0] if len(total_values) > 0 else None,
                    "sessions": total_values[1] if len(total_values) > 1 else sum(item["sessions"] for item in trend),
                    "views": total_values[2] if len(total_values) > 2 else sum(item["views"] for item in trend),
                    "key_events": total_values[3] if len(total_values) > 3 else None,
                }
                for key, value in totals.items():
                    if value is not None:
                        aggregate_totals[key] += value

                top_pages = []
                try:
                    page_report = client.run_report(RunReportRequest(
                        property=f"properties/{property_id}",
                        date_ranges=[DateRange(start_date="13daysAgo", end_date="today")],
                        dimensions=[{"name": "pagePath"}, {"name": "pageTitle"}],
                        metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers")],
                        order_bys=[{"metric": {"metric_name": "screenPageViews"}, "desc": True}],
                        limit=8,
                    ))
                    top_pages = [{
                        "path": row.dimension_values[0].value,
                        "title": row.dimension_values[1].value,
                        "views": float(row.metric_values[0].value or 0),
                        "active_users": float(row.metric_values[1].value or 0),
                    } for row in page_report.rows]
                except Exception as exc:
                    property_warnings.append(f"top pages unavailable: {_clean_error(exc)}")

                key_events = []
                if key_events_supported:
                    try:
                        event_report = client.run_report(RunReportRequest(
                            property=f"properties/{property_id}",
                            date_ranges=[DateRange(start_date="13daysAgo", end_date="today")],
                            dimensions=[{"name": "eventName"}],
                            metrics=[Metric(name="keyEvents")],
                            order_bys=[{"metric": {"metric_name": "keyEvents"}, "desc": True}],
                            limit=10,
                        ))
                        key_events = [{
                            "name": row.dimension_values[0].value,
                            "count": float(row.metric_values[0].value or 0),
                        } for row in event_report.rows if float(row.metric_values[0].value or 0) > 0]
                    except Exception as exc:
                        key_events_supported = False
                        property_warnings.append(f"key events unavailable: {_clean_error(exc)}")
                if property_warnings:
                    warnings.extend(f"{config['name']}: {message}" for message in property_warnings)
                properties.append({
                    **config,
                    "status": "degraded" if property_warnings else "ok",
                    "error": "; ".join(property_warnings) or None,
                    "totals": totals,
                    "trend": trend,
                    "top_pages": top_pages,
                    "key_events": key_events,
                    "key_events_supported": key_events_supported,
                })
        if not successes:
            raise RuntimeError(warnings[0] if warnings else "Google Analytics returned no readable properties.")

        active_points = [{"date": day, "value": values["active_users"]} for day, values in sorted(aggregate_days.items())]
        session_points = [{"date": day, "value": values["sessions"]} for day, values in sorted(aggregate_days.items())]
        bundle = {
            "legacy": {
                "active_users": _metric_payload("Active users", active_points, successes),
                "sessions": _metric_payload("Sessions", session_points, successes),
            },
            "portfolio": {
                "period": {"start": "13daysAgo", "end": "today", "days": 14},
                "property_count": len(configured),
                "readable_property_count": successes,
                "totals": aggregate_totals,
                "properties": properties,
                "limitations": warnings,
            },
            "warning": "; ".join(warnings[:4]),
        }
        _ga4_bundle_cache = (time.monotonic(), bundle)
        return copy.deepcopy(bundle)


def _collect_analytics() -> Collected:
    bundle = _get_ga4_bundle()
    return Collected(bundle["legacy"], bundle["warning"])


def _collect_analytics_portfolio() -> Collected:
    bundle = _get_ga4_bundle()
    return Collected(bundle["portfolio"], bundle["warning"])


def _collect_analytics_realtime() -> Collected:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import Metric, RunRealtimeReportRequest

    configured = _ga4_properties()

    active_users = 0.0
    page_views = 0.0
    properties = []
    errors: list[str] = []
    with _google_lock:
        client = BetaAnalyticsDataClient(credentials=google_credentials())
        for config in configured:
            property_id = config["id"]
            try:
                report = client.run_realtime_report(RunRealtimeReportRequest(
                    property=f"properties/{property_id}",
                    metrics=[Metric(name="activeUsers"), Metric(name="screenPageViews")],
                ))
                values = (
                    report.totals[0].metric_values
                    if report.totals
                    else report.rows[0].metric_values if report.rows else []
                )
                users = float(values[0].value) if len(values) > 0 else 0.0
                views = float(values[1].value) if len(values) > 1 else 0.0
                active_users += users
                page_views += views
                properties.append({
                    "id": property_id,
                    "name": config["name"],
                    "active_users": users,
                    "page_views_30m": views,
                })
            except Exception as exc:
                errors.append(f"property {property_id}: {_clean_error(exc)}")
    if not properties:
        raise RuntimeError(errors[0] if errors else "Google Analytics realtime returned no properties.")
    return Collected({
        "active_users": active_users,
        "page_views_30m": page_views,
        "properties": properties,
    }, "; ".join(errors[:3]))


def _collect_memory() -> dict:
    count = productivity.memory_count()
    by_source: dict[str, int] = {}
    last_sync = ""
    # Metadata only: memory text and embeddings never enter the dashboard feed.
    try:
        with productivity._db() as db:  # noqa: SLF001 - same local subsystem
            for source, source_count in db.execute(
                "SELECT source, COUNT(*) FROM memories GROUP BY source"
            ):
                by_source[source] = source_count
            row = db.execute("SELECT MAX(updated_at) FROM memories").fetchone()
            last_sync = row[0] if row and row[0] else ""
    except Exception:
        pass
    return {"count": count, "by_source": by_source, "last_sync_at": last_sync}


def _collect_approvals() -> dict:
    pending = productivity.pending_actions()
    now = _utc_now()
    rows = []
    for item in pending[:8]:
        created_at = item.get("created_at", "")
        age_minutes = None
        try:
            age_minutes = max(0, int((now - datetime.fromisoformat(created_at)).total_seconds() // 60))
        except (TypeError, ValueError):
            pass
        rows.append({
            "id": item.get("id", ""),
            "kind": item.get("kind", ""),
            "title": item.get("title", "Untitled action"),
            "notes": item.get("notes", "")[:500],
            "due": item.get("due", ""),
            "status": item.get("status", "pending"),
            "created_at": created_at,
            "age_minutes": age_minutes,
            "target": "Google Tasks" if item.get("kind") == "google_task" else item.get("kind", "Local action"),
            "effect": "Creates a cloud task" if item.get("kind") == "google_task" else "Executes the proposed action",
            "requires_explicit_approval": True,
        })
    return {
        "count": len(pending),
        "pending": rows,
        "oldest_age_minutes": max((item["age_minutes"] or 0 for item in rows), default=0),
        "cloud_writes_guarded": True,
    }


def _collect_files() -> Collected:
    items: list[dict] = []
    errors: list[str] = []
    with _google_lock:
        try:
            drive = google_service("drive", "v3")
            files = drive.files().list(
                q="trashed = false",
                pageSize=8,
                orderBy="modifiedTime desc",
                fields="files(id,name,mimeType,modifiedTime,webViewLink)",
            ).execute().get("files", [])
            items.extend({
                "id": item.get("id", ""),
                "name": item.get("name", "Untitled file"),
                "source": "Google Drive",
                "modified_at": item.get("modifiedTime", ""),
                "url": item.get("webViewLink", ""),
                "type": item.get("mimeType", ""),
            } for item in files if _safe_dashboard_reference(item.get("name", "")))
        except Exception as exc:
            errors.append(f"Google Drive: {_clean_error(exc)}")
    try:
        dbx = dropbox_client()
        result = dbx.files_list_folder("", recursive=True, limit=20)
        for item in result.entries:
            if not hasattr(item, "server_modified"):
                continue
            modified = item.server_modified
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            if not _safe_dashboard_reference(getattr(item, "name", "")):
                continue
            items.append({
                "id": getattr(item, "id", ""),
                "name": getattr(item, "name", "Untitled file"),
                "source": "Dropbox",
                "modified_at": modified.isoformat(),
                "url": "",
                "type": "file",
            })
    except Exception as exc:
        errors.append(f"Dropbox: {_clean_error(exc)}")
    if not items and errors:
        raise RuntimeError("; ".join(errors))
    items.sort(key=lambda item: item.get("modified_at", ""), reverse=True)
    return Collected(items[:10], "; ".join(errors))


def _collect_news() -> list[dict]:
    return lifestyle.news(limit=6)


def _read_operations_state() -> dict:
    path = SECRETS / "operations-state.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _collect_monitors() -> dict:
    monitor = _read_operations_state().get("monitor", {})
    if not isinstance(monitor, dict):
        monitor = {}
    timeline = operations.alerts_timeline(30)
    alerts = [item for item in timeline if item.get("active", True)]
    return {
        "checked_at": monitor.get("checked_at", ""),
        "important_email_count": monitor.get("important_email_count", 0),
        "analytics_delta": float(monitor.get("analytics_delta", 0) or 0),
        "next_check_at": (
            (_parse_timestamp(monitor.get("checked_at", "")) + timedelta(
                seconds=_monitor_interval_seconds()
            )).isoformat()
            if _parse_timestamp(monitor.get("checked_at", "")) else ""
        ),
        "alert_count": len(timeline),
        "active_alert_count": len(alerts),
        "alerts": alerts[:10],
        "timeline": timeline,
    }


def _collect_mode() -> dict:
    state = _read_operations_state()
    key = str(state.get("mode", "executive"))
    descriptions = {
        "executive": "Brief, email, calendar, tasks, and analytics first.",
        "research": "Sourced research and private-memory retrieval.",
        "monitor": "Important changes and anomalies first.",
        "creative": "Exploratory ideas and concise options.",
        "private": "Local memory and local inference first.",
        "operator": "System status and safe computer actions first.",
    }
    return {"mode": key, "description": descriptions.get(key, "Custom operating mode.")}


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _collect_workspace_sync() -> dict:
    memory = _collect_memory()
    sync_state = _read_operations_state().get("memory_sync", {})
    if not isinstance(sync_state, dict):
        sync_state = {}
    with _lock:
        files = copy.deepcopy(_module_data.get("files", []))
    # The shared doctor probe is cached for thirty seconds and prevents a
    # startup race where sync health briefly claims connected services are off.
    services = _get_doctor_bundle()["services"]
    source_map = {
        "google_drive": {"label": "Google Drive", "memory_labels": ("Google Drive", "Drive")},
        "dropbox": {"label": "Dropbox", "memory_labels": ("Dropbox",)},
    }
    sources = {}
    for key, config in source_map.items():
        indexed_count = sum(
            int(memory.get("by_source", {}).get(label, 0)) for label in config["memory_labels"]
        )
        indexed_rows = []
        try:
            with productivity._db() as db:  # noqa: SLF001 - metadata-only query
                placeholders = ",".join("?" for _ in config["memory_labels"])
                indexed_rows = db.execute(
                    f"SELECT MAX(updated_at) FROM memories WHERE source IN ({placeholders})",
                    config["memory_labels"],
                ).fetchone()
        except Exception:
            indexed_rows = []
        last_indexed = indexed_rows[0] if indexed_rows and indexed_rows[0] else ""
        remote_times = [
            item.get("modified_at", "") for item in files
            if item.get("source") == config["label"] and item.get("modified_at")
        ]
        last_remote = max(remote_times, default="")
        indexed_dt = _parse_timestamp(last_indexed)
        remote_dt = _parse_timestamp(last_remote)
        lag_seconds = (
            max(0, int((remote_dt - indexed_dt).total_seconds()))
            if indexed_dt and remote_dt else None
        )
        connected = bool(services.get("google" if key == "google_drive" else "dropbox"))
        if not connected:
            status = "disconnected"
        elif indexed_count == 0:
            status = "not_indexed"
        elif lag_seconds and lag_seconds > 0:
            status = "behind"
        else:
            status = "indexed"
        sources[key] = {
            "label": config["label"],
            "connected": connected,
            "indexed_count": indexed_count,
            "newest_indexed_document_at": last_indexed,
            "last_sync_at": sync_state.get("last_completed_at", ""),
            "last_sync_indexed": int(sync_state.get("indexed", {}).get(config["label"], 0)),
            "last_remote_modified_at": last_remote,
            "lag_seconds": lag_seconds,
            "status": status,
        }
    return {
        "total_indexed": sum(item["indexed_count"] for item in sources.values()),
        "memory_total": memory.get("count", 0),
        "last_sync_started_at": sync_state.get("last_started_at", ""),
        "last_sync_completed_at": sync_state.get("last_completed_at", ""),
        "last_sync_errors": sync_state.get("errors", []),
        "sources": sources,
        "checked_at": _iso(),
    }


def _collect_routines() -> dict:
    state = _read_operations_state()
    local_now = datetime.now().astimezone()
    digest_hour = max(0, min(int(state.get("digest_hour", 8)), 23))
    last_digest_date = str(state.get("last_digest_date", ""))
    digest_today = local_now.replace(hour=digest_hour, minute=0, second=0, microsecond=0)
    digest_due = local_now >= digest_today and last_digest_date != local_now.date().isoformat()
    next_digest = digest_today
    if local_now >= digest_today or last_digest_date == local_now.date().isoformat():
        next_digest += timedelta(days=1)

    monitor = state.get("monitor", {}) if isinstance(state.get("monitor", {}), dict) else {}
    monitor_interval = _monitor_interval_seconds()
    last_checked = _parse_timestamp(str(monitor.get("checked_at", "")))
    next_monitor = last_checked + timedelta(seconds=monitor_interval) if last_checked else None
    return {
        "timezone": str(local_now.tzinfo),
        "digest": {
            "hour": digest_hour,
            "label": digest_today.strftime("%-I:00 %p"),
            "last_delivered_date": last_digest_date,
            "due": digest_due,
            "next_due_at": next_digest.isoformat(),
        },
        "monitor": {
            "interval_seconds": monitor_interval,
            "last_checked_at": monitor.get("checked_at", ""),
            "next_check_at": next_monitor.isoformat() if next_monitor else "",
            "overdue": bool(next_monitor and _utc_now() > next_monitor),
        },
        "mode": state.get("mode", "executive"),
    }


def _collect_today_command_queue() -> dict:
    with _lock:
        tasks = copy.deepcopy(_module_data.get("tasks", []))
        approvals = copy.deepcopy(_module_data.get("approvals", {}))
        inbox = copy.deepcopy(_module_data.get("inbox_intelligence", {}))
        meeting = copy.deepcopy(_module_data.get("meeting_prep", {}))
        monitors = copy.deepcopy(_module_data.get("monitors", {}))
    queue = []

    for item in approvals.get("pending", []):
        queue.append({
            "id": f"approval:{item.get('id', '')}",
            "kind": "approval",
            "priority": "urgent",
            "priority_score": 100,
            "title": item.get("title", "Untitled approval"),
            "source": "Approval queue",
            "why": f"Explicit approval required before {item.get('effect', 'execution').lower()}.",
            "due_at": item.get("due", ""),
            "reference_id": item.get("id", ""),
        })
    for alert in monitors.get("alerts", []):
        queue.append({
            "id": f"alert:{alert.get('id', '')}",
            "kind": "alert",
            "priority": "urgent" if alert.get("severity") == "critical" else "high",
            "priority_score": 95 if alert.get("severity") == "critical" else 90,
            "title": alert.get("title", "Monitor alert"),
            "source": alert.get("source", "Monitor"),
            "why": alert.get("detail", "A configured monitor crossed its threshold."),
            "due_at": alert.get("last_seen_at", alert.get("detected_at", "")),
            "reference_id": alert.get("id", ""),
        })
    event = meeting.get("event") or {}
    minutes = event.get("starts_in_minutes")
    if _meeting_queue_due(event):
        queue.append({
            "id": f"meeting:{event.get('id', '')}",
            "kind": "meeting",
            "priority": "urgent" if minutes <= 30 else "high",
            "priority_score": 92 if minutes <= 30 else 75,
            "title": event.get("title", "Upcoming meeting"),
            "source": "Google Calendar",
            "why": "In progress" if event.get("phase") == "in_progress" else f"Starts in {max(minutes, 0)} minutes.",
            "due_at": event.get("start", ""),
            "reference_id": event.get("id", ""),
        })
    for task in tasks:
        due = _parse_timestamp(task.get("due", ""))
        local_today = datetime.now().astimezone().date()
        due_date = due.astimezone().date() if due else None
        # Google Tasks due values are date-only even though represented at midnight.
        overdue = bool(due_date and due_date < local_today)
        due_today = due_date == local_today
        if not overdue and not due_today:
            continue
        queue.append({
            "id": f"task:{task.get('id', '')}",
            "kind": "task",
            "priority": "urgent" if overdue else "high",
            "priority_score": 88 if overdue else 72,
            "title": task.get("title", "Untitled task"),
            "source": "Google Tasks",
            "why": "Overdue" if overdue else "Due today",
            "due_at": task.get("due", ""),
            "reference_id": task.get("id", ""),
        })
    for mail in [item for item in inbox.get("priority", []) if item.get("queue_eligible")][:2]:
        queue.append({
            "id": f"email:{mail.get('id', '')}",
            "kind": "email",
            "priority": "high",
            "priority_score": 74 if mail.get("starred") else 70,
            "title": mail.get("subject", "No subject"),
            "source": mail.get("who", "Gmail"),
            "why": "Starred in Gmail" if mail.get("starred") else "Marked important in Gmail",
            "due_at": mail.get("received_at", ""),
            "reference_id": mail.get("thread_id", mail.get("id", "")),
        })
    unique = {item["id"]: item for item in queue if item["id"].split(":", 1)[-1]}
    items = sorted(
        unique.values(),
        key=lambda item: (-item["priority_score"], item.get("due_at") or "9999"),
    )[:12]
    return {
        "generated_at": _iso(),
        "count": len(items),
        "urgent_count": sum(item["priority"] == "urgent" for item in items),
        "items": items,
    }


def _probe_tcp(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _timed_check(key: str, label: str, probe: Callable[[], Any]) -> dict:
    started = time.monotonic()
    try:
        probe()
        return {
            "id": key,
            "name": label,
            "ok": True,
            "status": "online",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": "Connected",
        }
    except Exception as exc:
        return {
            "id": key,
            "name": label,
            "ok": False,
            "status": "offline",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": _clean_error(exc),
        }


def _get_doctor_bundle() -> dict:
    global _doctor_bundle_cache
    with _doctor_bundle_lock:
        if _doctor_bundle_cache and time.monotonic() - _doctor_bundle_cache[0] < 30:
            return copy.deepcopy(_doctor_bundle_cache[1])

        def tcp(port: int) -> None:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return None

        def ollama() -> None:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError(f"Local AI returned status {response.status}")

        checks = [
            _timed_check("dashboard", "Dashboard", lambda: tcp(WEB_PORT)),
            _timed_check("voice_room", "Voice room", lambda: tcp(7880)),
            _timed_check("local_ai", "Local AI", ollama),
        ]
        with _google_lock:
            checks.append(_timed_check(
                "google", "Google Workspace",
                lambda: google_service("drive", "v3").about().get(fields="user").execute(),
            ))
            checks.append(_timed_check(
                "tasks", "Google Tasks",
                lambda: google_service("tasks", "v1").tasklists().list(maxResults=1).execute(),
            ))
        checks.append(_timed_check(
            "dropbox", "Dropbox", lambda: dropbox_client().users_get_current_account(),
        ))
        services = {item["id"]: item["ok"] for item in checks}
        failed = [item for item in checks if not item["ok"]]
        bundle = {
            "services": services,
            "doctor": {
                "overall": "healthy" if not failed else "degraded",
                "checked_at": _iso(),
                "healthy_count": len(checks) - len(failed),
                "total_count": len(checks),
                "checks": checks,
            },
            "warning": "; ".join(f"{item['name']}: {item['detail']}" for item in failed),
        }
        _doctor_bundle_cache = (time.monotonic(), bundle)
        return copy.deepcopy(bundle)


def _collect_services() -> Collected:
    bundle = _get_doctor_bundle()
    return Collected(bundle["services"], bundle["warning"])


def _collect_doctor() -> Collected:
    bundle = _get_doctor_bundle()
    return Collected(bundle["doctor"], bundle["warning"])


SPECS: dict[str, ModuleSpec] = {
    "emails": ModuleSpec(_interval("AIOS_EMAIL_REFRESH_SECONDS", 60), 180, [], _collect_emails),
    "inbox_intelligence": ModuleSpec(_interval("AIOS_EMAIL_REFRESH_SECONDS", 60), 180, {}, _collect_inbox_intelligence),
    "tasks": ModuleSpec(_interval("AIOS_TASK_REFRESH_SECONDS", 120), 360, [], _collect_tasks),
    "calendar": ModuleSpec(_interval("AIOS_CALENDAR_REFRESH_SECONDS", 300), 900, [], _collect_calendar),
    "meeting_prep": ModuleSpec(_interval("AIOS_MEETING_PREP_REFRESH_SECONDS", 300), 900, {"status": "none", "event": None, "related": []}, _collect_meeting_prep),
    "weather": ModuleSpec(_interval("AIOS_WEATHER_REFRESH_SECONDS", 900), 2700, {}, lifestyle.weather),
    "system": ModuleSpec(_interval("AIOS_SYSTEM_REFRESH_SECONDS", 2), 10, {}, lifestyle.computer_health, False),
    "analytics": ModuleSpec(_interval("AIOS_ANALYTICS_REFRESH_SECONDS", 900), 2700, {}, _collect_analytics),
    "analytics_portfolio": ModuleSpec(_interval("AIOS_ANALYTICS_REFRESH_SECONDS", 900), 2700, {"properties": []}, _collect_analytics_portfolio),
    "analytics_realtime": ModuleSpec(_interval("AIOS_ANALYTICS_REALTIME_REFRESH_SECONDS", 60), 180, {}, _collect_analytics_realtime),
    "memory": ModuleSpec(_interval("AIOS_MEMORY_REFRESH_SECONDS", 10), 60, {"count": 0}, _collect_memory),
    "approvals": ModuleSpec(_interval("AIOS_APPROVAL_REFRESH_SECONDS", 5), 30, {"count": 0, "pending": []}, _collect_approvals),
    "files": ModuleSpec(_interval("AIOS_FILES_REFRESH_SECONDS", 300), 900, [], _collect_files),
    "workspace_sync": ModuleSpec(_interval("AIOS_WORKSPACE_SYNC_REFRESH_SECONDS", 30), 120, {"sources": {}}, _collect_workspace_sync),
    "news": ModuleSpec(_interval("AIOS_NEWS_REFRESH_SECONDS", 600), 1800, [], _collect_news),
    "monitors": ModuleSpec(_interval("AIOS_MONITOR_STATE_REFRESH_SECONDS", 10), 60, {"alerts": [], "timeline": []}, _collect_monitors),
    "mode": ModuleSpec(_interval("AIOS_MODE_REFRESH_SECONDS", 5), 30, {"mode": "executive"}, _collect_mode),
    "routines": ModuleSpec(_interval("AIOS_ROUTINE_REFRESH_SECONDS", 10), 60, {}, _collect_routines),
    "today_command_queue": ModuleSpec(_interval("AIOS_COMMAND_QUEUE_REFRESH_SECONDS", 5), 30, {"items": [], "count": 0}, _collect_today_command_queue, False),
    "doctor": ModuleSpec(_interval("AIOS_SERVICE_REFRESH_SECONDS", 300), 600, {"checks": []}, _collect_doctor, False),
    "services": ModuleSpec(_interval("AIOS_SERVICE_REFRESH_SECONDS", 300), 600, {}, _collect_services, False),
}

_module_data: dict[str, Any] = {
    name: copy.deepcopy(spec.default) for name, spec in SPECS.items()
}
_module_meta: dict[str, dict[str, Any]] = {}
_has_good: set[str] = set()
_in_flight: set[str] = set()
_next_due: dict[str, float] = {name: 0.0 for name in SPECS}


def _new_meta(name: str) -> dict[str, Any]:
    spec = SPECS[name]
    return {
        "status": "loading",
        "updated_at": "",
        "last_attempt_at": "",
        "next_refresh_at": "",
        "stale_at": "",
        "refresh_seconds": spec.interval,
        "latency_ms": None,
        "revision": 0,
        "consecutive_failures": 0,
        "refreshing": False,
        "error": None,
    }


def _snapshot_status_locked() -> str:
    if not _has_good:
        return "starting"
    essential = ("emails", "tasks", "calendar", "weather", "system", "analytics", "memory", "approvals")
    if any(_module_meta[name]["status"] != "ok" for name in essential):
        return "degraded"
    return "online"


def _rebuild_snapshot_locked() -> None:
    global _snapshot, _snapshot_bytes, _etag
    services = copy.deepcopy(_module_data.get("services", {}))
    services["analytics"] = "analytics" in _has_good and _module_meta["analytics"]["status"] != "error"
    services["weather"] = "weather" in _has_good and _module_meta["weather"]["status"] != "error"
    portfolio = copy.deepcopy(_module_data.get("analytics_portfolio", {}))
    realtime_by_id = {
        item.get("id"): item
        for item in _module_data.get("analytics_realtime", {}).get("properties", [])
    }
    for item in portfolio.get("properties", []):
        realtime = realtime_by_id.get(item.get("id"))
        if realtime:
            item["realtime"] = {
                "active_users": realtime.get("active_users", 0),
                "page_views_30m": realtime.get("page_views_30m", 0),
            }
    doctor = copy.deepcopy(_module_data.get("doctor", {}))
    doctor["data_modules"] = [{
        "id": name,
        "status": meta.get("status", "loading"),
        "latency_ms": meta.get("latency_ms"),
        "updated_at": meta.get("updated_at", ""),
    } for name, meta in _module_meta.items() if name not in {"doctor", "services"}]
    errors = [
        f"{name}: {meta['error']}"
        for name, meta in _module_meta.items() if meta.get("error")
    ]
    _snapshot = {
        "v": CACHE_VERSION,
        "status": _snapshot_status_locked(),
        "generated_at": _iso(),
        # Backward-compatible fields consumed by the current dashboard.
        "emails": copy.deepcopy(_module_data["emails"]),
        "tasks": copy.deepcopy(_module_data["tasks"]),
        "calendar": copy.deepcopy(_module_data["calendar"]),
        "weather": copy.deepcopy(_module_data["weather"]),
        "system": copy.deepcopy(_module_data["system"]),
        "analytics": copy.deepcopy(_module_data["analytics"]),
        "memory": copy.deepcopy(_module_data["memory"]),
        "approvals": copy.deepcopy(_module_data["approvals"]),
        "action_capabilities": {
            "requires_exact_id": True,
            "requires_confirmation": True,
            "approve": {"method": "POST", "path": "/actions/approve"},
            "reject": {"method": "POST", "path": "/actions/reject"},
        },
        "services": services,
        "errors": errors,
        # New persistent-rail modules.
        "inbox_intelligence": copy.deepcopy(_module_data["inbox_intelligence"]),
        "today_command_queue": copy.deepcopy(_module_data["today_command_queue"]),
        "meeting_prep": copy.deepcopy(_module_data["meeting_prep"]),
        "analytics_realtime": copy.deepcopy(_module_data["analytics_realtime"]),
        "analytics_portfolio": portfolio,
        "files": copy.deepcopy(_module_data["files"]),
        "workspace_sync": copy.deepcopy(_module_data["workspace_sync"]),
        "news": copy.deepcopy(_module_data["news"]),
        "monitors": copy.deepcopy(_module_data["monitors"]),
        "alerts": copy.deepcopy(_module_data["monitors"].get("timeline", [])),
        "mode": copy.deepcopy(_module_data["mode"]),
        "routines": copy.deepcopy(_module_data["routines"]),
        "doctor": doctor,
        # Freshness/status metadata is intentionally separate from module data.
        "modules": copy.deepcopy(_module_meta),
    }
    _snapshot_bytes = json.dumps(_snapshot, separators=(",", ":"), default=str).encode("utf-8")
    _etag = hashlib.sha256(_snapshot_bytes).hexdigest()


def _cache_payload_locked() -> dict:
    names = [name for name, spec in SPECS.items() if spec.cache and name in _has_good]
    return {
        "v": CACHE_VERSION,
        "saved_at": _iso(),
        "data": {name: copy.deepcopy(_module_data[name]) for name in names},
        "meta": {name: copy.deepcopy(_module_meta[name]) for name in names},
    }


def _write_cache(payload: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_FILE.with_name(f".{CACHE_FILE.name}.{os.getpid()}.tmp")
    try:
        with _cache_write_lock:
            temporary.write_text(json.dumps(payload, separators=(",", ":"), default=str), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, CACHE_FILE)
            CACHE_FILE.chmod(0o600)
    except Exception:
        logger.exception("failed to persist dashboard cache")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _load_cache_locked() -> None:
    if not CACHE_FILE.exists():
        return
    try:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if cached.get("v") != CACHE_VERSION:
            return
        data = cached.get("data", {})
        old_meta = cached.get("meta", {})
        for name, value in data.items():
            if name not in SPECS or not SPECS[name].cache:
                continue
            _module_data[name] = value
            _has_good.add(name)
            meta = _module_meta[name]
            prior = old_meta.get(name, {})
            meta.update({
                "status": "stale",
                "updated_at": prior.get("updated_at", cached.get("saved_at", "")),
                "stale_at": prior.get("stale_at", cached.get("saved_at", "")),
                "revision": int(prior.get("revision", 0)),
                "error": None,
            })
        logger.info("loaded cached dashboard data for %s modules", len(_has_good))
    except Exception:
        logger.exception("ignored invalid dashboard cache")


def initialize() -> None:
    global _module_meta
    with _lock:
        _module_meta = {name: _new_meta(name) for name in SPECS}
        _load_cache_locked()
        _rebuild_snapshot_locked()


def _record_result(name: str, started: float, future: Future) -> None:
    global _cache_dirty
    finished_at = _utc_now()
    latency_ms = round((time.monotonic() - started) * 1000)
    try:
        raw = future.result()
        collected = raw if isinstance(raw, Collected) else Collected(raw)
    except Exception as exc:
        message = _clean_error(exc)
        logger.warning("dashboard source %s failed: %s", name, message)
        with _lock:
            meta = _module_meta[name]
            meta.update({
                "status": "stale" if name in _has_good else "error",
                "last_attempt_at": finished_at.isoformat(),
                "latency_ms": latency_ms,
                "consecutive_failures": meta["consecutive_failures"] + 1,
                "refreshing": False,
                "error": message,
            })
            delay = min(SPECS[name].interval * (2 ** min(meta["consecutive_failures"], 4)), 3600)
            _next_due[name] = time.monotonic() + delay
            meta["next_refresh_at"] = (finished_at + timedelta(seconds=delay)).isoformat()
            _in_flight.discard(name)
            _rebuild_snapshot_locked()
        return

    with _lock:
        _module_data[name] = collected.data
        _has_good.add(name)
        spec = SPECS[name]
        meta = _module_meta[name]
        meta.update({
            "status": "degraded" if collected.warning else "ok",
            "updated_at": finished_at.isoformat(),
            "last_attempt_at": finished_at.isoformat(),
            "next_refresh_at": (finished_at + timedelta(seconds=spec.interval)).isoformat(),
            "stale_at": (finished_at + timedelta(seconds=spec.stale_after)).isoformat(),
            "latency_ms": latency_ms,
            "revision": meta["revision"] + 1,
            "consecutive_failures": 0,
            "refreshing": False,
            "error": collected.warning or None,
        })
        _next_due[name] = time.monotonic() + spec.interval
        _in_flight.discard(name)
        _cache_dirty = _cache_dirty or spec.cache
        _rebuild_snapshot_locked()


def _submit(name: str) -> None:
    assert _executor is not None
    with _lock:
        if name in _in_flight:
            return
        _in_flight.add(name)
        _module_meta[name]["refreshing"] = True
        _module_meta[name]["last_attempt_at"] = _iso()
        # Reserve the normal interval immediately; the callback adjusts it for failures.
        _next_due[name] = time.monotonic() + SPECS[name].interval
        _rebuild_snapshot_locked()
    started = time.monotonic()
    future = _executor.submit(SPECS[name].collector)
    future.add_done_callback(lambda item, module=name, began=started: _record_result(module, began, item))


def _mark_expired_locked() -> bool:
    changed = False
    now = _utc_now()
    for name in _has_good:
        meta = _module_meta[name]
        stale_at = meta.get("stale_at")
        if not stale_at or meta["status"] in {"error", "stale"}:
            continue
        try:
            if datetime.fromisoformat(stale_at) <= now:
                meta["status"] = "stale"
                meta["error"] = "Last update is stale."
                changed = True
        except ValueError:
            continue
    return changed


def _scheduler() -> None:
    global _cache_dirty, _last_cache_write
    logger.info("dashboard module scheduler started (%s workers)", MAX_WORKERS)
    while not _stop.is_set():
        now = time.monotonic()
        for name in SPECS:
            if now >= _next_due[name] and name not in _in_flight:
                _submit(name)

        cache_payload = None
        with _lock:
            if _mark_expired_locked():
                _rebuild_snapshot_locked()
            if _cache_dirty and now - _last_cache_write >= CACHE_WRITE_SECONDS:
                cache_payload = _cache_payload_locked()
                _cache_dirty = False
                _last_cache_write = now
        if cache_payload is not None:
            _write_cache(cache_payload)
        _stop.wait(0.25)


def start_scheduler() -> None:
    global _executor, _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop.clear()
    _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="dashboard")
    _scheduler_thread = threading.Thread(target=_scheduler, name="dashboard-scheduler", daemon=True)
    _scheduler_thread.start()


def stop_scheduler() -> None:
    global _executor
    _stop.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=3)
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def current_snapshot() -> dict:
    """Return a copy of cached state; this never performs upstream work."""
    with _lock:
        return copy.deepcopy(_snapshot)


def _refresh_soon(*names: str) -> None:
    """Invalidate cached modules after a confirmed local action."""
    with _lock:
        for name in names:
            if name in _next_due:
                _next_due[name] = 0.0


_ACTION_ID = re.compile(r"^[0-9a-f]{8}$")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/snapshot", "/health"):
            self.send_error(404)
            return
        with _lock:
            if path == "/health":
                data = {
                    "status": _snapshot.get("status", "starting"),
                    "generated_at": _snapshot.get("generated_at", ""),
                    "scheduler_alive": bool(_scheduler_thread and _scheduler_thread.is_alive()),
                    "modules": copy.deepcopy(_module_meta),
                }
                payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
                etag = hashlib.sha256(payload).hexdigest()
            else:
                payload = _snapshot_bytes
                etag = _etag
        if self.headers.get("If-None-Match", "").strip('"') == etag:
            self.send_response(304)
            self.send_header("ETag", f'"{etag}"')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("ETag", f'"{etag}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/actions/approve", "/actions/reject", "/actions/dismiss"):
            self._send_json(404, {"ok": False, "error": "Unknown local action."})
            return
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self._send_json(415, {"ok": False, "error": "Content-Type must be application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 2 or length > 4096:
            self._send_json(400, {"ok": False, "error": "Invalid request size."})
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON."})
            return
        if not isinstance(body, dict) or body.get("confirm") is not True:
            self._send_json(400, {"ok": False, "error": "Explicit confirmation is required."})
            return
        action_id = body.get("id")
        if not isinstance(action_id, str) or not _ACTION_ID.fullmatch(action_id):
            self._send_json(400, {"ok": False, "error": "An exact eight-character approval ID is required."})
            return
        try:
            if path == "/actions/approve":
                item = productivity.approve_action(action_id)
                _refresh_soon("approvals", "tasks", "today_command_queue")
                verb = "approved"
            else:
                item = productivity.reject_action(action_id)
                _refresh_soon("approvals", "today_command_queue")
                verb = "rejected"
        except ValueError as exc:
            self._send_json(409, {"ok": False, "error": _clean_error(exc)})
            return
        except Exception as exc:
            logger.warning("local dashboard action failed: %s", type(exc).__name__)
            self._send_json(502, {
                "ok": False,
                "error": "The approved action could not be completed safely; review the approval queue.",
            })
            return
        self._send_json(200, {
            "ok": True,
            "action": verb,
            "item": {
                "id": item.get("id", ""),
                "kind": item.get("kind", ""),
                "title": item.get("title", ""),
                "status": item.get("status", ""),
                "approved_at": item.get("approved_at", ""),
                "rejected_at": item.get("rejected_at", ""),
            },
        })

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    start_scheduler()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    logger.info("dashboard data feed listening on http://127.0.0.1:%s", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_scheduler()


initialize()


if __name__ == "__main__":
    main()
