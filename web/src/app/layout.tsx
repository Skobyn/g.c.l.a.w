import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GClaw",
  description: "Personal AI Agent Platform",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
