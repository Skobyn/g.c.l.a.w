"use client";

/**
 * Sidebar — the mission-control left rail.
 *
 * Editorial numbered nav with small-caps labels and a signal-green active
 * rule. No icons. Sections grouped by domain; build version + phosphor
 * live-dot pinned to the footer.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

interface NavItem {
  href: string;
  label: string;
  num: string;
}

interface NavSection {
  heading: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    heading: "CONVERSE",
    items: [
      { href: "/chat", label: "Chat", num: "01" },
    ],
  },
  {
    heading: "WORK",
    items: [
      { href: "/board", label: "Board", num: "02" },
      { href: "/crons", label: "Crons", num: "03" },
    ],
  },
  {
    heading: "KNOW",
    items: [
      { href: "/memory", label: "Memory", num: "04" },
      { href: "/admin/context", label: "Context", num: "05" },
      { href: "/skills", label: "Skills", num: "06" },
    ],
  },
  {
    heading: "ADMIN",
    items: [
      { href: "/admin/agents", label: "Agents", num: "07" },
      { href: "/admin/models", label: "Models", num: "08" },
      { href: "/admin/heartbeat", label: "Heartbeat", num: "09" },
      { href: "/admin/usage", label: "Usage", num: "10" },
      { href: "/admin/live", label: "Live", num: "11" },
      { href: "/connections", label: "Connections", num: "12" },
      { href: "/admin/user", label: "User", num: "13" },
      { href: "/admin/tools", label: "Tools", num: "14" },
    ],
  },
];

const BUILD_VERSION =
  process.env.NEXT_PUBLIC_BUILD_VERSION || "v0.4.0";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  const displayEmail = user?.email ?? "—";
  const avatarLetter = (
    user?.displayName?.[0] ||
    user?.email?.[0] ||
    "?"
  ).toUpperCase();

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-30 flex flex-col
        bg-ink-900 hairline-r
        transition-[width] duration-200
        ${collapsed ? "w-[60px]" : "w-[224px]"}
      `}
    >
      {/* Wordmark */}
      <div className="hairline-b px-4 pt-5 pb-4">
        {!collapsed ? (
          <>
            <div className="flex items-baseline justify-between">
              <span
                className="font-display text-[22px] font-medium tracking-[0.24em] text-paper select-none"
                style={{ fontFeatureSettings: "'ss01'" }}
              >
                GCLAW
              </span>
              <button
                onClick={onToggle}
                aria-label="Collapse sidebar"
                className="text-paper-40 hover:text-signal font-mono text-xs transition-colors"
                title="Collapse"
              >
                [ ← ]
              </button>
            </div>
            <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.2em] text-paper-40 leading-relaxed">
              MISSION CONTROL
              <br />
              <span className="text-paper-60">apex-internal-apps</span>
            </p>
          </>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <span className="font-display text-lg font-medium tracking-wider text-paper select-none">
              GC
            </span>
            <button
              onClick={onToggle}
              aria-label="Expand sidebar"
              className="text-paper-40 hover:text-signal font-mono text-xs"
              title="Expand"
            >
              [→]
            </button>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-4">
        {SECTIONS.map((section) => (
          <div key={section.heading} className="mb-5">
            {!collapsed && (
              <div className="px-3 pb-2 label-caps">
                § {section.heading}
              </div>
            )}
            {collapsed && <div className="h-px bg-paper-08 mx-2 mb-3" />}
            <div className="flex flex-col">
              {section.items.map((item) => {
                const isActive =
                  pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={`
                      group relative flex items-center
                      px-3 py-2 transition-colors duration-100
                      ${collapsed ? "justify-center" : "justify-between"}
                      ${
                        isActive
                          ? "text-signal"
                          : "text-paper-60 hover:text-paper"
                      }
                    `}
                  >
                    {isActive && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-signal" />
                    )}
                    {!collapsed ? (
                      <>
                        <span
                          className={`font-mono text-[11px] tracking-widest uppercase ${
                            isActive ? "text-signal" : ""
                          }`}
                        >
                          {item.label}
                        </span>
                        <span
                          className={`font-mono text-[10px] ${
                            isActive ? "text-signal" : "text-paper-40"
                          }`}
                        >
                          {item.num}
                        </span>
                      </>
                    ) : (
                      <span
                        className={`font-mono text-[10px] ${
                          isActive ? "text-signal" : "text-paper-40"
                        }`}
                      >
                        {item.num}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="hairline-t px-3 py-3 space-y-2">
        {!collapsed ? (
          <>
            <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.18em] text-paper-40">
              <span className="flex items-center gap-2">
                <span className="phosphor-dot" />
                LIVE
              </span>
              <span>{BUILD_VERSION}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 shrink-0 border border-paper-15 flex items-center justify-center font-mono text-[10px] text-paper-60 select-none">
                {avatarLetter}
              </div>
              <p
                className="flex-1 truncate font-mono text-[10px] text-paper-60"
                title={displayEmail}
              >
                {displayEmail}
              </p>
              <button
                onClick={() => signOut()}
                title="Sign out"
                className="font-mono text-[10px] text-paper-40 hover:text-alert transition-colors"
              >
                [X]
              </button>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <span className="phosphor-dot" title="Live" />
            <button
              onClick={() => signOut()}
              title="Sign out"
              className="font-mono text-[10px] text-paper-40 hover:text-alert"
            >
              [X]
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
