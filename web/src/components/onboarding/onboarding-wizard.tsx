"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { OnboardingStepResponse } from "@/types";
import { OnboardingChat } from "./onboarding-chat";

const STEP_LABELS: Record<string, string> = {
  introduction: "Welcome",
  q1_identity: "1 · Identity",
  q2_chronotype: "2 · When you work",
  q3_detail_level: "3 · Detail level",
  q4_directness: "4 · Directness",
  q5_autonomy: "5 · Autonomy",
  q6_interrupts: "6 · Interrupts",
  q7_disagreement: "7 · Disagreement",
  q8_current_focus: "8 · Current focus",
  q9_hard_nos: "9 · Hard-nos",
  q10_latent_wish: "10 · Latent wish",
  complete: "Complete",
};

const STEP_ORDER = [
  "introduction",
  "q1_identity",
  "q2_chronotype",
  "q3_detail_level",
  "q4_directness",
  "q5_autonomy",
  "q6_interrupts",
  "q7_disagreement",
  "q8_current_focus",
  "q9_hard_nos",
  "q10_latent_wish",
  "complete",
];

export function OnboardingWizard() {
  const api = useApiClient();
  const [step, setStep] = useState<OnboardingStepResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .startOnboarding()
      .then(setStep)
      .finally(() => setLoading(false));
  }, [api]);

  const handleResponse = async (response: string) => {
    setLoading(true);
    try {
      const next = await api.advanceOnboarding(response);
      setStep(next);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !step) {
    return <p className="text-slate-400">Starting onboarding...</p>;
  }

  if (step?.completed) {
    const preview = step.user_profile_preview ?? step.soul_preview;
    return (
      <div className="text-center space-y-4">
        <h2 className="text-2xl font-bold text-slate-100">You are all set!</h2>
        <p className="text-slate-400">
          Your shared user profile has been compiled. Every agent now has
          this context in their system prompt.
        </p>
        {preview && (
          <pre className="text-left bg-slate-800 border border-slate-700 rounded p-4 text-sm text-slate-200 overflow-auto max-h-64">
            {preview}
          </pre>
        )}
        <a
          href="/chat"
          className="inline-block px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors"
        >
          Start Chatting
        </a>
      </div>
    );
  }

  const currentIdx = step
    ? STEP_ORDER.indexOf(step.step)
    : 0;
  const progress = ((currentIdx + 1) / STEP_ORDER.length) * 100;

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-sm text-slate-400 mb-1">
          <span>{STEP_LABELS[step?.step ?? "introduction"]}</span>
          <span>
            Step {currentIdx + 1} of {STEP_ORDER.length - 1}
          </span>
        </div>
        <div className="w-full bg-slate-700 rounded-full h-2">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Chat-based interview */}
      {step && (
        <OnboardingChat
          agentMessage={step.message}
          onRespond={handleResponse}
          loading={loading}
        />
      )}
    </div>
  );
}
