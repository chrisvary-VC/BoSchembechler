"use client";

import type { BriefPayload } from "@/lib/renderEvents";
import { useTypeIn } from "./useTypeIn";

export default function BriefPanel({ title, data }: { title: string; data: BriefPayload }) {
  const { shown, done } = useTypeIn(data.summary);

  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>

      <p className="brief-summary">
        {shown}
        {!done && <span className="caret" />}
      </p>

      {done && (
        <div className="chips">
          {data.signals.map((s, i) => (
            <div
              className={`chip${s.alert ? " chip-alert" : ""}`}
              key={`${s.label}-${i}`}
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <span className="chip-label">{s.label}</span>
              <span className="chip-value">{s.value}</span>
              {s.delta && <span className="chip-delta">{s.delta}</span>}
            </div>
          ))}
        </div>
      )}

      {done && (
        <div className="brief-sections">
          {data.sections.map((section, si) => (
            <section key={`${section.heading}-${si}`}>
              <h3 className="section-head" style={{ animationDelay: `${300 + si * 160}ms` }}>
                {section.heading}
              </h3>
              <ul>
                {section.lines.map((line, li) => (
                  <li key={`${si}-${li}`} style={{ animationDelay: `${380 + si * 160 + li * 90}ms` }}>
                    {line}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </article>
  );
}
