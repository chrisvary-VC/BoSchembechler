"use client";

import { useId, type CSSProperties } from "react";

export type VictorsReactorState =
  | "idle"
  | "listening"
  | "thinking"
  | "tool-running"
  | "speaking"
  | "success"
  | "alert"
  | "error"
  | "offline";

export interface VictorsReactorProps {
  /** Current assistant state. The root also exposes this as `data-state`. */
  state: VictorsReactorState;
  /** Live, normalized voice energy from 0 to 1. */
  amplitude?: number;
  /** Live, normalized frequency-band values from 0 to 1 (up to 64 bands). */
  bands?: readonly number[];
  /** Optional tool name shown while the agent is working. */
  activeTool?: string | null;
  /** Accessible and visible override for the state label. */
  statusLabel?: string;
  className?: string;
  style?: CSSProperties;
}

type ReactorStyle = CSSProperties & {
  "--reactor-amplitude": number;
  "--reactor-energy": number;
};

type BandStyle = CSSProperties & {
  "--band-index": number;
  "--band-level": number;
};

const DEFAULT_BAND_COUNT = 32;
const MAX_BAND_COUNT = 64;

const STATE_LABELS: Record<VictorsReactorState, string> = {
  idle: "Standing by",
  listening: "Listening",
  thinking: "Analyzing request",
  "tool-running": "Running tool",
  speaking: "Responding",
  success: "Command complete",
  alert: "Attention required",
  error: "System error",
  offline: "Offline",
};

const clampUnit = (value: number | undefined) => {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value ?? 0));
};

/**
 * An original, Michigan-color-ready reactor aperture for Jarvis.
 *
 * The component contains no university or entertainment artwork. All motion and
 * color are intentionally delegated to CSS through BEM classes, `data-state`,
 * `--reactor-amplitude`, and per-band `--band-level` custom properties.
 */
export default function VictorsReactor({
  state,
  amplitude = 0,
  bands,
  activeTool,
  statusLabel,
  className = "",
  style,
}: VictorsReactorProps) {
  const reactId = useId().replace(/:/g, "");
  const titleId = `${reactId}-title`;
  const descriptionId = `${reactId}-description`;
  const normalizedAmplitude = clampUnit(amplitude);
  const normalizedBands =
    bands && bands.length > 0
      ? Array.from(bands)
          .slice(0, MAX_BAND_COUNT)
          .map(clampUnit)
      : Array.from({ length: DEFAULT_BAND_COUNT }, () => 0);
  const label = statusLabel?.trim() || STATE_LABELS[state];
  const toolLabel = activeTool?.trim() || "";
  const isAudioActive = normalizedAmplitude > 0.025;
  const rootStyle: ReactorStyle = {
    ...style,
    "--reactor-amplitude": normalizedAmplitude,
    "--reactor-energy": Math.max(
      normalizedAmplitude,
      normalizedBands.reduce((total, level) => total + level, 0) /
        normalizedBands.length,
    ),
  };

  return (
    <figure
      className={`victors-reactor victors-reactor--${state}${className ? ` ${className}` : ""}`}
      data-state={state}
      data-audio-active={isAudioActive ? "true" : "false"}
      style={rootStyle}
    >
      <svg
        className="victors-reactor__svg"
        viewBox="0 0 360 360"
        role="img"
        aria-labelledby={`${titleId} ${descriptionId}`}
        focusable="false"
      >
        <title id={titleId}>{`Jarvis reactor: ${label}`}</title>
        <desc id={descriptionId}>
          A circular assistant-status reactor with the Vary Brain tiger logo at
          its center. The logo mouth and outer telemetry respond to live audio.
        </desc>

        <defs>
          <clipPath id={`${reactId}-jaw-clip`}>
            <rect x="166" y="197" width="88" height="52" rx="20" />
          </clipPath>
        </defs>

        <g className="victors-reactor__crosshair" aria-hidden="true">
          <path d="M180 9v48M180 303v48M9 180h48M303 180h48" />
          <circle cx="180" cy="180" r="162" />
        </g>

        <g className="victors-reactor__spectrum" aria-hidden="true">
          {normalizedBands.map((level, index) => {
            const angle = (360 / normalizedBands.length) * index;
            const bandStyle: BandStyle = {
              "--band-index": index,
              "--band-level": level,
            };

            return (
              <line
                className="victors-reactor__band"
                key={index}
                x1="180"
                y1="16"
                x2="180"
                y2={28 + level * 24}
                transform={`rotate(${angle} 180 180)`}
                style={bandStyle}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </g>

        <g className="victors-reactor__telemetry" aria-hidden="true">
          <circle
            className="victors-reactor__orbit victors-reactor__orbit--outer"
            cx="180"
            cy="180"
            r="146"
            pathLength="100"
          />
          <circle
            className="victors-reactor__orbit victors-reactor__orbit--middle"
            cx="180"
            cy="180"
            r="130"
            pathLength="100"
          />
          <circle
            className="victors-reactor__orbit victors-reactor__orbit--inner"
            cx="180"
            cy="180"
            r="113"
            pathLength="100"
          />
          {Array.from({ length: 36 }, (_, index) => (
            <line
              className="victors-reactor__tick"
              key={index}
              x1="180"
              y1={index % 3 === 0 ? 40 : 44}
              x2="180"
              y2="49"
              transform={`rotate(${index * 10} 180 180)`}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <circle className="victors-reactor__node" cx="180" cy="50" r="3" />
          <circle className="victors-reactor__node" cx="310" cy="180" r="3" />
          <circle className="victors-reactor__node" cx="180" cy="310" r="3" />
          <circle className="victors-reactor__node" cx="50" cy="180" r="3" />
        </g>

        <g className="victors-reactor__pulse-field" aria-hidden="true">
          <circle
            className="victors-reactor__pulse victors-reactor__pulse--outer"
            cx="180"
            cy="180"
            r="102"
          />
          <circle
            className="victors-reactor__pulse victors-reactor__pulse--inner"
            cx="180"
            cy="180"
            r="90"
          />
        </g>

        <g className="victors-reactor__aperture" aria-hidden="true">
          {Array.from({ length: 8 }, (_, index) => {
            const bladeStyle = {
              "--blade-index": index,
            } as CSSProperties;

            return (
              <path
                className="victors-reactor__blade"
                key={index}
                d="M180 78C199 79 220 86 235 99L220 137C208 128 196 123 183 123L158 89Z"
                transform={`rotate(${index * 45} 180 180)`}
                style={bladeStyle}
              />
            );
          })}
        </g>

        <g className="victors-reactor__core" aria-hidden="true">
          <circle
            className="victors-reactor__core-shell"
            cx="180"
            cy="180"
            r="87"
          />
          <circle className="victors-reactor__logo-halo" cx="180" cy="180" r="82" />
          <image
            className="victors-reactor__logo"
            href="/brand/varybrain-reactor-logo.png"
            x="100"
            y="104"
            width="160"
            height="152"
            preserveAspectRatio="xMidYMid meet"
          />
          <ellipse className="victors-reactor__mouth-gap" cx="214" cy="220" rx="21" ry="3" />
          <g clipPath={`url(#${reactId}-jaw-clip)`}>
            <image
              className="victors-reactor__logo-jaw"
              href="/brand/varybrain-reactor-logo.png"
              x="100"
              y="104"
              width="160"
              height="152"
              preserveAspectRatio="xMidYMid meet"
            />
          </g>
        </g>
      </svg>

      <figcaption className="victors-reactor__caption">
        <span className="victors-reactor__status">
          <i className="victors-reactor__status-dot" aria-hidden="true" />
          <span className="victors-reactor__status-label">{label}</span>
        </span>
        {toolLabel && (
          <span className="victors-reactor__tool">
            <span className="victors-reactor__tool-prefix" aria-hidden="true">
              //
            </span>{" "}
            {toolLabel}
          </span>
        )}
      </figcaption>
    </figure>
  );
}
