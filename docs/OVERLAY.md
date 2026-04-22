# Private overlay pattern

GClaw is meant to be forked, customized, and run by individuals. Most
of the framework is generic, but a handful of files are deeply
personal — they encode your voice, your relationships, your projects,
your scheduled jobs. You don't want those in a public repo.

The overlay pattern keeps the public framework and your private
configuration in separate repos:

- **Public repo** (this one) — framework code, generic agent
  definitions, template skills, deploy plumbing.
- **Private overlay repo** (your own) — your real `agents/`,
  `soul/`, `user.md`, personalized `crons/`, brand-specific skills.

At deploy time the overlay's contents are copied or mounted into
`GCLAW_CONFIG_DIR` (defaults to `/app` in the Dockerfile), and the
runtime reads from there.

## Files that belong in the overlay

| Path                              | Why                                       |
|-----------------------------------|-------------------------------------------|
| `user.md`                         | Your stable identity / preferences.       |
| `soul/base.md`                    | Your voice, the inheritance root.         |
| `soul/content.md`                 | Brand voice for social posts.             |
| `soul/<other>.md`                 | Domain-specific personality overlays.     |
| `agents/content-mgr.md`           | Brand channels, banned words, persona.    |
| `agents/<other>-mgr.md`           | Any manager you've personalized.          |
| `crons/heartbeat.json`            | Per-user heartbeat cadence.               |
| `crons/<other>.json`              | Schedule-specific jobs.                   |
| `skills/humanizer/...`            | Your banned-words list.                   |
| `skills/<your-brand-pipeline>/`   | Brand-specific or client-specific skills. |
| `.env`                            | Your secrets (never anywhere public).     |

The public repo ships **template versions** of these files (or none
at all, where the template would be useless). They boot the system
but feel generic — that's the point. Override in your overlay.

## Two ways to apply the overlay

### Option 1: Build-time copy (simplest)

Put your overlay repo next to gclaw and run a small wrapper that
copies overlay files over the public defaults before `docker build`:

```bash
# Layout:
#   ~/dev/gclaw/            <- public clone
#   ~/dev/gclaw-overlay/    <- your private overlay

cd ~/dev/gclaw
rsync -av ~/dev/gclaw-overlay/ ./   # overlay wins on conflicts
docker build -t gclaw .
```

Or wire the same step into a pre-build Cloud Build trigger.

### Option 2: Runtime mount (best for Cloud Run)

Keep the public image generic and mount the overlay at runtime via
a GCS bucket or a sidecar:

```bash
# Sync overlay → GCS
gsutil rsync -r ~/dev/gclaw-overlay/ gs://<your-bucket>/gclaw-overlay/

# At Cloud Run startup, the entrypoint pulls + extracts into /app
#   gsutil rsync -r gs://<your-bucket>/gclaw-overlay/ /app/
```

This keeps the public Docker image identical for every fork and lets
multiple deployments share a base image while reading different
overlays.

### Option 3: Git submodule (good for local dev)

```bash
cd ~/dev/gclaw
git submodule add git@github.com:<you>/gclaw-overlay.git overlay
ln -sf overlay/agents agents-private
ln -sf overlay/soul soul-private
export GCLAW_CONFIG_DIR=$(pwd)/overlay
```

Then the framework reads from `overlay/` instead of the in-tree
templates.

## What the public repo guarantees

- The public agent prompts are **functionally complete templates**.
  They route correctly, call the right tools, and won't crash if you
  start the system with no overlay. They will feel impersonal until
  you write your own.
- The public soul files are **placeholders** that establish the
  inheritance hierarchy but say almost nothing about voice. Override
  them.
- `user.md` ships as a section-headings-only template. Fill it in via
  the `profile-mgr` agent's onboarding flow or by writing the file
  yourself in your overlay.

## What the public repo does NOT do

- It does not pull from your overlay automatically. The overlay
  application step is yours to wire — the framework just reads from
  `GCLAW_CONFIG_DIR`.
- It does not validate that you applied the overlay. If you deploy
  without one, you get the generic templates. The system runs but
  your agents will sound like demo content.
- It does not version the overlay alongside the framework. You own
  the upgrade path between framework versions and overlay versions —
  most upgrades are non-breaking, but watch the changelog when
  agent/skill schemas change.

## Sample overlay layout

```
gclaw-overlay/
├── README.md                       # private notes for future-you
├── user.md                         # filled-in identity
├── agents/
│   ├── content-mgr.md              # branded version
│   └── ...                         # other personalized managers
├── soul/
│   ├── base.md                     # your real voice
│   ├── content.md                  # brand-specific content voice
│   └── ...
├── crons/
│   ├── heartbeat.json
│   └── ...
├── skills/
│   ├── humanizer/
│   │   └── SKILL.md                # your banned-words list
│   └── <your-brand-pipeline>/      # any brand- or client-specific skills
└── .env                            # secrets — never commit
```

Keep that overlay private. Push the framework changes through this
public repo's PR flow.
