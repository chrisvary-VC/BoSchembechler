"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  useConversationTelemetry,
  type ConversationTelemetryEntry,
} from "@/lib/useConversationTelemetry";
import styles from "./ConversationModule.module.css";

export interface ConversationModuleProps {
  title?: string;
  maxEntries?: number;
  /** Controlled privacy state. Omit to let the module manage its own toggle. */
  privacyMode?: boolean;
  defaultPrivacyMode?: boolean;
  onPrivacyModeChange?: (enabled: boolean) => void;
  className?: string;
}

const AVAILABILITY_COPY = {
  connecting: {
    title: "Connecting to voice telemetry",
    detail: "Transcript will appear when the LiveKit session is ready.",
  },
  empty: {
    title: "No conversation yet",
    detail: "Final speech and chat messages will appear here as they arrive.",
  },
  unavailable: {
    title: "Transcript unavailable",
    detail: "Reconnect the voice session to receive conversation telemetry.",
  },
  ready: {
    title: "Conversation ready",
    detail: "Live voice telemetry is available.",
  },
} as const;

const AGENT_STATE_COPY = {
  disconnected: "Offline",
  connecting: "Connecting",
  "pre-connect-buffering": "Preparing mic",
  failed: "Unavailable",
  initializing: "Initializing",
  idle: "Standing by",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
} as const;

function actorLabel(entry: ConversationTelemetryEntry) {
  if (entry.kind === "tool") return "Tool result";
  if (entry.kind === "agent-state") return "Agent state";
  if (entry.role === "user") return "You";
  if (entry.role === "assistant") return "Jarvis";
  return "Participant";
}

function displayText(entry: ConversationTelemetryEntry, privacyMode: boolean) {
  if (
    privacyMode &&
    (entry.kind === "transcript" || entry.kind === "chat")
  ) {
    return "Conversation content hidden.";
  }
  return entry.text;
}

function formatTimestamp(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function ConversationModule({
  title = "Conversation",
  maxEntries = 48,
  privacyMode,
  defaultPrivacyMode = false,
  onPrivacyModeChange,
  className = "",
}: ConversationModuleProps) {
  const telemetry = useConversationTelemetry({ maxEntries });
  const titleId = useId();
  const [internalPrivacyMode, setInternalPrivacyMode] = useState(defaultPrivacyMode);
  const listRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const masked = privacyMode ?? internalPrivacyMode;
  const conversationCount = telemetry.entries.filter(
    (entry) => entry.kind === "transcript" || entry.kind === "chat",
  ).length;
  const latestEntryId = telemetry.entries.at(-1)?.id;
  const emptyCopy = AVAILABILITY_COPY[telemetry.availability];

  const finalResponseAnnouncement = useMemo(() => {
    if (!telemetry.latestFinalAssistant) return "";
    return masked
      ? "Jarvis response received. Conversation content is hidden."
      : telemetry.latestFinalAssistant.text;
  }, [masked, telemetry.latestFinalAssistant]);

  useEffect(() => {
    if (!followLatest.current || !listRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      const list = listRef.current;
      if (list) list.scrollTop = list.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [latestEntryId]);

  const togglePrivacy = () => {
    const next = !masked;
    if (privacyMode === undefined) setInternalPrivacyMode(next);
    onPrivacyModeChange?.(next);
  };

  return (
    <section
      className={`conversation-module ${styles.module}${className ? ` ${className}` : ""}`}
      data-agent-state={telemetry.agentState}
      data-privacy={masked ? "masked" : "visible"}
      aria-labelledby={titleId}
    >
      <header className={`conversation-module__header ${styles.header}`}>
        <div className={styles.headingGroup}>
          <p className={styles.eyebrow}>// Live voice telemetry</p>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
        </div>
        <div className={styles.headerStatus}>
          <span
            className={`conversation-module__agent-state ${styles.agentState}`}
            title={`Agent state: ${AGENT_STATE_COPY[telemetry.agentState]}`}
          >
            <i aria-hidden="true" />
            {AGENT_STATE_COPY[telemetry.agentState]}
          </span>
          <span className={styles.count} aria-label={`${conversationCount} conversation entries`}>
            {String(conversationCount).padStart(2, "0")}
          </span>
        </div>
      </header>

      <div className={`conversation-module__toolbar ${styles.toolbar}`}>
        <span className={styles.sessionNote}>Session memory only</span>
        {telemetry.latestTool && (
          <span className={styles.latestTool}>
            Latest tool: <strong>{telemetry.latestTool.text}</strong>
          </span>
        )}
        <div className={styles.actions}>
          <button
            className={styles.actionButton}
            type="button"
            aria-pressed={masked}
            onClick={togglePrivacy}
          >
            {masked ? "Show content" : "Mask content"}
          </button>
          <button
            className={styles.actionButton}
            type="button"
            onClick={telemetry.clearHistory}
            disabled={telemetry.entries.length === 0}
          >
            Clear
          </button>
        </div>
      </div>

      <div
        className={`conversation-module__history ${styles.history}`}
        ref={listRef}
        onScroll={(event) => {
          const target = event.currentTarget;
          followLatest.current =
            target.scrollHeight - target.scrollTop - target.clientHeight < 48;
        }}
        aria-label="Conversation and agent activity history"
        aria-live="off"
      >
        {telemetry.availability !== "ready" && (
          <div
            className={`${styles.empty}${telemetry.entries.length > 0 ? ` ${styles.emptyWithHistory}` : ""}`}
            data-availability={telemetry.availability}
          >
            <i aria-hidden="true" />
            <div>
              <strong>{emptyCopy.title}</strong>
              <p>{emptyCopy.detail}</p>
            </div>
          </div>
        )}
        {telemetry.entries.length > 0 && (
          <ol className={styles.timeline}>
            {telemetry.entries.map((entry) => (
              <li
                className={`${styles.entry} ${styles[`role-${entry.role}`]} ${styles[`kind-${entry.kind}`]}`}
                key={entry.id}
                data-final={entry.final ? "true" : "false"}
              >
                <div className={styles.entryMeta}>
                  <span className={styles.actor}>{actorLabel(entry)}</span>
                  {!entry.final && <span className={styles.interim}>Live</span>}
                  <time dateTime={new Date(entry.timestamp).toISOString()}>
                    {formatTimestamp(entry.timestamp)}
                  </time>
                </div>
                <p className={styles.message}>{displayText(entry, masked)}</p>
              </li>
            ))}
          </ol>
        )}
      </div>

      <p
        className={styles.announcer}
        aria-live="polite"
        aria-atomic="true"
      >
        {finalResponseAnnouncement}
      </p>
    </section>
  );
}
