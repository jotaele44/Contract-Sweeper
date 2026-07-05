#!/usr/bin/env python3
from pathlib import Path
import json
import sys

root = Path("exports/federation")
required = ["manifest.json", "readiness.json", "blockers.json", "sources.json", "evidence_ledger.csv", "operator_report.md", "dashboard.html", "package.sha256"]
errors = [name for name in required if not (root / name).exists()]
manifest = json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").exists() else {}
if manifest.get("localhost_required") is not False:
    errors.append("localhost_required")
if manifest.get("offline_ready") is not True:
    errors.append("offline_ready")
for err in errors:
    print(f"FAIL: {err}", file=sys.stderr)
raise SystemExit(1 if errors else 0)
