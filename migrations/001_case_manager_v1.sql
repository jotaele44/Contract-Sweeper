-- MoneySweep Case Manager v1 additive schema.
-- This migration creates new tables only; it does not alter canonical_v1 evidence rows.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY, title TEXT NOT NULL, case_type TEXT NOT NULL,
  status TEXT NOT NULL, scope TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal',
  owner TEXT, visibility TEXT NOT NULL CHECK (visibility IN ('public','internal','restricted')),
  opened_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS case_evidence (
  case_evidence_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  evidence_id TEXT NOT NULL, role TEXT NOT NULL, relevance TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK (review_status IN ('pending','accepted','rejected')),
  visibility TEXT NOT NULL CHECK (visibility IN ('public','internal','restricted')),
  analyst_note TEXT, UNIQUE(case_id,evidence_id,role)
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  statement TEXT NOT NULL, claim_type TEXT NOT NULL, status TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  language_tier TEXT NOT NULL CHECK (language_tier IN ('observed','linked','inferred','blocked')),
  visibility TEXT NOT NULL CHECK (visibility IN ('public','internal','restricted'))
);
CREATE TABLE IF NOT EXISTS claim_evidence (
  claim_evidence_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES claims(claim_id),
  evidence_id TEXT NOT NULL, relation TEXT NOT NULL CHECK (relation IN ('support','contradict','qualify','supersede')),
  rationale TEXT, UNIQUE(claim_id,evidence_id,relation)
);
CREATE TABLE IF NOT EXISTS case_entities (
  case_entity_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  entity_id TEXT NOT NULL, role TEXT NOT NULL, valid_from TEXT, valid_to TEXT,
  visibility TEXT NOT NULL CHECK (visibility IN ('public','internal','restricted'))
);
CREATE TABLE IF NOT EXISTS case_events (
  case_event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  event_type TEXT NOT NULL, occurred_at TEXT NOT NULL, description TEXT NOT NULL,
  source_evidence_ids_json TEXT NOT NULL DEFAULT '[]', amount_usd TEXT,
  certainty REAL NOT NULL CHECK (certainty BETWEEN 0 AND 1), visibility TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contradictions (
  contradiction_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  claim_ids_json TEXT NOT NULL, contradiction_type TEXT NOT NULL, severity TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','resolved','held_apart')),
  resolution_rationale TEXT, assigned_reviewer TEXT
);
CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id), question TEXT NOT NULL,
  status TEXT NOT NULL, acquisition_target TEXT, owner TEXT, due_at TEXT,
  closure_evidence_ids_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  claim_id TEXT NOT NULL REFERENCES claims(claim_id), conclusion TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1), reviewer TEXT NOT NULL,
  contradiction_reviewed INTEGER NOT NULL CHECK (contradiction_reviewed IN (0,1)),
  status TEXT NOT NULL CHECK (status IN ('draft','accepted','withdrawn')), visibility TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_snapshots (
  case_snapshot_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  created_at TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, evidence_ids_json TEXT NOT NULL,
  supersedes_snapshot_id TEXT REFERENCES case_snapshots(case_snapshot_id), redaction_profile TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_audit_events (
  audit_event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
  sequence INTEGER NOT NULL, occurred_at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  object_type TEXT NOT NULL, object_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
  previous_event_sha256 TEXT, UNIQUE(case_id,sequence)
);

-- Append-only enforcement. Updates and deletes must create compensating events/records instead.
CREATE TRIGGER IF NOT EXISTS case_audit_events_no_update BEFORE UPDATE ON case_audit_events
BEGIN SELECT RAISE(ABORT, 'case_audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS case_audit_events_no_delete BEFORE DELETE ON case_audit_events
BEGIN SELECT RAISE(ABORT, 'case_audit_events is append-only'); END;
