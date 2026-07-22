# ogentic-shield HTTP service — Presidio + spaCy pipeline, lean by default.
#
# Self-contained: build context is THIS directory (deploy/). Installs the
# published wheel (>= 0.6.0, which has the configurable NER model). Railway:
# Root Directory = deploy.
FROM python:3.12-slim

WORKDIR /app

# System deps Presidio/spaCy may touch (small).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bundle BOTH spaCy models. Which one *loads* (and therefore how much RAM the
# service uses) is chosen at runtime by SHIELD_NER_MODEL:
#   en_core_web_sm — ~165 MB RAM, the default here (fits a 512 MB box)
#   en_core_web_lg — ~780 MB RAM, max NER recall (needs a >= 2 GB box)
# Disk cost of bundling both is small; RAM stays lean by default, and lg is one
# env var away with no rebuild.
RUN python -m spacy download en_core_web_sm \
    && python -m spacy download en_core_web_lg

COPY app.py .

ENV PORT=8080
# Lean by default — this is the setting that keeps the service from OOM-crashing
# on a small plan. Override to en_core_web_lg on a >= 2 GB box for max accuracy.
ENV SHIELD_NER_MODEL=en_core_web_sm
EXPOSE 8080
# Bind 0.0.0.0 (IPv4) — the platform edge connects over IPv4; a "::" (IPv6-only)
# bind on -slim gives a 502 even though the app is up.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
