"use client";

import type { IntelPayload } from "@/lib/renderEvents";

export default function IntelPanel({ title, data }: { title: string; data: IntelPayload }) {
  if (data.items.length === 0) {
    return (
      <article className="panel">
        <h2 className="panel-title">{title}</h2>
        <p className="empty">Nothing on that one.</p>
      </article>
    );
  }

  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>

      <ol className="timeline">
        {data.items.map((item, i) => (
          <li key={`${item.when}-${i}`} style={{ animationDelay: `${i * 110}ms` }}>
            <span className="tl-dot" aria-hidden />
            <div className="tl-meta">
              <span className="tl-when">{item.when}</span>
              <span className="tl-source">{item.source}</span>
            </div>
            <p className="tl-quote">&ldquo;{item.quote}&rdquo;</p>
            <span className="tl-who">— {item.who}</span>
            {item.url && <a className="tl-link" href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}
          </li>
        ))}
      </ol>
    </article>
  );
}
