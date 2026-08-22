"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import OperationalModules, {
  type AlertItem,
  type ApprovalItem,
  type CommandItem,
  type DoctorCheck,
  type ForecastDay,
  type InboxItem,
  type MeetingItem,
  type OperationalState,
  type ResearchItem,
  type RoutineItem,
  type WebsiteProperty,
  type WorkspaceFile,
} from "./OperationalModules";
import type { RenderEnvelope } from "@/lib/renderEvents";
import {
  requestDashboardRefresh,
  type DashboardApproval,
  type DashboardModuleMeta,
  type DashboardSnapshot,
} from "@/lib/dashboardSnapshot";
import styles from "./DashboardMissionDeck.module.css";

interface DashboardMissionDeckProps {
  open: boolean;
  onClose: () => void;
  onShowConversation: () => void;
  privacy: boolean;
  voiceLabel: string;
  voiceState: string;
  snapshot: DashboardSnapshot | null;
  history: RenderEnvelope[];
}

type ApprovalAction = "approve" | "reject";

export default function DashboardMissionDeck({
  open,
  onClose,
  onShowConversation,
  privacy,
  voiceLabel,
  voiceState,
  snapshot,
  history,
}: DashboardMissionDeckProps) {
  const rootRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const reviewRef = useRef<string | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => { reviewRef.current = reviewId; }, [reviewId]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    closeRef.current?.focus();
    const siblings = Array.from(rootRef.current?.parentElement?.children ?? [])
      .filter((element): element is HTMLElement => element instanceof HTMLElement && element !== rootRef.current)
      .map((element) => ({
        element,
        inert: element.inert,
        ariaHidden: element.getAttribute("aria-hidden"),
      }));
    siblings.forEach(({ element }) => {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (reviewRef.current) return;
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab" && !reviewRef.current && rootRef.current) {
        const focusable = Array.from(rootRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], select:not([disabled]), input:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
        )).filter((element) => element.offsetParent !== null);
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.documentElement.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      siblings.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
      previouslyFocused?.focus();
    };
  }, [open]);

  const mapped = useMemo(() => mapSnapshot(snapshot, history), [history, snapshot]);
  const approval = snapshot?.approvals.pending?.find((item) => item.id === reviewId) ?? null;
  if (!open) return null;

  const readyModules = Object.values(snapshot?.modules ?? {}).filter((item) => item.status === "ok").length;
  const totalModules = Object.keys(snapshot?.modules ?? {}).length;

  return (
    <section ref={rootRef} className={styles.backdrop} role="dialog" aria-modal="true" aria-labelledby="mission-deck-title">
      <div className={styles.shell}>
        <header className={styles.header}>
          <div>
            <span>// VARYBRAIN OPERATIONS</span>
            <h1 id="mission-deck-title">Mission Deck</h1>
            <p>Decision modules, live sources, and guarded actions.</p>
          </div>
          <div className={styles.headerStatus}>
            <span className={styles.voiceStatus} data-state={voiceState}>{voiceLabel}</span>
            <span data-health={snapshot?.status === "online" ? "online" : "degraded"}>
              {snapshot?.status?.toUpperCase() || "CONNECTING"}
            </span>
            <strong>{readyModules}/{totalModules || "—"} SOURCES</strong>
            <button type="button" onClick={onShowConversation}>Conversation</button>
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Close mission deck">Close ×</button>
          </div>
        </header>

        <div className={styles.scrollRegion}>
          <OperationalModules
            privacy={privacy}
            commandQueue={{ items: mapped.commands, state: mapped.states.today_command_queue }}
            approvalCenter={{ items: mapped.approvals, state: mapped.states.approvals, onReview: setReviewId }}
            inbox={{ items: mapped.inbox, state: mapped.states.inbox_intelligence }}
            websites={{ properties: mapped.websites, state: mapped.states.analytics_portfolio }}
            meetings={{ meetings: mapped.meetings, state: mapped.states.meeting_prep }}
            alerts={{ alerts: mapped.alerts, state: mapped.states.monitors }}
            workspace={{
              files: mapped.files,
              memoryCount: snapshot?.workspace_sync?.memory_total ?? snapshot?.memory.count,
              bySource: snapshot?.memory.by_source,
              lastSyncAt: friendlyTime(snapshot?.workspace_sync?.checked_at || snapshot?.memory.last_sync_at),
              syncState: mapped.workspaceState,
              state: mapped.states.workspace_sync,
            }}
            doctor={{ checks: mapped.doctor, state: mapped.states.doctor }}
            routines={{ routines: mapped.routines, state: mapped.states.routines }}
            forecast={{
              location: snapshot?.weather.location,
              currentCondition: snapshot?.weather.condition,
              currentTemperature: snapshot?.weather.temperature,
              days: mapped.forecast,
              state: mapped.states.weather,
            }}
            research={{ items: mapped.research, state: mapped.researchState }}
          />
        </div>
      </div>

      {reviewId && (
        <ApprovalDecision
          approval={approval}
          privacy={privacy}
          onClose={() => setReviewId(null)}
        />
      )}
    </section>
  );
}

function ApprovalDecision({ approval, privacy, onClose }: {
  approval: DashboardApproval | null;
  privacy: boolean;
  onClose: () => void;
}) {
  const decisionRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<ApprovalAction | null>(null);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const container = decisionRef.current;
    container?.querySelector<HTMLElement>("input, button")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !container) return;
      const focusable = Array.from(container.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
      )).filter((element) => element.offsetParent !== null);
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, []);

  const act = async (action: ApprovalAction) => {
    if (!approval || (action === "approve" && !confirmed)) return;
    setBusy(action);
    setResult(null);
    try {
      const response = await fetch("/api/dashboard/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, id: approval.id, confirm: true }),
      });
      const body = await response.json();
      if (!response.ok || !body.ok) throw new Error(body.error || "The action did not complete.");
      setResult({ ok: true, message: action === "approve" ? "Approved and executed." : "Rejected without a cloud change." });
      requestDashboardRefresh();
    } catch (error) {
      setResult({ ok: false, message: error instanceof Error ? error.message : "The action did not complete." });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.decisionBackdrop} role="alertdialog" aria-modal="true" aria-labelledby="approval-decision-title">
      <section ref={decisionRef} className={styles.decision}>
        <span>// EXPLICIT AUTHORIZATION REQUIRED</span>
        <h2 id="approval-decision-title">Review cloud action</h2>
        {!approval ? <p>This approval is no longer pending. Refresh the queue before retrying.</p> : (
          <>
            <dl>
              <div><dt>Action</dt><dd>{privacy ? "Private action" : approval.title}</dd></div>
              <div><dt>Target</dt><dd>{privacy ? "Private target" : approval.target || "Not provided"}</dd></div>
              <div><dt>Effect</dt><dd>{privacy ? "Action details hidden" : approval.effect || "Not provided"}</dd></div>
              <div><dt>Approval ID</dt><dd><code>{privacy ? "Private ID" : approval.id}</code></dd></div>
            </dl>
            {approval.notes && <p>{privacy ? "Notes hidden by Privacy Mode." : approval.notes}</p>}
            {!result?.ok && <label className={styles.confirmation}>
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              <span>I authorize Jarvis to perform this exact action.</span>
            </label>}
          </>
        )}
        {result && <p className={result.ok ? styles.success : styles.failure} role={result.ok ? "status" : "alert"}>{result.message}</p>}
        <div className={styles.decisionActions}>
          <button type="button" onClick={onClose}>{result?.ok ? "Done" : "Cancel"}</button>
          {approval && !result?.ok && <>
            <button type="button" className={styles.reject} disabled={Boolean(busy)} onClick={() => void act("reject")}>{busy === "reject" ? "Rejecting…" : "Reject"}</button>
            <button type="button" className={styles.approve} disabled={!confirmed || Boolean(busy)} onClick={() => void act("approve")}>{busy === "approve" ? "Approving…" : "Approve action"}</button>
          </>}
        </div>
      </section>
    </div>
  );
}

function mapSnapshot(snapshot: DashboardSnapshot | null, history: RenderEnvelope[]) {
  const states = new Proxy({} as Record<string, OperationalState>, {
    get: (_target, key: string) => moduleState(snapshot, key),
  });

  const commands: CommandItem[] = (snapshot?.today_command_queue?.items ?? []).map((item) => ({
    id: item.id,
    title: item.title,
    source: item.source,
    due: friendlyDue(item.due_at),
    priority: item.priority === "urgent" || item.priority === "high" ? "high" : item.priority === "low" ? "low" : "normal",
    status: item.why,
  }));

  const approvals: ApprovalItem[] = (snapshot?.approvals.pending ?? []).map((item) => ({
    id: item.id,
    title: item.title,
    kind: humanize(item.kind),
    notes: item.notes,
    target: item.target,
    effect: item.effect,
    due: friendlyDue(item.due),
    createdAt: friendlyTime(item.created_at),
    status: item.status,
    requiresExplicitApproval: item.requires_explicit_approval,
  }));

  const inboxSource = snapshot?.inbox_intelligence?.priority?.length
    ? snapshot.inbox_intelligence.priority
    : snapshot?.emails ?? [];
  const inbox: InboxItem[] = inboxSource.map((item, index) => ({
    id: item.id || `${item.received_at || item.when}-${index}`,
    subject: item.subject || item.source.replace(/^Email · /, ""),
    sender: item.who,
    receivedAt: item.when || friendlyTime(item.received_at),
    summary: item.quote,
    unread: item.unread,
    important: item.important || item.starred,
  }));

  const websites: WebsiteProperty[] = (snapshot?.analytics_portfolio?.properties ?? []).map((property) => {
    const trend = property.trend?.map((point) => point.sessions) ?? [];
    return {
      id: property.id,
      name: property.name,
      activeUsers: property.realtime?.active_users,
      pageViews30m: property.realtime?.page_views_30m,
      sessions: numberOrUndefined(property.totals?.sessions),
      views: numberOrUndefined(property.totals?.views),
      keyEvents: numberOrUndefined(property.totals?.key_events),
      changePct: percentChange(trend),
      trend,
      status: property.status,
      message: property.error || undefined,
      topPages: property.top_pages,
      events: property.key_events,
    };
  });

  const eventCandidate = snapshot?.meeting_prep?.event;
  const event = eventCandidate && !eventCandidate.all_day && eventCandidate.queue_eligible !== false
    ? eventCandidate
    : null;
  const attendeeNames = event?.attendees
    ?.filter((attendee) => !attendee.self)
    .map((attendee) => attendee.name || attendee.email || "Guest") ?? [];
  const meetings: MeetingItem[] = event ? [{
    id: event.id,
    title: event.title,
    start: meetingCountdown(event.starts_in_minutes, event.start),
    with: attendeeNames.join(" · ") || undefined,
    location: event.location,
    description: event.description,
    attendees: attendeeNames,
    meetingUrl: event.meeting_url,
    calendarUrl: event.calendar_url,
    prepNotes: snapshot?.meeting_prep?.related
      ?.filter((item) => (item.relevance ?? 0) >= 0.55 && safeAmbientTitle(item.title))
      .map((item) => `${item.title} · ${item.source}`),
    source: "Google Calendar",
  }] : [];

  const alerts: AlertItem[] = (snapshot?.alerts ?? snapshot?.monitors?.timeline ?? []).map((item) => ({
    id: item.id,
    title: item.title,
    source: item.source,
    severity: item.severity,
    detectedAt: friendlyTime(item.last_seen_at || item.detected_at || item.first_seen_at),
    detail: item.detail || (item.occurrences && item.occurrences > 1 ? `${item.occurrences} occurrences` : undefined),
  }));

  const files: WorkspaceFile[] = (snapshot?.files ?? []).filter((item) => safeAmbientTitle(item.name)).map((item, index) => ({
    id: item.id || `${item.source}-${item.name}-${index}`,
    name: item.name,
    source: item.source,
    modifiedAt: friendlyTime(item.modified_at || item.modified),
    type: item.type,
  }));

  const doctor: DoctorCheck[] = (snapshot?.doctor?.checks ?? []).map((item) => ({
    id: item.id,
    name: item.name,
    status: item.status || (item.ok ? "online" : "offline"),
    detail: item.detail,
    latencyMs: item.latency_ms,
  }));

  const routines: RoutineItem[] = [];
  if (snapshot?.routines?.digest) routines.push({
    id: "morning-digest",
    name: "Morning briefing",
    schedule: `Daily · ${snapshot.routines.digest.label || "configured hour"}`,
    nextRun: friendlyDateTime(snapshot.routines.digest.next_due_at),
    lastRun: snapshot.routines.digest.last_delivered_date || "No delivery recorded",
    enabled: true,
    status: snapshot.routines.digest.due ? "Due" : "Scheduled",
  });
  if (snapshot?.routines?.monitor) routines.push({
    id: "continuous-monitor",
    name: "Gmail + Analytics monitor",
    schedule: everyDuration(snapshot.routines.monitor.interval_seconds),
    nextRun: friendlyDateTime(snapshot.routines.monitor.next_check_at),
    lastRun: friendlyDateTime(snapshot.routines.monitor.last_checked_at),
    enabled: true,
    status: snapshot.routines.monitor.overdue ? "Overdue" : "Active",
  });
  if (snapshot?.routines?.mode) routines.push({
    id: "operating-mode",
    name: `${humanize(snapshot.routines.mode)} operating mode`,
    schedule: "Active until changed",
    enabled: true,
    status: "Active",
  });

  const forecast: ForecastDay[] = (snapshot?.weather.days ?? []).map((day) => ({
    day: day.day,
    condition: day.condition,
    high: day.high,
    low: day.low,
    rainChance: day.rain,
  }));

  const research: ResearchItem[] = history
    .filter((item) => item.tool === "deep_research")
    .map((item) => {
      const payload = item.payload as { query?: string; items?: Array<{ url?: string }> };
      return {
        id: item.id,
        title: item.title,
        query: payload.query,
        sourceCount: payload.items?.length,
        completedAt: friendlyDateTime(new Date(item.ts).toISOString()),
        summary: item.spoken,
        url: payload.items?.find((entry) => entry.url)?.url,
      };
    });

  const workspaceStates = Object.values(snapshot?.workspace_sync?.sources ?? {})
    .map((item) => item.status)
    .filter((item): item is string => Boolean(item));
  const workspaceState = workspaceStates.length
    ? workspaceStates.every((item) => item === "indexed") ? "Indexed" : workspaceStates.map(humanize).join(" · ")
    : "Awaiting sync data";

  return {
    states,
    commands,
    approvals,
    inbox,
    websites,
    meetings,
    alerts,
    files,
    doctor,
    routines,
    forecast,
    research,
    workspaceState,
    researchState: research.length
      ? { status: "ready" as const, updatedAt: research[0].completedAt }
      : { status: "unavailable" as const, message: "Research history appears here after a cited research request in this voice session." },
  };
}

function moduleState(snapshot: DashboardSnapshot | null, key: string): OperationalState {
  if (!snapshot) return { status: "loading", message: "Waiting for the local dashboard feed." };
  const meta: DashboardModuleMeta | undefined = snapshot.modules?.[key];
  if (!meta) return { status: "unavailable", message: "This module is not present in the current feed." };
  const status: OperationalState["status"] = meta.status === "ok"
    ? "ready"
    : meta.status === "loading" ? "loading"
    : meta.status === "stale" || meta.status === "degraded" ? "stale"
    : meta.status === "error" ? "error"
    : "unavailable";
  return { status, updatedAt: friendlyTime(meta.updated_at), message: meta.error || undefined };
}

function numberOrUndefined(value: number | null | undefined) {
  return typeof value === "number" ? value : undefined;
}

function percentChange(values: number[]) {
  if (values.length < 2 || values[0] === 0) return undefined;
  return Math.round(((values.at(-1)! - values[0]) / values[0]) * 1_000) / 10;
}

function meetingCountdown(minutes: number | null | undefined, start: string) {
  if (typeof minutes !== "number") return friendlyDateTime(start);
  if (minutes < 0) return "In progress";
  if (minutes < 60) return `In ${minutes}m`;
  if (minutes < 24 * 60) return `In ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return friendlyDateTime(start);
}

function friendlyDue(value?: string) {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function friendlyTime(value?: string) {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1_000));
  if (seconds < 30) return "Now";
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function friendlyDateTime(value?: string) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function everyDuration(seconds?: number) {
  if (!seconds) return "Configured interval";
  if (seconds % 3_600 === 0) return `Every ${seconds / 3_600}h`;
  return `Every ${Math.round(seconds / 60)}m`;
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function safeAmbientTitle(value: string) {
  return !/(password|credential|recovery code|secret key|api key|authentication token)/i.test(value);
}
