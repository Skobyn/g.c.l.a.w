"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to chat as the default view
    router.replace("/chat");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gclaw-muted">Loading GClaw...</p>
    </div>
  );
}
