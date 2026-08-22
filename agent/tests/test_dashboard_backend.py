from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import dashboard_feed
import operations
import productivity


class ApprovalQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory()
        root = Path(self.scratch.name)
        self.files = patch.multiple(
            productivity,
            QUEUE_FILE=root / "queue.json",
            QUEUE_LOCK=root / "queue.lock",
        )
        self.files.start()

    def tearDown(self) -> None:
        self.files.stop()
        self.scratch.cleanup()

    def test_concurrent_proposals_are_not_lost(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            created = list(pool.map(
                lambda index: productivity.propose_google_task(f"Test {index}"),
                range(20),
            ))
        self.assertEqual(len(productivity.pending_actions()), 20)
        self.assertEqual(len({item["id"] for item in created}), 20)

    def test_reject_requires_exact_id_and_confirmation(self) -> None:
        item = productivity.propose_google_task("Safe test")
        server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_feed.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"

            def post(body: dict) -> tuple[int, dict]:
                request = urllib.request.Request(
                    base + "/actions/reject",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=2) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as exc:
                    return exc.code, json.load(exc)

            self.assertEqual(post({"id": item["id"], "confirm": False})[0], 400)
            self.assertEqual(post({"id": "wrong", "confirm": True})[0], 400)
            status, result = post({"id": item["id"], "confirm": True})
            self.assertEqual(status, 200)
            self.assertEqual(result["item"]["status"], "rejected")
            self.assertEqual(productivity.pending_actions(), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class CacheTests(unittest.TestCase):
    def test_failed_refresh_preserves_last_good_value(self) -> None:
        name = "tasks"
        with dashboard_feed._lock:
            old_data = dashboard_feed._module_data[name]
            old_meta = dict(dashboard_feed._module_meta[name])
            old_good = name in dashboard_feed._has_good
            dashboard_feed._module_data[name] = []
            dashboard_feed._module_meta[name] = dashboard_feed._new_meta(name)
            dashboard_feed._has_good.discard(name)
        try:
            success = Future()
            success.set_result([{"id": "last-good"}])
            dashboard_feed._record_result(name, 0.0, success)
            failure = Future()
            failure.set_exception(RuntimeError("temporary upstream failure"))
            dashboard_feed._record_result(name, 0.0, failure)
            snapshot = dashboard_feed.current_snapshot()
            self.assertEqual(snapshot["tasks"], [{"id": "last-good"}])
            self.assertEqual(snapshot["modules"][name]["status"], "stale")
        finally:
            with dashboard_feed._lock:
                dashboard_feed._module_data[name] = old_data
                dashboard_feed._module_meta[name] = old_meta
                if old_good:
                    dashboard_feed._has_good.add(name)
                else:
                    dashboard_feed._has_good.discard(name)
                dashboard_feed._rebuild_snapshot_locked()


class AlertTimelineTests(unittest.TestCase):
    def test_repeated_alert_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            operations, "ALERTS_FILE", Path(directory) / "alerts.json"
        ):
            first = operations.record_alert(
                source="Gmail", title="Important email", dedupe_key="same"
            )
            operations.record_alert(
                source="Gmail", title="Important email again", dedupe_key="same"
            )
            timeline = operations.alerts_timeline()
            self.assertEqual(len(timeline), 1)
            self.assertEqual(timeline[0]["id"], first["id"])
            self.assertEqual(timeline[0]["occurrences"], 2)


class DashboardRelevanceTests(unittest.TestCase):
    def test_bulk_unread_mail_is_not_priority(self) -> None:
        labels = {"UNREAD", "IMPORTANT", "CATEGORY_PROMOTIONS"}
        self.assertEqual(
            dashboard_feed._gmail_priority_flags({}, labels, "mail", {"mail"}),
            (True, False, False),
        )
        newsletter = {"list-id": "<updates.example.com>"}
        self.assertEqual(
            dashboard_feed._gmail_priority_flags(
                newsletter, {"UNREAD", "IMPORTANT", "CATEGORY_PRIMARY"}, "mail", {"mail"}
            ),
            (True, False, False),
        )

    def test_non_bulk_important_and_starred_mail_are_actionable(self) -> None:
        self.assertEqual(
            dashboard_feed._gmail_priority_flags(
                {}, {"UNREAD", "IMPORTANT", "CATEGORY_PRIMARY"}, "mail", {"mail"}
            ),
            (False, True, True),
        )
        self.assertEqual(
            dashboard_feed._gmail_priority_flags({}, {"STARRED"}, "mail", {"mail"}),
            (False, True, True),
        )

    def test_meeting_selector_rejects_all_day_birthdays_and_declines(self) -> None:
        all_day = {
            "eventType": "birthday", "start": {"date": "2026-08-20"},
            "end": {"date": "2026-08-21"},
        }
        declined = {
            "eventType": "default", "start": {"dateTime": "2026-08-21T10:00:00Z"},
            "end": {"dateTime": "2026-08-21T11:00:00Z"},
            "attendees": [{"self": True, "responseStatus": "declined"}, {"email": "guest@example.com"}],
        }
        real = {
            "eventType": "default", "start": {"dateTime": "2026-08-21T12:00:00Z"},
            "end": {"dateTime": "2026-08-21T13:00:00Z"},
            "attendees": [{"self": True}, {"email": "guest@example.com"}],
        }
        self.assertIs(dashboard_feed._select_meeting_candidate([all_day, declined, real]), real)

    def test_meeting_queue_window_excludes_far_future_and_ended(self) -> None:
        now = datetime(2026, 8, 20, 18, tzinfo=timezone.utc)
        base = {
            "queue_eligible": True,
            "phase": "upcoming",
            "end": (now + timedelta(hours=2)).isoformat(),
        }
        self.assertTrue(dashboard_feed._meeting_queue_due({**base, "starts_in_minutes": 90}, now))
        self.assertFalse(dashboard_feed._meeting_queue_due({**base, "starts_in_minutes": 240}, now))
        active = {**base, "phase": "in_progress", "starts_in_minutes": -30}
        self.assertTrue(dashboard_feed._meeting_queue_due(active, now))
        ended = {**base, "phase": "in_progress", "starts_in_minutes": -90, "end": (now - timedelta(minutes=1)).isoformat()}
        self.assertFalse(dashboard_feed._meeting_queue_due(ended, now))


if __name__ == "__main__":
    unittest.main()
