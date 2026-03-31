FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY soul/ soul/
COPY agents/ agents/

RUN pip install --no-cache-dir .

ENV GCLAW_CONFIG_DIR=/app

EXPOSE 8080

CMD ["python", "-m", "gclaw.main"]
