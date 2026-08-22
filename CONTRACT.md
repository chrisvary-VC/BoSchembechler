# The render-event contract

The agent and the HUD never call each other directly. They agree on this, and only this.

| Piece | Value |
| --- | --- |
| Transport | LiveKit room data channel (reliable) |
| Topic | `aios.render` |
| Envelope | `{ v, type, id, ts, tool, spoken, title, payload }` |
| Types | `aios.brief`, `aios.metrics`, `aios.pipeline`, `aios.intel`, `aios.actions` |

Two files hard-code these strings and must stay byte-identical:

- `agent/render.py` (Python, publisher)
- `web/src/lib/renderEvents.ts` (TypeScript, listener)

**Change one, you must change the other.** If they drift by a single character the agent
publishes happily and the HUD silently ignores it. That is the #1 failure mode.

## Envelope fields

| Field | Type | Meaning |
| --- | --- | --- |
| `v` | number | Contract version. Currently `1`. |
| `type` | string | One of the five type strings above. |
| `id` | string | Unique per event. The HUD keys panels on it so animations replay. |
| `ts` | number | Unix ms, when the agent published. |
| `tool` | string | Which tool produced it, for debugging. |
| `spoken` | string | The exact sentence the voice says. Headline only. |
| `title` | string | Panel heading. |
| `payload` | object | Panel-specific data. See below. |

## Payload shapes

- `aios.brief` — `{ summary, signals: [{label, value, delta?}], sections: [{heading, lines: []}] }`
- `aios.metrics` — `{ metric, unit, points: [{date, value}], summary, delta_pct }`
- `aios.pipeline` — `{ stages: [{name, count, value}], deals: [{name, stage, value, at_risk, note}] }`
- `aios.intel` — `{ query, items: [{when, source, who, quote}] }`
- `aios.actions` — `{ items: [{rank, title, why, effort}] }`

The voice carries the headline, the screen carries the detail. Never read the payload out loud.
