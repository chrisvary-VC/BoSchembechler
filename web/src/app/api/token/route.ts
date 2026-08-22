import { AccessToken } from "livekit-server-sdk";
import { NextResponse } from "next/server";

export const revalidate = 0;

export async function GET(request: Request) {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  if (!apiKey || !apiSecret) {
    return NextResponse.json(
      { error: "LIVEKIT_API_KEY / LIVEKIT_API_SECRET missing from web/.env.local" },
      { status: 500 },
    );
  }

  const url = new URL(request.url);
  const roomBase = process.env.NEXT_PUBLIC_AIOS_ROOM || "aios";
  const requestedRoom = url.searchParams.get("room") || roomBase;
  const validRoom = /^[A-Za-z0-9_-]{1,64}$/.test(requestedRoom)
    && (requestedRoom === roomBase || requestedRoom.startsWith(`${roomBase}-`));
  if (!validRoom) {
    return NextResponse.json({ error: "Invalid room request." }, { status: 400 });
  }
  const room = requestedRoom;
  const identity = `hud-${Math.random().toString(36).slice(2, 10)}`;

  const at = new AccessToken(apiKey, apiSecret, { identity, ttl: "1h" });
  at.addGrant({ room, roomJoin: true, canPublish: true, canSubscribe: true, canPublishData: false });

  return NextResponse.json({ token: await at.toJwt(), room, identity });
}
