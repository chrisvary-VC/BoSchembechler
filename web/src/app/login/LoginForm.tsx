"use client";

import { FormEvent, useState } from "react";
import styles from "./login.module.css";

interface LoginFormProps {
  next: string;
  error: string;
}

export default function LoginForm({ next, error }: LoginFormProps) {
  const [accessCode, setAccessCode] = useState("");
  const [showPassword, setShowPassword] = useState(true);
  const [feedback, setFeedback] = useState(error);
  const [submitting, setSubmitting] = useState(false);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback("");
    setSubmitting(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessCode, next }),
      });
      const result = await response.json() as { error?: string; next?: string };
      if (!response.ok) {
        setFeedback(result.error || "Unable to unlock VaryBrain.");
        return;
      }
      window.location.assign(result.next || next);
    } catch {
      setFeedback("The secure console could not be reached. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form action="/api/auth/login" method="post" className={styles.form} onSubmit={unlock} aria-busy={submitting}>
      <input type="hidden" name="next" value={next} />
      <label htmlFor="varybrain-password">Access passcode</label>
      <div className={styles.passwordField}>
        <input
          id="varybrain-password"
          name="accessCode"
          type={showPassword ? "text" : "password"}
          value={accessCode}
          onChange={(event) => setAccessCode(event.target.value)}
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoFocus
          required
          maxLength={256}
        />
        <button
          className={styles.revealPassword}
          type="button"
          aria-pressed={showPassword}
          onClick={() => setShowPassword((visible) => !visible)}
        >
          {showPassword ? "Hide" : "Show"}
        </button>
      </div>
      {feedback && <p className={styles.error} role="alert">{feedback}</p>}
      <button className={styles.unlockButton} type="submit" disabled={submitting}>
        {submitting ? "Unlocking…" : "Unlock VaryBrain"}
      </button>
    </form>
  );
}
