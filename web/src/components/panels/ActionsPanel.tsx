"use client";

import type { ActionsPayload } from "@/lib/renderEvents";

export default function ActionsPanel({ title, data }: { title: string; data: ActionsPayload }) {
  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>

      <ol className="actions">
        {data.items.map((item, i) => (
          <li key={item.rank} style={{ animationDelay: `${i * 120}ms` }}>
            <span className="rank">{String(item.rank).padStart(2, "0")}</span>
            <div>
              <p className="action-title">{item.title}</p>
              <p className="action-why">{item.why}</p>
            </div>
            {item.effort && <span className="effort">{item.effort}</span>}
          </li>
        ))}
      </ol>
    </article>
  );
}
