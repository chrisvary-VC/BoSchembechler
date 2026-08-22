import { scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  SESSION_TTL_SECONDS,
  createAccessSession,
  isSameRequestOrigin,
  publicRequestOrigin,
  safeNextPath,
} from "@/lib/accessSession";

export const dynamic = "force-dynamic";

const scryptAsync = promisify(scrypt);
const MAX_ATTEMPTS = 5;
const WINDOW_MS = 15 * 60 * 1_000;
type Attempt = { count: number; resetAt: number };
const processState = globalThis as typeof globalThis & { varybrainLoginAttempts?: Map<string, Attempt> };
const attempts = processState.varybrainLoginAttempts ??= new Map<string, Attempt>();

function requestIp(request: Request) {
  return request.headers.get("cf-connecting-ip")
    || request.headers.get("x-forwarded-for")?.split(",", 1)[0]?.trim()
    || "local";
}

function isRateLimited(ip: string, now: number) {
  const current = attempts.get(ip);
  if (!current || current.resetAt <= now) {
    attempts.delete(ip);
    return false;
  }
  return current.count >= MAX_ATTEMPTS;
}

function recordFailure(ip: string, now: number) {
  const current = attempts.get(ip);
  if (!current || current.resetAt <= now) {
    attempts.set(ip, { count: 1, resetAt: now + WINDOW_MS });
  } else {
    current.count += 1;
  }
}

async function passwordMatches(password: string, encodedHash: string) {
  const separator = encodedHash.startsWith("scrypt:") ? ":" : "$";
  const [scheme, salt, expectedHex, ...rest] = encodedHash.split(separator);
  if (scheme !== "scrypt" || rest.length || !salt || !/^[a-f0-9]{128}$/i.test(expectedHex || "")) {
    return false;
  }
  const expected = Buffer.from(expectedHex, "hex");
  const actual = await scryptAsync(password, salt, expected.length) as Buffer;
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

function failureResponse(request: Request, next: string, status: number, error: string, json: boolean) {
  if (json) {
    return NextResponse.json({ ok: false, error }, {
      status,
      headers: { "Cache-Control": "no-store" },
    });
  }
  const location = new URL("/login", publicRequestOrigin(request));
  location.searchParams.set("error", status === 429 ? "rate" : status === 503 ? "config" : "invalid");
  location.searchParams.set("next", next);
  return NextResponse.redirect(location, 303);
}

export async function POST(request: Request) {
  const contentLength = Number(request.headers.get("content-length") || "0");
  const wantsJson = request.headers.get("content-type")?.includes("application/json") ?? false;
  if (!Number.isFinite(contentLength) || contentLength > 4_096 || !isSameRequestOrigin(request)) {
    return failureResponse(request, "/", 400, "Unable to authenticate.", wantsJson);
  }

  let password = "";
  let next = "/";
  try {
    if (wantsJson) {
      const body = await request.json() as { password?: unknown; next?: unknown };
      password = typeof body.password === "string" ? body.password : "";
      next = safeNextPath(typeof body.next === "string" ? body.next : "/");
    } else {
      const body = await request.formData();
      password = String(body.get("password") || "");
      next = safeNextPath(String(body.get("next") || "/"));
    }
  } catch {
    return failureResponse(request, next, 400, "Unable to authenticate.", wantsJson);
  }

  // Copying a passcode from a message can add an invisible leading or trailing
  // space. Ignore only that accidental whitespace; the password itself remains
  // case-sensitive and otherwise exact.
  password = password.trim();

  const passwordHash = process.env.JARVIS_GATE_PASSWORD_HASH;
  const sessionSecret = process.env.JARVIS_SESSION_SECRET;
  if (!passwordHash || !sessionSecret) {
    return failureResponse(request, next, 503, "Access control is unavailable.", wantsJson);
  }

  const ip = requestIp(request);
  const now = Date.now();
  if (isRateLimited(ip, now)) {
    return failureResponse(request, next, 429, "Too many attempts. Try again later.", wantsJson);
  }

  const valid = password.length <= 256 && await passwordMatches(password, passwordHash);
  if (!valid) {
    recordFailure(ip, now);
    return failureResponse(request, next, 401, "Unable to authenticate.", wantsJson);
  }
  attempts.delete(ip);

  const response = wantsJson
    ? NextResponse.json({ ok: true, next }, { headers: { "Cache-Control": "no-store" } })
    : NextResponse.redirect(new URL(next, publicRequestOrigin(request)), 303);
  const secure = new URL(publicRequestOrigin(request)).protocol === "https:";
  response.cookies.set(ACCESS_COOKIE, await createAccessSession(sessionSecret, now), {
    httpOnly: true,
    secure,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  return response;
}
