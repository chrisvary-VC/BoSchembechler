"use client";

import { useState } from "react";
import styles from "./login.module.css";

interface LoginFormProps {
  next: string;
  error: string;
}

export default function LoginForm({ next, error }: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <form action="/api/auth/login" method="post" className={styles.form}>
      <input type="hidden" name="next" value={next} />
      <label htmlFor="varybrain-password">Access password</label>
      <div className={styles.passwordField}>
        <input
          id="varybrain-password"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
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
      {error && <p className={styles.error} role="alert">{error}</p>}
      <button className={styles.unlockButton} type="submit">Unlock VaryBrain</button>
    </form>
  );
}
