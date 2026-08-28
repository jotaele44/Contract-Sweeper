from __future__ import annotations

from typing import Any

import pytest

from scripts import sec13f_certification_lock as lock

pytestmark = pytest.mark.unit


def _pass_vector() -> dict[str, Any]:
    return {
        "vector_id": "OFG_SEC13F_v1",
        "state": "PASS",
        "parent_main_sha": "a" * 40,
        "issuer": {"ticker": "OFG"},
        "provider_equivalence": "OPEN",
        "synthetic_row_identity": "FORBIDDEN",
        "certification_inheritance": "FORBIDDEN",
        "aggregation_policy": lock.WHOLE_ROW_POLICY,
        "deep_dive_promotion": "ELIGIBLE",
        "unresolved_residue": [],
    }


def test_preflight_accepts_exact_parent_and_semantic_boundaries() -> None:
    payload = _pass_vector()
    receipt = lock.build_preflight_receipt(
        payload,
        vector_path="vector.json",
        head_sha="b" * 40,
        base_sha="a" * 40,
        merge_base_sha="a" * 40,
        workflow_run_id="123",
        source_snapshot_artifact_id="9598537414",
    )
    assert receipt["phase"] == "PRE_MERGE_EXACT_HEAD"
    assert receipt["head_sha"] == "b" * 40
    assert receipt["base_sha"] == "a" * 40
    assert receipt["merge_base_sha"] == "a" * 40
    assert receipt["semantic_invariants"]["provider_equivalence"] == "OPEN"
    assert "MERGE_MUST_USE_EXPECTED_HEAD_SHA" in receipt["merge_preconditions"]
    assert (
        "POST_MERGE_FIRST_PARENT_DIFF_MUST_EQUAL_PR_CHANGED_PATH_SET"
        in receipt["merge_preconditions"]
    )


def test_preflight_rejects_stale_or_wrong_pr_base() -> None:
    payload = _pass_vector()
    with pytest.raises(lock.CertificationLockError, match="pull-request base"):
        lock.build_preflight_receipt(
            payload,
            vector_path="vector.json",
            head_sha="b" * 40,
            base_sha="c" * 40,
            merge_base_sha="a" * 40,
            workflow_run_id="123",
            source_snapshot_artifact_id="9598537414",
        )


def test_preflight_rejects_non_exact_ancestry_even_when_base_string_matches() -> None:
    payload = _pass_vector()
    with pytest.raises(lock.CertificationLockError, match="git merge-base"):
        lock.build_preflight_receipt(
            payload,
            vector_path="vector.json",
            head_sha="b" * 40,
            base_sha="a" * 40,
            merge_base_sha="d" * 40,
            workflow_run_id="123",
            source_snapshot_artifact_id="9598537414",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider_equivalence", "PASS", "equivalence"),
        ("synthetic_row_identity", "ALLOWED", "synthetic row identity"),
        ("certification_inheritance", "ALLOWED", "inheritance"),
        ("aggregation_policy", "SUM_BY_BRAND", "whole-source-row"),
    ],
)
def test_semantic_boundary_regressions_fail_closed(
    field: str,
    value: str,
    message: str,
) -> None:
    payload = _pass_vector()
    payload[field] = value
    with pytest.raises(lock.CertificationLockError, match=message):
        lock.validate_semantic_boundaries(payload)


def test_pass_with_residue_is_rejected() -> None:
    payload = _pass_vector()
    payload["unresolved_residue"] = ["DENOMINATOR_CONTRADICTION"]
    with pytest.raises(lock.CertificationLockError, match="PASS vector retains residue"):
        lock.validate_semantic_boundaries(payload)


def test_open_vector_requires_explicit_residue_and_nonpromotion() -> None:
    payload = _pass_vector()
    payload["state"] = "OPEN"
    payload["deep_dive_promotion"] = "NOT_ELIGIBLE"
    payload["unresolved_residue"] = ["EXACT_DENOMINATOR_OPEN"]
    lock.validate_semantic_boundaries(payload)


def test_post_merge_requires_exact_parent_order_and_path_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git_output(*args: str) -> str:
        calls.append(args)
        if args[:3] == ("show", "-s", "--format=%P"):
            return f"{'a' * 40} {'b' * 40}"
        if args[:2] == ("diff", "--name-only"):
            return "data/vector.json\ntests/test_vector.py"
        raise AssertionError(args)

    monkeypatch.setattr(lock, "_git_output", fake_git_output)
    receipt = lock.verify_post_merge(
        merge_sha="c" * 40,
        expected_first_parent="a" * 40,
        expected_second_parent="b" * 40,
        expected_paths={"data/vector.json", "tests/test_vector.py"},
    )
    assert receipt["state"] == "PASS"
    assert receipt["changed_paths"] == ["data/vector.json", "tests/test_vector.py"]
    assert calls


def test_post_merge_rejects_unexpected_file_multiplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git_output(*args: str) -> str:
        if args[:3] == ("show", "-s", "--format=%P"):
            return f"{'a' * 40} {'b' * 40}"
        return "data/vector.json\ntests/test_vector.py\nunexpected.txt"

    monkeypatch.setattr(lock, "_git_output", fake_git_output)
    with pytest.raises(lock.CertificationLockError, match="changed paths"):
        lock.verify_post_merge(
            merge_sha="c" * 40,
            expected_first_parent="a" * 40,
            expected_second_parent="b" * 40,
            expected_paths={"data/vector.json", "tests/test_vector.py"},
        )
