export const ACCESS_COOKIE = "varybrain_access";
export const SESSION_TTL_SECONDS = 12 * 60 * 60;

const encoder = new TextEncoder();

function hex(bytes: ArrayBuffer) {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function signature(expiresAt: number, secret: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(await crypto.subtle.sign("HMAC", key, encoder.encode(`varybrain:${expiresAt}`)));
}

function constantTimeEqual(left: string, right: string) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

export async function createAccessSession(secret: string, now = Date.now()) {
  const expiresAt = now + SESSION_TTL_SECONDS * 1_000;
  return `${expiresAt}.${await signature(expiresAt, secret)}`;
}

export async function verifyAccessSession(token: string | undefined, secret: string, now = Date.now()) {
  if (!token || !secret) return false;
  const [rawExpiresAt, suppliedSignature, ...rest] = token.split(".");
  if (rest.length || !rawExpiresAt || !suppliedSignature) return false;
  const expiresAt = Number(rawExpiresAt);
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= now) return false;
  return constantTimeEqual(suppliedSignature, await signature(expiresAt, secret));
}

export function safeNextPath(value: string | null | undefined) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  try {
    const parsed = new URL(value, "https://varybrain.local");
    if (parsed.origin !== "https://varybrain.local") return "/";
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return "/";
  }
}

export function publicRequestOrigin(request: Request) {
  const direct = new URL(request.url);
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",", 1)[0]?.trim();
  const host = forwardedHost || request.headers.get("host") || direct.host;
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim();
  const protocol = forwardedProto === "https" || forwardedProto === "http"
    ? forwardedProto
    : direct.protocol.slice(0, -1);
  try {
    return new URL(`${protocol}://${host}`).origin;
  } catch {
    return direct.origin;
  }
}

function isLoopback(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function effectivePort(url: URL) {
  return url.port || (url.protocol === "https:" ? "443" : "80");
}

export function isSameRequestOrigin(request: Request) {
  const rawOrigin = request.headers.get("origin");
  if (!rawOrigin) return true;
  try {
    const supplied = new URL(rawOrigin);
    const expected = new URL(publicRequestOrigin(request));
    return supplied.origin === expected.origin || (
      isLoopback(supplied.hostname)
      && isLoopback(expected.hostname)
      && supplied.protocol === expected.protocol
      && effectivePort(supplied) === effectivePort(expected)
    );
  } catch {
    return false;
  }
}
