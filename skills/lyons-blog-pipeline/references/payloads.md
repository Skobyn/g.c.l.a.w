# Lyons Blog Pipeline - Payload Formats

## Step 1: Blog Ideas Request

```bash
curl -s -X POST "https://n8n.digitalbrainworks.com/webhook/watson-blog-request" \
  -H "Content-Type: application/json" \
  -d '{
    "venue_name": "Lansdowne Pub",
    "event_title": "World Cup 2026 Patio Series",
    "event_description": "Detailed description of the event, dates, food, drinks, atmosphere...",
    "campaign_type": "restaurant_blog",
    "location": "Boston, MA",
    "target_keywords": ["keyword1", "keyword2", "keyword3"],
    "reservation_link": ""
  }'
```

**Response:** JSON array of 5 ideas with `idea_number`, `title`, `angle`, `seo_focus`, `venue_name`, `campaign_type`, `reservation_link`

## Step 2: DataForSEO Stats (per idea)

```bash
curl -s -X POST "https://n8n.digitalbrainworks.com/webhook/dataforseo-stats" \
  -H "Content-Type: application/json" \
  -d '{
    "idea_number": 1,
    "title": "Blog Title Here",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "location": "Boston,Massachusetts,United States",
    "location_code": 1018127,
    "venue": "Lansdowne Pub",
    "request_id": "lyons_lansdowne_20260302_idea1"
  }'
```

**Response:** Search volume, keyword difficulty, SERP results, AI search volume

## Step 3: Blog Selection (Full Generation)

```bash
curl -s -X POST "https://n8n.digitalbrainworks.com/webhook/watson-blog-selection" \
  -H "Content-Type: application/json" \
  -d '{
    "selected_idea": {
      "idea_number": 2,
      "title": "Blog Title",
      "angle": "The angle/approach for this blog",
      "seo_focus": "keyword1, keyword2, keyword3"
    },
    "venue_name": "Venue Name",
    "venue_context": {
      "location": "Street address, near landmarks",
      "vibe": "Atmosphere description",
      "differentiator": "What makes this venue unique",
      "positioning": "How to position in market"
    },
    "event_title": "Event Name",
    "event_tagline": "Catchy tagline",
    "content_strategy": {
      "tone": "Excited, welcoming, etc.",
      "approach": "TEASE or REVEAL",
      "reveal": ["Things to include openly"],
      "tease_dont_spoil": ["Things to hint at"],
      "cta": "Call to action"
    },
    "key_features": {
      "decor": "Visual elements",
      "atmosphere": "Experience elements",
      "patio": "Outdoor elements",
      "operations": "Logistics"
    },
    "target_audiences": ["audience1", "audience2"],
    "themed_days": ["Day 1", "Day 2"],
    "campaign_type": "restaurant_blog",
    "location": "City, ST",
    "target_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]
  }'
```

**Response:** Workflow runs async, blog saved to Google Docs + Slack notification

## Scoring Criteria

When selecting the best idea, prioritize:
1. **Unique angle** — Avoid generic "watch party" or "sports bar" content
2. **Keyword volume** — Higher search volume = more traffic potential
3. **Low difficulty** — Easier to rank
4. **AI search volume** — Trending in AI search (emerging signal)
5. **Geographic hooks** — Local landmarks (Lansdowne Street, Fenway) help SEO
