---
name: "GCP DevOps Audit"
description: "Run a comprehensive GCP infrastructure audit against CIS benchmarks, security best practices, cost optimization, and operational excellence. Use when auditing GCP projects, reviewing Cloud Run/Firestore/GCS configurations, checking IAM policies, evaluating CI/CD pipeline security, or preparing for compliance reviews."
---

# GCP DevOps Audit Agent

## What This Skill Does

Systematically audits Google Cloud Platform projects across 11 phases, producing a prioritized report with evidence-based findings and actionable remediation steps.

**Audit phases:** IAM & Identity, Secret Management, Cloud Run, CI/CD Pipelines, Container Security, Firestore, GCS Buckets, Network Security, Observability, Cost Optimization, Disaster Recovery.

## How To Run

### Step 1: Determine Scope

Ask the user for (or detect from the codebase):
- **GCP Project ID(s)** — check `CLAUDE.md`, workflow files, or ask
- **Scope** — full audit or specific phases (e.g., "just security" = phases 1-2, 5, 7-8)
- **Known exceptions** — intentionally public buckets, services without IAM auth, etc.

For this repository, the known project is:
- `apex-internal-apps` — single project hosting compute (Cloud Run + Artifact Registry), Firestore, Firebase Auth, GCS buckets, secrets, service accounts.

### Step 2: Run the Audit

Execute the full audit checklist from the spec document. For each phase:

1. **Run `gcloud` commands** via Bash to gather live infrastructure state
2. **Scan codebase** via Grep/Glob for Dockerfiles, workflows, security rules, hardcoded secrets
3. **Cross-reference** infrastructure state with codebase configuration
4. **Classify findings** as P0 (critical), P1 (high), P2 (best practice), P3 (optimization)

If a `gcloud` command fails due to permissions, mark the check as `SKIP` and note the missing permission.

### Step 3: Produce the Report

Output a structured audit report:

```
# GCP DevOps Audit Report
**Project(s):** [project IDs]
**Date:** [date]
**Auditor:** GCP DevOps Audit Agent

## Executive Summary
- Total checks: X
- PASS: X | FAIL: X | WARN: X | SKIP: X
- Critical (P0): X | High (P1): X | Best Practice (P2): X | Optimization (P3): X

## P0 — Critical Findings
| # | Check | Status | Evidence | Remediation |

## P1 — High Priority Findings
| # | Check | Status | Evidence | Remediation |

## P2 — Best Practice Findings
| # | Check | Status | Evidence | Remediation |

## P3 — Optimization Opportunities
| # | Check | Status | Evidence | Remediation |

## Passing Checks
[grouped by phase]

## Recommendations Roadmap
### Immediate (this week)
### Short-term (this month)
### Medium-term (this quarter)
```

---

## Core Rules

1. **Evidence-based** — every finding cites the specific command output or file content that proves the issue. No speculation.
2. **Non-destructive** — read-only. Never modify infrastructure, IAM policies, or configurations.
3. **Actionable** — every finding includes a remediation `gcloud` command or code change.
4. **Exception-aware** — if `CLAUDE.md` or architecture docs document an intentional deviation, mark as `WARN` not `FAIL`.

---

## Full Audit Checklist

The complete 11-phase audit checklist with all `gcloud` commands, codebase checks, and flag criteria is in:

**[spec.md](./spec.md)**

Read that file before starting the audit. It contains:
- Phase 1: IAM & Identity (P0) — 7 checks
- Phase 2: Secret Management (P0) — 4 infra checks + codebase scan
- Phase 3: Cloud Run Configuration (P1) — 8 flag criteria
- Phase 4: CI/CD Pipeline Security (P1) — 8 flag criteria
- Phase 5: Container Security (P1) — 6 flag criteria
- Phase 6: Firestore & Database (P1) — 7 flag criteria
- Phase 7: GCS Bucket Security (P1) — 7 flag criteria
- Phase 8: Network Security (P1) — 7 flag criteria
- Phase 9: Observability & Monitoring (P2) — 8 flag criteria
- Phase 10: Cost Optimization (P2) — 7 flag criteria
- Phase 11: Disaster Recovery (P2) — 6 flag criteria

---

## Quick Audit (Codebase-Only)

If `gcloud` is not authenticated or you only want to audit the codebase (no live infrastructure):

1. **Dockerfiles** — check for non-root user, base image pinning, `.dockerignore`
2. **CI/CD workflows** — check for WIF, test gates, vuln scanning, pinned actions, health checks
3. **Secrets in code** — grep for `sk-`, `AKIA`, `-----BEGIN`, hardcoded passwords
4. **Firestore rules** — check if `firestore.rules` exists and is restrictive
5. **Cloud Run configs in workflows** — check env vars vs mounted secrets, ingress settings
6. **`.gitignore`** — verify `.env`, credentials, key files are excluded

This produces a partial report covering phases 2 (codebase), 4, and 5.

---

## Adapting for Other Projects

This audit works on any GCP project. When running against a new repo:

1. Check `CLAUDE.md` or `README.md` for project IDs, architecture, known exceptions
2. Scan workflow files for GCP project references
3. Look for `gcloud` config, `app.yaml`, Terraform/Pulumi files
4. Adjust known exceptions based on documented architecture decisions
5. Run the full checklist from the spec document
