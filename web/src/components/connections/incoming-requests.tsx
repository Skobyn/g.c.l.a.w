"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionInfo } from "@/types";

interface IncomingRequestsProps {
  onAction?: () => void;
}

export function IncomingRequests({ onAction }: IncomingRequestsProps) {
  const api = useApiClient();
  const [requests, setRequests] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listIncomingRequests()
      .then(setRequests)
      .finally(() => setLoading(false));
  }, [api]);

  const handleAccept = async (id: string) => {
    await api.acceptConnection(id);
    setRequests((prev) => prev.filter((r) => r.id !== id));
    onAction?.();
  };

  const handleReject = async (id: string) => {
    await api.rejectConnection(id);
    setRequests((prev) => prev.filter((r) => r.id !== id));
    onAction?.();
  };

  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (requests.length === 0)
    return <p className="text-slate-400">No incoming requests.</p>;

  return (
    <div className="space-y-3">
      {requests.map((req) => (
        <div
          key={req.id}
          className="border border-slate-700 bg-slate-800 rounded-lg p-4 flex items-center justify-between"
        >
          <div>
            <p className="font-medium text-slate-100">{req.from_user_id}</p>
            <p className="text-sm text-slate-400">
              Requested permission: {req.permission}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleAccept(req.id)}
              className="px-3 py-1 text-sm bg-green-900/50 text-green-400 border border-green-700 rounded hover:bg-green-900 transition-colors"
            >
              Accept
            </button>
            <button
              onClick={() => handleReject(req.id)}
              className="px-3 py-1 text-sm bg-red-900/50 text-red-400 border border-red-700 rounded hover:bg-red-900 transition-colors"
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
