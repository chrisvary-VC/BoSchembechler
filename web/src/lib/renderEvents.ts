/**
 * The TypeScript mirror of the render-event contract.
 *
 * LOCKED CONTRACT — see ../../CONTRACT.md.
 * These five type strings and the topic must stay byte-identical to
 * agent/render.py. Change one without the other and the agent will publish
 * while the HUD silently ignores it. That is the #1 failure mode.
 */

export const RENDER_TOPIC = "aios.render";
export const CONTRACT_VERSION = 1;

export const BRIEF = "aios.brief";
export const METRICS = "aios.metrics";
export const PIPELINE = "aios.pipeline";
export const INTEL = "aios.intel";
export const ACTIONS = "aios.actions";

export const RENDER_TYPES = [BRIEF, METRICS, PIPELINE, INTEL, ACTIONS] as const;
export type RenderType = (typeof RENDER_TYPES)[number];

export interface RenderEnvelope<P = unknown> {
  v: number;
  type: RenderType;
  id: string;
  ts: number;
  tool: string;
  spoken: string;
  title: string;
  payload: P;
}

export interface BriefPayload {
  summary: string;
  signals: { label: string; value: string; delta?: string; alert?: boolean }[];
  sections: { heading: string; lines: string[] }[];
}

export interface MetricsPayload {
  metric: string;
  unit: string;
  summary: string;
  delta_pct: number;
  points: { date: string; value: number }[];
}

export interface PipelinePayload {
  stages: { name: string; count: number; value: number }[];
  deals: { name: string; stage: string; value: number; at_risk: boolean; note?: string }[];
}

export interface IntelPayload {
  query: string;
  items: { when: string; source: string; who: string; quote: string; url?: string }[];
}

export interface ActionsPayload {
  items: { rank: number; title: string; why: string; effort?: string }[];
}

export function isRenderType(value: unknown): value is RenderType {
  return typeof value === "string" && (RENDER_TYPES as readonly string[]).includes(value);
}

/** Parse a data-channel payload. Returns null for anything off-contract. */
export function parseRenderEvent(bytes: Uint8Array): RenderEnvelope | null {
  try {
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    if (!parsed || typeof parsed !== "object") return null;
    if (!isRenderType(parsed.type)) return null;
    if (typeof parsed.id !== "string") return null;
    return parsed as RenderEnvelope;
  } catch {
    return null;
  }
}
