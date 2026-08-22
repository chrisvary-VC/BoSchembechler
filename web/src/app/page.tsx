"use client";

import { useCallback, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, StartAudio } from "@livekit/components-react";
import HudStage from "@/components/HudStage";

export default function Page() {
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  const engage = useCallback(async () => {
    setConnecting(true);
    setError(null);
    try {
      const roomBase = process.env.NEXT_PUBLIC_AIOS_ROOM || "aios";
      const room = `${roomBase}-${Date.now().toString(36)}`;
      const res = await fetch(`/api/token?room=${encodeURIComponent(room)}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "token request failed");
      setToken(body.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setConnecting(false);
    }
  }, []);

  const voiceRequested = token !== null;

  return (
    <LiveKitRoom
      token={token ?? undefined}
      serverUrl={process.env.NEXT_PUBLIC_LIVEKIT_URL}
      connect={voiceRequested}
      audio={
        voiceRequested
          ? {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
              channelCount: 1,
            }
          : false
      }
      video={false}
      onConnected={() => setConnecting(false)}
      onDisconnected={() => {
        if (token) {
          setError((current) => current ?? "Voice session disconnected. Click Engage to reconnect.");
        }
        setToken(null);
        setConnecting(false);
      }}
      onError={(err) => {
        setError(`Connection failed: ${err.message}`);
        setToken(null);
        setConnecting(false);
      }}
      onMediaDeviceFailure={(failure) => {
        setError(`Microphone unavailable${failure ? `: ${failure}` : "."}`);
        setToken(null);
        setConnecting(false);
      }}
    >
      <RoomAudioRenderer />
      {voiceRequested && <StartAudio className="start-audio" label="Enable voice audio" />}
      <HudStage
        onEngage={engage}
        engaging={connecting}
        voiceRequested={voiceRequested}
        voiceError={error}
      />
    </LiveKitRoom>
  );
}
