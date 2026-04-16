import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/contexts/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-fraunces)", "serif"],
        body: ["var(--font-instrument-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          900: "var(--ink-900)",
          800: "var(--ink-800)",
          700: "var(--ink-700)",
          600: "var(--ink-600)",
        },
        paper: {
          DEFAULT: "var(--paper)",
          "60": "var(--paper-60)",
          "40": "var(--paper-40)",
          "15": "var(--paper-15)",
          "08": "var(--paper-08)",
        },
        signal: {
          DEFAULT: "var(--signal)",
          dim: "var(--signal-dim)",
        },
        alert: {
          DEFAULT: "var(--alert)",
          dim: "var(--alert-dim)",
        },
        gold: {
          DEFAULT: "var(--gold)",
        },
        // Legacy — keep the old gclaw-* names mapped so anything
        // not yet touched in the redesign still reads correctly.
        gclaw: {
          primary: "var(--signal)",
          secondary: "var(--signal-dim)",
          accent: "var(--gold)",
          danger: "var(--alert)",
          bg: "var(--ink-900)",
          surface: "var(--ink-800)",
          text: "var(--paper)",
          muted: "var(--paper-60)",
        },
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "4px",
        lg: "6px",
      },
      letterSpacing: {
        tightish: "-0.01em",
        widecaps: "0.14em",
      },
    },
  },
  plugins: [],
};

export default config;
