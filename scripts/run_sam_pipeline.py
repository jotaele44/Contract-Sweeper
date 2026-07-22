"""Offline-first SAM entity resolution with an optional bounded API residual.

The default path never requires a SAM key: it preserves source UEIs, consumes a
monthly public extract when present, applies local classifications/cache entries,
merges the index into the staging master, and rebuilds ``entities_resolved.csv``.
Live name search must be explicitly requested and is protected by both a request
budget and a sustained-failure circuit breaker.

Usage:
  python3 scripts/run_sam_pipeline.py
  python3 scripts/run_sam_pipeline.py --dat /path/to/SAM_PUBLIC_MONTHLY_V2.dat
  python3 scripts/run_sam_pipeline.py --use-api --max-api 100
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_dat(root: Path, explicit: str | Path | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"SAM monthly extract not found: {path}")
        return path
    search_dirs = [root / "data" / "raw" / "sam"]
    if os.environ.get("SAM_BULK_DIR"):
        search_dirs.insert(0, Path(os.environ["SAM_BULK_DIR"]))
    candidates: list[Path] = []
    for directory in search_dirs:
        if directory.exists():
            candidates.extend(directory.glob("SAM_PUBLIC_MONTHLY_V2_*.dat"))
    return sorted(candidates)[-1] if candidates else None


def run(
    root: Path | None = None,
    *,
    dat: str | Path | None = None,
    use_api: bool = False,
    max_api: int = 100,
    circuit_breaker_failures: int = 3,
) -> dict[str, Any]:
    """Run all offline resolution layers, then an optional live residual pass."""
    from scripts.config import setup_logging

    root = Path(root or ROOT)
    logger = setup_logging("run_sam_pipeline")

    # Materialize a target cache (including source UEIs) before bulk ingestion.
    from scripts.sam_enrichment import load_targets, run as run_enrichment

    targets = load_targets(root)
    logger.info(f"[SAM] Targets ready: {len(targets):,}")

    bulk_summary: dict[str, Any] = {"status": "not_available"}
    dat_path = _find_dat(root, dat)
    if dat_path is None:
        logger.info("[SAM] No monthly public extract found — continuing with other offline layers")
    else:
        from scripts.ingest_sam_bulk import run as ingest_bulk
        from scripts.ingest_sam_bulk import write_outputs

        logger.info(f"[SAM] Streaming monthly public extract: {dat_path.name}")
        raw_summary = ingest_bulk(dat_path, root)
        outputs = write_outputs(raw_summary, root)
        bulk_summary = {key: value for key, value in raw_summary.items() if key != "_matches"}
        bulk_summary.update(
            {
                "status": "complete",
                "authoritative": outputs["n_auth"],
                "confirmed_k2": outputs["n_confirmed"],
            }
        )

    # Always complete the seconds-long offline scan first. This ensures even a
    # small live request budget cannot prevent later vendors receiving bulk UEIs.
    offline = run_enrichment(root=root, resume=True, use_api=False, max_api=max_api)
    residual = None
    if use_api:
        residual = run_enrichment(
            root=root,
            resume=True,
            use_api=True,
            max_api=max_api,
            circuit_breaker_failures=circuit_breaker_failures,
        )

    from scripts.parent_collapse import build_entities

    entities = build_entities(root)
    logger.info(
        f"[SAM] Complete — offline resolved={offline.get('vendors_resolved', 0):,}; "
        f"API calls={(residual or {}).get('api_calls', 0):,}; "
        f"entities={entities.get('entity_count', 0):,}"
    )
    return {
        "targets": len(targets),
        "bulk": bulk_summary,
        "offline": offline,
        "residual": residual,
        "entities": entities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline-first SAM resolution pipeline")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--dat", help="Path to SAM_PUBLIC_MONTHLY_V2_*.dat")
    api_group = parser.add_mutually_exclusive_group()
    api_group.add_argument(
        "--use-api",
        action="store_true",
        help="Enable a bounded live residual pass (off by default)",
    )
    api_group.add_argument(
        "--skip-api",
        action="store_true",
        help="Deprecated compatibility alias; the default is already offline-only",
    )
    parser.add_argument("--max-api", type=int, default=100)
    parser.add_argument("--circuit-breaker-failures", type=int, default=3)
    args = parser.parse_args(argv)
    run(
        Path(args.root),
        dat=args.dat,
        use_api=args.use_api,
        max_api=args.max_api,
        circuit_breaker_failures=args.circuit_breaker_failures,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
