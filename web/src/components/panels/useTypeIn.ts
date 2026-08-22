"use client";

import { useEffect, useState } from "react";

/**
 * Reveals text character by character.
 *
 * Driven by requestAnimationFrame off elapsed time, not setInterval: browsers
 * clamp short timers badly and the type-in would crawl. The trade with rAF is
 * that a hidden tab gets no frames at all, so when the page is not visible we
 * skip straight to the full text — nobody is watching it type anyway — and the
 * animation is armed again the next time the tab becomes visible.
 */
export function useTypeIn(text: string, msPerChar = 18) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    setCount(0);
    if (!text) return;

    let frame = 0;
    let start = 0;

    const tick = (now: number) => {
      if (!start) start = now;
      const next = Math.min(text.length, Math.floor((now - start) / msPerChar));
      setCount(next);
      if (next < text.length) frame = requestAnimationFrame(tick);
    };

    const run = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        setCount(text.length);
        return;
      }
      start = 0;
      frame = requestAnimationFrame(tick);
    };

    run();
    document.addEventListener("visibilitychange", run);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", run);
    };
  }, [text, msPerChar]);

  return { shown: text.slice(0, count), done: count >= text.length };
}
