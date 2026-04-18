FROM python:3.12-slim

# System deps + CLI tool binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — via the official apt repo
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Google Workspace CLI (gws) — download the prebuilt x86_64 linux-gnu binary.
# Verified against github.com/googleworkspace/cli/releases/latest (v0.22.5 as of 2026-04).
RUN set -eux; \
    tmp="$(mktemp -d)"; \
    curl -fsSL "https://github.com/googleworkspace/cli/releases/latest/download/google-workspace-cli-x86_64-unknown-linux-gnu.tar.gz" \
      | tar -xz -C "$tmp"; \
    find "$tmp" -type f -name gws -exec mv {} /usr/local/bin/gws \;; \
    chmod +x /usr/local/bin/gws; \
    rm -rf "$tmp"; \
    /usr/local/bin/gws --version || true

WORKDIR /app

COPY pyproject.toml .
COPY user.md .
COPY src/ src/
COPY soul/ soul/
COPY agents/ agents/
COPY skills/ skills/

RUN pip install --no-cache-dir .

ENV GCLAW_CONFIG_DIR=/app

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "gclaw.main:app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
