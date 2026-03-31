# Morning Briefing Skill

Deliver a concise, personalised start-of-day summary to help the user hit the ground running.

## Sections to include (in order)

1. **Calendar** — List today's meetings/events with times and any prep notes
2. **Tasks** — Top open tasks ordered by priority (limit to `max_items_per_section`)
3. **Weather** *(optional)* — Brief outlook for the user's location if available
4. **News / Context** *(optional)* — Key items from memory relevant to today's work

## Tone guidelines

- Be brief and scannable — bullet points preferred over prose
- Lead with the most time-sensitive item
- Surface blockers or conflicts proactively (e.g. back-to-back meetings, overdue tasks)
- End with an encouraging one-liner if appropriate

## Memory integration

Before composing the briefing, recall memories scoped to the user for any:
- Ongoing projects or priorities the user has mentioned
- Preferences for briefing format or focus areas
- Context from recent sessions
