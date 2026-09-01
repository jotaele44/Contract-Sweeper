from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


WHOLE_ROW_POLICY = "WHOLE_SOURCE_OBSERVATIONS_ONLY_NO_CROSS_HOLDER_SUMMATION"


class CertificationLockError(RuntimeError):
    """Raised when a certification lock invariant fails."""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CertificationLockError(f"expected JSON object: {path}")
    return payload


def validate_vector_parent(
    payload: dict[str, Any],
    *,
    base_sha: str,
    merge_base_sha: str,
) -> None:
    parent = str(payload.get("parent_main_sha", ""))
    if not parent:
        raise CertificationLockError("vector parent_main_sha is missing")
    if parent != base_sha:
        raise CertificationLockError(f"declared parent {parent} != pull-request base {base_sha}")
    if parent != merge_base_sha:
        raise CertificationLockError(f"declared parent {parent} != git merge-base {merge_base_sha}")


def validate_semantic_boundaries(payload: dict[str, Any]) -> None:
    if payload.get("provider_equivalence") != "OPEN":
        raise CertificationLockError("provider/Morningstar equivalence was promoted")
    if payload.get("synthetic_row_identity") != "FORBIDDEN":
        raise CertificationLockError("synthetic row identity boundary was weakened")
    if payload.get("certification_inheritance") != "FORBIDDEN":
        raise CertificationLockError("cross-issuer certification inheritance was enabled")
    if payload.get("aggregation_policy") != WHOLE_ROW_POLICY:
        raise CertificationLockError("whole-source-row aggregation policy was weakened")

    state = payload.get("state")
    residue = payload.get("unresolved_residue")
    if not isinstance(residue, list):
        raise CertificationLockError("unresolved_residue must be a list")
    if state == "PASS":
        if residue:
            raise CertificationLockError(f"PASS vector retains residue: {residue}")
        if payload.get("deep_dive_promotion") not in {"ELIGIBLE", "PROMOTION_ELIGIBLE"}:
            raise CertificationLockError("PASS vector is not explicitly promotion eligible")
    elif state == "OPEN":
        if not residue:
            raise CertificationLockError("OPEN vector has no explicit unresolved residue")
        if payload.get("deep_dive_promotion") != "NOT_ELIGIBLE":
            raise CertificationLockError("OPEN vector is promotion eligible")
    else:
        raise CertificationLockError(f"unsupported vector state: {state!r}")


def build_preflight_receipt(
    payload: dict[str, Any],
    *,
    vector_path: str,
    head_sha: str,
    base_sha: str,
    merge_base_sha: str,
    workflow_run_id: str,
    source_snapshot_artifact_id: str,
) -> dict[str, Any]:
    validate_vector_parent(payload, base_sha=base_sha, merge_base_sha=merge_base_sha)
    validate_semantic_boundaries(payload)
    return {
        "schema": "moneysweep.sec13f-certification-lock/v1",
        "phase": "PRE_MERGE_EXACT_HEAD",
        "vector_id": payload.get("vector_id"),
        "issuer": payload.get("issuer"),
        "declared_state": payload.get("state"),
        "vector_path": vector_path,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "merge_base_sha": merge_base_sha,
        "workflow_run_id": str(workflow_run_id),
        "source_snapshot_artifact_id": str(source_snapshot_artifact_id),
        "semantic_invariants": {
            "provider_equivalence": "OPEN",
            "synthetic_row_identity": "FORBIDDEN",
            "certification_inheritance": "FORBIDDEN",
            "aggregation_policy": WHOLE_ROW_POLICY,
        },
        "merge_preconditions": [
            "PR_HEAD_SHA_MUST_EQUAL_THIS_RECEIPT_HEAD_SHA",
            "PR_BASE_SHA_MUST_EQUAL_THIS_RECEIPT_BASE_SHA",
            "ALL_EXACT_HEAD_WORKFLOWS_TERMINAL_SUCCESS",
            "CERTIFICATION_ARTIFACT_MUST_BIND_TO_THIS_HEAD_SHA",
            "MERGE_MUST_USE_EXPECTED_HEAD_SHA",
            "POST_MERGE_FIRST_PARENT_DIFF_MUST_EQUAL_PR_CHANGED_PATH_SET",
        ],
    }


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def verify_post_merge(
    *,
    merge_sha: str,
    expected_first_parent: str,
    expected_second_parent: str,
    expected_paths: set[str],
) -> dict[str, Any]:
    parents = _git_output("show", "-s", "--format=%P", merge_sha).split()
    if parents != [expected_first_parent, expected_second_parent]:
        raise CertificationLockError(
            f"merge parents {parents} != expected "
            f"[{expected_first_parent}, {expected_second_parent}]"
        )
    changed = {
        line
        for line in _git_output(
            "diff", "--name-only", expected_first_parent, merge_sha
        ).splitlines()
        if line
    }
    if changed != expected_paths:
        raise CertificationLockError(
            f"post-merge changed paths {sorted(changed)} != expected {sorted(expected_paths)}"
        )
    return {
        "schema": "moneysweep.sec13f-certification-lock/v1",
        "phase": "POST_MERGE_TREE_EQUIVALENCE",
        "merge_sha": merge_sha,
        "first_parent": expected_first_parent,
        "second_parent": expected_second_parent,
        "changed_paths": sorted(changed),
        "state": "PASS",
    }


def _preflight(args: argparse.Namespace) -> int:
    vector_path = Path(args.vector)
    payload = _load_json(vector_path)
    receipt = build_preflight_receipt(
        payload,
        vector_path=str(vector_path),
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        merge_base_sha=args.merge_base_sha,
        workflow_run_id=args.workflow_run_id,
        source_snapshot_artifact_id=args.source_snapshot_artifact_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _postmerge(args: argparse.Namespace) -> int:
    receipt = verify_post_merge(
        merge_sha=args.merge_sha,
        expected_first_parent=args.expected_first_parent,
        expected_second_parent=args.expected_second_parent,
        expected_paths=set(args.expected_path),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed SEC 13F certification lock")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--vector", required=True)
    preflight.add_argument("--head-sha", required=True)
    preflight.add_argument("--base-sha", required=True)
    preflight.add_argument("--merge-base-sha", required=True)
    preflight.add_argument("--workflow-run-id", required=True)
    preflight.add_argument("--source-snapshot-artifact-id", required=True)
    preflight.add_argument("--output", required=True)
    preflight.set_defaults(func=_preflight)

    postmerge = subparsers.add_parser("postmerge")
    postmerge.add_argument("--merge-sha", required=True)
    postmerge.add_argument("--expected-first-parent", required=True)
    postmerge.add_argument("--expected-second-parent", required=True)
    postmerge.add_argument("--expected-path", action="append", default=[], required=True)
    postmerge.add_argument("--output", required=True)
    postmerge.set_defaults(func=_postmerge)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except CertificationLockError as exc:
        raise SystemExit(f"SEC 13F certification lock FAIL: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
