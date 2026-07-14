# ogentic-shield HTTP service (deploy)

The thin FastAPI wrapper that exposes `POST /analyze` for Zashboard's `ShieldClient`
(`packages/shield`). Full Presidio + spaCy pipeline. Runs on any container host;
listens on `$PORT` (default 8080).

## Contract
- `POST /analyze` — body `{ "text": string, "profiles"?: string[] }`
  (profiles e.g. `shield-finance` / `shield-legal` / `shield-therapy`).
  Optional `Authorization: Bearer <SHIELD_API_KEY>`.
  Returns snake_case `{ text_hash, entities[], score, sensitivity_level,
  routing_suggestion, entity_count, processing_time_ms, layers_invoked, profile_ids }`.
- `GET /health` → `{ "ok": true }`.

## Env
- `PORT` — set by the host.
- `SHIELD_API_KEY` (optional) — if set, `/analyze` requires the matching Bearer token.
  Set the SAME value as `SHIELD_API_KEY` in the Zashboard (Vercel) env.

## Deploy (pick one; all build this Dockerfile)

**Google Cloud Run**
```
gcloud run deploy ogentic-shield --source deploy --region us-central1 \
  --allow-unauthenticated --memory 2Gi --cpu 2 \
  --set-env-vars SHIELD_API_KEY=<generate-a-secret>
```

**Fly.io**
```
cd deploy && fly launch --now --dockerfile Dockerfile --vm-memory 2048
fly secrets set SHIELD_API_KEY=<generate-a-secret>
```

**Railway / Render** — connect this repo, root `deploy/`, Dockerfile build,
add `SHIELD_API_KEY`. (No CLI needed — dashboard "New service → from repo".)

> Memory: the Presidio + `en_core_web_lg` pipeline wants ~1.5–2 GB. Use ≥2 GB
> and scale with replicas, not workers.

## Wire Zashboard
Once you have the service URL, set on the `zashboardapp` Vercel project (Production +
Preview) and redeploy:
```
SHIELD_URL=https://<your-shield-host>
SHIELD_API_KEY=<same secret as above>   # only if you set one
```
Then the governed loop's Approve/Reject/dispatch calls redact through Shield and
return 200 instead of 503.
