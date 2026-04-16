# Content Quality Gate Skill

## Purpose
Score LinkedIn post drafts before they reach Postiz. Catch weak drafts. Don't let garbage through.

## When to Use
Run this against any draft in `~/.openclaw/shared-context/queue/scott/` or `~/.openclaw/shared-context/queue/apex/` before submitting to Postiz.

## Scoring Rubric (100 points total)

### 1. Hook Strength (25 pts)
- **25** — First line is specific, surprising, or creates genuine curiosity. Can't stop reading.
- **15** — Decent opener but predictable. Gets the job done.
- **5** — Generic. "AI is changing everything." "Here's what I learned." Starts with "I". Any opener that could apply to 1000 posts.
- **0** — "In today's fast-paced world..." or similar. Auto-fail the whole post.

### 2. Clarity (20 pts)
- **20** — Point is obvious in 10 seconds of skimming. No reread required.
- **12** — Mostly clear but buries the lead or meanders.
- **5** — Confusing. Reader has to work to find the point.

### 3. Credibility Signal (20 pts)
- **20** — References real data, a specific situation, lived experience, or named example.
- **12** — Has a perspective but it's vague ("many businesses struggle with...").
- **5** — Pure opinion with nothing to back it. Feels made up.

### 4. Audience Fit (15 pts)
- **15** — Written for SMB owners, ops leaders, or restaurant operators specifically. Reader feels like it's for them.
- **10** — Somewhat targeted but could apply to anyone in tech/business broadly.
- **3** — Generic. Written for no one in particular.

### 5. CTA Quality (10 pts)
- **10** — Ends with a question, challenge, or prompt that naturally invites engagement.
- **6** — Has a CTA but it's weak ("thoughts?") or feels tacked on.
- **2** — No CTA or just trails off.

### 6. Human Voice (10 pts)
- **10** — Reads like a real person wrote it. Varied sentence length. Has a point of view. No AI smell.
- **6** — Mostly human but has a few AI patterns (em dashes, "it's worth noting", rule of three, slogany closer).
- **2** — Obvious AI output. Inflated language, excessive parallelism, "delve", "tapestry", hollow closer.

## Pass/Fail Thresholds
- **80-100** — ✅ Pass. Submit to Postiz.
- **65-79** — ⚠️ Conditional pass. Note the specific weakness. Submit but flag for Scott's review.
- **Below 65** — ❌ Fail. Do not submit. Rewrite the weak section(s) and re-score.

## Auto-Fail Conditions (regardless of score)
- Opens with "In today's fast-paced world" or equivalent throat-clearing
- Uses "delve", "tapestry", "multifaceted", "it's worth noting", "game-changing" as a compliment
- Has no source link when it references a stat or external claim
- Is longer than 1500 characters for a single-image post (caption too long)
- Body is just a list with no narrative connective tissue
- Contains an em dash (—). Replace with colon, comma, or split into two sentences.

## Output Format
When scoring a draft, output:

```
## Quality Gate — [Post Title]

Hook Strength:     XX/25 — [one-line note]
Clarity:           XX/20 — [one-line note]  
Credibility:       XX/20 — [one-line note]
Audience Fit:      XX/15 — [one-line note]
CTA Quality:       XX/10 — [one-line note]
Human Voice:       XX/10 — [one-line note]

TOTAL: XX/100 — ✅ PASS / ⚠️ CONDITIONAL / ❌ FAIL

[If fail or conditional: specific rewrite recommendation in 2-3 sentences]
```

## Notes
- This rubric grades craft, not viral potential. A post can score 90/100 and still not perform if the topic doesn't resonate. That's normal.
- Once LinkedIn Community Management API is active, backfill rubric scores against actual impressions and recalibrate weights accordingly.
- The goal right now: filter out garbage. Not predict hits.
