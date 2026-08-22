"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ConnectionState,
  RoomEvent,
  type ChatMessage,
  type Participant,
  type TranscriptionSegment,
} from "livekit-client";
import {
  useConnectionState,
  useRoomContext,
  useVoiceAssistant,
  type AgentState,
} from "@livekit/components-react";
import { useRenderEvents } from "./useRenderEvents";

export type ConversationRole = "user" | "assistant" | "system" | "unknown";
export type ConversationEntryKind =
  | "transcript"
  | "chat"
  | "tool"
  | "agent-state";

export interface ConversationTelemetryEntry {
  id: string;
  timestamp: number;
  updatedAt: number;
  role: ConversationRole;
  kind: ConversationEntryKind;
  text: string;
  final: boolean;
  source: "livekit-transcription" | "livekit-chat" | "render-event" | "agent";
}
export type ConversationAvailability =
  | "connecting"
  | "ready"
  | "empty"
  | "unavailable";

export interface ConversationTelemetry {
  entries: ConversationTelemetryEntry[];
  agentState: AgentState;
  connectionState: ConnectionState;
  availability: ConversationAvailability;
  latestFinalAssistant: ConversationTelemetryEntry | null;
  latestTool: ConversationTelemetryEntry | null;
  clearHistory: () => void;
}

export interface UseConversationTelemetryOptions {
  /** In-memory entry limit. Values are constrained to 10–100. */
  maxEntries?: number;
}

const DEFAULT_MAX_ENTRIES = 48;
const MAX_TEXT_LENGTH = 4_000;
const CROSS_SOURCE_DUPLICATE_WINDOW_MS = 8_000;

const AGENT_STATE_LABELS: Record<AgentState, string> = {
  disconnected: "Agent disconnected",
  connecting: "Agent connecting",
  "pre-connect-buffering": "Preparing microphone",
  failed: "Agent unavailable",
  initializing: "Agent initializing",
  idle: "Agent standing by",
  listening: "Agent listening",
  thinking: "Agent thinking",
  speaking: "Agent speaking",
};

function normalizeLimit(value: number | undefined) {
  const numeric = Number.isFinite(value) ? Math.trunc(value ?? DEFAULT_MAX_ENTRIES) : DEFAULT_MAX_ENTRIES;
  return Math.min(100, Math.max(10, numeric));
}

function cleanText(value: string) {
  return value
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .trim()
    .slice(0, MAX_TEXT_LENGTH);
}

function normalizeTimestamp(value: number | undefined) {
  if (!Number.isFinite(value) || !value || value < 0) return Date.now();
  return value < 1_000_000_000_000 ? value * 1_000 : value;
}

function normalizeComparableText(value: string) {
  return value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function humanizeTool(value: string) {
  return cleanText(value.replaceAll("_", " ").replace(/\s+/g, " ")).slice(0, 96);
}

function resolveRole(participant: Participant | undefined, localIdentity: string): ConversationRole {
  if (!participant) return "unknown";
  if (participant.isAgent) return "assistant";
  if (participant.isLocal || participant.identity === localIdentity) return "user";
  return "unknown";
}

function isConversationContent(entry: ConversationTelemetryEntry) {
  return entry.kind === "transcript" || entry.kind === "chat";
}

function upsertEntry(
  current: ConversationTelemetryEntry[],
  incoming: ConversationTelemetryEntry,
  limit: number,
) {
  const byId = current.findIndex((entry) => entry.id === incoming.id);
  let next = [...current];

  if (byId >= 0) {
    next[byId] = {
      ...next[byId],
      ...incoming,
      timestamp: Math.min(next[byId].timestamp, incoming.timestamp),
    };
  } else {
    const duplicateIndex =
      incoming.final && isConversationContent(incoming)
        ? next.findIndex(
            (entry) =>
              entry.final &&
              isConversationContent(entry) &&
              entry.role === incoming.role &&
              entry.source !== incoming.source &&
              Math.abs(entry.timestamp - incoming.timestamp) <=
                CROSS_SOURCE_DUPLICATE_WINDOW_MS &&
              normalizeComparableText(entry.text) ===
                normalizeComparableText(incoming.text),
          )
        : -1;

    if (duplicateIndex >= 0) {
      // Prefer the spoken transcription when the same finalized content also
      // arrives through chat. Both are authentic LiveKit messages, but showing
      // them twice makes the conversation appear to repeat itself.
      if (incoming.kind === "transcript") {
        next[duplicateIndex] = {
          ...incoming,
          timestamp: Math.min(next[duplicateIndex].timestamp, incoming.timestamp),
        };
      }
    } else {
      next.push(incoming);
    }
  }

  return next
    .sort((left, right) => left.timestamp - right.timestamp || left.id.localeCompare(right.id))
    .slice(-limit);
}

export function useConversationTelemetry(
  options: UseConversationTelemetryOptions = {},
): ConversationTelemetry {
  const room = useRoomContext();
  const connectionState = useConnectionState(room);
  const { state: agentState } = useVoiceAssistant();
  const renderEvent = useRenderEvents();
  const maxEntries = normalizeLimit(options.maxEntries);
  const [entries, setEntries] = useState<ConversationTelemetryEntry[]>([]);
  const lastAgentState = useRef<AgentState | null>(null);
  const stateSequence = useRef(0);

  useEffect(() => {
    const localIdentity = room.localParticipant.identity;

    const onTranscription = (
      segments: TranscriptionSegment[],
      participant?: Participant,
    ) => {
      const role = resolveRole(participant, localIdentity);
      const participantKey = participant?.identity || "unknown";

      setEntries((current) => {
        let next = current;

        for (const segment of segments) {
          const text = cleanText(segment.text);
          if (!text) continue;

          next = upsertEntry(
            next,
            {
              id: `transcript:${participantKey}:${segment.id}`,
              timestamp: normalizeTimestamp(segment.firstReceivedTime),
              updatedAt: normalizeTimestamp(segment.lastReceivedTime),
              role,
              kind: "transcript",
              text,
              final: segment.final,
              source: "livekit-transcription",
            },
            maxEntries,
          );
        }

        return next;
      });
    };

    const onChatMessage = (message: ChatMessage, participant?: Participant) => {
      const text = cleanText(message.message);
      if (!text) return;

      const role = resolveRole(participant, localIdentity);
      const timestamp = normalizeTimestamp(message.timestamp);
      const participantKey = participant?.identity || "unknown";

      setEntries((current) =>
        upsertEntry(
          current,
          {
            id: `chat:${participantKey}:${message.id}`,
            timestamp,
            updatedAt: normalizeTimestamp(message.editTimestamp ?? message.timestamp),
            role,
            kind: "chat",
            text,
            final: true,
            source: "livekit-chat",
          },
          maxEntries,
        ),
      );
    };

    room.on(RoomEvent.TranscriptionReceived, onTranscription);
    room.on(RoomEvent.ChatMessage, onChatMessage);

    return () => {
      room.off(RoomEvent.TranscriptionReceived, onTranscription);
      room.off(RoomEvent.ChatMessage, onChatMessage);
    };
  }, [maxEntries, room]);

  useEffect(() => {
    if (!renderEvent) return;
    const tool = humanizeTool(renderEvent.tool);
    if (!tool) return;

    setEntries((current) =>
      upsertEntry(
        current,
        {
          id: `tool:${renderEvent.id}`,
          timestamp: normalizeTimestamp(renderEvent.ts),
          updatedAt: normalizeTimestamp(renderEvent.ts),
          role: "system",
          kind: "tool",
          text: tool,
          final: true,
          source: "render-event",
        },
        maxEntries,
      ),
    );
  }, [maxEntries, renderEvent]);

  useEffect(() => {
    if (lastAgentState.current === agentState) return;
    lastAgentState.current = agentState;
    const timestamp = Date.now();
    stateSequence.current += 1;

    setEntries((current) =>
      upsertEntry(
        current,
        {
          id: `agent-state:${timestamp}:${stateSequence.current}`,
          timestamp,
          updatedAt: timestamp,
          role: "system",
          kind: "agent-state",
          text: AGENT_STATE_LABELS[agentState],
          final: true,
          source: "agent",
        },
        maxEntries,
      ),
    );
  }, [agentState, maxEntries]);

  const latestFinalAssistant = useMemo(
    () =>
      [...entries]
        .reverse()
        .find(
          (entry) =>
            entry.role === "assistant" &&
            entry.final &&
            isConversationContent(entry),
        ) ?? null,
    [entries],
  );

  const latestTool = useMemo(
    () => [...entries].reverse().find((entry) => entry.kind === "tool") ?? null,
    [entries],
  );

  const availability = useMemo<ConversationAvailability>(() => {
    if (connectionState === ConnectionState.Disconnected) return "unavailable";
    if (
      connectionState === ConnectionState.Connecting ||
      connectionState === ConnectionState.Reconnecting ||
      connectionState === ConnectionState.SignalReconnecting
    ) {
      return "connecting";
    }
    if (entries.some(isConversationContent)) return "ready";
    return "empty";
  }, [connectionState, entries]);

  const clearHistory = useCallback(() => {
    // Conversation content exists only in this component's React state. It is
    // never written to localStorage, IndexedDB, logs, cookies, or an API.
    setEntries([]);
  }, []);

  return {
    entries,
    agentState,
    connectionState,
    availability,
    latestFinalAssistant,
    latestTool,
    clearHistory,
  };
}
