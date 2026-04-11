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

# Google Workspace CLI (gws) — download the prebuilt linux-x64 binary.
# Note: release asset name may differ across versions; verify against
# https://github.com/googleworkspace/cli/releases if build fails.
ARG GWS_VERSION=latest
RUN curl -fsSL "https://github.com/googleworkspace/cli/releases/${GWS_VERSION}/download/gws-linux-x64.tar.gz" \
      | tar -xz -C /usr/local/bin gws \
    && chmod +x /usr/local/bin/gws

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY soul/ soul/
COPY agents/ agents/

RUN pip install --no-cache-dir .

ENV GCLAW_CONFIG_DIR=/app

EXPOSE 8080

CMD ["python", "-m", "gclaw.main"]
