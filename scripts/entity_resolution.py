"""
Entity Resolution — Top N Vendors → Parent Entity Hierarchy

Resolves the top N vendors (by total obligation) to their parent entities.
The default path uses existing identifiers, SAM enrichment output, and cache
only. A bounded USASpending residual is explicit via ``--use-api``.

Usage:
  python3 scripts/entity_resolution.py               # offline-first
  python3 scripts/entity_resolution.py --top 50      # top 50
  python3 scripts/entity_resolution.py --use-api --max-api 100
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.config import PROJECT_ROOT, setup_logging
from scripts.sam_enrichment import normalize_vendor, name_similarity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USAS_RECIPIENT_SEARCH = "https://api.usaspending.gov/api/v2/recipient/search/"
USAS_RECIPIENT_DETAIL = "https://api.usaspending.gov/api/v2/recipient/{hash_or_id}/"
RATE_DELAY = 0.3
MATCH_THRESHOLD = 0.75
TOP_N_DEFAULT = 10_000  # analyze all significant entities, not just top 100


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _http_post(url: str, payload: dict, timeout: int = 12) -> dict | None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass
    return None


def _http_get(url: str, timeout: int = 12) -> dict | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass
    return None


def search_recipient(vendor_name: str) -> dict | None:
    """Search USASpending for a recipient. Returns best match or None."""
    norm = normalize_vendor(vendor_name)
    # Use the original name for search (better results than normalized),
    # but compare using normalized names for scoring.
    payload = {"search_text": vendor_name, "order": "desc", "sort": "amount", "limit": 5}
    data = _http_post(USAS_RECIPIENT_SEARCH, payload)
    if not data:
        return None
    results = data.get("results", [])
    if not results:
        return None
    best, best_score = None, 0.0
    for r in results:
        # USASpending recipient/search returns "name" (not "recipient_name")
        result_name = r.get("name") or r.get("recipient_name", "")
        score = name_similarity(norm, normalize_vendor(result_name))
        if score > best_score:
            best_score, best = score, r
    if best and best_score >= MATCH_THRESHOLD:
        best["match_score"] = round(best_score, 3)
        return best
    return None


def get_recipient_detail(recipient_id: str) -> dict | None:
    """Fetch recipient detail page (has parent info). recipient_id is the hash."""
    url = USAS_RECIPIENT_DETAIL.format(hash_or_id=recipient_id)
    return _http_get(url)


# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------


def load_vendor_rankings(root: Path, top_n: int) -> list[dict]:
    """Load top vendors from master CSV, ranked by total obligation."""
    # Prefer master_enriched (has UEI already)
    enriched = root / "data" / "staging" / "processed" / "enrichment" / "master_enriched.csv"
    master = root / "data" / "staging" / "processed" / "pr_contracts_master.csv"
    unified = root / "data" / "staging" / "processed" / "pr_all_awards_master.csv"
    source_path = enriched if enriched.exists() else (master if master.exists() else unified)

    if not source_path.exists():
        raise FileNotFoundError(f"No master CSV found at {source_path}")

    vendor_totals: dict[str, dict] = {}
    with open(source_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            # Support both old (vendor_name) and unified (recipient_name) schemas
            vn = (row.get("vendor_name") or row.get("recipient_name") or "").strip()
            if not vn:
                continue
            try:
                amt = float(row.get("obligated_amount") or 0)
            except (ValueError, TypeError):
                amt = 0.0
            if vn not in vendor_totals:
                vendor_totals[vn] = {
                    "vendor_name": vn,
                    "total_obligation": 0.0,
                    "record_count": 0,
                    "known_uei": (row.get("recipient_uei") or "").strip(),
                    "known_parent_uei": (row.get("parent_uei") or "").strip(),
                    "known_parent_name": (row.get("parent_name") or "").strip(),
                }
            vendor_totals[vn]["total_obligation"] += amt
            vendor_totals[vn]["record_count"] += 1
            # Carry UEI if found in any row
            if not vendor_totals[vn]["known_uei"]:
                vendor_totals[vn]["known_uei"] = (row.get("recipient_uei") or "").strip()

    ranked = sorted(vendor_totals.values(), key=lambda x: x["total_obligation"], reverse=True)
    return ranked[:top_n]


def load_sam_index(root: Path) -> dict[str, dict]:
    """Load vendor_uei_index.csv from SAM enrichment if it exists."""
    index_path = root / "data" / "staging" / "processed" / "enrichment" / "vendor_uei_index.csv"
    if not index_path.exists():
        return {}
    index = {}
    with open(index_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vn = (row.get("vendor_name") or "").strip()
            if vn:
                index[vn] = row
                index.setdefault(normalize_vendor(vn), row)
    return index


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_vendor(
    vendor: dict, sam_index: dict, cache: dict, logger, *, use_api: bool = False
) -> dict:
    """Resolve a vendor to its parent entity. Returns enriched dict."""
    vn = vendor["vendor_name"]
    norm = normalize_vendor(vn)

    result = {
        "vendor_name": vn,
        "rank": vendor.get("_rank", 0),
        "total_obligation": vendor["total_obligation"],
        "record_count": vendor["record_count"],
        "uei": vendor.get("known_uei", ""),
        "parent_uei": vendor.get("known_parent_uei", ""),
        "parent_name": vendor.get("known_parent_name", ""),
        "business_types": "",
        "match_confidence": 0.0,
        "source": "none",
    }

    # Already have parent from SAM enrichment — done
    if result["parent_uei"] or result["parent_name"]:
        result["source"] = "sam_enrichment"
        return result

    # Check SAM index
    sam_row = sam_index.get(vn) or sam_index.get(norm)
    if sam_row and sam_row.get("parent_uei"):
        result["uei"] = sam_row.get("uei", result["uei"])
        result["parent_uei"] = sam_row["parent_uei"]
        result["parent_name"] = sam_row.get("parent_name", "")
        result["match_confidence"] = float(sam_row.get("match_score") or 0)
        result["source"] = "sam_index"
        return result
    if sam_row and sam_row.get("resolution_status") == "RESOLVED_LOCAL_GOV":
        result["source"] = "local_government"
        return result

    # Cache hit
    if vn in cache:
        cached = cache[vn]
        # A parentless cache entry is useful offline but must not suppress a
        # later explicitly requested residual lookup.
        if not use_api or cached.get("parent_uei") or cached.get("parent_name"):
            result.update(cached)
            result["source"] = "cache"
            return result

    if not use_api:
        result["source"] = "offline_unresolved"
        return result

    # Query USASpending
    time.sleep(RATE_DELAY)
    search = search_recipient(vn)
    if not search:
        result["source"] = "unresolved"
        cache[vn] = {"parent_uei": "", "parent_name": "", "uei": result["uei"]}
        return result

    result["match_confidence"] = search.get("match_score", 0.0)
    if not result["uei"]:
        result["uei"] = search.get("uei", "")

    # Fetch detail for parent info
    recipient_id = search.get("recipient_hash") or search.get("id", "")
    if recipient_id:
        time.sleep(RATE_DELAY)
        detail = get_recipient_detail(recipient_id)
        if detail:
            parent = detail.get("parents") or []
            if parent:
                p = parent[0] if isinstance(parent, list) else parent
                result["parent_uei"] = p.get("uei", "") or p.get("recipient_uei", "")
                result["parent_name"] = p.get("name", "") or p.get("recipient_name", "")
            # Also check top-level parent fields
            if not result["parent_uei"]:
                result["parent_uei"] = detail.get("parent_uei", "")
                result["parent_name"] = detail.get("parent_name", "")
            bt = detail.get("business_types_description") or detail.get("business_types", [])
            if isinstance(bt, list):
                result["business_types"] = "; ".join(bt)
            else:
                result["business_types"] = str(bt)

    result["source"] = "usaspending"
    cache[vn] = {
        "parent_uei": result["parent_uei"],
        "parent_name": result["parent_name"],
        "uei": result["uei"],
        "business_types": result["business_types"],
    }
    logger.info(
        f"  {vn[:45]:<45}  parent={result['parent_name'][:30] or '—':<30}  "
        f"score={result['match_confidence']:.2f}"
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    root: Path | None = None,
    top_n: int = TOP_N_DEFAULT,
    resume: bool = False,
    *,
    use_api: bool = False,
    max_api: int = 100,
) -> Path:
    if root is None:
        root = PROJECT_ROOT

    output_dir = root / "data" / "staging" / "processed" / "enrichment"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "entity_cache.json"
    out_path = output_dir / "entity_hierarchy.csv"

    logger = setup_logging("entity_resolution")
    if use_api and max_api < 1:
        raise ValueError("max_api must be at least 1")
    logger.info(
        f"Entity resolution — top {top_n} vendors "
        f"({'offline + bounded API' if use_api else 'offline-only'})"
    )

    vendors = load_vendor_rankings(root, top_n)
    sam_index = load_sam_index(root)
    # Cache reads are always safe and make the default offline path useful on
    # repeated runs. ``--resume`` remains accepted for CLI compatibility.
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    logger.info(f"  Loaded {len(vendors)} vendors, {len(sam_index)} SAM index entries")

    rows = []
    resolved_count = 0
    for rank, vendor in enumerate(vendors, 1):
        vendor["_rank"] = rank
        result = resolve_vendor(vendor, sam_index, cache, logger, use_api=False)
        rows.append(result)
        if result.get("parent_uei") or result.get("parent_name"):
            resolved_count += 1
        if rank % 25 == 0:
            logger.info(
                f"  [PROGRESS] {rank}/{len(vendors)} processed, {resolved_count} with parent entity"
            )

    api_calls = 0
    if use_api:
        logger.info(f"  Live residual budget: {max_api} vendor lookups")
        for idx, (vendor, current) in enumerate(zip(vendors, rows, strict=True)):
            if current.get("parent_uei") or current.get("parent_name"):
                continue
            if current.get("source") == "local_government":
                continue
            if api_calls >= max_api:
                break
            updated = resolve_vendor(vendor, sam_index, cache, logger, use_api=True)
            rows[idx] = updated
            api_calls += 1

    resolved_count = sum(1 for row in rows if row.get("parent_uei") or row.get("parent_name"))

    # Save cache
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # Write hierarchy CSV
    fieldnames = [
        "rank",
        "vendor_name",
        "total_obligation",
        "record_count",
        "uei",
        "parent_uei",
        "parent_name",
        "business_types",
        "match_confidence",
        "source",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    logger.info(
        f"\nEntity hierarchy written: {out_path}\n"
        f"  {resolved_count}/{len(rows)} vendors resolved to parent entity; "
        f"live API calls={api_calls}"
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Entity resolution for top N vendors")
    parser.add_argument("--top", type=int, default=TOP_N_DEFAULT, help="Number of top vendors")
    parser.add_argument("--resume", action="store_true", help="Resume from cache")
    parser.add_argument(
        "--use-api", action="store_true", help="Enable a bounded USASpending residual pass"
    )
    parser.add_argument("--max-api", type=int, default=100)
    args = parser.parse_args()
    run(top_n=args.top, resume=args.resume, use_api=args.use_api, max_api=args.max_api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
