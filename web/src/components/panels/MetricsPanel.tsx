"use client";

import { useMemo } from "react";
import type { MetricsPayload } from "@/lib/renderEvents";

const W = 960;
const H = 300;
const PAD = { top: 24, right: 24, bottom: 12, left: 56 };

export default function MetricsPanel({ title, data }: { title: string; data: MetricsPayload }) {
  const { path, area, ticks, lo, hi } = useMemo(() => {
    const pts = data.points;
    if (pts.length === 0) return { path: "", area: "", ticks: [] as string[], lo: 0, hi: 0 };

    const values = pts.map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const span = hi - lo || 1;
    const innerW = W - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;

    const xy = pts.map((p, i) => {
      const x = PAD.left + (i / Math.max(pts.length - 1, 1)) * innerW;
      const y = PAD.top + innerH - ((p.value - lo) / span) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const path = `M ${xy.join(" L ")}`;
    const area = `${path} L ${W - PAD.right},${H - PAD.bottom} L ${PAD.left},${H - PAD.bottom} Z`;

    // A handful of evenly spaced dates. The axis is plain HTML underneath, so
    // labels never distort when the chart stretches.
    const step = Math.max(1, Math.floor(pts.length / 5));
    const ticks = pts.filter((_, i) => i % step === 0).map((p) => p.date.slice(5));

    return { path, area, ticks, lo, hi };
  }, [data.points]);

  const up = data.delta_pct >= 0;

  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>

      <div className="metric-head">
        <span className="metric-now">
          {data.points.at(-1)?.value.toLocaleString() ?? "—"}
          <em>{data.unit}</em>
        </span>
        <span className={`metric-delta${up ? " up" : " down"}`}>
          {up ? "▲" : "▼"} {Math.abs(data.delta_pct)}%
        </span>
      </div>

      <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.30" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((f) => (
          <line
            key={f}
            className="grid"
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + f * (H - PAD.top - PAD.bottom)}
            y2={PAD.top + f * (H - PAD.top - PAD.bottom)}
          />
        ))}
        <path className="chart-area" d={area} fill="url(#fill)" />
        {/* stroke-dashoffset animates the line drawing itself left to right */}
        <path className="chart-line" d={path} />
      </svg>

      <div className="axis">
        {ticks.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>

      <p className="metric-summary">{data.summary}</p>
      <p className="metric-range">
        range {lo.toLocaleString()} – {hi.toLocaleString()}
      </p>
    </article>
  );
}
