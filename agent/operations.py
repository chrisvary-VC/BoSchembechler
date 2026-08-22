"""Health, modes, synchronization, monitoring, and local deep research."""

from __future__ import annotations

import json
import hashlib
import os
import re
import socket
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import aios_data
import lifestyle
import productivity
from services import SECRETS, dropbox_client, google_service

STATE_FILE = SECRETS / "operations-state.json"
ALERTS_FILE = SECRETS / "alerts-timeline.json"
_state_lock = threading.RLock()
try:
    MONITOR_INTERVAL_SECONDS = max(60, int(os.getenv("AIOS_MONITOR_INTERVAL_SECONDS", "900")))
except ValueError:
    MONITOR_INTERVAL_SECONDS = 900
MODES = {
    "executive": "Brief, email, calendar, tasks, and analytics first.",
    "research": "Prefer sourced research and private-memory retrieval.",
    "monitor": "Prioritize important changes and anomalies.",
    "creative": "Prefer exploratory ideas and concise options.",
    "private": "Use local memory and local inference; avoid web search unless explicitly requested.",
    "operator": "Prefer system status and safe computer actions.",
}


def _state() -> dict:
    if STATE_FILE.exists():
        try:
            value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            pass
    return {"mode": "executive", "digest_hour": 8, "monitor": {}}


def _save(state: dict) -> None:
    with _state_lock:
        SECRETS.mkdir(parents=True, exist_ok=True)
        temporary = STATE_FILE.with_name(f".{STATE_FILE.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, STATE_FILE)
        STATE_FILE.chmod(0o600)


def _alert_id(source: str, title: str, dedupe_key: str = "") -> str:
    raw = dedupe_key.strip() or f"{source.strip().lower()}:{title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_alerts() -> list[dict]:
    if not ALERTS_FILE.exists():
        return []
    try:
        value = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_alerts(items: list[dict]) -> None:
    SECRETS.mkdir(parents=True, exist_ok=True)
    temporary = ALERTS_FILE.with_name(f".{ALERTS_FILE.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(items[:100], indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, ALERTS_FILE)
    ALERTS_FILE.chmod(0o600)


def record_alert(
    *, source: str, title: str, detail: str = "", severity: str = "warning",
    dedupe_key: str = "", detected_at: str = "",
) -> dict:
    """Persist one alert, updating its occurrence count instead of duplicating it."""
    now = detected_at or datetime.now(timezone.utc).isoformat()
    alert_id = _alert_id(source, title, dedupe_key)
    with _state_lock:
        items = _read_alerts()
        existing = next((item for item in items if item.get("id") == alert_id), None)
        if existing:
            existing.update({
                "source": source,
                "title": title,
                "detail": detail,
                "severity": severity,
                "last_seen_at": now,
                "occurrences": int(existing.get("occurrences", 1)) + 1,
                "active": True,
            })
            alert = existing
        else:
            alert = {
                "id": alert_id,
                "source": source,
                "title": title,
                "detail": detail,
                "severity": severity,
                "first_seen_at": now,
                "last_seen_at": now,
                "occurrences": 1,
                "active": True,
            }
            items.append(alert)
        items.sort(key=lambda item: item.get("last_seen_at", ""), reverse=True)
        _write_alerts(items)
        return dict(alert)


def alerts_timeline(limit: int = 30) -> list[dict]:
    """Return the persistent deduplicated alert timeline, newest first."""
    with _state_lock:
        items = _read_alerts()
    items.sort(key=lambda item: item.get("last_seen_at", ""), reverse=True)
    return items[: max(1, min(int(limit), 100))]


def set_mode(mode: str) -> dict:
    key = mode.strip().lower()
    aliases = {"deep research": "research", "website monitor": "monitor", "computer": "operator"}
    key = aliases.get(key, key)
    if key not in MODES:
        raise ValueError(f"Choose one of: {', '.join(MODES)}")
    state = _state()
    state["mode"] = key
    _save(state)
    return {"mode": key, "description": MODES[key]}


def mode() -> dict:
    state = _state()
    key = state.get("mode", "executive")
    return {"mode": key, "description": MODES.get(key, MODES["executive"])}


def configure_digest(hour: int = 8) -> dict:
    hour = max(0, min(int(hour), 23))
    state = _state()
    state["digest_hour"] = hour
    _save(state)
    return {"hour": hour, "label": datetime(2000, 1, 1, hour).strftime("%-I:00 %p")}


def digest_due() -> bool:
    state = _state()
    now = datetime.now().astimezone()
    return now.hour >= int(state.get("digest_hour", 8)) and state.get("last_digest_date") != now.date().isoformat()


def mark_digest_delivered() -> None:
    state = _state()
    state["last_digest_date"] = datetime.now().astimezone().date().isoformat()
    _save(state)


def doctor() -> list[dict]:
    checks = []
    web_port = int(os.getenv("AIOS_WEB_PORT", "4310"))
    for name, port in (("Dashboard", web_port), ("Voice room", 7880), ("Local AI", 11434)):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                checks.append({"name": name, "ok": True, "detail": f"port {port} responding"})
        except OSError as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)})
    probes = [
        ("Google Workspace", lambda: google_service("drive", "v3").about().get(fields="user").execute()),
        ("Google Tasks", lambda: google_service("tasks", "v1").tasklists().list(maxResults=1).execute()),
        ("Dropbox", lambda: dropbox_client().users_get_current_account()),
        ("Weather", lambda: lifestyle.weather()),
        ("News", lambda: lifestyle.news(limit=1)),
    ]
    for name, probe in probes:
        try:
            probe()
            checks.append({"name": name, "ok": True, "detail": "connected"})
        except Exception as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)[:120]})
    return checks


def sync_memory(limit: int = 20) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    limit = max(1, min(int(limit), 50))
    indexed = {"Google Drive": 0, "Dropbox": 0}
    errors = []
    drive = google_service("drive", "v3")
    fields = "files(id,name,mimeType,modifiedTime,webViewLink,size)"
    files = drive.files().list(q="trashed = false", pageSize=limit, orderBy="modifiedTime desc", fields=fields).execute().get("files", [])
    for item in files:
        text = f"Drive file: {item['name']}\nType: {item.get('mimeType','')}\nLink: {item.get('webViewLink','')}"
        try:
            if item.get("mimeType") == "application/vnd.google-apps.document":
                body = drive.files().export(fileId=item["id"], mimeType="text/plain").execute()
                text += "\n" + body.decode("utf-8", errors="replace")[:12000]
            productivity.remember(f"drive:{item['id']}", "Google Drive", item["name"], text, item.get("modifiedTime", ""))
            indexed["Google Drive"] += 1
        except Exception as exc:
            errors.append(f"Drive {item['name']}: {str(exc)[:80]}")
    try:
        dbx = dropbox_client()
        result = dbx.files_list_folder("", recursive=True, limit=limit)
        for item in result.entries[:limit]:
            if not hasattr(item, "path_lower"):
                continue
            text = f"Dropbox file: {item.name}\nPath: {item.path_display}"
            if item.name.lower().endswith((".txt", ".md", ".csv", ".json")) and getattr(item, "size", 0) <= 1_000_000:
                try:
                    _meta, response = dbx.files_download(item.path_lower)
                    text += "\n" + response.content.decode("utf-8", errors="replace")[:12000]
                except Exception:
                    pass
            productivity.remember(f"dropbox:{item.id}", "Dropbox", item.name, text, getattr(item, "server_modified", datetime.now(timezone.utc)).isoformat())
            indexed["Dropbox"] += 1
    except Exception as exc:
        errors.append(f"Dropbox: {str(exc)[:120]}")
    result = {
        "indexed": indexed,
        "total": sum(indexed.values()),
        "memory_total": productivity.memory_count(),
        "errors": errors[:5],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    state = _state()
    state["memory_sync"] = {
        "last_started_at": result["started_at"],
        "last_completed_at": result["completed_at"],
        "indexed": indexed,
        "memory_total": result["memory_total"],
        "errors": result["errors"],
    }
    _save(state)
    return result


def check_monitors() -> dict:
    state = _state()
    previous = state.setdefault("monitor", {})
    alerts = []
    checked_at = datetime.now(timezone.utc).isoformat()
    gmail = google_service("gmail", "v1")
    important = gmail.users().messages().list(userId="me", q="in:inbox is:important newer_than:1d", maxResults=20).execute()
    count = important.get("resultSizeEstimate", len(important.get("messages", [])))
    old_count = previous.get("important_email_count")
    if old_count is not None and count > old_count:
        alert = record_alert(
            source="Gmail",
            title=f"{count - old_count} new important email",
            detail=f"Important inbox count increased from {old_count} to {count}.",
            severity="warning",
            dedupe_key="gmail-important-email-increase",
            detected_at=checked_at,
        )
        alerts.append({**alert, "why": "Gmail monitor"})
    previous["important_email_count"] = count
    metrics = aios_data.get_metrics("active_users", 7)
    delta = metrics.get("delta_pct", 0)
    if abs(delta) >= 35:
        alert = record_alert(
            source="Google Analytics",
            title=f"Website traffic is {'up' if delta > 0 else 'down'} {abs(delta)}%",
            detail="Seven-day active-user trend crossed the configured 35 percent threshold.",
            severity="warning",
            dedupe_key=f"analytics-active-users-{'up' if delta > 0 else 'down'}",
            detected_at=checked_at,
        )
        alerts.append({**alert, "why": "Google Analytics anomaly"})
    previous["analytics_delta"] = delta
    previous["checked_at"] = checked_at
    previous["last_alert_ids"] = [item["id"] for item in alerts]
    _save(state)
    return {"alerts": alerts, "important_email_count": count, "analytics_delta": delta, "checked_at": previous["checked_at"]}


def _strip_html(raw: str) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def deep_research(query: str, limit: int = 5) -> dict:
    clean = query.strip()
    if not clean:
        raise ValueError("Research needs a topic.")
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": clean, "format": "rss"})
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JarvisAIOS"})
    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())
    sources = []
    for item in root.findall("./channel/item"):
        target = (item.findtext("link") or "").strip()
        if not target.startswith(("http://", "https://")):
            continue
        title = (item.findtext("title") or target).strip()
        excerpt = _strip_html(item.findtext("description") or "")[:900]
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0 JarvisAIOS"})
            with urllib.request.urlopen(req, timeout=8) as response:
                page_text = _strip_html(response.read(180_000).decode("utf-8", errors="replace"))[:900]
                if page_text:
                    excerpt = page_text
        except Exception:
            pass
        sources.append({"title": title, "url": target, "excerpt": excerpt})
        if len(sources) >= max(2, min(limit, 8)):
            break
    memories = productivity.search_memory(clean, limit=3) if productivity.memory_count() else []
    return {"query": clean, "sources": sources, "memories": memories}
