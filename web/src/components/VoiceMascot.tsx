"use client";

import type { CSSProperties } from "react";
import styles from "./VoiceMascot.module.css";

export type VoiceMascotState =
  | "idle"
  | "listening"
  | "thinking"
  | "tool-running"
  | "speaking"
  | "success"
  | "alert"
  | "error"
  | "offline";

export interface VoiceMascotProps {
  state: VoiceMascotState;
  /** Normalized assistant-output energy from 0 to 1. */
  amplitude?: number;
  /** Normalized assistant-output frequency bands from 0 to 1. */
  bands?: readonly number[];
  label?: string;
  className?: string;
  style?: CSSProperties;
}

type MascotStyle = CSSProperties & {
  "--mascot-mouth": number;
  "--mascot-energy": number;
  "--mascot-eye-left": number;
  "--mascot-eye-right": number;
  "--mascot-gaze": number;
};

type MeterStyle = CSSProperties & {
  "--meter-index": number;
  "--meter-level": number;
};

const LABELS: Record<VoiceMascotState, string> = {
  idle: "Standing by",
  listening: "Listening",
  thinking: "Thinking",
  "tool-running": "Running tool",
  speaking: "Speaking",
  success: "Command complete",
  alert: "Attention required",
  error: "Voice fault",
  offline: "Voice offline",
};

const METER_COUNT = 16;

function clamp(value: number | undefined) {
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value ?? 0)) : 0;
}

function average(values: readonly number[], start: number, end: number) {
  const slice = values.slice(start, end);
  return slice.length ? slice.reduce((total, value) => total + value, 0) / slice.length : 0;
}

/**
 * Drop-in voice mascot driven entirely by the real assistant audio values passed
 * by its parent. It does not open a microphone or synthesize idle mouth motion.
 */
export default function VoiceMascot({
  state,
  amplitude = 0,
  bands = [],
  label,
  className = "",
  style,
}: VoiceMascotProps) {
  const normalizedBands = Array.from(bands, clamp);
  const rawAmplitude = clamp(amplitude);
  const bandEnergy = average(normalizedBands, 0, normalizedBands.length);
  const isSpeaking = state === "speaking";

  // Lift quiet speech above the visual noise floor without manufacturing motion
  // while the assistant is not in its speaking state.
  const speechEnergy = isSpeaking
    ? clamp(Math.pow(Math.max(rawAmplitude, bandEnergy * 1.35), 0.72) * 1.18)
    : 0;
  const lowerBands = average(normalizedBands, 0, Math.ceil(normalizedBands.length / 2));
  const upperBands = average(normalizedBands, Math.floor(normalizedBands.length / 2), normalizedBands.length);
  const stateEnergy = state === "thinking" || state === "tool-running"
    ? 0.38
    : state === "listening" ? 0.2 : state === "success" ? 0.3 : 0;
  const visualEnergy = Math.max(speechEnergy, stateEnergy);
  const leftEye = clamp(visualEnergy * 0.72 + lowerBands * (isSpeaking ? 0.5 : 0));
  const rightEye = clamp(visualEnergy * 0.72 + upperBands * (isSpeaking ? 0.5 : 0));
  const spectralGaze = clamp(0.5 + (upperBands - lowerBands) * 1.8);
  const gaze = state === "thinking" || state === "tool-running"
    ? 0.76
    : state === "listening" ? 0.5 : spectralGaze;
  const rootStyle: MascotStyle = {
    ...style,
    "--mascot-mouth": speechEnergy,
    "--mascot-energy": visualEnergy,
    "--mascot-eye-left": leftEye,
    "--mascot-eye-right": rightEye,
    "--mascot-gaze": gaze,
  };
  const status = label?.trim() || LABELS[state];

  return (
    <figure
      className={`${styles.mascot}${className ? ` ${className}` : ""}`}
      data-state={state}
      data-speaking={isSpeaking ? "true" : "false"}
      data-audio-active={speechEnergy > 0.025 ? "true" : "false"}
      style={rootStyle}
      aria-label={`Jarvis mascot: ${status}`}
    >
      <div className={styles.stage} aria-hidden="true">
        <div className={styles.crosshair} />
        <div className={`${styles.orbit} ${styles.orbitOuter}`} />
        <div className={`${styles.orbit} ${styles.orbitInner}`} />

        <div className={styles.portrait}>
          <img
            className={styles.face}
            src="/brand/varybrain-reactor-logo.png"
            alt=""
            draggable={false}
          />

          <span className={`${styles.eye} ${styles.eyeLeft}`}><i /></span>
          <span className={`${styles.eye} ${styles.eyeRight}`}><i /></span>
          <span className={styles.mouthGap} />

          <span className={styles.jawMask}>
            <img
              className={styles.jaw}
              src="/brand/varybrain-reactor-logo.png"
              alt=""
              draggable={false}
            />
          </span>
        </div>

        <div className={styles.meters}>
          {Array.from({ length: METER_COUNT }, (_, index) => {
            const sourceIndex = normalizedBands.length
              ? Math.round((index / Math.max(METER_COUNT - 1, 1)) * (normalizedBands.length - 1))
              : 0;
            const level = isSpeaking ? normalizedBands[sourceIndex] ?? 0 : 0;
            const meterStyle: MeterStyle = {
              "--meter-index": index,
              "--meter-level": clamp(level),
            };
            return <i key={index} style={meterStyle} />;
          })}
        </div>
      </div>

      <figcaption className={styles.caption}>
        <i aria-hidden="true" />
        <span>{status}</span>
      </figcaption>
    </figure>
  );
}
