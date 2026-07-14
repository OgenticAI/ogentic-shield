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

## Deploy — Railway (OgenticAI's standard host for services)

Railway builds this `Dockerfile` directly (`railway.json` here configures the
builder + `/health` healthcheck). Fastest path is the CLI from this dir:

```
cd deploy
railway up --detach --service <service>   # builds this Dockerfile + railway.json
railway variables --set "SHIELD_API_KEY=<generate-a-secret>" --service <service>
```

Or via the dashboard: **New Project → Deploy from GitHub repo** →
`OgenticAI/ogentic-shield`, then **Settings → Root Directory = `deploy`** so it
picks up this Dockerfile + `railway.json`.

### Two Railway gotchas that will cost you an hour (both hit us on first deploy)

1. **Bind `0.0.0.0`, not `::`.** Railway's edge/proxy connects to the container
   over **IPv4**. A `--host ::` bind is IPv6-only on `python:*-slim`
   (`bindv6only`), so the edge gets a 502 *"Application failed to respond"* even
   though the app is up. The `startCommand` here uses `--host 0.0.0.0` — keep it.
2. **The public domain needs a target port bound to 8080.** After generating the
   domain, Railway may leave the target port **unset** (the domain editor shows
   *"Select a port"*). Symptoms: healthcheck fails *"service unavailable"* → deploy
   never goes live → edge returns 404 *"Application not found"*; or, with no
   healthcheck, a 502. Fix in **Settings → Networking → the domain → edit → Edit
   Port → 8080** (Railway "magic" detects `8080 (uvicorn)` for you). The CLI
   cannot set this on an existing domain — use the dashboard, then redeploy so the
   running deployment re-registers with the proxy.

> Memory: the Presidio + `en_core_web_lg` pipeline wants ~1.5–2 GB. The service
> boots on the 1 GB trial plan (models load lazily on first `/analyze`), but give
> it ≥ **2 GB** for headroom and scale with replicas, not workers.

<details><summary>Other hosts (same Dockerfile)</summary>

- **Cloud Run:** `gcloud run deploy ogentic-shield --source deploy --region us-central1 --allow-unauthenticated --memory 2Gi --cpu 2`
- **Fly.io:** `cd deploy && fly launch --now --dockerfile Dockerfile --vm-memory 2048`
</details>

## Wire Zashboard
Once you have the service URL, set on the `zashboardapp` Vercel project (Production +
Preview) and redeploy:
```
SHIELD_URL=https://<your-shield-host>
SHIELD_API_KEY=<same secret as above>   # only if you set one
```
Then the governed loop's Approve/Reject/dispatch calls redact through Shield and
return 200 instead of 503.
