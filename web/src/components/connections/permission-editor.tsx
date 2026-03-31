"use client";

import { ConnectionPermission } from "@/types";

interface PermissionEditorProps {
  permission: ConnectionPermission;
  onChange: (permission: ConnectionPermission) => void;
}

export function PermissionEditor({
  permission,
  onChange,
}: PermissionEditorProps) {
  return (
    <select
      value={permission}
      onChange={(e) => onChange(e.target.value as ConnectionPermission)}
      className="border border-slate-600 bg-slate-800 text-slate-200 rounded px-2 py-1 text-sm"
    >
      <option value="read">Read</option>
      <option value="write">Write</option>
      <option value="task">Task</option>
      <option value="full">Full</option>
    </select>
  );
}
