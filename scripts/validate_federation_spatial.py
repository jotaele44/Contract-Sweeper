#!/usr/bin/env python3
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = {"feature", "layer", "map_runtime", "offline_package", "impact_report"}


def main() -> int:
    problems = []
    try:
        m = json.loads((ROOT / "federation.spatial.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"BLOCKED: cannot read spatial manifest: {e}")
        return 1
    if m.get("contract_version") != "federation-spatial-manifest/1.0":
        problems.append("wrong contract_version")
    if m.get("producer_repo") != "moneysweep-pr":
        problems.append("producer_repo mismatch")
    if m.get("cross_repo", {}).get("identity_default") != "CANDIDATE_NOT_IDENTITY":
        problems.append("identity default must fail closed")
    if m.get("cross_repo", {}).get("hub_correlation_authority") != "thehub-pr":
        problems.append("hub correlation authority drift")
    if not HEX40.fullmatch(str(m.get("frozen_base_sha", ""))):
        problems.append("invalid frozen_base_sha")
    if set(m.get("contracts", {})) != REQUIRED:
        problems.append("contract path set mismatch")
    for label, rel in m.get("contracts", {}).items():
        p = ROOT / rel
        if not p.is_file():
            problems.append(f"missing {label}: {rel}")
        else:
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                problems.append(f"invalid JSON schema {rel}: {e}")
    for key in ("postgis_migration", "mvt_migration"):
        rel = m.get("storage", {}).get(key)
        if not rel or not (ROOT / rel).is_file():
            problems.append(f"missing storage artifact: {key}")
    if m.get("storage", {}).get("ownership") != "REPO_LOCAL":
        problems.append("storage ownership must be REPO_LOCAL")
    print(
        json.dumps(
            {"ok": not problems, "producer_repo": "moneysweep-pr", "problems": problems}, indent=2
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
