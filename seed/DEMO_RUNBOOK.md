# On-camera runbook

## Thirty seconds before you roll

```bash
cd seed && python3 verify_seed.py     # must print PASS five times
```

Confirm `AIOS_DEMO_MODE=1` in `.env`. Confirm the agent log says `Connected to room`.
Confirm the HUD is at `http://127.0.0.1:4310`, unlocked, engaged, mic allowed, and
the idle ring is pulsing.

## The script, in order

| # | Say | What should happen |
| --- | --- | --- |
| 1 | "JARVIS, brief me." | Summary types itself in, chips fade up, section lines cascade. Northwind chip is red. |
| 2 | "How are my subscribers trending?" | Line draws left to right across the date axis, +12.6%. |
| 3 | "What's at risk in my pipeline?" | Funnel bars grow from the left; Northwind and Cedar & Vale pulse red. |
| 4 | "What was said about Northwind?" | Timeline of two mentions; Dana Reyes on top. |
| 5 | "What should I work on today?" | Five ranked actions reveal one by one. |

Every panel is keyed on the event id, so all of these replay fresh on retakes.
Ask the same question twice and the animation runs again.

## If something goes wrong mid-take

- **Voice answers, screen doesn't move.** Room mismatch. Both `.env` files must point
  at the same LiveKit project. Second suspect: the five type strings drifted between
  `agent/render.py` and `web/src/lib/renderEvents.ts`.
- **Panel comes up empty.** A seed filename no longer matches `SEED_FILES` in
  `agent/aios_data.py`. Run the seed check.
- **Voice sounds flat.** Drop `ELEVENLABS_STABILITY` toward 0.3, raise `ELEVENLABS_STYLE`.
- **401 from a provider.** Test every key before filming; one dead key kills the loop.

All names and figures in the seed are fictional.
