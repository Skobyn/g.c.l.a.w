"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionInfo, ConnectionPermission } from "@/types";
import { PermissionEditor } from "./permission-editor";

interface ConnectionListProps {
  onRevoke?: () => void;
}

export function ConnectionList({ onRevoke }: ConnectionListProps) {
  const api = useApiClient();
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listConnections()
      .then(setConnections)
      .finally(() => setLoading(false));
  }, [api]);

  const handleRevoke = async (id: string) => {
    await api.revokeConnection(id);
    setConnections((prev) => prev.filter((c) => c.id !== id));
    onRevoke?.();
  };

  const handlePermissionChange = async (
    id: string,
    permission: ConnectionPermission,
  ) => {
    const updated = await api.updateConnectionPermission(id, permission);
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? updated : c)),
    );
  };

  if (loading) return <p className="text-slate-400">Loading connections...</p>;
  if (connections.length === 0)
    return <p className="text-slate-400">No active connections.</p>;

  return (
    <div className="space-y-3">
      {connections.map((conn) => (
        <div
          key={conn.id}
          className="border border-slate-700 bg-slate-800 rounded-lg p-4 flex items-center justify-between"
        >
          <div>
            <p className="font-medium text-slate-100">
              {conn.from_user_id === "me"
                ? conn.to_user_id
                : conn.from_user_id}
            </p>
            <p className="text-sm text-slate-400">
              Channel: {conn.shared_channel}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <PermissionEditor
              permission={conn.permission}
              onChange={(p) => handlePermissionChange(conn.id, p)}
            />
            <button
              onClick={() => handleRevoke(conn.id)}
              className="px-3 py-1 text-sm bg-red-900/50 text-red-400 border border-red-700 rounded hover:bg-red-900 transition-colors"
            >
              Revoke
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
