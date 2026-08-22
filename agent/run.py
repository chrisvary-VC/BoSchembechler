"""Direct room connection - no worker mode."""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import deepgram, elevenlabs, silero

from llm_provider import check_ollama, create_llm
import render
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
        raise SystemExit("Refusing to start. Missing in .env: " + ", ".join(missing))
    check_ollama()


class Jarvis(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS, tools=tools.ALL_TOOLS)


async def main():
    check_env()

    room_name = os.getenv("LIVEKIT_ROOM", "aios")
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    logger.info(f"Connecting to room: {room_name}")

    async with agents.VirtualParticipant.create(
        name="jarvis",
        room_name=room_name,
        url=url,
        token=agents.AccessToken(api_key=api_key, api_secret=api_secret).with_grants(
            agents.TokenGrants(can_publish=True, can_publish_data=True, can_subscribe=True)
        ).to_jwt(identity="jarvis"),
    ) as room:
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

        render.set_room(room)
        logger.info(f"Connected to room {room.name}")

        await session.start(
            room=room,
            agent=Jarvis(),
            room_input_options=RoomInputOptions(),
        )

        await session.say(GREETING, allow_interruptions=False)

        # Keep alive
        try:
            await asyncio.sleep(86400)
        except KeyboardInterrupt:
            logger.info("Shutting down")


if __name__ == "__main__":
    asyncio.run(main())
