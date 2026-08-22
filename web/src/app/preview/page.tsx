"use client";

/**
 * Panel preview — no LiveKit, no keys, no microphone.
 * Style the HUD here, then check it for real in the room.
 * Data comes from the same seed files the agent reads.
 */

import { useState } from "react";
import brief from "../../../../seed/daily_brief.json";
import metricsSeed from "../../../../seed/metrics.json";
import pipeline from "../../../../seed/pipeline.json";
import intel from "../../../../seed/intel.json";
import actions from "../../../../seed/actions.json";
import BriefPanel from "@/components/panels/BriefPanel";
import MetricsPanel from "@/components/panels/MetricsPanel";
import PipelinePanel from "@/components/panels/PipelinePanel";
import IntelPanel from "@/components/panels/IntelPanel";
import ActionsPanel from "@/components/panels/ActionsPanel";
import type {
  ActionsPayload, BriefPayload, IntelPayload, MetricsPayload, PipelinePayload,
} from "@/lib/renderEvents";

const series = (metricsSeed as any).series.subscribers;
const points = series.points as { date: string; value: number }[];
const deltaPct = Math.round(
  ((points[points.length - 1].value - points[0].value) / points[0].value) * 1000,
) / 10;

const metrics: MetricsPayload = {
  metric: series.label,
  unit: series.unit,
  summary: series.summary,
  delta_pct: deltaPct,
  points,
};

const TABS = ["brief", "metrics", "pipeline", "intel", "actions"] as const;

export default function Preview() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("brief");
  const [nonce, setNonce] = useState(0);
  const show = (t: (typeof TABS)[number]) => { setTab(t); setNonce((n) => n + 1); };
  const k = `${tab}-${nonce}`; // remount so the animations replay, same as the real stage

  return (
    <main className="stage">
      <header className="stage-head">
        <span className="stage-mark">JARVIS</span>
        <span className="chips" style={{ margin: 0 }}>
          {TABS.map((t) => (
            <button key={t} className="engage-btn" style={{ margin: 0, padding: "0.35rem 0.9rem", fontSize: "0.6rem" }} onClick={() => show(t)}>
              {t}
            </button>
          ))}
        </span>
      </header>

      <section className="stage-body">
        {tab === "brief" && <BriefPanel key={k} title="Daily Brief · preview" data={brief as unknown as BriefPayload} />}
        {tab === "metrics" && <MetricsPanel key={k} title={`${metrics.metric} · last ${points.length} days`} data={metrics} />}
        {tab === "pipeline" && <PipelinePanel key={k} title="Pipeline · preview" data={pipeline as unknown as PipelinePayload} />}
        {tab === "intel" && <IntelPanel key={k} title='"Northwind" · mentions' data={{ query: "Northwind", items: (intel as any).items } as IntelPayload} />}
        {tab === "actions" && <ActionsPanel key={k} title="Today · preview" data={actions as unknown as ActionsPayload} />}
      </section>

      <footer className="stage-foot">preview mode · seed data · no room joined</footer>
    </main>
  );
}
