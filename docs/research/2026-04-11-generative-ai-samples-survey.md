# `GoogleCloudPlatform/generative-ai` — survey for GClaw

**Date:** 2026-04-11
**Source:** `github.com/GoogleCloudPlatform/generative-ai` @ `main` (shallow clone)
**Scope:** Samples that touch agents, ADK, Vertex AI Memory Bank, multi-agent orchestration, tool use, evaluation, or open models — the areas where GClaw has active or partial work.

## What's in the repo (one-level)

Top-level directories relevant to GClaw: `agents/`, `gemini/`, `rag-grounding/`, `open-models/`, `embeddings/`, `search/`. The `gemini/` tree alone has 111 Python/notebook files, of which the `agents/`, `function-calling/`, `evaluation/`, and `orchestration/` subtrees are the load-bearing ones for us.

Everything else (`audio/`, `vision/`, `translation/`, `migration/`, `workshops/`) is either application-domain samples not aligned with GClaw's platform focus, or migration guides already covered by our stack choices.

## The samples that matter for GClaw

### A. Memory Bank — directly applicable

GClaw already has a working Memory Bank REST client (`src/gclaw/memory/client.py`) on the `reasoningEngines` surface. These notebooks are the canonical references to validate against and to steal techniques from:

| Sample | Path | What it shows |
|---|---|---|
| Memory Bank on ADK | `agents/agent_engine/memory_bank/get_started_with_memory_bank_on_adk.ipynb` | The *blessed* ADK + Memory Bank wire-up. Cross-check our `AgentRunner` hooks against this. |
| Memory Bank basics | `agents/agent_engine/memory_bank/get_started_with_memory_bank.ipynb` | Canonical request/response shapes for `memories:generate`, `memories:retrieve`, `memories:list`, `memories:delete`. |
| Custom topics | `agents/agent_engine/memory_bank/get_started_with_memory_bank_custom_topics.ipynb` | How to steer extraction with a topic taxonomy — we currently don't pass `topics` at all. |
| Governance | `agents/agent_engine/memory_bank/get_started_with_memory_bank_governance.ipynb` | PII handling, user-initiated deletion, scope audits — a whole compliance surface GClaw doesn't touch yet. |
| Multimodal memory | `agents/agent_engine/memory_bank/tutorial_get_started_with_multimodal_agents_with_memory_bank.ipynb` | Storing memories extracted from images/audio/PDFs, not just text. |
| **Cloud Run + memory** | `agents/cloud_run/agents_with_memory/get_started_with_memory_for_adk_in_cloud_run.ipynb` | **The exact deployment topology GClaw uses.** Read this first. |
| GKE + memory | `agents/gke/agents_with_memory/` | Same pattern on GKE — not our target but good for sanity-checks. |

### B. Always-on memory agent — the reference the user cited

`gemini/agents/always-on-memory-agent/` is the repo behind the pattern the user pointed at in the original prompt. It's a full project (`agent.py`, `dashboard.py`, `docs/`, `requirements.txt`) built on **Gemini 3.1 Flash-Lite + ADK**.

**Core thesis (from its README):**
> Most AI agents have amnesia. This project gives agents a persistent, evolving memory that runs 24/7 as a lightweight background process, continuously processing, consolidating, and connecting information. No vector DB. No embeddings. Just an LLM that reads, thinks, and writes structured memory.

Architecture highlights we should cross-check against GClaw:

- **IngestAgent** reads arbitrary inputs (text/image/audio/video/PDF) and produces structured memories with `summary`, `entities`, `topics`, `importance` — directly maps to what we could store in our Memory model but don't today.
- **Orchestrator routes incoming requests to specialist agents** — matches our AgentTool-based orchestrator pattern.
- **Continuous consolidation** runs in the background — we already have `MemoryConsolidator` via heartbeat, but this reference shows a more aggressive "brain replay" pattern we could borrow from.

### C. Multi-agent orchestration and design patterns

| Sample | Path | What it shows |
|---|---|---|
| Research multi-agents | `gemini/agents/research-multi-agents/ev_agent/` | A multi-agent research workflow — `agent_handler` + `api_handler` split. Reference for how a manager delegates research tasks. |
| Experience Concierge | `gemini/agents/genai-experience-concierge/agent-design-patterns/` | LangGraph implementations of four production patterns: **guardrail classifier**, **semantic router**, **function-calling with streaming**, **task planner with reflection**. The README lists them as reusable design patterns. |
| Intro multi-agents with ADK 2.0 | `gemini/agents/research-multi-agents/intro_research_multi_agents_gemini_2_0.ipynb` | Gemini 2.0-based multi-agent intro; lighter reference. |

### D. Function calling and ReAct

| Sample | Path | What it shows |
|---|---|---|
| DIY ReAct agent | `gemini/function-calling/intro_diy_react_agent.ipynb` | Manual ReAct loop — useful to understand what ADK's `LlmAgent` does for us under the hood. |
| Parallel function calling | `gemini/function-calling/parallel_function_calling.ipynb` | Multiple tool calls per turn — we should verify our managers actually use this when appropriate. |
| Forced function calling | `gemini/function-calling/forced_function_calling.ipynb` | Forcing a specific tool — a missing capability for GClaw's dispatcher. |
| Multimodal function calling | `gemini/function-calling/multimodal_function_calling.ipynb` | Tools that take images/audio as args — relevant once GClaw touches voice/vision. |

### E. Evaluation — GClaw's biggest blind spot

GClaw has no agent evaluation framework. Everything we have is unit tests. These samples show what "real" eval looks like for ADK agents:

| Sample | Path | What it shows |
|---|---|---|
| **Evaluating ADK agent** | `gemini/evaluation/evaluating_adk_agent.ipynb` | **Direct reference.** Uses Vertex AI Gen AI Evaluation Service to score agent trajectories. |
| Tool use eval | `gemini/evaluation/evaluate_gemini_tool_use.ipynb` | Scoring agents on correct tool selection. |
| Final answer eval with custom parsing | `gemini/evaluation/evaltask_approach/evaluate_agent_final_answer_with_custom_parsing.ipynb` | Parsing agent output to extract final answer and score it — applicable to our orchestrator. |
| Groundedness eval | `gemini/evaluation/evaluate_groundedness_with_custom_parsing.ipynb` | Did the agent hallucinate vs. cite sources — relevant once we add retrieval. |
| Rubric eval | `gemini/evaluation/rubric_based_eval.ipynb` | LLM-as-judge rubric scoring — candidate for evaluating GClaw manager performance. |
| Intro Gen AI Eval SDK | `gemini/evaluation/intro_to_gen_ai_evaluation_service_sdk.ipynb` | SDK basics; prerequisite before touching the above. |

### F. Open models — validation of multi-provider routing

GClaw shipped multi-provider routing via `LiteLlm` today. These samples confirm the official patterns:

| Sample | Path | What it shows |
|---|---|---|
| Model Garden SDK basics | `open-models/get_started_with_model_garden_sdk.ipynb` | The SDK path for serving open models on Vertex. |
| OSS MaaS reasoning via OpenAI SDK | `open-models/get_started_with_oss_maas_reasoning_open_ai_sdk.ipynb` | OpenAI-compatible surface for open models — our LiteLlm path aligns. |
| Custom Model Import | `open-models/get_started_with_model_garden_sdk_custom_import.ipynb` | Importing Nemotron-style custom checkpoints. |
| Terraform deployment | `open-models/get_started_with_model_garden_terraform_deployment.ipynb` | IaC for endpoints — follow-up if we want reproducible router targets. |

### G. Tangential but noted

- `gemini/orchestration/intro_langgraph_gemini.ipynb` — LangGraph is not our stack, but the concierge sample uses it. Reference only.
- `rag-grounding/` — RAG is not on GClaw's critical path right now (memory is), but the dir exists if we pivot.

## Apply-to-GClaw table

Priority-ordered by what closes a real gap with minimal effort:

| Sample | GClaw gap it closes | Est. effort |
|---|---|---|
| `agents/cloud_run/agents_with_memory/get_started_with_memory_for_adk_in_cloud_run.ipynb` | Validate our Cloud Run + Memory Bank wire-up against the blessed pattern. Catch anything we got wrong. | 1 hr read + 1-2 hr fix |
| `gemini/agents/always-on-memory-agent/` | Cross-check our AgentRunner recall/capture + consolidation against the reference. Borrow the `summary/entities/topics/importance` memory shape for richer extraction. | 2-3 hr read + 3-5 hr to adopt structured memory extraction |
| `gemini/evaluation/evaluating_adk_agent.ipynb` + `intro_to_gen_ai_evaluation_service_sdk.ipynb` | Build GClaw's first agent evaluation harness — score orchestrator routing + manager tool selection on a held-out set. | 1 day for a minimum eval suite |
| `agents/agent_engine/memory_bank/get_started_with_memory_bank_governance.ipynb` | Add PII scrubbing + user-initiated memory deletion endpoint. Compliance gap. | 4-6 hr |
| `agents/agent_engine/memory_bank/get_started_with_memory_bank_custom_topics.ipynb` | Pass `topics` to `MemoryBankClient.generate_memories` so extraction is steered — we currently pass nothing. | 1-2 hr |
| `gemini/agents/genai-experience-concierge/agent-design-patterns/` (guardrail classifier + task planner) | Add a guardrail layer in front of the orchestrator; add a task-planner workflow to complement `morning_brief` and `commit_message`. | 1-2 days each |
| `gemini/function-calling/parallel_function_calling.ipynb` | Verify GClaw managers emit parallel tool calls when the context allows. May need an AgentFactory tweak. | 2-3 hr |
| `gemini/agents/research-multi-agents/ev_agent/` | Reference for a research manager implementation; currently our `research-mgr` has stub tools. | 1 day |

## Recommendations

1. **Read the Cloud Run + Memory Bank notebook first.** Highest ROI: validates the architecture we already deployed. One hour of reading; possibly saves a day of debugging later.
2. **Build a minimal eval harness next.** GClaw has 370 unit tests but zero agent-level eval. Starting with `evaluating_adk_agent.ipynb` adapted to our orchestrator would close the biggest quality-measurement gap in the project.
3. **Borrow the structured memory shape from `always-on-memory-agent`.** Our current `Memory` model stores `fact` + `topic`. Adopting `summary/entities/topics/importance` gives recall much more to score against and enables the "importance" decay pattern for consolidation.
4. **Add governance endpoints.** `DELETE /memory/user/{id}` + a PII scrub pass on ingest is a 4-6 hour task that we'll need before any real user beyond sbens.
5. **Defer LangGraph samples.** We're on ADK-native; LangGraph samples are reference-only and would create divergence.

## Out of scope for this survey

- `audio/`, `vision/`, `translation/` — domain-specific samples not aligned with GClaw's platform work.
- `rag-grounding/` — RAG isn't on the critical path while memory is the active area.
- `embeddings/` — handled transitively by Memory Bank.
- `workshops/`, `setup-env/`, `migration/` — meta-material.

## How this survey was produced

1. `git clone --depth 1 --filter=blob:none https://github.com/GoogleCloudPlatform/generative-ai.git /tmp/genai-samples`
2. Enumerated top-level dirs, counted Python/notebook files per dir.
3. Drilled into `agents/`, `gemini/agents/`, `gemini/function-calling/`, `gemini/evaluation/`, `open-models/`.
4. Read each sample's README or first 30-50 lines of the entrypoint to confirm relevance.
5. Filtered to samples that use Gemini + Python AND demonstrate agent patterns, Memory Bank, ADK, multi-agent orchestration, tool use, or evaluation.

The clone at `/tmp/genai-samples` is scratch and should not be committed. Re-run step 1 to refresh.
