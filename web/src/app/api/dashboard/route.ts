import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const DASHBOARD_MODULES = [
  "emails", "inbox_intelligence", "tasks", "calendar", "meeting_prep",
  "weather", "system", "analytics", "analytics_portfolio", "analytics_realtime",
  "memory", "approvals", "files", "workspace_sync", "news", "monitors",
  "mode", "routines", "today_command_queue", "doctor", "services",
] as const;

export async function GET() {
  try {
    const response = await fetch("http://127.0.0.1:8788/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`feed returned ${response.status}`);
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Local dashboard feed unavailable";
    return NextResponse.json({
      status: "offline", generated_at: "", emails: [], tasks: [], calendar: [],
      weather: {}, system: {}, analytics: {}, memory: { count: 0 }, approvals: { count: 0 },
      services: {},
      modules: Object.fromEntries(DASHBOARD_MODULES.map((name) => [name, {
        status: "disconnected", error: message,
      }])),
      errors: [message],
    }, { status: 503 });
  }
}
