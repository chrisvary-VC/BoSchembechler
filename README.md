# JARVIS AIOS

A voice assistant with a face. You talk to it, an LLM thinks, a cloned voice answers,
and a cinematic HUD draws the matching panel in sync with the speech.

The one idea that makes it feel alive: **every answer travels two paths at once.**
The voice path speaks a short human summary; the visual path publishes a structured
render event to the dashboard. Both fire from the same tool call, so the screen and
the voice land together.

```
you speak ─► LiveKit room ─► Deepgram (STT) ─► local Ollama picks a tool
                                                      │
                              ┌───────────────────────┴────────────────────┐
                              ▼                                            ▼
                   ElevenLabs speaks the summary            render event ─► HUD panel animates
```

## Three moving parts

- **`agent/`** — Python service: listen, think, speak, publish render events.
- **`web/`** — Next.js HUD: joins the same room, listens for render events, animates panels.
- **`seed/`** — what it knows. Curated seed for filming; live databases for real use.

## The five things it can do

| Ask for | Tool | Panel |
| --- | --- | --- |
| "Brief me" | `get_daily_brief` | Brief card: summary + signals + chips |
| "How are subscribers trending?" | `query_metrics` | Glowing line chart |
| "What's at risk?" | `get_pipeline` | Funnel + deal list, at-risk in red |
| "What was said about X?" | `search_intel` | Timeline of meetings and messages |
| "What should I work on?" | `plan_my_day` | Prioritized action list |

The voice gives the headline; the screen carries the detail. Nobody wants an
assistant reading sixteen numbers out loud.

## Quick start

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for the full walkthrough. Short version:

```bash
cp .env.example .env                 # fill in LiveKit, Deepgram, and ElevenLabs
cd agent && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull gemma4:12b && python3 agent.py dev
```

```bash
cd web && cp .env.example .env.local  # SAME LiveKit project as the agent
npm install && npm run dev            # http://127.0.0.1:4310 → unlock, then Engage
```

## Private access

The dashboard, live data APIs, and voice-token route are protected by a signed,
expiring server-side session. Put a salted password hash in
`JARVIS_GATE_PASSWORD_HASH` and a separate random secret in
`JARVIS_SESSION_SECRET`; both belong in the ignored `web/.env.local`, never in Git.

For free remote access, run the dashboard locally on port `4310` and point an
authenticated outbound tunnel only at `http://127.0.0.1:4310`. Never publish the
dashboard feed (`8788`), Ollama (`11434`), or LiveKit's local control port directly.
The local Mac and Jarvis services must remain running for a tunnel URL to work.

## The load-bearing part

[CONTRACT.md](CONTRACT.md). Five type strings, one topic, one envelope shape,
mirrored byte-for-byte in `agent/render.py` and `web/src/lib/renderEvents.ts`.
Change one without the other and the agent publishes into the void.

All names and figures in the seed are fictional.
