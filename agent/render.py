"""The render-event builder and publish helper.

LOCKED CONTRACT — see ../CONTRACT.md.
The five type strings below are mirrored byte-for-byte in
web/src/lib/renderEvents.ts. Do not change one without the other, or the
agent will publish and the HUD will silently ignore it.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger("aios.render")

# ---- locked strings (mirror of web/src/lib/renderEvents.ts) ----
RENDER_TOPIC = "aios.render"
CONTRACT_VERSION = 1

BRIEF = "aios.brief"
METRICS = "aios.metrics"
PIPELINE = "aios.pipeline"
INTEL = "aios.intel"
ACTIONS = "aios.actions"

RENDER_TYPES = (BRIEF, METRICS, PIPELINE, INTEL, ACTIONS)
# ---- end locked strings ----

# agent.py stashes the room here once the job starts, so the tools can publish
# without threading the room through every call.
_room: Any = None


def set_room(room: Any) -> None:
    global _room
    _room = room


def build_event(
    *, type: str, tool: str, spoken: str, title: str, payload: dict
) -> dict:
    if type not in RENDER_TYPES:
        raise ValueError(f"{type!r} is not one of {RENDER_TYPES}")
    return {
        "v": CONTRACT_VERSION,
        "type": type,
        "id": uuid.uuid4().hex,
        "ts": int(time.time() * 1000),
        "tool": tool,
        "spoken": spoken,
        "title": title,
        "payload": payload,
    }


async def publish(event: dict) -> None:
    """Push a render event down the room data channel."""
    if _room is None:
        logger.warning("no room stashed; dropping %s", event.get("type"))
        return
    try:
        await _room.local_participant.publish_data(
            json.dumps(event).encode("utf-8"),
            reliable=True,
            topic=RENDER_TOPIC,
        )
        logger.info("published %s (%s)", event["type"], event["id"])
    except Exception:
        # A dead data channel must never take the voice down with it.
        logger.exception("failed to publish %s", event.get("type"))


async def render(
    *, type: str, tool: str, spoken: str, title: str, payload: dict
) -> str:
    """Build, publish, and return the spoken line. Tools end with this."""
    await publish(
        build_event(type=type, tool=tool, spoken=spoken, title=title, payload=payload)
    )
    return spoken
