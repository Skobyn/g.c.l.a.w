"use client";

import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";

export default function OnboardingPage() {
  return (
    <div className="min-h-screen bg-slate-900 flex items-start justify-center pt-16">
      <div className="w-full max-w-2xl px-6">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-indigo-400">GClaw</h1>
          <p className="text-slate-400 mt-2">Let&apos;s get you set up</p>
        </div>
        <OnboardingWizard />
      </div>
    </div>
  );
}
