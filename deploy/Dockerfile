# ogentic-shield HTTP service — full Presidio + spaCy pipeline.
#
# Build context is the REPO ROOT (not deploy/), so shield is installed from
# source — the configurable NER model (SHIELD_NER_MODEL) isn't in the published
# 0.4 wheel yet. Switch to a pinned wheel after the next release.
# Railway: Root Directory = repo root, Dockerfile Path = deploy/Dockerfile.
FROM python:3.12-slim

WORKDIR /app

# System deps Presidio/spaCy may touch (small).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install shield (server extra) from source. README.md is referenced by
# pyproject's `readme=`, so it's needed for the build.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[server]" "uvicorn[standard]>=0.29"

# Bundle BOTH spaCy models. Which one *loads* (and therefore how much RAM the
# service uses) is chosen at runtime by SHIELD_NER_MODEL:
#   en_core_web_sm — ~165 MB RAM, the default here (fits a 512 MB box)
#   en_core_web_lg — ~780 MB RAM, max NER recall (needs a >= 2 GB box)
# Disk cost of bundling both is small; RAM stays lean by default, and lg is one
# env var away with no rebuild.
RUN python -m spacy download en_core_web_sm \
    && python -m spacy download en_core_web_lg

COPY deploy/app.py ./app.py

ENV PORT=8080
# Lean by default — this is the setting that keeps the service from OOM-crashing
# on a small plan. Override to en_core_web_lg on a >= 2 GB box for max accuracy.
ENV SHIELD_NER_MODEL=en_core_web_sm
EXPOSE 8080
# Bind 0.0.0.0 (IPv4) — the platform edge connects over IPv4; a "::" (IPv6-only)
# bind on -slim gives a 502 even though the app is up.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
