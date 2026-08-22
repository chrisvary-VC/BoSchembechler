"""The voice loop: listen, think, speak — and stash the room so tools can draw.

Run with:  python3 agent.py dev
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, StopResponse
from livekit.plugins import deepgram, elevenlabs, silero

from llm_provider import check_ollama, create_llm
import render
import operations
import tools
from prompts import GREETING, INSTRUCTIONS

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aios.agent")

REQUIRED = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
]


def check_env() -> None:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise SystemExit(
            "Refusing to start. Missing in .env: " + ", ".join(missing)
        )
    check_ollama()


class Jarvis(Agent):
    def __init__(self) -> None:
        active = operations.mode()
        mode_instruction = f"\n## Active operating mode\n{active['mode'].title()}: {active['description']}\n"
        super().__init__(instructions=INSTRUCTIONS + mode_instruction, tools=tools.ALL_TOOLS)
        self.awaiting_brief_confirmation = True

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Route screen-critical intents deterministically before the small LLM."""
        text = (new_message.raw_text_content or "").strip().lower()
        affirmative = bool(re.fullmatch(r"(yes|yeah|yep|please|go ahead)[.! ]*", text))
        explicit_brief = "brief" in text and any(
            word in text for word in ("show", "give", "refresh", "screen", "display", "pull", "bring")
        )
        if (self.awaiting_brief_confirmation and affirmative) or explicit_brief:
            self.awaiting_brief_confirmation = False
            await tools.deliver_daily_brief(self.session)
            raise StopResponse()
        # The small local model sometimes narrates a news result without making
        # the tool call. News always needs a live fetch and a render event, so
        # route that screen-critical intent before generation.
        news_request = bool(re.search(r"\b(news|headlines|top stories)\b", text))
        if news_request:
            topic = ""
            match = re.search(r"\b(?:news|headlines)\s+(?:about|on)\s+(.+?)[.!?]*$", text)
            if match:
                topic = match.group(1).strip()
            await tools.deliver_news(self.session, topic)
            raise StopResponse()
        if "jarvis doctor" in text or "system check" in text:
            checks = await asyncio.to_thread(operations.doctor)
            rows = [{"rank": i + 1, "title": x["name"], "why": x["detail"], "effort": "ONLINE" if x["ok"] else "FAILED"} for i, x in enumerate(checks)]
            failed = [x for x in checks if not x["ok"]]
            spoken = "All Jarvis systems passed." if not failed else f"{len(failed)} systems need attention."
            result = await render.render(type=render.ACTIONS, tool="run_jarvis_doctor", spoken=spoken, title="Jarvis Doctor", payload={"items": rows})
            await self.session.say(result, allow_interruptions=False)
            raise StopResponse()
        if re.search(r"\b(check|show|run) (?:my )?monitors\b", text):
            report = await asyncio.to_thread(operations.check_monitors)
            await tools.deliver_monitor_report(self.session, report)
            raise StopResponse()
        research_match = re.search(r"\b(?:deeply research|deep research|research)\s+(.+?)[.!?]*$", text)
        if research_match:
            query = research_match.group(1).strip()
            d = await asyncio.to_thread(operations.deep_research, query)
            items = [{"when": "Web", "source": x["title"], "who": tools.urllib_host(x["url"]), "quote": x["excerpt"] or x["title"], "url": x["url"]} for x in d["sources"]]
            spoken = f"Research found {len(d['sources'])} cited web sources. They're on screen."
            result = await render.render(type=render.INTEL, tool="deep_research", spoken=spoken, title=f'Research · "{query}"', payload={"query": query, "items": items})
            await self.session.say(result, allow_interruptions=False)
            raise StopResponse()
        self.awaiting_brief_confirmation = False


async def monitor_loop(session) -> None:
    """Check for meaningful Gmail/Analytics changes every fifteen minutes."""
    while True:
        await asyncio.sleep(operations.MONITOR_INTERVAL_SECONDS)
        try:
            report = await asyncio.to_thread(operations.check_monitors)
            if report.get("alerts"):
                await tools.deliver_monitor_report(session, report)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("background monitor check failed")


async def entrypoint(ctx: agents.JobContext) -> None:
    check_env()
    await ctx.connect()

    # Tools publish render events through this room.
    render.set_room(ctx.room)
    logger.info("Connected to room %s", ctx.room.name)

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=create_llm(),
        tts=elevenlabs.TTS(
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
            model=os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            voice_settings=elevenlabs.VoiceSettings(
                stability=float(os.getenv("ELEVENLABS_STABILITY", "0.35")),
                similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY", "0.75")),
                style=float(os.getenv("ELEVENLABS_STYLE", "0.45")),
                use_speaker_boost=True,
            ),
        ),
        vad=silero.VAD.load(),
        turn_handling={"interruption": {"mode": "vad"}},
    )

    await session.start(
        room=ctx.room,
        agent=Jarvis(),
        room_input_options=RoomInputOptions(),
    )
    await session.say(GREETING, allow_interruptions=False)
    if operations.digest_due():
        try:
            await tools.deliver_daily_brief(session)
            operations.mark_digest_delivered()
        except Exception:
            logger.exception("scheduled morning digest failed")
    asyncio.create_task(monitor_loop(session))


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
