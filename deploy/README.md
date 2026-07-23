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
- `SHIELD_NER_MODEL` (optional) — spaCy model for the NER layer. **Defaults to
  `en_core_web_sm`** here (~165 MB RAM — fits a 512 MB box). Set to
  `en_core_web_lg` (~780 MB RAM) on a ≥ 2 GB box for maximum NER recall. See
  [Memory & sizing](#memory--sizing).
- `SHIELD_PROFILES` (optional) — comma-separated profile ids
  (default `shield-finance,shield-legal,shield-therapy`).

## Deploy — Railway (OgenticAI's standard host for services)

The `Dockerfile` is self-contained (build context = this `deploy/` dir) and
installs the published wheel (`ogentic-shield[server]>=0.6.1`, which has the
configurable NER model). `railway.json` sets the Dockerfile + `/health` healthcheck.

Dashboard: **New Project → Deploy from GitHub repo** → `OgenticAI/ogentic-shield`,
then **Settings → Root Directory = `deploy`**. Set `SHIELD_API_KEY` (and optionally
`SHIELD_NER_MODEL=en_core_web_lg` if you gave it ≥ 2 GB).

Or from the CLI in this dir:

```
cd deploy
railway up --detach --service <service>
railway variables --set "SHIELD_API_KEY=<generate-a-secret>" --service <service>
```

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

## Memory & sizing

The Presidio + spaCy pipeline is the memory driver. Measured peak RSS with the
three regulated profiles loaded:

| `SHIELD_NER_MODEL` | Peak RAM | Fits | NER recall |
|---|---|---|---|
| `en_core_web_sm` (default here) | **~165 MB** | 512 MB box / most serverless | good — all regex + rule recognizers identical; slightly lower name/org NER |
| `en_core_web_lg` | ~780 MB | ≥ 2 GB box | maximum |

Two things that used to make this OOM-crash on small plans, both now handled:

1. **The model loaded on *every* request.** `run_layer1` built a fresh Presidio
   engine per call, so under concurrency the model multiplied in RAM until the
   container was OOM-killed. The analyzer is now **cached** (loads once, reused
   across request threads) — first `/analyze` pays the load, the rest are ~ms.
2. **`en_core_web_lg` was hardcoded.** Now selectable via `SHIELD_NER_MODEL`;
   `sm` is the lean default here.

Net: on a **512 MB–1 GB** plan, keep the `sm` default. Only bump to `lg` (and
≥ 2 GB) if you need maximum name/organization NER recall. Scale with replicas,
not workers (single worker per process — the engine is shared per process).

<details><summary>Other hosts (same Dockerfile, build from repo root)</summary>

- **Cloud Run:** `gcloud run deploy ogentic-shield --source deploy --region us-central1 --allow-unauthenticated --memory 512Mi --cpu 1` (bump to `--memory 2Gi` for `lg`)
- **Fly.io:** `cd deploy && fly launch --now --dockerfile Dockerfile --vm-memory 512`
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
