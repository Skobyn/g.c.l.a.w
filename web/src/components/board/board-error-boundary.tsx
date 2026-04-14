"use client";

import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

export class BoardErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[Board] render crash:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
          <h2 className="text-lg font-semibold text-slate-100">
            Board failed to render
          </h2>
          <pre className="max-w-2xl overflow-auto rounded-md border border-red-900 bg-red-950/40 p-3 text-xs text-red-300">
            {this.state.error.message}
            {"\n\n"}
            {this.state.error.stack?.split("\n").slice(0, 6).join("\n")}
          </pre>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
