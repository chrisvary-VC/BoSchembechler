"use client";

import { useCallback, useEffect, useState } from "react";

export type DashboardModuleStatus =
  | "loading"
  | "ok"
  | "degraded"
  | "stale"
  | "error"
  | "disconnected";

export interface DashboardModuleMeta {
  status?: DashboardModuleStatus;
  updated_at?: string;
  stale_at?: string;
  next_refresh_at?: string;
  latency_ms?: number | null;
  error?: string | null;
}

export interface DashboardEmail {
  id?: string;
  thread_id?: string;
  received_at?: string;
  when: string;
  source: string;
  subject?: string;
  who: string;
  quote: string;
  unread?: boolean;
  important?: boolean;
  starred?: boolean;
  priority?: "high" | "attention" | "normal";
  priority_score?: number;
  bulk?: boolean;
  priority_eligible?: boolean;
  queue_eligible?: boolean;
}

export interface DashboardTask {
  id: string;
  title: string;
  due: string;
  status: string;
  updated?: string;
}

export interface DashboardCalendarEvent {
  id?: string;
  title: string;
  start: string;
  end?: string;
  all_day?: boolean;
  location?: string;
}

export interface DashboardApproval {
  id: string;
  kind: string;
  title: string;
  notes?: string;
  due?: string;
  status?: string;
  created_at?: string;
  age_minutes?: number | null;
  target?: string;
  effect?: string;
  requires_explicit_approval?: boolean;
}

export interface DashboardCommandItem {
  id: string;
  kind: "approval" | "alert" | "meeting" | "task" | "email" | string;
  priority: "urgent" | "high" | "normal" | "low";
  priority_score?: number;
  title: string;
  source?: string;
  why?: string;
  due_at?: string;
  reference_id?: string;
}

export interface DashboardAlert {
  id: string;
  title: string;
  source?: string;
  severity?: "info" | "warning" | "critical";
  detected_at?: string;
  first_seen_at?: string;
  last_seen_at?: string;
  detail?: string;
  active?: boolean;
  occurrences?: number;
}

export interface DashboardSnapshot {
  v?: number;
  status: string;
  generated_at: string;
  emails: DashboardEmail[];
  inbox_intelligence?: {
    recent_24h_estimate?: number;
    unread_estimate?: number;
    unread_24h_estimate?: number;
    important_24h_estimate?: number;
    starred_estimate?: number;
    priority_count?: number;
    priority?: DashboardEmail[];
    last_received_at?: string;
    counts_are_estimates?: boolean;
  };
  tasks: DashboardTask[];
  calendar: DashboardCalendarEvent[];
  meeting_prep?: {
    status?: string;
    prepared_at?: string;
    event?: {
      id: string;
      title: string;
      start: string;
      end?: string;
      all_day?: boolean;
      starts_in_minutes?: number | null;
      phase?: string;
      location?: string;
      description?: string;
      calendar_url?: string;
      meeting_url?: string;
      queue_eligible?: boolean;
      attendee_count?: number;
      attendees?: Array<{
        name?: string;
        email?: string;
        response_status?: string;
        self?: boolean;
        organizer?: boolean;
      }>;
    } | null;
    related?: Array<{
      id: string;
      source: string;
      title: string;
      snippet?: string;
      updated_at?: string;
      relevance?: number;
    }>;
  };
  weather: {
    location?: string;
    condition?: string;
    temperature?: number;
    feels_like?: number;
    humidity?: number;
    wind?: number;
    precipitation?: number;
    days?: Array<{
      day: string;
      condition: string;
      high?: number;
      low?: number;
      rain?: number;
    }>;
  };
  system: {
    cpu?: number;
    memory?: number;
    disk?: number;
    disk_free_gb?: number;
    battery?: number | null;
    charging?: boolean | null;
  };
  analytics: Record<string, {
    metric: string;
    delta_pct: number;
    points: { date: string; value: number }[];
  }>;
  analytics_realtime?: {
    active_users?: number;
    page_views_30m?: number;
    properties?: Array<{
      id: string;
      name?: string;
      active_users: number;
      page_views_30m: number;
    }>;
  };
  analytics_portfolio?: {
    period?: { start?: string; end?: string; days?: number };
    property_count?: number;
    readable_property_count?: number;
    totals?: Record<string, number>;
    limitations?: string[];
    properties?: Array<{
      id: string;
      name?: string;
      name_configured?: boolean;
      status?: string;
      error?: string | null;
      totals?: {
        active_users?: number | null;
        sessions?: number | null;
        views?: number | null;
        key_events?: number | null;
      };
      trend?: Array<{
        date: string;
        active_users: number;
        sessions: number;
        views: number;
        key_events?: number | null;
      }>;
      top_pages?: Array<{
        path: string;
        title: string;
        views: number;
        active_users: number;
      }>;
      key_events?: Array<{ name: string; count: number }>;
      key_events_supported?: boolean;
      realtime?: { active_users?: number; page_views_30m?: number };
    }>;
  };
  memory: { count: number; by_source?: Record<string, number>; last_sync_at?: string };
  approvals: {
    count: number;
    pending?: DashboardApproval[];
    oldest_age_minutes?: number;
    cloud_writes_guarded?: boolean;
  };
  today_command_queue?: {
    generated_at?: string;
    count?: number;
    urgent_count?: number;
    items?: DashboardCommandItem[];
  };
  services: Record<string, boolean>;
  files?: Array<{
    id?: string;
    source: string;
    name: string;
    modified?: string;
    modified_at?: string;
    type?: string;
    url?: string;
  }>;
  workspace_sync?: {
    total_indexed?: number;
    memory_total?: number;
    checked_at?: string;
    sources?: Record<string, {
      label: string;
      connected?: boolean;
      indexed_count?: number;
      last_indexed_at?: string;
      last_remote_modified_at?: string;
      lag_seconds?: number | null;
      status?: string;
    }>;
  };
  news?: { title: string; source: string; published?: string; url?: string }[];
  monitors?: {
    state?: string;
    checked_at?: string;
    next_check_at?: string;
    important_email_count?: number;
    analytics_delta?: number;
    alert_count?: number;
    active_alert_count?: number;
    alerts?: DashboardAlert[];
    timeline?: DashboardAlert[];
  };
  alerts?: DashboardAlert[];
  mode?: string | { mode?: string; description?: string };
  routines?: {
    timezone?: string;
    digest?: {
      hour?: number;
      label?: string;
      last_delivered_date?: string;
      due?: boolean;
      next_due_at?: string;
    };
    monitor?: {
      interval_seconds?: number;
      last_checked_at?: string;
      next_check_at?: string;
      overdue?: boolean;
    };
    mode?: string;
  };
  doctor?: {
    overall?: string;
    checked_at?: string;
    healthy_count?: number;
    total_count?: number;
    checks?: Array<{
      id: string;
      name: string;
      ok?: boolean;
      status?: "online" | "degraded" | "offline" | "unknown";
      latency_ms?: number;
      detail?: string;
    }>;
    data_modules?: Array<{
      id: string;
      status: DashboardModuleStatus;
      latency_ms?: number | null;
      updated_at?: string;
    }>;
  };
  modules?: Record<string, DashboardModuleMeta>;
  errors: string[];
}

export const DASHBOARD_REFRESH_EVENT = "aios:dashboard-refresh";

export function requestDashboardRefresh() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(DASHBOARD_REFRESH_EVENT));
  }
}

export function useDashboardSnapshot() {
  const [data, setData] = useState<DashboardSnapshot | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store", signal });
      const body = await response.json();
      setData(body);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      // Keep the last good snapshot; its own freshness metadata communicates
      // degraded/offline state without blanking the dashboard.
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const run = () => void refresh(controller.signal);
    run();
    const timer = window.setInterval(run, 5_000);
    window.addEventListener(DASHBOARD_REFRESH_EVENT, run);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener(DASHBOARD_REFRESH_EVENT, run);
    };
  }, [refresh]);

  return data;
}
