"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";
import { formatTickerStamp } from "@/lib/format";

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/chat");
    }
  }, [user, loading, router]);

  return (
    <div className="relative flex min-h-screen flex-col bg-ink-900 text-paper">
      {/* Ticker */}
      <div className="hairline-b px-6 h-7 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-paper-60">
        <span>{formatTickerStamp()}</span>
        <span className="flex items-center gap-2">
          <span className="phosphor-dot" />
          <span className="text-signal">CHANNEL OPEN</span>
        </span>
      </div>

      <div className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-md">
          <div className="label-caps mb-3">§ MISSION CONTROL · AUTH</div>
          <h1 className="font-display text-[52px] leading-[0.95] tracking-tight text-paper">
            GCLAW
          </h1>
          <p className="mt-3 font-display italic text-[20px] text-paper-60">
            An observatory for agents.
          </p>
          <div className="hairline-t mt-6 pt-6">
            <p className="font-body text-[13px] text-paper-60 leading-relaxed">
              Sign in with your Google account to open the channel. Session
              state rides on Firebase; transcripts persist on the server.
            </p>
            <button
              onClick={signInWithGoogle}
              disabled={loading}
              className="mt-6 w-full flex items-center justify-center gap-3 border border-paper-15 hover:border-signal hover:text-signal px-5 py-3 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors disabled:opacity-50"
            >
              <svg className="h-4 w-4 opacity-80" viewBox="0 0 24 24">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  fill="currentColor"
                  opacity="0.9"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="currentColor"
                  opacity="0.7"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  fill="currentColor"
                  opacity="0.5"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="currentColor"
                  opacity="0.3"
                />
              </svg>
              <span>Sign in with Google</span>
            </button>
            <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40">
              APEX-INTERNAL-APPS · PERSONAL USE ONLY
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
