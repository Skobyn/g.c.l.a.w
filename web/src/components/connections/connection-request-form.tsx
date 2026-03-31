"use client";

import { useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionPermission } from "@/types";

interface ConnectionRequestFormProps {
  onSent?: () => void;
}

export function ConnectionRequestForm({ onSent }: ConnectionRequestFormProps) {
  const api = useApiClient();
  const [userId, setUserId] = useState("");
  const [permission, setPermission] = useState<ConnectionPermission>("read");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    try {
      await api.requestConnection({
        to_user_id: userId,
        permission,
      });
      setSuccess(true);
      setUserId("");
      onSent?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to send request");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap gap-3 items-end">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">User ID</label>
        <input
          type="text"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="border border-slate-600 bg-slate-800 text-slate-100 rounded px-3 py-2 placeholder-slate-500"
          placeholder="Enter user ID"
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Permission</label>
        <select
          value={permission}
          onChange={(e) =>
            setPermission(e.target.value as ConnectionPermission)
          }
          className="border border-slate-600 bg-slate-800 text-slate-100 rounded px-3 py-2"
        >
          <option value="read">Read</option>
          <option value="write">Write</option>
          <option value="task">Task</option>
          <option value="full">Full</option>
        </select>
      </div>
      <button
        type="submit"
        className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors"
      >
        Send Request
      </button>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {success && (
        <p className="text-green-400 text-sm">Request sent!</p>
      )}
    </form>
  );
}
