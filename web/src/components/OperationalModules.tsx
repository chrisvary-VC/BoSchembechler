"use client";

import { useId, useState, type ReactNode } from "react";
import "@/app/operational-modules.css";

export type OperationalStatus = "ready" | "loading" | "stale" | "error" | "unavailable";

export interface OperationalState {
  status?: OperationalStatus;
  updatedAt?: string;
  message?: string;
}

export interface CommandItem {
  id: string;
  title: string;
  source?: string;
  due?: string;
  priority?: "high" | "normal" | "low";
  status?: string;
}

export interface ApprovalItem {
  id: string;
  title: string;
  kind?: string;
  notes?: string;
  target?: string;
  effect?: string;
  due?: string;
  createdAt?: string;
  status?: string;
  requiresExplicitApproval?: boolean;
}

export interface InboxItem {
  id: string;
  subject: string;
  sender: string;
  receivedAt?: string;
  summary?: string;
  unread?: boolean;
  important?: boolean;
}

export interface WebsiteProperty {
  id: string;
  name?: string;
  activeUsers?: number;
  pageViews30m?: number;
  sessions?: number;
  views?: number;
  keyEvents?: number;
  changePct?: number;
  trend?: number[];
  status?: string;
  message?: string;
  topPages?: Array<{ path: string; title?: string; views: number }>;
  events?: Array<{ name: string; count: number }>;
}

export interface MeetingItem {
  id: string;
  title: string;
  start: string;
  with?: string;
  location?: string;
  description?: string;
  attendees?: string[];
  meetingUrl?: string;
  calendarUrl?: string;
  prepNotes?: string[];
  source?: string;
}

export interface AlertItem {
  id: string;
  title: string;
  source?: string;
  severity?: "info" | "warning" | "critical";
  detectedAt?: string;
  detail?: string;
}

export interface WorkspaceFile {
  id: string;
  name: string;
  source: string;
  modifiedAt?: string;
  type?: string;
}

export interface DoctorCheck {
  id: string;
  name: string;
  status: "online" | "degraded" | "offline" | "unknown";
  detail?: string;
  latencyMs?: number;
}

export interface RoutineItem {
  id: string;
  name: string;
  schedule?: string;
  nextRun?: string;
  lastRun?: string;
  enabled?: boolean;
  status?: string;
}

export interface ForecastDay {
  day: string;
  condition: string;
  high?: number;
  low?: number;
  rainChance?: number;
}

export interface ResearchItem {
  id: string;
  title: string;
  query?: string;
  sourceCount?: number;
  completedAt?: string;
  summary?: string;
  url?: string;
}

interface PrivacyProps {
  privacy?: boolean;
}

export interface CommandQueueProps extends PrivacyProps {
  items?: CommandItem[];
  state?: OperationalState;
}

export interface ApprovalCenterProps extends PrivacyProps {
  items?: ApprovalItem[];
  state?: OperationalState;
  onReview?: (id: string) => void;
}

export interface InboxIntelligenceProps extends PrivacyProps {
  items?: InboxItem[];
  state?: OperationalState;
}

export interface WebsitePortfolioProps extends PrivacyProps {
  properties?: WebsiteProperty[];
  state?: OperationalState;
}

export interface MeetingPrepProps extends PrivacyProps {
  meetings?: MeetingItem[];
  state?: OperationalState;
}

export interface AlertTimelineProps extends PrivacyProps {
  alerts?: AlertItem[];
  state?: OperationalState;
}

export interface WorkspaceActivityProps extends PrivacyProps {
  files?: WorkspaceFile[];
  memoryCount?: number;
  bySource?: Record<string, number>;
  lastSyncAt?: string;
  syncState?: string;
  state?: OperationalState;
}

export interface JarvisDoctorProps {
  checks?: DoctorCheck[];
  state?: OperationalState;
}

export interface RoutinesProps extends PrivacyProps {
  routines?: RoutineItem[];
  state?: OperationalState;
}

export interface ForecastProps {
  location?: string;
  currentCondition?: string;
  currentTemperature?: number;
  days?: ForecastDay[];
  state?: OperationalState;
}

export interface RecentResearchProps extends PrivacyProps {
  items?: ResearchItem[];
  state?: OperationalState;
}

export interface OperationalModulesProps {
  className?: string;
  privacy?: boolean;
  commandQueue?: Omit<CommandQueueProps, "privacy">;
  approvalCenter?: Omit<ApprovalCenterProps, "privacy">;
  inbox?: Omit<InboxIntelligenceProps, "privacy">;
  websites?: Omit<WebsitePortfolioProps, "privacy">;
  meetings?: Omit<MeetingPrepProps, "privacy">;
  alerts?: Omit<AlertTimelineProps, "privacy">;
  workspace?: Omit<WorkspaceActivityProps, "privacy">;
  doctor?: JarvisDoctorProps;
  routines?: Omit<RoutinesProps, "privacy">;
  forecast?: ForecastProps;
  research?: Omit<RecentResearchProps, "privacy">;
}

export default function OperationalModules({
  className = "",
  privacy = false,
  commandQueue,
  approvalCenter,
  inbox,
  websites,
  meetings,
  alerts,
  workspace,
  doctor,
  routines,
  forecast,
  research,
}: OperationalModulesProps) {
  return (
    <section
      className={`operational-modules${privacy ? " is-private" : ""}${className ? ` ${className}` : ""}`}
      aria-label="Jarvis operational modules"
      data-privacy={privacy ? "on" : "off"}
    >
      <CommandQueue {...commandQueue} privacy={privacy} />
      <ApprovalCenter {...approvalCenter} privacy={privacy} />
      <InboxIntelligence {...inbox} privacy={privacy} />
      <WebsitePortfolio {...websites} privacy={privacy} />
      <MeetingPrep {...meetings} privacy={privacy} />
      <AlertTimeline {...alerts} privacy={privacy} />
      <WorkspaceActivity {...workspace} privacy={privacy} />
      <JarvisDoctor {...doctor} />
      <Routines {...routines} privacy={privacy} />
      <FourDayForecast {...forecast} />
      <RecentResearch {...research} privacy={privacy} />
    </section>
  );
}

export function CommandQueue({ items = [], state, privacy = false }: CommandQueueProps) {
  const high = items.filter((item) => item.priority === "high").length;
  return (
    <OperationalCard title="Today’s Command Queue" eyebrow="Mission priorities" count={items.length} state={state} className="op-command op-span-4">
      {items.length ? (
        <>
          <div className="op-statline"><span>High priority</span><strong>{high}</strong></div>
          <ol className="op-list op-command-list">
            {items.slice(0, 4).map((item, index) => (
              <li key={item.id} data-priority={item.priority ?? "normal"}>
                <span className="op-rank">{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{privateText(item.title, privacy, "Private command")}</strong><span>{privacy ? "Details hidden" : `${item.source || "Jarvis"}${item.due ? ` · ${item.due}` : ""}`}</span></div>
                {item.status && <em>{privateText(item.status, privacy, "Private")}</em>}
              </li>
            ))}
          </ol>
          <OverflowDetails count={items.length - 4}>{items.slice(4).map((item) => <p key={item.id}>{privateText(item.title, privacy, "Private command")}</p>)}</OverflowDetails>
        </>
      ) : <EmptyState>No commands are queued.</EmptyState>}
    </OperationalCard>
  );
}

export function ApprovalCenter({ items = [], state, privacy = false, onReview }: ApprovalCenterProps) {
  return (
    <OperationalCard title="Approval Center" eyebrow="Guarded cloud actions" count={items.length} state={state} className="op-approvals op-span-4">
      {items.length ? (
        <ul className="op-list op-approval-list">
          {items.slice(0, 5).map((item) => (
            <li key={item.id}>
              <div className="op-row-head"><strong>{privateText(item.title, privacy, "Private approval")}</strong><code>{privacy ? "Private ID" : item.id}</code></div>
              <span>{item.kind || "Pending action"}{item.due ? ` · due ${item.due}` : ""}</span>
              <details className="op-drilldown">
                <summary>Review details</summary>
                <dl>
                  <div><dt>Status</dt><dd>{item.status || "Pending"}</dd></div>
                  <div><dt>Target</dt><dd>{privacy ? "Private target" : item.target || item.kind || "Not provided"}</dd></div>
                  <div><dt>Effect</dt><dd>{privacy ? "Action details hidden" : item.effect || "Not provided"}</dd></div>
                  <div><dt>Created</dt><dd>{item.createdAt || "Not provided"}</dd></div>
                </dl>
                {item.notes && <p>{privateText(item.notes, privacy, "Approval notes hidden")}</p>}
                {onReview && <button type="button" onClick={() => onReview(item.id)}>Review &amp; decide</button>}
              </details>
            </li>
          ))}
        </ul>
      ) : <EmptyState>No actions are waiting for approval.</EmptyState>}
    </OperationalCard>
  );
}

export function InboxIntelligence({ items = [], state, privacy = false }: InboxIntelligenceProps) {
  const unread = items.filter((item) => item.unread).length;
  const important = items.filter((item) => item.important).length;
  return (
    <OperationalCard title="Inbox Intelligence" eyebrow="Gmail priority scan" count={items.length} state={state} className="op-inbox op-span-4">
      <div className="op-metric-pair"><span><strong>{unread}</strong> unread</span><span><strong>{important}</strong> important</span></div>
      {items.length ? <ul className="op-list">{items.slice(0, 5).map((item) => (
        <li key={item.id} className={item.important ? "is-priority" : ""}>
          <div className="op-row-head"><strong>{privateText(item.subject, privacy, "Private message")}</strong>{item.unread && <em>Unread</em>}</div>
          <span>{privateText(item.sender, privacy, "Sender hidden")}{item.receivedAt ? ` · ${item.receivedAt}` : ""}</span>
          {item.summary && <details className="op-drilldown"><summary>Preview</summary><p>{privateText(item.summary, privacy, "Preview hidden in privacy mode")}</p></details>}
        </li>
      ))}</ul> : <EmptyState>No recent inbox activity.</EmptyState>}
    </OperationalCard>
  );
}

export function WebsitePortfolio({ properties = [], state, privacy = false }: WebsitePortfolioProps) {
  const selectorId = useId();
  const [selectedId, setSelectedId] = useState("");
  const selected = properties.find((item) => item.id === selectedId) ?? properties[0];
  return (
    <OperationalCard title="Website Portfolio" eyebrow="Google Analytics" count={properties.length} state={state} className="op-websites op-span-6">
      {properties.length ? (
        <>
          <label className="op-selector" htmlFor={selectorId}><span>Property</span><select id={selectorId} value={selected?.id ?? ""} onChange={(event) => setSelectedId(event.target.value)}>{properties.map((property, index) => <option key={property.id} value={property.id}>{privacy ? `Private website ${index + 1}` : property.name || property.id}</option>)}</select></label>
          {selected && <div className="op-website-focus">
            <div className="op-metrics"><Metric label="Active now" value={formatNumber(selected.activeUsers)} /><Metric label="Views · 30m" value={formatNumber(selected.pageViews30m)} /><Metric label="Sessions · 14d" value={formatNumber(selected.sessions)} /><Metric label="Views · 14d" value={formatNumber(selected.views)} /><Metric label="Key events" value={formatNumber(selected.keyEvents)} /><Metric label="Change" value={formatPercent(selected.changePct)} tone={selected.changePct !== undefined && selected.changePct < 0 ? "down" : "up"} /></div>
            <Sparkline values={selected.trend} label={`${privacy ? "Private website" : selected.name || selected.id} traffic trend`} />
            {(selected.topPages?.length || selected.events?.length || selected.message) && <details className="op-drilldown op-web-detail"><summary>Pages &amp; conversions</summary>
              {selected.message && <p>{selected.message}</p>}
              {!!selected.topPages?.length && <div><h3>Top pages</h3><ol>{selected.topPages.slice(0, 5).map((page, index) => <li key={`${selected.id}-${page.path}`}><span>{privacy ? `Private page ${index + 1}` : page.title || page.path}</span><strong>{formatNumber(page.views)}</strong></li>)}</ol></div>}
              {!!selected.events?.length && <div><h3>Key events</h3><ol>{selected.events.slice(0, 5).map((event, index) => <li key={`${selected.id}-${event.name}`}><span>{privacy ? `Private event ${index + 1}` : event.name}</span><strong>{formatNumber(event.count)}</strong></li>)}</ol></div>}
            </details>}
          </div>}
        </>
      ) : <EmptyState>No website properties are available.</EmptyState>}
    </OperationalCard>
  );
}

export function MeetingPrep({ meetings = [], state, privacy = false }: MeetingPrepProps) {
  return (
    <OperationalCard title="Meeting Prep" eyebrow="Next on calendar" count={meetings.length} state={state} className="op-meetings op-span-3">
      {meetings.length ? <ul className="op-list">{meetings.slice(0, 4).map((meeting) => (
        <li key={meeting.id}>
          <time>{meeting.start}</time><strong>{privateText(meeting.title, privacy, "Private meeting")}</strong>
          <span>{privateText(meeting.with || meeting.location || meeting.source || "Calendar", privacy, "Details hidden")}</span>
          {meeting.description && <details className="op-drilldown"><summary>Agenda &amp; attendees</summary><p>{privateText(meeting.description, privacy, "Meeting description hidden")}</p>{!!meeting.attendees?.length && <p>{privateText(meeting.attendees.join(" · "), privacy, "Attendees hidden")}</p>}{!privacy && <div className="op-meeting-links">{meeting.meetingUrl && <a href={meeting.meetingUrl} target="_blank" rel="noreferrer">Join meeting ↗</a>}{meeting.calendarUrl && <a href={meeting.calendarUrl} target="_blank" rel="noreferrer">Open calendar ↗</a>}</div>}</details>}
          {!!meeting.prepNotes?.length && <details className="op-drilldown"><summary>Prep brief</summary><ul>{meeting.prepNotes.map((note, index) => <li key={`${meeting.id}-${index}`}>{privateText(note, privacy, "Prep note hidden")}</li>)}</ul></details>}
        </li>
      ))}</ul> : <EmptyState>No upcoming meetings require preparation.</EmptyState>}
    </OperationalCard>
  );
}

export function AlertTimeline({ alerts = [], state, privacy = false }: AlertTimelineProps) {
  return (
    <OperationalCard title="Alert Timeline" eyebrow="Material changes" count={alerts.length} state={state} className="op-alerts op-span-3">
      {alerts.length ? <ol className="op-timeline">{alerts.slice(0, 6).map((alert) => (
        <li key={alert.id} data-severity={alert.severity ?? "info"}><i aria-hidden /><div><time>{alert.detectedAt || "Recent"}</time><strong>{privateText(alert.title, privacy, "Private alert")}</strong><span>{privateText(alert.source || "Jarvis monitor", privacy, "Source hidden")}</span>{alert.detail && <p>{privateText(alert.detail, privacy, "Alert details hidden")}</p>}</div></li>
      ))}</ol> : <EmptyState>No material changes detected.</EmptyState>}
    </OperationalCard>
  );
}

export function WorkspaceActivity({ files = [], memoryCount, bySource = {}, lastSyncAt, syncState, state, privacy = false }: WorkspaceActivityProps) {
  return (
    <OperationalCard title="Workspace Activity" eyebrow="Drive · Dropbox · Memory" count={files.length} state={state} className="op-workspace op-span-4">
      <div className="op-statline"><span>Indexed memory</span><strong>{formatNumber(memoryCount)}</strong></div>
      <div className="op-sync-health"><span>{syncState || "Sync state unavailable"}</span>{lastSyncAt && <time>{lastSyncAt}</time>}</div>
      {Object.keys(bySource).length > 0 && <dl className="op-source-counts">{Object.entries(bySource).map(([source, count]) => <div key={source}><dt>{source}</dt><dd>{count}</dd></div>)}</dl>}
      {files.length ? <ul className="op-list">{files.slice(0, 4).map((file) => <li key={file.id}><span>{file.source}</span><strong>{privateText(file.name, privacy, "Private file")}</strong><time>{file.modifiedAt || ""}</time></li>)}</ul> : <EmptyState>No recent workspace activity.</EmptyState>}
    </OperationalCard>
  );
}

export function JarvisDoctor({ checks = [], state }: JarvisDoctorProps) {
  const failed = checks.filter((check) => check.status === "offline" || check.status === "degraded").length;
  return (
    <OperationalCard title="Jarvis Doctor & Latency" eyebrow="Systems diagnostic" count={checks.length} state={state} className="op-doctor op-span-4">
      {checks.length ? <>
        <div className={`op-health-summary${failed ? " has-faults" : ""}`}><strong>{failed ? `${failed} need attention` : "Systems nominal"}</strong></div>
        <ul className="op-checks">{checks.map((check) => <li key={check.id} data-check={check.status}><i aria-hidden /><span>{check.name}</span><strong>{humanizeStatus(check.status)}{check.latencyMs === undefined ? "" : ` · ${check.latencyMs} ms`}</strong>{check.detail && <small>{check.detail}</small>}</li>)}</ul>
      </> : <EmptyState>No diagnostic result is available.</EmptyState>}
    </OperationalCard>
  );
}

export function Routines({ routines = [], state, privacy = false }: RoutinesProps) {
  return (
    <OperationalCard title="Routines" eyebrow="Scheduled automations" count={routines.length} state={state} className="op-routines op-span-4">
      {routines.length ? <ul className="op-list">{routines.slice(0, 5).map((routine) => <li key={routine.id} data-enabled={routine.enabled === false ? "false" : "true"}><div className="op-row-head"><strong>{privateText(routine.name, privacy, "Private routine")}</strong><em>{routine.enabled === false ? "Paused" : routine.status || "Active"}</em></div><span>{routine.schedule || "Schedule not provided"}</span>{(routine.nextRun || routine.lastRun) && <details className="op-drilldown"><summary>Run history</summary><dl><div><dt>Next</dt><dd>{routine.nextRun || "Not scheduled"}</dd></div><div><dt>Last</dt><dd>{routine.lastRun || "No run recorded"}</dd></div></dl></details>}</li>)}</ul> : <EmptyState>No routines are configured.</EmptyState>}
    </OperationalCard>
  );
}

export function FourDayForecast({ location, currentCondition, currentTemperature, days = [], state }: ForecastProps) {
  return (
    <OperationalCard title="4-Day Forecast" eyebrow={location || "Local weather"} count={days.length} state={state} className="op-forecast op-span-4">
      {(currentCondition || currentTemperature !== undefined) && <div className="op-weather-now"><strong>{formatTemperature(currentTemperature)}</strong><span>{currentCondition || "Current conditions unavailable"}</span></div>}
      {days.length ? <details className="op-forecast-details"><summary>Expand forecast</summary><ol>{days.slice(0, 4).map((day) => <li key={day.day}><strong>{day.day}</strong><span>{day.condition}</span><em>{formatTemperature(day.high)} / {formatTemperature(day.low)}</em>{day.rainChance !== undefined && <small>{day.rainChance}% rain</small>}</li>)}</ol></details> : <EmptyState>No forecast is available.</EmptyState>}
    </OperationalCard>
  );
}

export function RecentResearch({ items = [], state = { status: "unavailable", message: "Research history is not connected yet." }, privacy = false }: RecentResearchProps) {
  return (
    <OperationalCard title="Recent Research" eyebrow="Cited intelligence" count={items.length} state={state} className="op-research op-span-8">
      {items.length ? <ul className="op-list op-research-list">{items.slice(0, 5).map((item) => <li key={item.id}><div><strong>{privateText(item.title, privacy, "Private research")}</strong><span>{item.completedAt || item.query || "Recent"}</span></div>{item.sourceCount !== undefined && <em>{item.sourceCount} sources</em>}{item.summary && <details className="op-drilldown"><summary>Read summary</summary><p>{privateText(item.summary, privacy, "Summary hidden in privacy mode")}</p>{item.url && !privacy && <a href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}</details>}</li>)}</ul> : <EmptyState>No recent research has been saved.</EmptyState>}
    </OperationalCard>
  );
}

interface OperationalCardProps {
  title: string;
  eyebrow: string;
  count?: number;
  state?: OperationalState;
  className?: string;
  children: ReactNode;
}

function OperationalCard({ title, eyebrow, count, state, className = "", children }: OperationalCardProps) {
  const headingId = useId();
  const status = state?.status ?? "ready";
  const blocked = status === "loading" || status === "error" || status === "unavailable";
  return (
    <article className={`operational-card ${className}`} data-status={status} aria-labelledby={headingId} aria-busy={status === "loading"}>
      <header className="op-card-head"><div><span>{eyebrow}</span><h2 id={headingId}>{title}</h2></div><div className="op-card-meta"><StatusBadge state={state} />{count !== undefined && <strong aria-label={`${count} items`}>{count}</strong>}</div></header>
      <div className="op-card-body">{blocked ? <ModuleStateNotice state={{ ...state, status }} /> : children}</div>
    </article>
  );
}

function StatusBadge({ state }: { state?: OperationalState }) {
  const status = state?.status ?? "ready";
  const labels: Record<OperationalStatus, string> = { ready: "Ready", loading: "Syncing", stale: "Stale", error: "Error", unavailable: "Unavailable" };
  return <span className="op-status" data-status={status} title={state?.message}>{labels[status]}{state?.updatedAt ? ` · ${state.updatedAt}` : ""}</span>;
}

function ModuleStateNotice({ state }: { state: OperationalState }) {
  const status = state.status ?? "unavailable";
  const fallback: Record<OperationalStatus, string> = {
    ready: "Module ready.",
    loading: "Synchronizing this module.",
    stale: "Showing the last available result.",
    error: "This module could not refresh.",
    unavailable: "This data source is not available yet.",
  };
  return <div className="op-state-notice" role={status === "error" ? "alert" : "status"}><i aria-hidden /><strong>{fallback[status]}</strong>{state.message && <p>{state.message}</p>}</div>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="op-empty">{children}</p>;
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return <div className="op-metric" data-tone={tone}><span>{label}</span><strong>{value}</strong></div>;
}

function Sparkline({ values = [], label }: { values?: number[]; label: string }) {
  if (!values.length) return <div className="op-chart-empty">Trend unavailable</div>;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const spread = high - low || 1;
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${28 - ((value - low) / spread) * 24}`).join(" ");
  return <svg className="op-sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label={label}><polyline points={points} /></svg>;
}

function OverflowDetails({ count, children }: { count: number; children: ReactNode }) {
  if (count <= 0) return null;
  return <details className="op-overflow"><summary>{count} more</summary><div>{children}</div></details>;
}

function privateText(value: string, privacy: boolean, replacement: string) {
  return privacy ? replacement : value;
}

function formatNumber(value?: number) {
  return value === undefined ? "—" : new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatPercent(value?: number) {
  return value === undefined ? "—" : `${value > 0 ? "+" : ""}${value}%`;
}

function formatTemperature(value?: number) {
  return value === undefined ? "—" : `${Math.round(value)}°`;
}

function humanizeStatus(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
