# JARVIS AIOS — Build & Setup Guide

How the voice + glowing HUD system is wired, and how to get it running from scratch.
Roughly fifteen minutes once you have the keys.

## 1. What this actually is

A voice assistant with a face. You talk to it, it thinks with an LLM, it answers out
loud in a cloned voice, and a cinematic dashboard draws the matching panel in sync
with the speech.

Every answer travels two paths at once. The **voice path** speaks a short human
summary. The **visual path** pushes a structured render event to the dashboard, which
animates the right panel. Both fire from the same tool call, so screen and voice land
together.

- `agent/` — Python service: listen, think, speak, publish render events.
- `web/` — Next.js HUD: joins the same room, listens, animates.
- `seed/` — what it knows. Curated seed for filming, live databases for real use.

## 2. One request, end to end

```
you speak → LiveKit room → Deepgram (STT) → local Ollama picks one of five tools
                                                   │
                                      the tool pulls data (seed or live DB)
                                                   │
                        ┌──────────────────────────┴──────────────────────────┐
                        ▼                                                     ▼
             ElevenLabs speaks the summary                render event → HUD panel animates
```

The agent and the HUD are two clients in the same LiveKit room. That shared room is
the entire reason they stay in sync with no extra server.

## 3. The five things it can do

| Ask for… | Tool | Panel that animates |
| --- | --- | --- |
| "Brief me" | `get_daily_brief` | Brief card (summary + signal chips + sections) |
| "How are my subscribers trending?" | `query_metrics` | Glowing line chart over time |
| "What's in my pipeline / at risk?" | `get_pipeline` | Funnel + deal list, at-risk in red |
| "What was said about X?" | `search_intel` | Timeline of meetings and messages |
| "What should I work on today?" | `plan_my_day` | Prioritized action list |

The voice gives the headline; the screen carries the detail. That split is deliberate —
nobody wants an assistant reading sixteen numbers out loud.

## 4. The render-event contract (the load-bearing part)

Full spec in [CONTRACT.md](CONTRACT.md). In short:

- One transport: the LiveKit room data channel.
- One topic: `aios.render`.
- One envelope: `{ v, type, id, ts, tool, spoken, title, payload }`.
- Five types: `aios.brief`, `aios.metrics`, `aios.pipeline`, `aios.intel`, `aios.actions`.

`agent/render.py` and `web/src/lib/renderEvents.ts` hard-code those strings. If they
drift by one character the agent publishes happily and the HUD silently ignores it.
That is the number one failure mode; both files carry the warning.

Why a data channel instead of an HTTP endpoint? The HUD is already a participant in
the room — it has to be, to play the audio. Reusing that connection means no second
server, no CORS, and the panel switch arrives on the same pipe as the voice.

## 5. Real but seeded

One environment variable, `AIOS_DEMO_MODE`, picks the source:

- **`=1` (default, for filming).** Every tool reads the curated JSON in `seed/`.
  Hand-written, realistic, never changes. No database, no fumble.
- **`=0` (live).** Tools query real sources. If a live query fails or returns empty,
  it falls back to the same seed rather than showing a blank panel.

All of it lives in `agent/aios_data.py` — the only file that touches data, which keeps
the tools clean and the whole thing testable. The live functions (`_live_brief`,
`_live_metrics`, …) are stubs returning `None`; fill them in and live mode starts
using them, with the seed still there as the safety net.

## 6. How the smooth visuals are done

No video, no game engine — CSS animation and hand-rolled SVG, so it holds frame rate
while recording.

- **The brief types itself in.** A character count grows on `requestAnimationFrame`;
  chips fade in after, then section lines cascade on staggered CSS delays.
- **The line chart draws itself.** One SVG path animated from `stroke-dashoffset:
  4000` to `0`. The date axis is a separate crisp HTML row, so labels never distort
  when the chart stretches.
- **The funnel bars grow.** Stage bars scale out from the left; at-risk deals pulse red.
- **Everything glows.** Shared CSS variables define the cyan accent, dark ground, and
  glow. A scanline layer sits over the grid.
- **It replays every time.** Each panel is keyed on the event id, so React remounts it
  on every answer and the animations fire fresh on every take.
- **The voice sounds human.** Two levers: the persona in `agent/prompts.py` (tone
  examples plus a banned-words list — no "Understood", no "Absolutely"), and the
  ElevenLabs settings in `.env` (lower stability, a little style).

## 7. Setup, step by step

**Prerequisites:** Python 3.11+, Node 18+, Ollama, and accounts for LiveKit, Deepgram,
and ElevenLabs. The language model runs locally, so no OpenAI account or API key is needed.

> On this machine both installs are already done: `agent/.venv` runs Python 3.12
> (Homebrew) with livekit-agents 1.6.10 and all four plugins, and `web/node_modules`
> is populated. Steps 3 and 5 only need re-running if you move or clone the project.

### Step 1 — Get the keys

- LiveKit project URL, API key, API secret (one project).
- Deepgram API key (speech to text).
- Ollama running locally with the configured model (the brain).
- ElevenLabs API key plus a voice id (the spoken voice).

### Step 2 — Configure the agent

```bash
cd projects/jarvis-aios
cp .env.example .env
```

Fill in every key. Leave `AIOS_DEMO_MODE=1` for filming. The agent refuses to start
without a voice id, on purpose, so it can never fall back to a stranger's voice on camera.

Install and prepare the local model once:

```bash
ollama pull gemma4:12b
```

Ollama normally starts automatically. If it is not running, use `ollama serve`.

### Step 3 — Install and run the agent

```bash
cd projects/jarvis-aios/agent
/opt/homebrew/bin/python3.12 -m venv .venv     # already done here
source .venv/bin/activate
pip install -r requirements.txt                # already done here
python3 agent.py dev
```

`python3 agent.py console` runs the same loop entirely in the terminal — handy for
testing the voice and the tools before you bring the HUD up.

You should see `Connected to room`. Leave it running.

### Step 4 — Point the HUD at the same room

```bash
cd projects/jarvis-aios/web
cp .env.example .env.local
```

Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and
`NEXT_PUBLIC_LIVEKIT_URL` to the **same project the agent uses**. Different projects
mean different rooms and nothing shows up.

### Step 5 — Install and run the HUD

```bash
cd projects/jarvis-aios/web
npm install
npm run dev
```

Open http://127.0.0.1:4310, unlock the private console, click **Engage**, and allow
the microphone.

### Step 6 — Talk to it

1. "JARVIS, brief me." — the brief card types in.
2. "How are my subscribers trending?" — the line draws across the date axis.
3. "What's at risk in my pipeline?" — the funnel grows, at-risk deals pulse red.
4. "What was said about Northwind?" — the timeline reveals.
5. "What should I work on today?" — the action list cascades.

If the voice answers but the panel does not change, that is almost always the room
mismatch from Step 4.

### Bonus — style the HUD without any keys

```bash
cd projects/jarvis-aios/web && npm run dev
```

Then open http://127.0.0.1:4310/preview. Every panel renders straight from the seed
files, with buttons to replay each animation. No room, no microphone, no keys.

### Private remote access

The web console includes a server-side access gate. Configure these in the ignored
`web/.env.local` file:

```dotenv
JARVIS_GATE_PASSWORD_HASH=scrypt:YOUR_RANDOM_SALT:YOUR_SCRYPT_HASH
JARVIS_SESSION_SECRET=YOUR_RANDOM_32_BYTE_SECRET
```

The raw password must not be committed. The dashboard issues a signed, HTTP-only
session cookie after a successful unlock, and automatically expires it after 12
hours. To access Jarvis away from home without opening inbound firewall ports, use
an outbound HTTPS tunnel pointed only at `http://127.0.0.1:4310`. Keep ports `8788`
and `11434` private. Remote access works only while this Mac and the local Jarvis
services are running.

## 8. Tuning and troubleshooting

| Symptom | Fix |
| --- | --- |
| Voice too flat | Drop `ELEVENLABS_STABILITY` toward 0.3; raise `ELEVENLABS_STYLE`. Too swingy: back toward 0.5. |
| Voice talks, no panel moves | Agent and HUD in different LiveKit projects, or the five type strings drifted between `agent/render.py` and `web/src/lib/renderEvents.ts`. |
| A panel comes up empty | A seed filename no longer matches `SEED_FILES` in `agent/aios_data.py`. Run `cd seed && python3 verify_seed.py`. |
| The brief is blank | The brief seed is `daily_brief.json`, not `brief.json`. The data layer maps the short name; update the map if you rename. |
| 401 from a provider | Test each key before filming. One dead key crashes the whole voice loop. |

## 9. File map

```
projects/jarvis-aios/
  agent/
    agent.py        # voice loop: STT, LLM, TTS, VAD; stashes the room for tools
    tools.py        # the 5 tools; each speaks AND publishes a render event
    render.py       # render-event builder + publish helper (locked contract)
    aios_data.py    # the only file that reads data; demo mode + seed fallback
    prompts.py      # the JARVIS persona and greeting (tone, banned words)
    requirements.txt
  web/
    src/lib/renderEvents.ts     # the TS mirror of the locked contract
    src/lib/useRenderEvents.ts  # subscribes to the data channel, routes by type
    src/components/HudStage.tsx # panel router + idle state
    src/components/panels/*.tsx # one component per render type
    src/app/globals.css         # the glow, the animations, the theme
    src/app/api/token/route.ts  # mints the HUD's LiveKit token
    src/app/preview/page.tsx    # every panel from seed, no keys needed
  seed/
    daily_brief.json metrics.json pipeline.json intel.json actions.json
    verify_seed.py   # validates every seed against the contract
    DEMO_RUNBOOK.md  # the on-camera script
  CONTRACT.md        # the human-readable render-event contract
  SETUP_GUIDE.md     # this document
```

All names and figures in the seed are fictional. The system is real; the demo data is
made up so nothing private ends up on camera.
