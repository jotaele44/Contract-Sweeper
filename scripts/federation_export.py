#!/usr/bin/env python3
"""Materialize moneysweep-pr's canonical export as a Hub-conformant package.

Reuses the canonical_v1 -> federation bridge
(``moneysweep.federation.canonical_v1_bridge.build_streams`` +
``scripts.bridge_canonical_v1_federation.merge_external_sources``) to build the
``sources``/``entities``/``relationships`` streams, then writes them plus a Hub
``federation_export_manifest.json`` (``manifest.json``) and a diagnostic
``coverage.json`` under ``<out>`` (default ``data/exports/canonical_v1_federation``).

The rows are unchanged from the bridge (already Hub-schema-valid); the only thing
this adds over ``bridge_canonical_v1_federation.py`` is the Hub-conformant
``manifest.json`` (``package_id``/``producer``/``mode``/``federation``/``files``…)
that ``hub validate-package`` / ``hub aggregate`` require.

Why committed rather than generated on demand: moneysweep-pr is
``ready_for_hub_live_execution: false``, so the Hub cannot run this export against
live sources — it discovers, validates, and aggregates the *committed* package.
``--now`` is threaded through every row + the manifest so the committed package is
byte-reproducible (pass a fixed timestamp; the default is wall-clock UTC).

CLI::

    python3 scripts/federation_export.py --mode test
    python3 scripts/federation_export.py --check            # validate rows, no write
    python3 scripts/federation_export.py --now 2026-06-07T01:08:53.877935+00:00
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from moneysweep.federation.canonical_v1_bridge import build_streams  # noqa: E402
from moneysweep.federation.centinelas_awards_bridge import (  # noqa: E402
    merge_centinelas_awards,
)
from scripts.bridge_canonical_v1_federation import (  # noqa: E402
    FEDERAL_PUBLICATIONS_PHASE,
    merge_external_sources,
    validate_rows,
)

PRODUCER = "moneysweep-pr"
HUB_PARENT = "thehub-pr"
EXPORT_CONTRACT_VERSION = "1.0.0"
DEFAULT_OUT = "data/exports/canonical_v1_federation"

# stream -> Hub canonical schema id. The bridge rows already validate against
# these (see tests/test_canonical_v1_bridge.py and `hub validate-package`).
STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
    "funding_awards": "federation_funding_award.schema.json",
}
# The three core streams are always present. ``funding_awards`` is optional — it
# is appended only when Centinelas pre-official candidates were ingested, so the
# committed 3-stream package (no candidates) is byte-unchanged.
STREAM_ORDER = ("sources", "entities", "relationships")
_OPTIONAL_STREAMS = ("funding_awards",)


def _stream_order(streams: dict) -> tuple[str, ...]:
    """Core streams + any optional stream that has rows."""
    return STREAM_ORDER + tuple(s for s in _OPTIONAL_STREAMS if streams.get(s))


def _validate_funding_awards(streams: dict, root: Path) -> list[str]:
    """Validate funding_awards rows against moneysweep_funding_award.schema.json
    (required keys + id patterns). Stdlib only, mirrors validate_rows."""
    rows = streams.get("funding_awards") or []
    if not rows:
        return []
    schema = json.loads(
        (root / "schemas" / "moneysweep_funding_award.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema.get("required", []))
    patterns = {
        "award_id": re.compile(r"^awd_[a-f0-9]{32}$"),
        "source_id": re.compile(r"^src_[a-f0-9]{32}$"),
        "recipient_entity_id": re.compile(r"^ent_[a-f0-9]{32}$"),
        "funding_agency_entity_id": re.compile(r"^ent_[a-f0-9]{32}$"),
        "currency": re.compile(r"^[A-Z]{3}$"),
    }
    errors: list[str] = []
    for i, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            errors.append(f"funding_awards[{i}]: missing {sorted(missing)}")
        for key, pat in patterns.items():
            val = row.get(key)
            if val is not None and not pat.match(str(val)):
                errors.append(f"funding_awards[{i}]: {key}={val!r} fails {pat.pattern}")
    return errors


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _synthetic_counts(streams) -> dict:
    """Per-stream count of rows flagged ``synthetic: true`` (a production export
    must contain none — mirrors the federation-wide production invariant)."""
    return {
        s: sum(1 for r in streams[s] if r.get("synthetic") is True) for s in _stream_order(streams)
    }


def write_package(streams, out_dir: Path, *, mode: str, now: str) -> dict:
    """Write the JSONL streams + a Hub ``federation_export_manifest.json``.

    Serialization matches ``bridge_canonical_v1_federation.write_streams``
    (``ensure_ascii=False``, insertion-order keys) so regenerating with the same
    ``now`` + inputs is byte-identical to the committed streams."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for stream in _stream_order(streams):
        rows = streams[stream]
        fpath = out_dir / f"{stream}.jsonl"
        fpath.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        files.append(
            {
                "filename": f"{stream}.jsonl",
                "stream": stream,
                "record_count": len(rows),
                "sha256": _sha256(fpath),
                "schema_id": STREAM_SCHEMA[stream],
            }
        )
    # Deterministic package id from sorted (filename, sha256) + mode (mirrors the
    # Hub's own bridge.write_manifest and the sibling producers).
    digest = hashlib.sha256(
        (
            "|".join(
                f"{f['filename']}:{f['sha256']}"
                for f in sorted(files, key=lambda x: str(x["filename"]))
            )
            + f"|{mode}"
        ).encode()
    ).hexdigest()[:32]
    manifest = {
        "package_id": f"pkg_{digest}",
        "producer": PRODUCER,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "mode": mode,
        "created_at": now,
        "extracted_at": now,
        "federation": {"producer_repo": PRODUCER, "hub_parent": HUB_PARENT},
        "files": files,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def build_coverage(streams, *, mode: str, now: str) -> dict:
    """The diagnostic metadata the bridge used to stash in its manifest, kept in a
    separate ``coverage.json`` now that ``manifest.json`` is the Hub manifest."""
    fed_pubs = sum(
        1
        for s in streams["sources"]
        if (s.get("lineage") or {}).get("producer_phase") == FEDERAL_PUBLICATIONS_PHASE
    )
    rels = len(streams["relationships"])
    not_fed = len(streams.get("not_yet_federated", []))
    return {
        "producer": PRODUCER,
        "gate": "PRODUCTION" if mode == "production" else "NON_PRODUCTION_DIAGNOSTIC",
        "stream_counts": {s: len(streams[s]) for s in _stream_order(streams)},
        "source_feeds": {
            "federal_publications": fed_pubs,
            "canonical_v1_evidence": len(streams["sources"]) - fed_pubs,
        },
        "not_yet_federated_count": not_fed,
        "edges_federated_pct": round(100.0 * rels / max(1, rels + not_fed), 2),
        "generated_at": now,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write moneysweep-pr's Hub-conformant canonical export package."
    )
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--out", default=None, help=f"output dir (default <root>/{DEFAULT_OUT})")
    ap.add_argument("--mode", default="test", choices=["test", "production"])
    ap.add_argument(
        "--now",
        default=None,
        help="ISO timestamp for a reproducible package (default: wall-clock UTC)",
    )
    ap.add_argument("--check", action="store_true", help="validate rows without writing")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    now = args.now or _iso_now()
    out_dir = Path(args.out) if args.out else root / DEFAULT_OUT

    streams = build_streams(root, now=now)
    merge_external_sources(streams, root)
    # Optional: fold in Centinelas pre-official candidates as a funding_awards stream
    # (no-op when exports/centinelas_intake/funding_awards.jsonl is absent).
    merge_centinelas_awards(streams, root, now)
    errors = validate_rows(streams, root)
    errors += _validate_funding_awards(streams, root)
    if errors:
        print(json.dumps({"ok": False, "errors": errors[:50]}, indent=2))
        return 1
    if args.mode == "production":
        synthetic = {s: c for s, c in _synthetic_counts(streams).items() if c}
        if synthetic:
            total = sum(synthetic.values())
            print(
                json.dumps(
                    {
                        "ok": False,
                        "errors": [
                            f"production export rejects synthetic rows ({total} found: {synthetic})"
                        ],
                    },
                    indent=2,
                )
            )
            return 1
    if args.check:
        print(
            json.dumps(
                {"ok": True, "stream_counts": {s: len(streams[s]) for s in _stream_order(streams)}},
                indent=2,
            )
        )
        return 0

    manifest = write_package(streams, out_dir, mode=args.mode, now=now)
    coverage = build_coverage(streams, mode=args.mode, now=now)
    (out_dir / "coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "package_id": manifest["package_id"],
                "mode": args.mode,
                "out": str(out_dir),
                "stream_counts": coverage["stream_counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
