/**
 * Unit tests for the /admin/live cockpit widgets.
 *
 * Components are driven by the AgentRunDoc shape the Phase 4 Firestore
 * repo writes. We render them with static props so no Firebase stub is
 * needed — useRunDoc is the only module that touches Firestore, and it
 * isn't exercised here.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { NowPlayingCard } from "@/components/admin/live/NowPlayingCard";
import {
  ContextGauge,
  __test as ctxTest,
} from "@/components/admin/live/ContextGauge";
import { TokenMeter } from "@/components/admin/live/TokenMeter";
import {
  CostTicker,
  __test as costTest,
} from "@/components/admin/live/CostTicker";
import type { AgentRunDoc } from "@/hooks/useRunDoc";

const activeRun: AgentRunDoc = {
  run_id: "sess-1",
  active_agent: "orchestrator",
  model_id: "gemini-2.5-flash",
  provider: "vertex",
  status: "OK",
  tokens: { in: 42310, out: 1204, total: 43514, cache_read: 38000 },
  context_window: { used: 42310, max: 1048576, pct: 42310 / 1048576 },
  cost_usd_session: 0.0187,
  cost_usd_turn: 0.0024,
  tool_in_flight: { name: "gws.calendar.list" },
  updated_at: "2026-04-18T10:55:12Z",
};

describe("NowPlayingCard", () => {
  it("renders empty state when no run is active", () => {
    render(<NowPlayingCard run={null} />);
    expect(screen.getByText(/no active run/i)).toBeInTheDocument();
  });

  it("renders agent, model, status, and tool chip when live", () => {
    render(<NowPlayingCard run={activeRun} />);
    expect(screen.getByText("orchestrator")).toBeInTheDocument();
    expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText(/gws\.calendar\.list/)).toBeInTheDocument();
  });
});

describe("ContextGauge", () => {
  it("shows utilisation percentage and used/max counts", () => {
    render(<ContextGauge run={activeRun} />);
    // 42310 / 1048576 ≈ 4.0%
    expect(screen.getByText(/4\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/42,310/)).toBeInTheDocument();
    expect(screen.getByText(/1,048,576/)).toBeInTheDocument();
  });

  it("shows em-dash when max is unknown", () => {
    render(
      <ContextGauge
        run={{ tokens: { in: 100 }, context_window: { used: 100, max: 0 } }}
      />,
    );
    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
  });

  it("bandColor follows 60/85 thresholds", () => {
    expect(ctxTest.bandColor(0.1)).toBe("#22c55e"); // green
    expect(ctxTest.bandColor(0.5)).toBe("#22c55e");
    expect(ctxTest.bandColor(0.6)).toBe("#f59e0b"); // amber
    expect(ctxTest.bandColor(0.84)).toBe("#f59e0b");
    expect(ctxTest.bandColor(0.85)).toBe("#ef4444"); // red
    expect(ctxTest.bandColor(0.99)).toBe("#ef4444");
  });
});

describe("TokenMeter", () => {
  it("renders in/out/total and cache read when present", () => {
    render(<TokenMeter run={activeRun} />);
    expect(screen.getByText(/42,310/)).toBeInTheDocument();
    expect(screen.getByText(/1,204/)).toBeInTheDocument();
    expect(screen.getByText(/43,514/)).toBeInTheDocument();
    expect(screen.getByText(/cache read/i)).toBeInTheDocument();
    expect(screen.getByText(/38,000/)).toBeInTheDocument();
  });

  it("hides cache-read row when zero or missing", () => {
    render(
      <TokenMeter
        run={{ tokens: { in: 100, out: 5, total: 105, cache_read: 0 } }}
      />,
    );
    expect(screen.queryByText(/cache read/i)).not.toBeInTheDocument();
  });
});

describe("CostTicker", () => {
  it("formats session total and turn delta", () => {
    render(<CostTicker run={activeRun} />);
    expect(screen.getByText("$0.0187")).toBeInTheDocument();
    expect(screen.getByText(/\+\$0\.0024 this turn/)).toBeInTheDocument();
  });

  it("shows em-dash when cost is unknown", () => {
    render(<CostTicker run={{}} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formatUsd picks precision by magnitude", () => {
    expect(costTest.formatUsd(0.0123)).toBe("$0.0123");
    expect(costTest.formatUsd(12.5)).toBe("$12.50");
    expect(costTest.formatUsd(1500)).toBe("$1500");
  });
});
