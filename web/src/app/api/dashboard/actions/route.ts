import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const ACTION_ID = /^[a-f0-9]{8}$/i;

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin) {
    try {
      if (new URL(origin).host !== request.nextUrl.host) {
        return json({ ok: false, error: "Cross-origin dashboard actions are not allowed." }, 403);
      }
    } catch {
      return json({ ok: false, error: "Invalid request origin." }, 403);
    }
  }

  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return json({ ok: false, error: "Content-Type must be application/json." }, 415);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "Request body must be valid JSON." }, 400);
  }

  if (!body || typeof body !== "object") {
    return json({ ok: false, error: "Invalid action request." }, 400);
  }

  const { action, id, confirm } = body as Record<string, unknown>;
  if ((action !== "approve" && action !== "reject") || typeof id !== "string" || !ACTION_ID.test(id)) {
    return json({ ok: false, error: "A valid action and exact approval ID are required." }, 400);
  }
  if (confirm !== true) {
    return json({ ok: false, error: "Explicit confirmation is required." }, 400);
  }

  try {
    const response = await fetch(`http://127.0.0.1:8788/actions/${action}`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, confirm: true }),
      signal: AbortSignal.timeout(20_000),
    });
    const result = await response.json();
    return json(result, response.status);
  } catch (error) {
    const message = error instanceof Error && error.name === "TimeoutError"
      ? "The approval service timed out before making a confirmed change. Check the queue before retrying."
      : "The local approval service is unavailable.";
    return json({ ok: false, error: message }, 503);
  }
}

function json(body: unknown, status: number) {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}
