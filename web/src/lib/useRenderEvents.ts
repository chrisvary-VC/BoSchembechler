"use client";

import { useEffect, useState } from "react";
import { RoomEvent } from "livekit-client";
import { useRoomContext } from "@livekit/components-react";
import { RENDER_TOPIC, parseRenderEvent, type RenderEnvelope } from "./renderEvents";

/**
 * Subscribes to the room data channel and routes by type.
 * Returns the latest render event, or null before the first one lands.
 */
export function useRenderEvents(): RenderEnvelope | null {
  const room = useRoomContext();
  const [event, setEvent] = useState<RenderEnvelope | null>(null);

  useEffect(() => {
    if (!room) return;

    const onData = (payload: Uint8Array, _p?: unknown, _k?: unknown, topic?: string) => {
      if (topic && topic !== RENDER_TOPIC) return;
      const parsed = parseRenderEvent(payload);
      if (!parsed) {
        // Off-contract payloads land here. If panels stopped moving, check that
        // agent/render.py and lib/renderEvents.ts still agree.
        console.warn("[aios] ignored an off-contract data message", { topic });
        return;
      }
      setEvent(parsed);
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room]);

  return event;
}
