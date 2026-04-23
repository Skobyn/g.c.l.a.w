# Architecture Decision Records

Each ADR captures one decision and the reasoning behind it. Numbering
is sequential and immutable. Status moves `Proposed` → `Accepted` →
`Superseded` (when a later ADR replaces this one — link both ways).

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-selective-adoption-of-agents-cli.md) | Selective adoption of `google/agents-cli` | Accepted |
| [0002](0002-agent-architect-for-in-process-creation.md) | agent-architect for in-process agent creation | Accepted |
| [0003](0003-bigquery-agent-analytics.md) | BigQuery Agent Analytics adoption | Proposed |
| [0004](0004-prompt-response-logging-gcs.md) | Prompt-response logging to GCS | Proposed |
| [0005](0005-evalset-framework.md) | Evalset framework + `gclaw eval` CLI | Proposed |
| [0006](0006-architect-uses-eval-feedback-loop.md) | architect-uses-eval feedback loop | Proposed |

## Reading order

For someone catching up on where gclaw is going:

1. **0001** — the meta-decision: keep gclaw's multi-agent model,
   adopt agents-cli's *formats* but not its framework.
2. **0002** — the architect agent that lets you create new agents
   conversationally. Implementation lands in the same PR as this
   ADR set.
3. **0003 + 0004** — the observability gap: BigQuery analytics
   table + GCS prompt log. They ship together.
4. **0005** — eval framework. Format-compatible with agents-cli so
   evalsets survive a possible future migration.
5. **0006** — closes the loop: architect generates → architect runs
   evals → user approves with eyes open.
