"""Google Tasks, local approvals, and private semantic memory."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import SECRETS, google_service

QUEUE_FILE = SECRETS / "approval-queue.json"
QUEUE_LOCK = SECRETS / "approval-queue.lock"
MEMORY_DB = SECRETS / "memory.sqlite3"
EMBED_MODEL = os.getenv("AIOS_EMBED_MODEL", "nomic-embed-text")
_queue_thread_lock = threading.RLock()


@contextmanager
def _queue_guard():
    """Serialize queue updates across threads and local Jarvis processes."""
    import fcntl

    SECRETS.mkdir(parents=True, exist_ok=True)
    with _queue_thread_lock:
        with QUEUE_LOCK.open("a+", encoding="utf-8") as lock_file:
            QUEUE_LOCK.chmod(0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_queue_unlocked() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        value = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The local approval queue is unreadable.") from exc
    if not isinstance(value, list):
        raise RuntimeError("The local approval queue has an invalid format.")
    return value


def _write_queue_unlocked(items: list[dict]) -> None:
    temporary = QUEUE_FILE.with_name(f".{QUEUE_FILE.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(items, indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, QUEUE_FILE)
    QUEUE_FILE.chmod(0o600)


def _queue() -> list[dict]:
    with _queue_guard():
        return _read_queue_unlocked()


def _save_queue(items: list[dict]) -> None:
    with _queue_guard():
        _write_queue_unlocked(items)


def propose_google_task(title: str, notes: str = "", due: str = "") -> dict:
    item = {"id": uuid.uuid4().hex[:8], "kind": "google_task", "title": title.strip(), "notes": notes.strip(), "due": due.strip(), "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}
    with _queue_guard():
        items = _read_queue_unlocked()
        items.append(item)
        _write_queue_unlocked(items)
    return item


def pending_actions() -> list[dict]:
    with _queue_guard():
        return [dict(x) for x in _read_queue_unlocked() if x.get("status") == "pending"]


def approve_action(action_id: str) -> dict:
    with _queue_guard():
        items = _read_queue_unlocked()
        item = next((x for x in items if x.get("id") == action_id and x.get("status") == "pending"), None)
        if not item:
            raise ValueError(f"No pending action named {action_id}")
        item["status"] = "executing"
        item["execution_started_at"] = datetime.now(timezone.utc).isoformat()
        _write_queue_unlocked(items)
        work = dict(item)

    try:
        external_id = ""
        if work["kind"] == "google_task":
            tasks = google_service("tasks", "v1")
            lists = tasks.tasklists().list(maxResults=1).execute().get("items", [])
            if not lists:
                raise RuntimeError("No Google Tasks list is available")
            body = {"title": work["title"]}
            if work.get("notes"):
                body["notes"] = work["notes"]
            if work.get("due"):
                due = datetime.fromisoformat(work["due"]).replace(tzinfo=timezone.utc)
                body["due"] = due.isoformat().replace("+00:00", "Z")
            created = tasks.tasks().insert(tasklist=lists[0]["id"], body=body).execute()
            external_id = created["id"]
        else:
            raise ValueError(f"Unsupported approval action kind: {work.get('kind', '')}")
    except Exception as exc:
        with _queue_guard():
            items = _read_queue_unlocked()
            current = next((x for x in items if x.get("id") == action_id), None)
            if current and current.get("status") == "executing":
                current["status"] = "pending"
                current["last_error"] = type(exc).__name__
                current.pop("execution_started_at", None)
                _write_queue_unlocked(items)
        raise

    with _queue_guard():
        items = _read_queue_unlocked()
        item = next((x for x in items if x.get("id") == action_id and x.get("status") == "executing"), None)
        if not item:
            raise RuntimeError("Approval queue changed while the action was executing.")
        if external_id:
            item["external_id"] = external_id
        item["status"] = "approved"
        item["approved_at"] = datetime.now(timezone.utc).isoformat()
        item.pop("execution_started_at", None)
        item.pop("last_error", None)
        _write_queue_unlocked(items)
        return dict(item)


def reject_action(action_id: str) -> dict:
    """Reject one pending local proposal without making a cloud change."""
    with _queue_guard():
        items = _read_queue_unlocked()
        item = next((x for x in items if x.get("id") == action_id and x.get("status") == "pending"), None)
        if not item:
            raise ValueError(f"No pending action named {action_id}")
        item["status"] = "rejected"
        item["rejected_at"] = datetime.now(timezone.utc).isoformat()
        _write_queue_unlocked(items)
        return dict(item)


def list_google_tasks(limit: int = 10) -> list[dict]:
    tasks = google_service("tasks", "v1")
    lists = tasks.tasklists().list(maxResults=1).execute().get("items", [])
    if not lists:
        return []
    return tasks.tasks().list(tasklist=lists[0]["id"], showCompleted=False, maxResults=limit).execute().get("items", [])


def _db() -> sqlite3.Connection:
    SECRETS.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(MEMORY_DB)
    db.execute("CREATE TABLE IF NOT EXISTS memories (source_id TEXT PRIMARY KEY, source TEXT, title TEXT, text TEXT, updated_at TEXT, embedding TEXT)")
    return db


def _embed(texts: list[str]) -> list[list[float]]:
    data = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request("http://localhost:11434/api/embed", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)["embeddings"]


def remember(source_id: str, source: str, title: str, text: str, updated_at: str = "") -> None:
    vector = _embed([f"search_document: {title}\n{text[:6000]}"])[0]
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?,?)", (source_id, source, title, text, updated_at or datetime.now(timezone.utc).isoformat(), json.dumps(vector)))


def search_memory(query: str, limit: int = 6) -> list[dict]:
    qv = _embed([f"search_query: {query}"])[0]
    with _db() as db:
        rows = db.execute("SELECT source_id,source,title,text,updated_at,embedding FROM memories").fetchall()
    qn = math.sqrt(sum(v * v for v in qv)) or 1
    scored = []
    for source_id, source, title, text, updated_at, raw in rows:
        v = json.loads(raw)
        vn = math.sqrt(sum(x * x for x in v)) or 1
        score = sum(a * b for a, b in zip(qv, v)) / (qn * vn)
        scored.append({"id": source_id, "source": source, "title": title, "text": text, "updated_at": updated_at, "score": score})
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:limit]


def memory_count() -> int:
    with _db() as db:
        return db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
