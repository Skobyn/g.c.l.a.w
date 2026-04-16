import type { Metadata } from "next";
import { Fraunces, Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { AuthProvider } from "@/contexts/auth-context";
import { ServiceWorkerRegistrar } from "@/components/service-worker-registrar";
import "./globals.css";

// Display — editorial serif, optical sizing on.
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
  display: "swap",
});

// Body — humanist sans, restrained.
const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-instrument-sans",
  display: "swap",
});

// Mono — technical data, IDs, timestamps.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GClaw · Mission Control",
  description:
    "GClaw — personal multi-agent orchestration platform. Phosphor observatory.",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const fontVars = `${fraunces.variable} ${instrumentSans.variable} ${jetbrainsMono.variable}`;
  return (
    <html lang="en" className={fontVars}>
      <body className="min-h-screen antialiased bg-ink-900 text-paper font-body">
        <AuthProvider>
          <ServiceWorkerRegistrar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
