import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "V.A.R.Y.B.R.A.I.N. — Chris Vary's Jarvis",
  description: "Chris Vary's voice-reactive Jarvis command center.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="scanlines" aria-hidden />
        {children}
      </body>
    </html>
  );
}
