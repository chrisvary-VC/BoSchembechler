import type { Metadata } from "next";
import Image from "next/image";
import { safeNextPath } from "@/lib/accessSession";
import styles from "./login.module.css";

export const metadata: Metadata = {
  title: "Secure Access — V.A.R.Y.B.R.A.I.N.",
};

interface LoginPageProps {
  searchParams: Promise<{ error?: string; next?: string }>;
}

const errorCopy: Record<string, string> = {
  invalid: "Access denied. Enter the exact passcode; capitalization matters.",
  rate: "Too many attempts. Access is temporarily locked.",
  config: "Secure access is not configured on this deployment.",
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const error = params.error ? errorCopy[params.error] : "";

  return (
    <main className={styles.screen}>
      <div className={styles.brand}>
        <strong>V. A. R. Y. B. R. A. I. N.</strong>
        <span>CHRIS VARY&apos;S JARVIS</span>
      </div>

      <section className={styles.console} aria-labelledby="access-title">
        <div className={styles.reactor} aria-hidden>
          <i /><i /><i />
          <Image src="/brand/varybrain-reactor-logo.png" alt="" width={148} height={140} priority />
        </div>
        <span className={styles.kicker}>// SECURE CONSOLE</span>
        <h1 id="access-title">Welcome back, Chris.</h1>
        <p>Your private command center is locked.</p>

        <form action="/api/auth/login" method="post" className={styles.form}>
          <input type="hidden" name="next" value={next} />
          <label htmlFor="varybrain-password">Access password</label>
          <input
            id="varybrain-password"
            name="password"
            type="password"
            autoComplete="current-password"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            autoFocus
            required
            maxLength={256}
          />
          {error && <p className={styles.error} role="alert">{error}</p>}
          <button type="submit">Unlock VaryBrain</button>
        </form>

        <div className={styles.security}>
          <span><i />Encrypted session</span>
          <span><i />Private data protected</span>
          <span><i />Cloud actions guarded</span>
        </div>
      </section>

      <footer>AUTHORIZED ACCESS ONLY · SESSION EXPIRES AUTOMATICALLY</footer>
    </main>
  );
}
