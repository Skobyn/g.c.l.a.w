"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";

export default function Home() {
  const router = useRouter();
  const { user, loading, getIdToken } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }

    const api = createApiClient(getIdToken);
    api
      .getOnboardingStatus()
      .then((status) => {
        if (!status.completed) {
          router.replace("/onboarding");
        } else {
          router.replace("/chat");
        }
      })
      .catch(() => {
        // If onboarding status check fails, fall through to chat
        router.replace("/chat");
      });
  }, [loading, user, router, getIdToken]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-900">
      <p className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
        BOOTING GCLAW<span className="signal-cursor" />
      </p>
    </div>
  );
}
