"""SQLite persistence adapter for Case Manager Phase 1.

All writes are performed inside explicit transactions. Canonical evidence is referenced by
identifier only and is never mutated by this adapter.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence


class CaseManagerConflict(RuntimeError):
    """Raised when a transactional invariant or optimistic sequence check fails."""


class CaseManagerNotFound(LookupError):
    """Raised when a requested Case Manager object does not exist."""


class SQLiteCaseManagerRepository:
    """Small, explicit SQLite repository with no canonical-data write capability."""

    def __init__(self, database: str | Path | sqlite3.Connection):
        if isinstance(database, sqlite3.Connection):
            self.connection = database
            self._owns_connection = False
        else:
            self.connection = sqlite3.connect(str(database), check_same_thread=False)
            self._owns_connection = True
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def apply_migration(self, migration_path: str | Path) -> None:
        self.connection.executescript(Path(migration_path).read_text())

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        begin = "BEGIN IMMEDIATE" if immediate else "BEGIN"
        try:
            self.connection.execute(begin)
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _payload(record: Any) -> dict[str, Any]:
        if not is_dataclass(record):
            raise TypeError("record must be a dataclass instance")
        return asdict(record)

    @staticmethod
    def _json(value: Sequence[str]) -> str:
        return json.dumps(list(value), separators=(",", ":"), sort_keys=True)

    def insert_case(self, case: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(case)
        connection.execute(
            "INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                p["case_id"], p["title"], p["case_type"], p["status"], p["scope"],
                p["priority"], p["owner"], p["visibility"], p["opened_at"], p["closed_at"],
            ),
        )

    def insert_case_evidence(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO case_evidence VALUES(?,?,?,?,?,?,?,?)",
            tuple(p[k] for k in (
                "case_evidence_id", "case_id", "evidence_id", "role", "relevance",
                "review_status", "visibility", "analyst_note",
            )),
        )

    def insert_claim(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO claims VALUES(?,?,?,?,?,?,?,?)",
            tuple(p[k] for k in (
                "claim_id", "case_id", "statement", "claim_type", "status", "confidence",
                "language_tier", "visibility",
            )),
        )

    def insert_claim_evidence(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO claim_evidence VALUES(?,?,?,?,?,?)",
            tuple(p[k] for k in (
                "claim_evidence_id", "claim_id", "evidence_id", "relation", "rationale",
                "visibility",
            )),
        )

    def insert_contradiction(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO contradictions VALUES(?,?,?,?,?,?,?,?,?)",
            (
                p["contradiction_id"], p["case_id"], self._json(p["claim_ids"]),
                p["contradiction_type"], p["severity"], p["status"],
                p["resolution_rationale"], p["assigned_reviewer"], p["visibility"],
            ),
        )

    def resolve_contradiction(
        self,
        contradiction_id: str,
        status: str,
        rationale: str,
        reviewer: str,
        connection: sqlite3.Connection,
    ) -> None:
        result = connection.execute(
            "UPDATE contradictions SET status=?,resolution_rationale=?,assigned_reviewer=? "
            "WHERE contradiction_id=? AND status='open'",
            (status, rationale, reviewer, contradiction_id),
        )
        if result.rowcount != 1:
            raise CaseManagerConflict("contradiction is missing or no longer open")

    def insert_lead(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO leads VALUES(?,?,?,?,?,?,?,?,?)",
            (
                p["lead_id"], p["case_id"], p["question"], p["status"],
                p["acquisition_target"], p["owner"], p["due_at"],
                self._json(p["closure_evidence_ids"]), p["visibility"],
            ),
        )

    def close_lead(
        self,
        lead_id: str,
        closure_evidence_ids: Sequence[str],
        connection: sqlite3.Connection,
    ) -> None:
        result = connection.execute(
            "UPDATE leads SET status='closed',closure_evidence_ids_json=? "
            "WHERE lead_id=? AND status!='closed'",
            (self._json(closure_evidence_ids), lead_id),
        )
        if result.rowcount != 1:
            raise CaseManagerConflict("lead is missing or already closed")

    def insert_finding(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?)",
            (
                p["finding_id"], p["case_id"], p["claim_id"], p["conclusion"],
                p["confidence"], p["reviewer"], int(p["contradiction_reviewed"]),
                p["status"], p["visibility"],
            ),
        )

    def accept_finding(self, finding_id: str, connection: sqlite3.Connection) -> None:
        result = connection.execute(
            "UPDATE findings SET status='accepted' "
            "WHERE finding_id=? AND status='draft' AND contradiction_reviewed=1",
            (finding_id,),
        )
        if result.rowcount != 1:
            raise CaseManagerConflict("finding cannot be accepted")

    def insert_snapshot(self, record: Any, connection: sqlite3.Connection) -> None:
        p = self._payload(record)
        connection.execute(
            "INSERT INTO case_snapshots VALUES(?,?,?,?,?,?,?)",
            (
                p["case_snapshot_id"], p["case_id"], p["created_at"],
                p["manifest_sha256"], self._json(p["evidence_ids"]),
                p["supersedes_snapshot_id"], p["redaction_profile"], p["visibility"],
            ) if False else (
                p["case_snapshot_id"], p["case_id"], p["created_at"],
                p["manifest_sha256"], self._json(p["evidence_ids"]),
                p["supersedes_snapshot_id"], p["redaction_profile"], p["visibility"],
            ),
        )

    def append_audit_event(
        self,
        event: Any,
        expected_previous_sequence: int,
        connection: sqlite3.Connection,
    ) -> None:
        p = self._payload(event)
        row = connection.execute(
            "SELECT sequence,payload_sha256 FROM case_audit_events WHERE case_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (p["case_id"],),
        ).fetchone()
        current_sequence = int(row["sequence"]) if row else 0
        previous_hash = row["payload_sha256"] if row else None
        if current_sequence != expected_previous_sequence:
            raise CaseManagerConflict("audit sequence changed concurrently")
        if p["sequence"] != current_sequence + 1:
            raise CaseManagerConflict("audit sequence is not contiguous")
        if p["previous_event_sha256"] != previous_hash:
            raise CaseManagerConflict("audit predecessor hash mismatch")
        connection.execute(
            "INSERT INTO case_audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            tuple(p[k] for k in (
                "audit_event_id", "case_id", "sequence", "occurred_at", "actor", "action",
                "object_type", "object_id", "payload_sha256", "previous_event_sha256",
                "visibility",
            )),
        )

    def latest_audit(self, case_id: str) -> tuple[int, str | None]:
        row = self.connection.execute(
            "SELECT sequence,payload_sha256 FROM case_audit_events WHERE case_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return (int(row["sequence"]), row["payload_sha256"]) if row else (0, None)

    def fetch_one(self, table: str, id_column: str, object_id: str) -> dict[str, Any]:
        allowed = {
            "cases", "case_evidence", "claims", "claim_evidence", "contradictions",
            "leads", "findings", "case_snapshots", "case_audit_events", "case_events",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE {id_column}=?", (object_id,)
        ).fetchone()
        if row is None:
            raise CaseManagerNotFound(object_id)
        return dict(row)

    def fetch_case_rows(self, table: str, case_id: str) -> list[dict[str, Any]]:
        direct = {
            "case_evidence", "claims", "contradictions", "case_events", "leads", "findings",
            "case_snapshots", "case_audit_events",
        }
        if table not in direct:
            raise ValueError("unsupported case table")
        order = "sequence" if table == "case_audit_events" else "rowid"
        rows = self.connection.execute(
            f"SELECT * FROM {table} WHERE case_id=? ORDER BY {order}", (case_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def list_cases(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM cases ORDER BY opened_at,case_id").fetchall()
        return [dict(row) for row in rows]
