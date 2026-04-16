---
name: devils-advocate
version: 1.0.0
description: Critically evaluate a plan, proposal, or decision before committing. Stress-test ideas by finding logical fallacies, challenging assumptions, surfacing missing perspectives, and proposing alternative framings. Use before finalizing Apex strategy, architecture decisions, product direction, or any high-stakes plan that feels "too clean" or has unanimous support.
allowed-tools:
  - Read
  - Write
  - memory_search
  - memorybank_search
  - web_search
---

# Devil's Advocate

Rigorously stress-test a proposal before committing. The goal is improvement, not destruction.

## Arguments

`$ARGUMENTS` — The proposal, plan, or decision to evaluate. Can be a description, a document path, or a reference to something discussed in context.

---

## Step 1: Understand the Proposal

Summarize the core proposal in 2-3 sentences. Identify:
- The stated problem being solved
- The proposed solution(s)
- The expected outcomes

Confirm understanding before proceeding.

---

## Step 2: Identify Logical Fallacies

Look for:

**Causal fallacies**
- Post hoc (A happened before B, therefore A caused B)
- Correlation mistaken for causation
- Single cause oversimplification

**Assumption fallacies**
- Begging the question (conclusion assumed in premise)
- False dichotomy (only two options presented when more exist)
- Hasty generalization (broad conclusion from limited examples)
- Survivorship bias (only examining successes)

**Evidence fallacies**
- Cherry picking
- Appeal to authority without substantive reasoning
- Anecdotal evidence used as systematic data

**Process fallacies**
- Sunk cost (continuing because of past investment)
- Planning fallacy (underestimating time/resources)
- Optimism bias (assuming best-case scenarios)

---

## Step 3: Challenge Core Assumptions

For each major assumption, ask:
1. Is this actually true? What evidence supports it?
2. Under what conditions does this break?
3. What if the opposite were true? How would the plan change?

---

## Step 4: Identify Missing Perspectives

- Who benefits? Who loses?
- Whose voice is missing from this analysis?
- What would a skeptic say?
- What would someone who tried this before say?

For Apex decisions: check if restaurant operator perspective is represented.
For architecture decisions: check if the person who has to maintain it was considered.

---

## Step 5: Propose Alternative Framings

Offer 2-3 alternative ways to frame the problem or solution:
- **Inversion**: What if we did the opposite?
- **First principles**: Strip assumptions — what is the actual core problem?
- **Analogy**: How do others solve similar problems?
- **Scale test**: Does this work at 10x? At 0.1x?

---

## Step 6: Steelman the Counterarguments

For each criticism raised, also present the strongest defense of the original proposal. Fair analysis requires acknowledging strengths.

---

## Step 7: Synthesize

Conclude with:
1. **Top 3 concerns** that should be addressed before proceeding
2. **Suggested modifications** to strengthen the proposal
3. **Questions to answer** before finalizing
4. **Overall assessment**: Is the direction sound despite the concerns? Should it proceed with modifications, or needs rethinking?

---

## Output Format

```markdown
# Devil's Advocate Analysis

## Proposal Summary
{2-3 sentence summary}

## Logical Fallacies Detected
### {Fallacy Name}
**Where it appears**: {quote or reference}
**Why it's problematic**: {explanation}
**Steelman defense**: {strongest counter to this criticism}

## Challenged Assumptions
### Assumption: "{assumption}"
- Evidence for: {what supports this}
- Evidence against: {what contradicts this}
- Breaking conditions: {when this assumption fails}

## Missing Perspectives
| Stakeholder | Their Likely View | Why It Matters |
|-------------|-------------------|----------------|
| {who} | {what they'd say} | {impact} |

## Alternative Framings
### Frame 1: {name}
{description}

### Frame 2: {name}
{description}

## Synthesis
### Top 3 Concerns
1. {concern}
2. {concern}
3. {concern}

### Suggested Modifications
- {modification}

### Questions to Answer
- {question}

### Overall Assessment
{Honest evaluation}
```

---

## When to Use This

- Before finalizing Apex product or go-to-market strategy
- Before committing to a major architecture decision
- When a plan has unanimous internal support (danger sign)
- Before pitching to an investor or customer
- When stakes are high and reversibility is low
