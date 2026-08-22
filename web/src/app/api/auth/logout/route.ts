import { NextResponse } from "next/server";
import { ACCESS_COOKIE, publicRequestOrigin } from "@/lib/accessSession";

export async function POST(request: Request) {
  const publicOrigin = publicRequestOrigin(request);
  const response = NextResponse.redirect(new URL("/login", publicOrigin), 303);
  response.cookies.set(ACCESS_COOKIE, "", {
    httpOnly: true,
    secure: new URL(publicOrigin).protocol === "https:",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
