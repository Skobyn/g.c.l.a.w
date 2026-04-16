---
name: lyons-blog-pipeline
description: Generate SEO-optimized blog posts for Lyons Group restaurant venues. Use when Tyler Hall sends venue/event content (Word docs, emails) for blog creation. Full pipeline: extract content → generate 5 blog ideas → score with DataForSEO → select best idea → generate full HTML blog. Venues include Lansdowne Pub, Loretta's Last Call, City Winery, Game On, The Harp, Saltwater Coastal Grill.
---

# Lyons Blog Pipeline

Automated blog generation for Lyons Group venues via n8n webhooks.

## Pipeline Steps

1. **Extract** venue/event details from Tyler's email or Word doc
2. **Generate Ideas** → POST to `watson-blog-request` (returns 5 ideas)
3. **Score Ideas** → POST each to `dataforseo-stats` (parallel OK, 180s timeout)
4. **Select Best** → Pick idea with best volume/difficulty/angle
5. **Generate Blog** → POST to `watson-blog-selection` (240s timeout, ~2m40s)

## Webhooks

| Endpoint | Timeout | Purpose |
|----------|---------|---------|
| `/webhook/watson-blog-request` | 120s | Generate 5 blog ideas |
| `/webhook/dataforseo-stats` | 180s | Keyword metrics per idea |
| `/webhook/watson-blog-selection` | 240s | Full HTML blog generation |

Base URL: `https://n8n.digitalbrainworks.com`

## Location Codes (DataForSEO)

| Venue | Code | Location String |
|-------|------|-----------------|
| Saltwater Coastal Grill | 2840 | Chicago,Illinois,United States |
| Lansdowne Pub | 1018127 | Boston,Massachusetts,United States |
| Loretta's Last Call | 1018127 | Boston,Massachusetts,United States |
| City Winery | 1018127 | Boston,Massachusetts,United States |
| Game On | 1018127 | Boston,Massachusetts,United States |
| The Harp | 1018127 | Boston,Massachusetts,United States |

## Content Strategy

- **Tease, don't spoil** — Build anticipation without revealing everything
- **3 keywords per idea** — Standard for DataForSEO scoring
- **Pick unique angles** — Avoid generic "watch party" content

## Payloads

See [references/payloads.md](references/payloads.md) for full payload formats.

## Contact

Tyler Hall (thall@lyonsgroup.com) — Marketing Manager, Lyons Group
