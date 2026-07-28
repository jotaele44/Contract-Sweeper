import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from moneysweep.case_manager import (
    AuditEvent,
    Case,
    CaseEvidence,
    Claim,
    ClaimEvidence,
    Contradiction,
    Finding,
    ValidationError,
    deterministic_id,
    validate_append_only_events,
    validate_case_bundle,
)


def test_deterministic_ids_are_idempotent():
    left = deterministic_id("case", "FEMA", 4339, "PW", 8535)
    right = deterministic_id("case", "FEMA", 4339, "PW", 8535)
    assert left == right
    assert left.startswith("case_")


def test_claim_and_finding_are_separate_and_evidence_relations_are_explicit():
    case_id = deterministic_id("case", "FEMA:4339:PW:8535")
    evidence_id = "evidence_carraizo_qpr_2026_q2_abc123"
    claim_id = deterministic_id("claim", case_id, "schedule changed")
    case = Case(case_id, "Carraizo", "project_oversight", "open", "QPR review")
    claim = Claim(
        claim_id,
        case_id,
        "The projected completion date changed.",
        "schedule",
        "pending",
        0.85,
        "linked",
    )
    bundle = {
        "case": case,
        "canonical_evidence_ids": (evidence_id,),
        "case_evidence": (
            CaseEvidence(
                deterministic_id("case_evidence", case_id, evidence_id),
                case_id,
                evidence_id,
                "qpr",
            ),
        ),
        "claims": (claim,),
        "claim_evidence": (
            ClaimEvidence(
                deterministic_id("claim_evidence", claim_id, evidence_id, "support"),
                claim_id,
                evidence_id,
                "support",
            ),
        ),
        "contradictions": (),
        "findings": (
            Finding(
                deterministic_id("finding", claim_id),
                case_id,
                claim_id,
                "Schedule changed across reports.",
                0.85,
                "reviewer",
                True,
                "accepted",
            ),
        ),
        "audit_events": (),
    }
    validate_case_bundle(bundle)


def test_unresolved_contradictions_are_not_auto_collapsed():
    case_id = deterministic_id("case", "x")
    c1 = deterministic_id("claim", "a")
    c2 = deterministic_id("claim", "b")
    contradiction = Contradiction(
        deterministic_id("contradiction", c1, c2),
        case_id,
        (c1, c2),
        "temporal",
        "high",
    )
    assert contradiction.status == "open"
    assert contradiction.claim_ids == (c1, c2)


def test_accepted_finding_requires_contradiction_review():
    case_id = deterministic_id("case", "x")
    claim_id = deterministic_id("claim", "x")
    bundle = {
        "case": Case(case_id, "X", "audit", "open", "scope"),
        "canonical_evidence_ids": (),
        "case_evidence": (),
        "claims": (
            Claim(claim_id, case_id, "X", "test", "pending", 0.5, "inferred"),
        ),
        "claim_evidence": (),
        "contradictions": (),
        "findings": (
            Finding(
                deterministic_id("finding", claim_id),
                case_id,
                claim_id,
                "X",
                0.5,
                "r",
                False,
                "accepted",
            ),
        ),
        "audit_events": (),
    }
    with pytest.raises(ValidationError):
        validate_case_bundle(bundle)


def test_audit_events_are_append_only_and_hash_chained():
    case_id = deterministic_id("case", "x")
    first_hash = hashlib.sha256(b"first").hexdigest()
    events = (
        AuditEvent(
            deterministic_id("audit_event", 1),
            case_id,
            1,
            "2026-01-01T00:00:00Z",
            "tester",
            "create",
            "case",
            case_id,
            first_hash,
        ),
        AuditEvent(
            deterministic_id("audit_event", 2),
            case_id,
            2,
            "2026-01-02T00:00:00Z",
            "tester",
            "review",
            "case",
            case_id,
            hashlib.sha256(b"second").hexdigest(),
            first_hash,
        ),
    )
    validate_append_only_events(events)


def test_audit_event_rejects_nonmatching_predecessor_hash():
    case_id = deterministic_id("case", "x")
    first_hash = hashlib.sha256(b"first").hexdigest()
    events = (
        AuditEvent(
            deterministic_id("audit_event", 1),
            case_id,
            1,
            "2026-01-01T00:00:00Z",
            "tester",
            "create",
            "case",
            case_id,
            first_hash,
        ),
        AuditEvent(
            deterministic_id("audit_event", 2),
            case_id,
            2,
            "2026-01-02T00:00:00Z",
            "tester",
            "review",
            "case",
            case_id,
            hashlib.sha256(b"second").hexdigest(),
            "0" * 64,
        ),
    )
    with pytest.raises(ValidationError):
        validate_append_only_events(events)


def test_case_manager_schema_is_valid_draft7():
    schema = json.loads(
        Path("schemas/case_manager_v1/case_manager.schema.json").read_text()
    )
    Draft7Validator.check_schema(schema)
    assert "definitions" in schema
    assert "$defs" not in schema
    assert "visibility" in schema["definitions"]["case_event"]["required"]
    assert "visibility" in schema["definitions"]["finding"]["required"]


def test_sql_migration_is_idempotent_from_clean_state():
    sql = Path("migrations/001_case_manager_v1.sql").read_text()
    for _ in range(2):
        db = sqlite3.connect(":memory:")
        db.executescript(sql)
        db.executescript(sql)
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert len(tables) == 11
        assert "cases" in tables
        assert "case_audit_events" in tables
        db.close()


def test_sql_migration_blocks_audit_event_update_and_delete():
    sql = Path("migrations/001_case_manager_v1.sql").read_text()
    db = sqlite3.connect(":memory:")
    db.executescript(sql)
    db.execute(
        "INSERT INTO cases(case_id,title,case_type,status,scope,visibility) "
        "VALUES('case_x','X','audit','open','scope','internal')"
    )
    db.execute(
        "INSERT INTO case_audit_events VALUES"
        "('audit_event_x','case_x',1,'2026-01-01','tester','create','case','case_x',?,NULL)",
        ("a" * 64,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE case_audit_events SET actor='other'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM case_audit_events")


def test_fixture_is_read_only_and_not_promoted():
    fixture = json.loads(Path("tests/fixtures/case_manager/carraizo_case.json").read_text())
    assert fixture["fixture_status"] == "read_only_pending_review"
    assert fixture["canonical_promotion"] is False
