# Ogentic Shield — No-Telemetry Policy

**Version:** 0.1.0
**Status:** Draft — pending review by Craig + external counsel before going live
**Ticket:** [OGE-446](https://linear.app/ogenticai/issue/OGE-446)
**Last updated:** 2026-06-27

---

## Commitment

`ogentic-shield` and the Sotto Desktop application that embeds it make **no
outbound network calls** except to the model update channel, which is
strictly one-way (download only). No chat content, document text, analysis
result, or user identifier is ever transmitted off the device.

This document is OgenticAI's on-record architectural commitment to that
property, including the explicit allow-list of permitted endpoints, a
user-runnable verification recipe, and the terms under which this policy
could ever change.

---

## Network allow-list

The following is the **complete** list of outbound network endpoints used by
Sotto Desktop and `ogentic-shield`:

| Endpoint | Protocol | Direction | Purpose |
|---|---|---|---|
| `updates.ogenticai.com` | HTTPS (443) | Outbound — **download only** | Model weight and config updates |
| `releases.ogenticai.com` | HTTPS (443) | Outbound — **download only** | Application version updates |

**No other outbound calls are made.** In particular, the following do NOT
occur:

- Chat message content is never transmitted
- Document text passed to `shield.analyze()` is never transmitted
- `AnalysisResult` objects (detected entities, scores, routing suggestions)
  are never transmitted
- User identifiers, session identifiers, or device identifiers are never
  transmitted
- Layer 3 LLM inference (when enabled) runs against `localhost` via Ollama,
  not against any remote API (see `ogentic-shield.yaml`: `llm.enabled: false`
  by default; when enabled, `llm.endpoint` defaults to `http://localhost:11434`)

---

## User-runnable verification recipe

You can confirm this policy independently using standard network capture tools.
The following procedures work on macOS, Linux, and Windows.

### macOS — using tcpdump

```bash
# 1. Start a capture on all interfaces, filtering for non-localhost traffic
sudo tcpdump -i any -n 'not host 127.0.0.1 and not host ::1' -w /tmp/sotto_capture.pcap &
TCPDUMP_PID=$!

# 2. Run ogentic-shield against a sample document for ~30 seconds
echo "Meeting with outside counsel re: litigation strategy, privileged and confidential." \
  | ogentic-shield analyze --profiles shield-legal --output json

# 3. Stop the capture
sudo kill $TCPDUMP_PID

# 4. Inspect the capture
tcpdump -r /tmp/sotto_capture.pcap -n
# Expected: no packets, or only DNS + TLS to updates.ogenticai.com / releases.ogenticai.com
```

### macOS — using Little Snitch (GUI)

1. Open Little Snitch Network Monitor.
2. Run `ogentic-shield analyze "text..."` in Terminal.
3. Observe the connection log. You should see only connections to
   `updates.ogenticai.com` (if an update check runs) and no other outbound
   connections.

### Linux — using Wireshark / tshark

```bash
# Capture traffic excluding localhost, for 60 seconds
sudo tshark -i any -f "not host 127.0.0.1" -a duration:60 -w /tmp/sotto_capture.pcap

# In another terminal, run the analysis
ogentic-shield analyze "Privileged memo re: settlement strategy." --profiles shield-legal

# Inspect
tshark -r /tmp/sotto_capture.pcap -T fields -e ip.dst -e tcp.dstport
# Expected: empty or only updates.ogenticai.com:443
```

### Windows — using Wireshark

1. Open Wireshark, start capturing on your primary network interface.
2. Apply display filter: `ip.dst != 127.0.0.1 and ip.dst != ::1`
3. Run `ogentic-shield analyze "text..."` in PowerShell.
4. Stop the capture. Expected: no packets to unexpected destinations.

---

## Opt-in commitment

OgenticAI commits to the following terms for any future telemetry:

1. **Opt-in only**: Any feature that transmits data (usage analytics, error
   reporting, model improvement signals) will require an explicit user opt-in
   via a clearly labeled setting in Sotto Desktop.
2. **Version bump required**: Any addition of a telemetry feature requires a
   minor or major version bump in Sotto Desktop (`MAJOR.MINOR.PATCH`). No
   telemetry feature will be introduced as a patch release.
3. **No silent rollout**: Telemetry features will be announced in `CHANGELOG.md`
   and in the Sotto Desktop release notes before deployment.
4. **Scope disclosure**: Any opt-in telemetry feature will disclose exactly
   what data is transmitted, to what endpoint, and for what purpose, in both
   the settings UI and in this document (updated in the same PR as the feature).
5. **Revocable**: Any opt-in can be revoked at any time from Sotto Desktop
   settings. Revocation takes effect immediately (no grace period, no
   pending-transmission queue).

This commitment applies to `ogentic-shield` (the OSS library) and to Sotto
Desktop (the commercial application that embeds it). Changes to this policy
require a new version of this document, committed with a PR that references
the relevant Linear ticket.

---

## Scope

This policy covers:

- `ogentic-shield` Python library (all versions)
- Sotto Desktop (all versions)
- The `ogentic-shield serve --mcp` and `ogentic-shield serve --http` server
  modes

This policy does NOT cover:

- Third-party integrations built by customers using `ogentic-shield` (customers
  own their own network policies)
- Upstream model providers (if a customer configures Layer 3 to use a remote
  LLM endpoint — that endpoint's data policy is the provider's responsibility)

---

## Contact

Questions about this document: [security@ogenticai.com](mailto:security@ogenticai.com)

To report a suspected violation of this policy (i.e., you observed unexpected
outbound traffic from Sotto Desktop or `ogentic-shield`):
[security@ogenticai.com](mailto:security@ogenticai.com)
