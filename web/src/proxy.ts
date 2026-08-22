import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE, safeNextPath, verifyAccessSession } from "@/lib/accessSession";

const PUBLIC_PATHS = new Set(["/login", "/api/auth/login", "/api/auth/logout"]);

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  const passwordHash = process.env.JARVIS_GATE_PASSWORD_HASH;
  const sessionSecret = process.env.JARVIS_SESSION_SECRET;
  if (!passwordHash || !sessionSecret) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: "Access control is not configured." },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    const login = request.nextUrl.clone();
    login.pathname = "/login";
    login.search = "?error=config";
    return NextResponse.redirect(login);
  }

  const valid = await verifyAccessSession(request.cookies.get(ACCESS_COOKIE)?.value, sessionSecret);
  if (valid) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      { error: "Authentication required." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  const login = request.nextUrl.clone();
  login.pathname = "/login";
  login.search = "";
  login.searchParams.set("next", safeNextPath(`${pathname}${search}`));
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|brand/).*)"],
};
