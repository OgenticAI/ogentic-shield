# ogentic-shield HTTP service — full Presidio + spaCy pipeline.
# Runs on any container host (Cloud Run / Fly.io / Railway / Render); listens on
# $PORT (defaults to 8080). See deploy/README.md.
FROM python:3.12-slim

WORKDIR /app

# System deps Presidio/spaCy may touch (small).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Presidio's default NLP engine loads en_core_web_lg — bundle it into the image
# so there is no cold-start download. (Swap to en_core_web_sm for a much smaller
# image if NER accuracy can be traded for size.)
RUN python -m spacy download en_core_web_lg

COPY app.py .

ENV PORT=8080
EXPOSE 8080
# Single worker: the Presidio pipeline is memory-heavy; scale with replicas, not workers.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
