# Shared rubric: response quality

This rubric is the default criterion for `rubric_based_final_response_quality_v1`
metrics when an evalset case doesn't override it. Keep it short and concrete —
judges score better against checklists than vibes.

## What a "good" response looks like

1. **Answers the user's actual question.** Partial credit for a useful tangent;
   full credit only if the core ask is addressed.
2. **Cites sources when it makes factual claims.** A URL, a domain name, or an
   explicit "I looked this up via <tool>" is enough. Bare assertions about
   dates, numbers, or quotes without a source are a deduction.
3. **Says "I don't know" when the tools didn't produce an answer.** Inventing
   plausible-looking detail to fill silence is the worst failure mode.
4. **Calls the right tool for the job.** If the question was "fetch this URL"
   and the agent ran a web search instead, the response quality suffers even if
   the content looks okay.
5. **Stays in scope.** Research Manager responses shouldn't pivot into code
   suggestions or home automation.

## What a "bad" response looks like

- Fabricated URLs, fabricated quote attributions, fabricated statistics.
- Confident answers to ambiguous questions without asking for clarification.
- Repeats the question back as a "search query" without calling a tool.
- Long summary of what the agent is _about_ to do, then stops without doing it.

## Scoring guidance

- `1.0` — meets every "good" item, zero "bad" items.
- `0.7` — meets the core ask with one minor gap (missing citation, slightly
  off-topic tangent).
- `0.4` — partial answer plus a notable issue (one fabrication, or wrong tool).
- `0.0` — outright wrong, refuses without reason, or fabricates the entire
  response.
