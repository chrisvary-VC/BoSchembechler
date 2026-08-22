"use client";

import type { PipelinePayload } from "@/lib/renderEvents";

const money = (n: number) => `$${(n / 1000).toFixed(n % 1000 ? 1 : 0)}K`;

export default function PipelinePanel({ title, data }: { title: string; data: PipelinePayload }) {
  const widest = Math.max(...data.stages.map((s) => s.value), 1);

  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>

      <div className="funnel">
        {data.stages.map((s, i) => (
          <div className="funnel-row" key={s.name} style={{ animationDelay: `${i * 90}ms` }}>
            <span className="funnel-name">{s.name}</span>
            <div className="funnel-track">
              <div
                className="funnel-bar"
                style={{ width: `${(s.value / widest) * 100}%`, animationDelay: `${i * 90}ms` }}
              />
            </div>
            <span className="funnel-value">
              {money(s.value)} <em>· {s.count}</em>
            </span>
          </div>
        ))}
      </div>

      <ul className="deals">
        {data.deals.map((d, i) => (
          <li
            className={`deal${d.at_risk ? " at-risk" : ""}`}
            key={d.name}
            style={{ animationDelay: `${420 + i * 80}ms` }}
          >
            <span className="deal-name">{d.name}</span>
            <span className="deal-stage">{d.stage}</span>
            <span className="deal-value">{money(d.value)}</span>
            {d.note && <span className="deal-note">{d.note}</span>}
          </li>
        ))}
      </ul>
    </article>
  );
}
