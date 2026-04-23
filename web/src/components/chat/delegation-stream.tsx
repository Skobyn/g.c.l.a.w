"use client";

/**
 * DelegationStream — ephemeral binary-digit animation that fires when
 * the orchestrator delegates a task to the board. Visually: a stream
 * of `0`s and `1`s emitted from a source element (the orchestrator
 * turn bubble) that flow down/along to a target element (the
 * BoardSummaryCard). The animation is purely decorative; it does not
 * block rendering or gate state.
 *
 * Aesthetic: mission-control / phosphor observatory — glyph-thin,
 * signal-green (or gold for HIGH), trailing-opacity fade. No frames
 * or GIFs; pure CSS transforms + React-managed particle list.
 *
 * Usage from ChatView:
 *
 *   const stream = useDelegationStream();
 *   // when a task.delegated event fires for this turn:
 *   stream.fire({ sourceEl, targetEl, priority: "high" });
 *   // render at layout root:
 *   <DelegationStreamOverlay state={stream.state} />
 *
 * The overlay lives at the document body level (fixed positioning) so
 * particles can traverse between components that otherwise sit in
 * different stacking contexts.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

// ── Particle model ─────────────────────────────────────────────────

interface Particle {
  id: string;
  glyph: "0" | "1";
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  /** Stagger in ms relative to the burst's t0 so the stream feels
   *  emitted, not all-at-once. */
  delay: number;
  /** ms the particle animates end-to-end. */
  duration: number;
  /** Extra class for HIGH-priority colouring. */
  color: "signal" | "gold";
}

interface FireInput {
  sourceEl: HTMLElement | null;
  targetEl: HTMLElement | null;
  priority: "high" | "medium" | "low";
}

interface StreamState {
  particles: Particle[];
}

interface StreamApi {
  state: StreamState;
  fire: (input: FireInput) => void;
}

const PARTICLE_TTL_MS = 1200;
const PARTICLE_DURATION_MS = 900;
const BURST_SIZE = 14; // ~14 glyphs over ~600ms feels like a stream

// ── Hook ───────────────────────────────────────────────────────────

export function useDelegationStream(): StreamApi {
  const [particles, setParticles] = useState<Particle[]>([]);
  const nextId = useRef(0);

  const fire = useCallback((input: FireInput) => {
    const { sourceEl, targetEl, priority } = input;
    if (!sourceEl || !targetEl) return;
    const s = sourceEl.getBoundingClientRect();
    const t = targetEl.getBoundingClientRect();

    // Emit from the bottom-center of the source (turn bubble), land
    // at the top-center of the target (board card summary row).
    const sx = s.left + s.width / 2;
    const sy = s.bottom - 2;
    const tx = t.left + t.width / 2;
    const ty = t.top + 8;

    const burst: Particle[] = [];
    for (let i = 0; i < BURST_SIZE; i++) {
      burst.push({
        id: `p-${nextId.current++}`,
        glyph: Math.random() < 0.5 ? "0" : "1",
        // Jitter source x a few px for stream feel.
        startX: sx + (Math.random() - 0.5) * 20,
        startY: sy,
        // Small horizontal jitter at target too so it doesn't all
        // land on a single pixel.
        endX: tx + (Math.random() - 0.5) * 40,
        endY: ty,
        delay: i * 30,
        duration: PARTICLE_DURATION_MS,
        color: priority === "high" ? "gold" : "signal",
      });
    }
    setParticles((prev) => [...prev, ...burst]);

    // Sweep expired particles a bit after their max lifetime.
    const maxLife =
      Math.max(...burst.map((b) => b.delay)) +
      PARTICLE_DURATION_MS +
      100;
    setTimeout(() => {
      setParticles((prev) =>
        prev.filter((p) => !burst.some((b) => b.id === p.id)),
      );
    }, maxLife);
  }, []);

  return { state: { particles }, fire };
}

// ── Overlay renderer ───────────────────────────────────────────────

export function DelegationStreamOverlay({ state }: { state: StreamState }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-50 overflow-hidden"
    >
      {state.particles.map((p) => (
        <ParticleGlyph key={p.id} p={p} />
      ))}
    </div>
  );
}

function ParticleGlyph({ p }: { p: Particle }) {
  const [style, setStyle] = useState<CSSProperties>({
    left: p.startX,
    top: p.startY,
    opacity: 0,
    transform: "translate(-50%, -50%) scale(0.8)",
  });

  useEffect(() => {
    // Frame 1 — "birth": fade in at start position.
    const birth = setTimeout(() => {
      setStyle({
        left: p.startX,
        top: p.startY,
        opacity: 1,
        transform: "translate(-50%, -50%) scale(1)",
        transition: "opacity 120ms linear",
      });
    }, p.delay);
    // Frame 2 — "travel": translate to target, fade out near the end.
    const travel = setTimeout(() => {
      setStyle({
        left: p.endX,
        top: p.endY,
        opacity: 0,
        transform: "translate(-50%, -50%) scale(0.6)",
        transition: `
          left ${p.duration}ms cubic-bezier(0.4, 0, 0.2, 1),
          top ${p.duration}ms cubic-bezier(0.4, 0, 0.2, 1),
          opacity ${p.duration}ms ease-in,
          transform ${p.duration}ms ease-in
        `.trim(),
      });
    }, p.delay + 120);
    return () => {
      clearTimeout(birth);
      clearTimeout(travel);
    };
  }, [p]);

  const colorClass =
    p.color === "gold" ? "text-gold" : "text-signal";

  return (
    <span
      className={`
        absolute font-mono text-[11px] leading-none tabular-nums
        ${colorClass} drop-shadow-[0_0_6px_currentColor]
      `}
      style={style}
    >
      {p.glyph}
    </span>
  );
}
