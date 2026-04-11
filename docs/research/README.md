# GClaw Research Notes

Research notes and surveys that inform GClaw's implementation. These are reference documents, not plans — see `docs/superpowers/plans/` for implementation plans.

| Date | Doc | Topic |
|---|---|---|
| 2026-04-11 | [generative-ai samples survey](2026-04-11-generative-ai-samples-survey.md) | Survey of `GoogleCloudPlatform/generative-ai` samples relevant to GClaw (memory, multi-agent, evaluation, open models) |
| 2026-04-11 | [Cloud Run + Memory Bank validation](2026-04-11-cloud-run-memory-validation.md) | Diff of GClaw's memory wire-up against the blessed ADK Cloud Run + Memory Bank reference notebook. No blocking bugs; one tech-debt follow-up (VertexAiMemoryBankService migration) |
| 2026-04-11 | [Multi-agent ADK orchestration validation](2026-04-11-multi-agent-adk-validation.md) | Diff of GClaw's orchestrator + composed workflows against the "Build multi-agentic systems using Google ADK" Google Cloud Blog post (the PDF referenced in the original prompt). 100% aligned — every pattern the PDF teaches is live in GClaw. |
