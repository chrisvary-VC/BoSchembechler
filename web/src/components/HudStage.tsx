"use client";

import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { ConnectionState } from "livekit-client";
import {
  useConnectionState,
  useMultibandTrackVolume,
  useVoiceAssistant,
} from "@livekit/components-react";
import { useRenderEvents } from "@/lib/useRenderEvents";
import { useDashboardSnapshot, type DashboardSnapshot } from "@/lib/dashboardSnapshot";
import {
  ACTIONS, BRIEF, INTEL, METRICS, PIPELINE,
  type ActionsPayload, type BriefPayload, type IntelPayload,
  type MetricsPayload, type PipelinePayload, type RenderEnvelope,
} from "@/lib/renderEvents";
import BriefPanel from "./panels/BriefPanel";
import MetricsPanel from "./panels/MetricsPanel";
import PipelinePanel from "./panels/PipelinePanel";
import IntelPanel from "./panels/IntelPanel";
import ActionsPanel from "./panels/ActionsPanel";
import VictorsReactor, { type VictorsReactorState } from "./VictorsReactor";
import DashboardDock from "./DashboardDock";
import ConversationModule from "./ConversationModule";
import DashboardMissionDeck from "./DashboardMissionDeck";

interface HudStageProps {
  onEngage: () => void;
  engaging: boolean;
  voiceRequested: boolean;
  voiceError: string | null;
}

export default function HudStage({ onEngage, engaging, voiceRequested, voiceError }: HudStageProps) {
  const event = useRenderEvents();
  const live = useDashboardSnapshot();
  const voice = useJarvisVoice(voiceRequested);
  const [clock, setClock] = useState("--:--:--");
  const [date, setDate] = useState("SYSTEM DATE");
  const [history, setHistory] = useState<RenderEnvelope[]>([]);
  const [privacyMode, setPrivacyMode] = useState(true);
  const [missionDeckOpen, setMissionDeckOpen] = useState(false);
  const [dismissedEventId, setDismissedEventId] = useState<string | null>(null);

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setClock(now.toLocaleTimeString([], { hour12: false }));
      setDate(now.toLocaleDateString([], { weekday: "short", month: "short", day: "2-digit", year: "numeric" }).toUpperCase());
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (event) setHistory(current => [event, ...current.filter(x => x.id !== event.id)].slice(0, 24));
  }, [event]);

  const visibleEvent = event?.id === dismissedEventId ? null : event;
  const moduleName = visibleEvent?.tool.replaceAll("_", " ").toUpperCase() || "VOICE INTERFACE";
  const closeMissionDeck = useCallback(() => setMissionDeckOpen(false), []);
  const showConversation = useCallback(() => {
    if (event) setDismissedEventId(event.id);
    setMissionDeckOpen(false);
  }, [event]);

  return (
    <main
      className={`stage command-center has-systems agent-${voice.state}${voice.speaking ? " voice-active" : ""}${voice.connected ? " voice-connected" : ""}${privacyMode ? " privacy-mode" : ""}`}
      data-agent-state={voice.state}
      style={{ "--voice-level": voice.level.toFixed(3) } as CSSProperties}
    >
      <header className="command-head">
        <div className="command-state" data-state={voice.state}>
          <i className={`dot${voice.connected ? " active" : ""}`} />
          <span>{voice.label}</span>
          <button
            type="button"
            className="voice-engage-btn"
            onClick={onEngage}
            disabled={engaging || voiceRequested}
          >
            {engaging ? "LINKING…" : voiceRequested ? "VOICE LINKED" : "ENGAGE VOICE"}
          </button>
          <button type="button" className="privacy-toggle" aria-pressed={privacyMode} onClick={() => setPrivacyMode(current => !current)}>
            {privacyMode ? "PRIVATE ON" : "PRIVACY"}
          </button>
          <form className="lock-console" action="/api/auth/logout" method="post"><button type="submit">LOCK</button></form>
          {voiceError && <small className="voice-error" role="alert">{voiceError}</small>}
        </div>
        <div className="command-brand"><strong>V. A. R. Y. B. R. A. I. N.</strong><span>CHRIS VARY&apos;S JARVIS</span></div>
        <div className="command-clock">
          <strong>{clock}</strong>
          <div className="command-clock-meta"><span>{date}</span><button type="button" className="module-deck-btn" onClick={() => setMissionDeckOpen(true)}>Mission deck · 11</button></div>
        </div>
      </header>

      <div className="mobile-command-controls">
        <span><i className={`dot${voice.connected ? " active" : ""}`} />{voice.label}</span>
        <button type="button" className="voice-engage-btn" onClick={onEngage} disabled={engaging || voiceRequested}>
          {engaging ? "LINKING…" : voiceRequested ? "VOICE LINKED" : "ENGAGE VOICE"}
        </button>
        <button type="button" className="privacy-toggle" aria-pressed={privacyMode} onClick={() => setPrivacyMode(current => !current)}>
          {privacyMode ? "PRIVATE ON" : "PRIVACY"}
        </button>
        <button type="button" className="module-deck-btn" onClick={() => setMissionDeckOpen(true)}>MODULES · 11</button>
        <form className="lock-console" action="/api/auth/logout" method="post"><button type="submit">LOCK</button></form>
        {voiceError && <small className="voice-error" role="alert">{voiceError}</small>}
      </div>

      <section className="command-grid">
        <aside className="command-column left-stack">
          <Module title="Priority inbox · 24h" count={live?.emails?.length || 0} freshness={live?.modules?.emails} grow>
            <DataBoundary meta={live?.modules?.emails} hasData={Boolean(live?.emails?.length)} empty="No recent inbox mail.">
              <div className="inbox-intelligence-strip">
                <span><strong>{live?.inbox_intelligence?.unread_24h_estimate ?? "—"}</strong> unread est.</span>
                <span><strong>{live?.inbox_intelligence?.priority_count ?? "—"}</strong> priority</span>
              </div>
              <div className="live-list">
                {live?.emails?.slice(0, 6).map((mail, i) => <div className="live-list-row" key={`${mail.source}-${i}`}><span>{mail.when}</span><strong>{privacyMode ? "Private message" : mail.source.replace(/^Email · /, "")}</strong><p>{privacyMode ? "Sender hidden" : mail.who}</p></div>)}
              </div>
            </DataBoundary>
          </Module>
          <Module title="Google tasks" count={live?.tasks?.length || 0} freshness={live?.modules?.tasks}>
            <DataBoundary meta={live?.modules?.tasks} hasData={Boolean(live?.tasks?.length)} empty="No open tasks.">
              <div className="task-mini-list">{live?.tasks?.slice(0, 5).map((task, i) => <div key={task.id || i}><i /> <span>{privacyMode ? "Private task" : task.title}</span></div>)}</div>
            </DataBoundary>
          </Module>
          <Module title="Today’s command queue" count={live?.today_command_queue?.count ?? 0} freshness={live?.modules?.today_command_queue}>
            <DataBoundary meta={live?.modules?.today_command_queue} hasData={Boolean(live?.today_command_queue?.items?.length)} empty="No urgent actions are queued.">
              <div className="command-queue-mini">
                {live?.today_command_queue?.items?.slice(0, 3).map((item) => (
                  <div key={item.id} data-priority={item.priority}>
                    <i /><span><strong>{privacyMode ? "Private priority" : item.title}</strong><small>{privacyMode ? humanize(item.kind) : item.why || item.source}</small></span>
                  </div>
                ))}
              </div>
            </DataBoundary>
            <button type="button" className="open-deck-inline" onClick={() => setMissionDeckOpen(true)}>Open all operational modules</button>
          </Module>
        </aside>

        <section className="command-main">
          <div className="core-zone">
            <div className="core-readout"><span>ACTIVE MODULE</span><strong>{moduleName}</strong></div>
            <VictorsReactor
              state={reactorState(voice.state, Boolean(visibleEvent))}
              amplitude={voice.level}
              bands={voice.bands}
              activeTool={visibleEvent ? moduleName : undefined}
              statusLabel={coreStatus(voice.state, Boolean(visibleEvent))}
            />
          </div>

          <section className={`active-display${visibleEvent ? " has-event" : ""}`}>
            <ConversationModule privacyMode={privacyMode} onPrivacyModeChange={setPrivacyMode} maxEntries={48} />
            {visibleEvent && <div className="event-result-overlay">
              <button type="button" className="event-result-close" onClick={() => setDismissedEventId(visibleEvent.id)}>← Return to conversation</button>
              <div className="event-result-panel">
                {visibleEvent.type === BRIEF && <BriefPanel key={visibleEvent.id} title={visibleEvent.title} data={visibleEvent.payload as BriefPayload} />}
                {visibleEvent.type === METRICS && <MetricsPanel key={visibleEvent.id} title={visibleEvent.title} data={visibleEvent.payload as MetricsPayload} />}
                {visibleEvent.type === PIPELINE && <PipelinePanel key={visibleEvent.id} title={visibleEvent.title} data={visibleEvent.payload as PipelinePayload} />}
                {visibleEvent.type === INTEL && <IntelPanel key={visibleEvent.id} title={visibleEvent.title} data={visibleEvent.payload as IntelPayload} />}
                {visibleEvent.type === ACTIONS && <ActionsPanel key={visibleEvent.id} title={visibleEvent.title} data={visibleEvent.payload as ActionsPayload} />}
              </div>
            </div>}
          </section>
        </section>

        <aside className="command-column right-stack">
          <Module title="Website performance" freshness={live?.modules?.analytics_realtime}>
            <DataBoundary meta={live?.modules?.analytics_portfolio} hasData={Boolean(live?.analytics_portfolio?.readable_property_count)} empty="No readable Analytics properties are configured.">
              <div className="analytics-realtime">
                <div><span>Active now</span><strong>{formatCompactNumber(live?.analytics_realtime?.active_users)}</strong></div>
                <div><span>Views · 30m</span><strong>{formatCompactNumber(live?.analytics_realtime?.page_views_30m)}</strong></div>
              </div>
              <button type="button" className="portfolio-link" onClick={() => setMissionDeckOpen(true)}>{live?.analytics_portfolio?.readable_property_count} websites · open portfolio</button>
              <AnalyticsMini label="Active users · 14d" metric={live?.analytics?.active_users} />
              <AnalyticsMini label="Sessions · 14d" metric={live?.analytics?.sessions} />
            </DataBoundary>
          </Module>
          <Module title="Today · calendar" count={live?.calendar?.length || 0} freshness={live?.modules?.calendar} grow>
            <DataBoundary meta={live?.modules?.calendar} hasData={Boolean(live?.calendar?.length)} empty="Calendar is clear.">
              {live?.meeting_prep?.event && !live.meeting_prep.event.all_day && <button type="button" className="next-meeting-callout" onClick={() => setMissionDeckOpen(true)}><span>Next meeting</span><strong>{privacyMode ? "Private meeting" : live.meeting_prep.event.title}</strong><em>{formatCountdown(live.meeting_prep.event.starts_in_minutes, live.meeting_prep.event.start)}</em></button>}
              <div className="calendar-mini">{live?.calendar?.slice(0, 6).map((item, i) => <div key={`${item.start}-${i}`}><strong>{formatEventTime(item.start)}</strong><span>{privacyMode ? "Private event" : item.title}</span></div>)}</div>
            </DataBoundary>
            <div className="radar-field" aria-hidden><i /><b /><span /></div>
          </Module>
          <Module title="Environment + system" freshness={live?.modules?.system}>
            <div className="system-grid">
              <MetricBox label={live?.weather?.condition || "Weather"} value={live?.weather?.temperature === undefined ? "--" : `${live.weather.temperature}°`} />
              <MetricBox label="CPU" value={live?.system?.cpu === undefined ? "--" : `${live.system.cpu}%`} />
              <MetricBox label="Memory" value={live?.system?.memory === undefined ? "--" : `${live.system.memory}%`} />
              <MetricBox label="Storage" value={live?.system?.disk_free_gb === undefined ? "--" : `${live.system.disk_free_gb}G`} />
            </div>
          </Module>
        </aside>
      </section>

      <DashboardDock
        recentFiles={live?.files?.map(file => ({ ...file, name: privacyMode ? "Private file" : file.name, modified: friendlyAge(file.modified || file.modified_at) }))}
        news={live?.news}
        services={live?.services}
        monitorAlerts={live?.monitors?.alerts?.map((alert) => privacyMode ? { ...alert, title: "Private alert", detail: "Alert details hidden" } : alert)}
        monitorState={dashboardModuleUsable(live?.modules?.monitors) ? live?.monitors?.state || (live?.monitors?.alerts?.length ? "Attention" : "Clear") : live?.modules?.monitors?.status === "loading" ? "Syncing" : "Unavailable"}
        operatingMode={typeof live?.mode === "string" ? live.mode : live?.mode?.mode}
        memoryCount={live?.memory?.count}
        approvalCount={live?.approvals?.count}
        fileStatus={live?.modules?.files?.status}
        monitorStatus={live?.modules?.monitors?.status}
        newsStatus={live?.modules?.news?.status}
        servicesStatus={live?.modules?.services?.status}
      />

      <DashboardMissionDeck
        open={missionDeckOpen}
        onClose={closeMissionDeck}
        onShowConversation={showConversation}
        privacy={privacyMode}
        voiceLabel={voice.label}
        voiceState={voice.state}
        snapshot={live}
        history={history}
      />

      <footer className="event-ticker"><strong>// EVENT STREAM</strong><div>{history.map(item => <span key={item.id}>{new Date(item.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {item.tool}</span>)}</div><em>{visibleEvent?.type.toUpperCase() || "AIOS.IDLE"}</em></footer>
    </main>
  );
}

function useJarvisVoice(requested: boolean) {
  const assistant = useVoiceAssistant();
  const connection = useConnectionState();
  const rawBands = useMultibandTrackVolume(assistant.audioTrack, {
    bands: 30,
    loPass: 0,
    hiPass: 160,
    updateInterval: 50,
    analyserOptions: { fftSize: 2048, smoothingTimeConstant: 0.68 },
  });
  const bands = Array.from({ length: 30 }, (_, i) => clamp(rawBands[i] ?? 0));
  const speaking = assistant.state === "speaking";
  const level = speaking ? Math.max(...bands, 0) : 0;
  const connected = requested && connection === ConnectionState.Connected;

  return {
    bands,
    connected,
    label: voiceLabel(requested ? assistant.state : "disconnected"),
    level,
    speaking,
    state: requested ? assistant.state : "disconnected",
  };
}

type DashboardModuleMeta = NonNullable<DashboardSnapshot["modules"]>[string];

function Module({ title, count, freshness, grow, children }: { title: string; count?: number; freshness?: DashboardModuleMeta; grow?: boolean; children: React.ReactNode }) {
  return <section className={`command-module${grow ? " grow" : ""}`}><header><strong>// {title}</strong><div className="module-head-meta">{freshness && <Freshness meta={freshness} />}{count !== undefined && <span>{count}</span>}</div></header><div className="module-body">{children}</div></section>;
}
function Freshness({ meta }: { meta: DashboardModuleMeta }) {
  const status = meta.status || "loading";
  const label = status === "ok" ? friendlyAge(meta.updated_at, true) : status === "degraded" ? "PARTIAL" : status === "loading" ? "SYNCING" : status.toUpperCase();
  const tone = status === "ok" ? "" : status === "stale" || status === "degraded" ? " stale" : status === "error" || status === "disconnected" ? " error" : "";
  return <small className={`module-freshness${tone}`} title={meta.error || undefined}>{label}</small>;
}
function dashboardModuleUsable(meta?: DashboardModuleMeta) {
  return meta?.status === "ok" || meta?.status === "stale" || meta?.status === "degraded";
}
function DataBoundary({ meta, hasData, empty, children }: { meta?: DashboardModuleMeta; hasData: boolean; empty: string; children: ReactNode }) {
  if (!meta || meta.status === "loading") return <p className="module-empty module-state">Synchronizing live data…</p>;
  if (meta.status === "error" || meta.status === "disconnected") return <p className="module-empty module-state error">Data source unavailable.</p>;
  if (!hasData) return <p className="module-empty">{empty}</p>;
  return <>{children}</>;
}
function StatusRow({ label, value, active }: { label: string; value: string; active?: boolean }) { return <div className="status-row"><span>{label}</span><strong>{value}</strong><i className={active ? "active" : ""} /></div>; }
function MetricBox({ label, value, calm }: { label: string; value: string; calm?: boolean }) { return <div className={`metric-box${calm ? " calm" : ""}`}><span>{label}</span><strong>{value}</strong></div>; }
function AnalyticsMini({ label, metric }: { label: string; metric?: { delta_pct: number; points: { value: number }[] } }) {
  const values = metric?.points?.map(point => point.value) || [];
  const max = Math.max(...values, 1); const min = Math.min(...values, 0); const spread = max - min || 1;
  const points = values.map((value, i) => `${(i / Math.max(values.length - 1, 1)) * 100},${30 - ((value - min) / spread) * 28}`).join(" ");
  return <div className="analytics-mini"><header><span>{label}</span><strong className={(metric?.delta_pct || 0) < 0 ? "down" : ""}>{metric ? `${metric.delta_pct > 0 ? "+" : ""}${metric.delta_pct}%` : "--"}</strong></header><svg viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden><polyline points={points} /></svg></div>;
}

function formatEventTime(value: string) { if (!value) return "ALL DAY"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "ALL DAY" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }

function formatCountdown(minutes?: number | null, start?: string) {
  if (typeof minutes !== "number") return start ? formatEventTime(start) : "UPCOMING";
  if (minutes < 0) return "IN PROGRESS";
  if (minutes < 60) return `IN ${minutes}M`;
  if (minutes < 1440) return `IN ${Math.floor(minutes / 60)}H ${minutes % 60}M`;
  return start ? new Date(start).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }).toUpperCase() : "UPCOMING";
}

function formatCompactNumber(value?: number) { return value === undefined ? "--" : new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value); }

function friendlyAge(value?: string, liveNow = false) {
  if (!value) return liveNow ? "WAIT" : "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 15) return liveNow ? "LIVE" : "NOW";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function clamp(value: number) { return Math.max(0, Math.min(1, value)); }

function humanize(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase()); }

function voiceLabel(state: string) {
  switch (state) {
    case "speaking": return "SPEAKING";
    case "thinking": return "THINKING";
    case "listening": return "LISTENING";
    case "idle": return "READY";
    case "failed": return "VOICE ERROR";
    case "connecting":
    case "initializing":
    case "pre-connect-buffering": return "CONNECTING";
    default: return "STANDBY";
  }
}

function coreStatus(state: string, hasEvent: boolean) {
  switch (state) {
    case "speaking": return "VOICE OUTPUT ACTIVE";
    case "thinking": return "PROCESSING REQUEST";
    case "listening": return "ACQUIRING VOICE";
    case "connecting":
    case "initializing":
    case "pre-connect-buffering": return "ESTABLISHING VOICE LINK";
    case "failed": return "VOICE LINK FAULT";
    default: return hasEvent ? "COMMAND COMPLETE" : "STANDBY";
  }
}

function reactorState(state: string, hasEvent: boolean): VictorsReactorState {
  switch (state) {
    case "speaking": return "speaking";
    case "thinking": return "thinking";
    case "listening": return "listening";
    case "failed": return "error";
    case "connecting":
    case "initializing":
    case "pre-connect-buffering": return "tool-running";
    case "disconnected": return "offline";
    default: return hasEvent ? "success" : "idle";
  }
}
