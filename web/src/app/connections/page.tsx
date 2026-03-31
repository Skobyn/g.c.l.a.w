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
      <div className="max-w-4xl mx-auto p-6 space-y-8 text-slate-100">
        <h1 className="text-2xl font-bold">Connections</h1>

        <section>
          <h2 className="text-lg font-semibold mb-4 text-slate-200">Connect with a User</h2>
          <ConnectionRequestForm onSent={refresh} />
        </section>

        <section>
          <h2 className="text-lg font-semibold mb-4 text-slate-200">Incoming Requests</h2>
          <IncomingRequests key={`incoming-${refreshKey}`} onAction={refresh} />
        </section>

        <section>
          <h2 className="text-lg font-semibold mb-4 text-slate-200">Active Connections</h2>
          <ConnectionList key={`active-${refreshKey}`} onRevoke={refresh} />
        </section>
      </div>
    </AppShell>
  );
}
