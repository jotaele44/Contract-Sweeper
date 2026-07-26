#!/usr/bin/env python3
"""Durably ingest one idempotent Centinelas handoff envelope."""
import hashlib
import json
import os
from pathlib import Path

payload = json.loads(os.environ["CENTINELAS_CLIENT_PAYLOAD"])
key = payload["idempotency_key"]
if payload["target"] != os.environ["EXPECTED_TARGET"]:
    raise SystemExit("handoff target mismatch")
out = Path("data/centinelas_handoffs") / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
duplicate = out.exists()
out.parent.mkdir(parents=True, exist_ok=True)
if not duplicate:
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if github_output := os.environ.get("GITHUB_OUTPUT"):
    with open(github_output, "a", encoding="utf-8") as handle:
        handle.write(f"duplicate={str(duplicate).lower()}\nreceipt_path={out}\n")
