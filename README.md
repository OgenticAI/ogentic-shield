# ogentic-shield

Regulatory sensitivity detection for AI applications. Detects attorney-client privilege, HIPAA PHI, financial MNPI, and 50+ PII types before content reaches an AI model.

## Install

```bash
pip install ogentic-shield
```

## Quick Start

```python
from ogentic_shield import Shield

shield = Shield(profiles=["shield-legal"])
result = shield.analyze("Per our conversation with outside counsel at Davis Polk...")

print(result.score)               # 94
print(result.sensitivity_level)   # CRITICAL
print(result.routing_suggestion)  # LOCAL_ONLY
```

## CLI

```bash
# Analyze text
ogentic-shield analyze "privileged and confidential" --profiles shield-legal --output json

# List profiles
ogentic-shield profiles list

# Show profile details
ogentic-shield profiles show shield-legal
```

## Profiles

| Profile | Domain | Entities |
|---------|--------|----------|
| `shield-legal` | Attorney-client privilege, work product, litigation | 10 |
| `shield-therapy` | HIPAA PHI, psychotherapy notes, clinical risk | 10 |
| `shield-finance` | MNPI, deal terms, fund information | 10 |

## License

Apache 2.0
