export interface DockFile {
  source: string;
  name: string;
  modified?: string;
}

export interface DockNewsItem {
  title: string;
  source: string;
}

export interface DockMonitorAlert {
  title: string;
  detail?: string;
  severity?: "info" | "warning" | "critical";
}

export interface DashboardDockProps {
  recentFiles?: DockFile[];
  news?: DockNewsItem[];
  services?: Record<string, boolean>;
  monitorAlerts?: Array<DockMonitorAlert | string>;
  monitorState?: string;
  operatingMode?: string;
  memoryCount?: number;
  approvalCount?: number;
  fileStatus?: string;
  monitorStatus?: string;
  newsStatus?: string;
  servicesStatus?: string;
}

export default function DashboardDock({
  recentFiles = [],
  news = [],
  services = {},
  monitorAlerts = [],
  monitorState = "Standby",
  operatingMode,
  memoryCount,
  approvalCount,
  fileStatus,
  monitorStatus,
  newsStatus,
  servicesStatus,
}: DashboardDockProps) {
  const serviceEntries = Object.entries(services);
  const onlineServices = serviceEntries.filter(([, online]) => online).length;

  return (
    <section className="systems-dock" aria-label="Persistent systems overview">
      <article className="dock-module dock-files" aria-labelledby="dock-files-title">
        <header className="dock-module-head">
          <div>
            <span className="dock-kicker">// Connected intelligence</span>
            <h2 id="dock-files-title">Files &amp; memory</h2>
          </div>
          <span className="dock-badge" aria-label={memoryCount === undefined ? "Memory index unavailable" : `${memoryCount} indexed memories`}>
            {memoryCount ?? "—"}
          </span>
        </header>

        <ul className="dock-list" aria-label="Recently indexed files">
          {recentFiles.slice(0, 4).map((file, index) => (
            <li key={`${file.source}-${file.name}-${file.modified ?? ""}-${index}`}>
              <span className="dock-source">{file.source}</span>
              <strong className="dock-title">{file.name}</strong>
              {file.modified && <time className="dock-meta">{file.modified}</time>}
            </li>
          ))}
          {recentFiles.length === 0 && <li className="dock-empty">{emptySourceCopy(fileStatus, "No recent file activity.")}</li>}
        </ul>
      </article>

      <article className="dock-module dock-monitor" aria-labelledby="dock-monitor-title">
        <header className="dock-module-head">
          <div>
            <span className="dock-kicker">// Continuous watch</span>
            <h2 id="dock-monitor-title">Monitor &amp; approvals</h2>
          </div>
          <span className={`monitor-state${monitorAlerts.length ? " has-alerts" : ""}`}>
            {monitorState}
          </span>
        </header>

        <div className="dock-counts" aria-label="Action counts">
          <span><strong>{sourceUsable(monitorStatus) ? monitorAlerts.length : "—"}</strong> alerts</span>
          <span><strong>{approvalCount ?? "—"}</strong> approvals</span>
        </div>

        <ul className="dock-list dock-alerts" aria-live="polite">
          {monitorAlerts.slice(0, 3).map((alert, index) => {
            const item = typeof alert === "string" ? { title: alert, severity: "info" as const } : alert;
            return (
              <li className={`severity-${item.severity ?? "info"}`} key={`${item.title}-${index}`}>
                <i aria-hidden />
                <strong className="dock-title">{item.title}</strong>
                {item.detail && <span className="dock-meta">{item.detail}</span>}
              </li>
            );
          })}
          {monitorAlerts.length === 0 && <li className="dock-empty">{emptySourceCopy(monitorStatus, "No material changes detected.")}</li>}
        </ul>
      </article>

      <article className="dock-module dock-news" aria-labelledby="dock-news-title">
        <header className="dock-module-head">
          <div>
            <span className="dock-kicker">// Intelligence feed</span>
            <h2 id="dock-news-title">News briefing</h2>
          </div>
          <span className="dock-badge" aria-label={`${news.length} headlines`}>
            {news.length}
          </span>
        </header>

        <ol className="dock-list" aria-label="Current headlines">
          {news.slice(0, 4).map((item, index) => (
            <li key={`${item.source}-${item.title}-${index}`}>
              <span className="dock-source">{item.source}</span>
              <strong className="dock-title">{item.title}</strong>
            </li>
          ))}
          {news.length === 0 && <li className="dock-empty">{emptySourceCopy(newsStatus, "Awaiting the next news cycle.")}</li>}
        </ol>
      </article>

      <article className="dock-module dock-services" aria-labelledby="dock-services-title">
        <header className="dock-module-head">
          <div>
            <span className="dock-kicker">// Operating envelope</span>
            <h2 id="dock-services-title">Service mesh</h2>
          </div>
          <span className="dock-badge" aria-label={`${onlineServices} of ${serviceEntries.length} services online`}>
            {onlineServices}/{serviceEntries.length}
          </span>
        </header>

        <div className="operating-mode">
          <span>Mode</span>
          <strong>{operatingMode || "Unavailable"}</strong>
        </div>

        <ul className="service-mesh" aria-label="Connected service status">
          {serviceEntries.map(([service, online]) => (
            <li className={online ? "service-online" : "service-offline"} key={service}>
              <i aria-hidden />
              <span>{humanize(service)}</span>
              <strong>{online ? "Online" : "Offline"}</strong>
            </li>
          ))}
          {serviceEntries.length === 0 && <li className="dock-empty">{emptySourceCopy(servicesStatus, "No service status received.")}</li>}
        </ul>
      </article>
    </section>
  );
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sourceUsable(status?: string) {
  return status === "ok" || status === "stale" || status === "degraded";
}

function emptySourceCopy(status: string | undefined, empty: string) {
  if (!status || status === "loading") return "Synchronizing live data…";
  if (!sourceUsable(status)) return "Data source unavailable.";
  return empty;
}
