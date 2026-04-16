"use client";

import { useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { ConnectionList } from "@/components/connections/connection-list";
import { ConnectionRequestForm } from "@/components/connections/connection-request-form";
import { IncomingRequests } from "@/components/connections/incoming-requests";

export default function ConnectionsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <AppShell>
      <div className="flex h-full flex-col bg-ink-900 text-paper">
        <header className="hairline-b px-8 pt-6 pb-5">
          <div className="label-caps mb-1.5">§ 11 · LINKAGE</div>
          <h1 className="font-display text-[30px] italic leading-none">
            Connections
          </h1>
          <p className="mt-2 font-body text-[13px] text-paper-60">
            Cross-user channels for agent-to-agent collaboration.
          </p>
        </header>
        <main className="flex-1 overflow-y-auto px-8 py-8">
          <div className="max-w-3xl space-y-10">
            <section>
              <h2 className="font-display text-[18px] italic text-paper mb-3 hairline-b pb-1">
                Connect with a user
              </h2>
              <ConnectionRequestForm onSent={refresh} />
            </section>

            <section>
              <h2 className="font-display text-[18px] italic text-paper mb-3 hairline-b pb-1">
                Incoming requests
              </h2>
              <IncomingRequests key={`incoming-${refreshKey}`} onAction={refresh} />
            </section>

            <section>
              <h2 className="font-display text-[18px] italic text-paper mb-3 hairline-b pb-1">
                Active connections
              </h2>
              <ConnectionList key={`active-${refreshKey}`} onRevoke={refresh} />
            </section>
          </div>
        </main>
      </div>
    </AppShell>
  );
}
