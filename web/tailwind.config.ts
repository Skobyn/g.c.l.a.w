import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/contexts/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gclaw: {
          primary: "#4285F4",    // Google Blue
          secondary: "#34A853",  // Google Green
          accent: "#FBBC05",     // Google Yellow
          danger: "#EA4335",     // Google Red
          bg: "#0F172A",         // Dark slate
          surface: "#1E293B",    // Lighter slate
          text: "#F1F5F9",       // Light gray
          muted: "#94A3B8",      // Muted gray
        },
      },
    },
  },
  plugins: [],
};

export default config;
