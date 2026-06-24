"""
Smoke test for ogentic-shield.

Run against the locally-installed package (pip install -e .) during development,
or against the public PyPI release after `pip install ogentic-shield==<version>`
in a fresh venv.

Exit 0  — smoke passed.
Exit 1  — smoke failed (message printed to stderr).
"""

import sys

# -- import check ------------------------------------------------------------
try:
    from ogentic_shield import Shield, AnalysisResult
except ImportError as exc:
    print(f"SMOKE FAIL: import error — {exc}", file=sys.stderr)
    sys.exit(1)

# -- basic analyze -----------------------------------------------------------
s = Shield()

result = s.analyze("The weather is nice today.")
assert isinstance(result, AnalysisResult), "analyze() must return AnalysisResult"
print(f"analyze:          OK  (score={result.score}, routing={result.routing_suggestion})")

# -- classify_batch ----------------------------------------------------------
texts = [
    "Attorney-client privileged memorandum — do not distribute.",
    "Patient diagnosis: F32.1 Major depressive disorder.",
    "The weather is nice today.",
]

batch = s.classify_batch(texts)
assert len(batch) == len(texts), f"classify_batch must return {len(texts)} results, got {len(batch)}"
for i, item in enumerate(batch):
    assert isinstance(item, AnalysisResult), f"Item {i} must be AnalysisResult, got {type(item)}"
print(f"classify_batch:   OK  ({len(batch)} results)")

# -- empty-list fast path ----------------------------------------------------
empty = s.classify_batch([])
assert empty == [], f"classify_batch([]) must return [], got {empty!r}"
print("classify_batch[]: OK  (empty-list fast path)")

print("\nsmoke OK — all checks passed")
