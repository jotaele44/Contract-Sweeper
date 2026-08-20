"""
Enrich RDC civil-claim rows from their detail pages (the second half of the lane).

scripts/scrape_rdc_demandas.py sweeps the registry's list view, which does not
render the parties. The detail page at ``/rdc/Home/Details/{case_number}`` does:

    Demandante                  the claimant
    Representante de Demandante the claimant's attorney
    Demandado                   THE GOVERNMENT ENTITY BEING SUED
    Representante de Demandado  its attorney

The Demandado is what makes this source useful to a public-money node — it is
the join to registries/government_entity_registry.yaml. Nothing else in the
registry names the agency in a structured field.

This pass is deliberately separate and **resumable**. There are ~44,700 cases,
so a full enrichment is many hours of requests against a small government host.
Every run is bounded by ``--limit`` and/or ``--max-runtime``, progress is
flushed to disk periodically, and rows already carrying
``defendant_attribution_method == "detail_page"`` are skipped, so the corpus
fills in over as many short runs as it takes. This must never be wired into a
blocking pipeline stage.

Two honesty constraints:

* **Ambiguous case numbers are skipped by default.** The detail route keys on
  Núm del Caso alone, and that value is not unique across the registry, so for
  a flagged row the app may serve a different case entirely. Importing that
  would be worse than leaving the row unenriched. ``--include-ambiguous``
  overrides for investigation, and rows fetched that way are marked
  ``review_status = ambiguous_key`` rather than ``verified``.

* **Parties are not zipped to their attorneys.** The two lists are independent
  on the page — case 09 has two Demandados and one Representante de Demandado —
  so pairing them positionally would invent a relationship the source does not
  assert. All four roles are written as a flat long-format list instead.

Outputs:
  data/staging/processed/pr_rdc_demandas_civiles.csv   (updated in place)
  data/staging/processed/pr_rdc_demandas_parties.csv   (long format, one row per party)

Usage:
  python3 scripts/enrich_rdc_details.py --limit 10          # smoke test
  python3 scripts/enrich_rdc_details.py --limit 2000
  python3 scripts/enrich_rdc_details.py --max-runtime 3600
  python3 scripts/enrich_rdc_details.py --include-ambiguous --limit 50
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lxml.html
import pandas as pd
import requests

from moneysweep.runtime.base_downloader import build_session
from moneysweep.runtime.post_ingest import apply_post_ingest
from moneysweep.runtime.retry_runtime import RetryExhausted, RetryPolicy, with_retry
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.scrape_rdc_demandas import (
    DEMANDA_COLUMNS,
    HTTP,
    OUT_PATH_REL,
    SOURCE_ID,
    _RateLimited,
    _clean,
)

PARTIES_PATH_REL = "data/staging/processed/pr_rdc_demandas_parties.csv"

RETRY_POLICY = RetryPolicy(
    max_attempts=HTTP.max_retries,
    base_delay_seconds=HTTP.base_delay_seconds,
    max_delay_seconds=HTTP.max_delay_seconds,
)

PARTY_COLUMNS = [
    "rdc_case_uid",
    "case_number",
    "party_role",
    "party_ordinal",
    "party_name",
    "source_system",
    "source_url",
]

# <h4> headings on the detail page, mapped to the role recorded per party row.
PARTY_ROLES = {
    "Demandante": "demandante",
    "Representante de Demandante": "representante_demandante",
    "Demandado": "demandado",
    "Representante de Demandado": "representante_demandado",
}

# Label/value blocks worth reading. The list view already has most of these;
# they are re-read because the detail page renders amounts at full precision
# (400000.0000 vs 400000.00) and is the only place Disposición is reliable.
DETAIL_LABELS = {
    "Número de Caso": "case_number",
    "Causa de Acción": "causa_de_accion",
    "Cuantía Reclamada": "claimed_amount",
    "Cantidad Adjudicada": "adjudicated_amount",
    "Resolución final": "resolucion_final",
    "Fecha Resolución Final": "fecha_resolucion_final",
    "Disposición": "disposicion",
    "Epígrafe": "epigrafe",
}

# Money columns the detail page can restate at full precision. Their
# `*_canonical` companions must be recomputed rather than carried over.
DETAIL_REFRESHED_AMOUNTS = ("claimed_amount", "adjudicated_amount")

# The registry's own "no value" sentinel. Stored as blank so downstream
# consumers do not have to know the phrase.
_NULL_SENTINEL = "-No hay Información-"

# How often progress is flushed to disk. A killed run keeps everything up to
# the last flush rather than losing the whole pass.
FLUSH_EVERY = 200


def _detail_url(case_number: str) -> str:
    return f"https://justicia1.justicia.pr.gov/rdc/Home/Details/{case_number}"


def parse_detail(html: str) -> dict[str, Any]:
    """Parse one detail page into {fields: {...}, parties: [{role, ordinal, name}]}.

    Returns empty structures rather than raising when the page is an error page
    or its shape has drifted, so a single bad case cannot kill a long run.
    """
    empty: dict[str, Any] = {"fields": {}, "parties": []}
    try:
        tree = lxml.html.fromstring(html)
    except (lxml.etree.ParserError, ValueError):
        return empty

    fields: dict[str, str] = {}
    for block in tree.xpath("//div[contains(@class,'d-inline-flex')]"):
        children = block.xpath("./div")
        if len(children) != 2:
            continue
        label = _clean(children[0].text_content())
        canonical = DETAIL_LABELS.get(label)
        if not canonical:
            continue
        value = _clean(children[1].text_content())
        fields[canonical] = "" if value == _NULL_SENTINEL else value

    parties: list[dict[str, Any]] = []
    for heading in tree.xpath("//h4"):
        role = PARTY_ROLES.get(_clean(heading.text_content()))
        if not role:
            continue
        container = heading.getparent()
        if container is None:
            continue
        ordinal = 0
        for cell in container.xpath(".//table//tbody/tr/td"):
            name = _clean(cell.text_content())
            if not name:
                continue
            ordinal += 1
            parties.append({"party_role": role, "party_ordinal": ordinal, "party_name": name})

    return {"fields": fields, "parties": parties}


def _fetch_detail(session: requests.Session, url: str, logger) -> str | None:
    """GET one detail page. None on a terminal 4xx or retry exhaustion."""

    def _once() -> str | None:
        resp = session.get(url, timeout=HTTP.timeout)
        if resp.status_code == 429:
            logger.warning(f"  Rate limited on {url} — sleeping {HTTP.rate_limit_sleep}s")
            time.sleep(HTTP.rate_limit_sleep)
            raise _RateLimited()
        if 400 <= resp.status_code < 500:
            logger.error(f"  HTTP {resp.status_code} on {url}")
            return None
        resp.raise_for_status()
        time.sleep(HTTP.page_sleep)
        return resp.text

    try:
        return with_retry(
            _once, policy=RETRY_POLICY, retry_on=(requests.RequestException, _RateLimited)
        )
    except RetryExhausted as exc:
        logger.error(f"  {url} failed: {exc}")
        return None


def select_pending(frame: pd.DataFrame, include_ambiguous: bool = False) -> pd.DataFrame:
    """Rows still needing a detail fetch, in file order.

    Rows whose detail page has already been read are skipped so the pass
    resumes. The predicate is ``detail_fetched_at``, not the presence of a
    defendant: a case that legitimately names no Demandado is still done, and
    keying off the defendant would re-fetch it on every run forever.

    Ambiguous case numbers are skipped unless explicitly requested, because the
    detail route cannot address them unambiguously.
    """
    if frame.empty:
        return frame
    if "detail_fetched_at" not in frame.columns:
        frame = frame.assign(detail_fetched_at="")
    pending = frame["detail_fetched_at"].fillna("").astype(str).str.strip() == ""
    if not include_ambiguous and "case_number_ambiguous" in frame.columns:
        pending &= frame["case_number_ambiguous"].fillna("false") != "true"
    return frame[pending]


def apply_detail(row: dict, parsed: dict, ambiguous: bool, fetched_on: str) -> dict:
    """Merge one parsed detail page into its case row.

    Detail values win over list values where both exist — the detail page
    carries full-precision amounts and the authoritative Disposición — but a
    blank detail value never erases a populated list value.

    ``detail_fetched_at`` is stamped whenever the page parsed to anything at
    all, including when it names no Demandado. Some cases genuinely have none
    (bankruptcies; captions where the government is the plaintiff), and marking
    those done by the presence of a defendant would re-fetch them forever.
    """
    updated = dict(row)
    for canonical, value in parsed["fields"].items():
        if value:
            updated[canonical] = value

    defendants = [p["party_name"] for p in parsed["parties"] if p["party_role"] == "demandado"]
    plaintiffs = [p["party_name"] for p in parsed["parties"] if p["party_role"] == "demandante"]

    if defendants:
        updated["defendant_name"] = defendants[0]
        updated["defendant_count"] = str(len(defendants))
        updated["defendant_attribution_method"] = "detail_page"
    else:
        # Read from the page and found none — that is a fact, not a gap.
        updated["defendant_count"] = "0"
    if plaintiffs:
        updated["plaintiff_name"] = plaintiffs[0]

    updated["detail_fetched_at"] = fetched_on
    if ambiguous:
        # The key problem dominates: we may not even be looking at this case.
        updated["review_status"] = "ambiguous_key"
    elif defendants:
        updated["review_status"] = "verified"
    else:
        # The page was read and listed no Demandado. Calling that "verified"
        # would overstate a row still carrying a caption-parsed candidate the
        # detail page never corroborated, and would contradict defendant_count=0.
        updated["review_status"] = "no_defendant_listed"
    return updated


def _write_outputs(
    cases: pd.DataFrame,
    parties: pd.DataFrame,
    case_path: Path,
    parties_path: Path,
    root: Path,
) -> None:
    """Write both CSVs, re-running post-ingest so canonical columns stay current.

    ``canonicalize_currency`` is idempotent by design: it skips any money column
    that already has a ``*_canonical`` companion. That is right for a producer
    writing fresh rows, but wrong here — the list sweep already wrote canonical
    amounts, and the detail page is the authoritative, full-precision source for
    the raw ones. Left alone, an enriched row would carry a detail-sourced raw
    amount beside a list-sourced numeric, and every downstream total would be
    computed from the stale number. So the affected companions are dropped and
    recomputed rather than preserved.
    """
    case_path.parent.mkdir(parents=True, exist_ok=True)
    stale = [f"{col}_canonical" for col in DETAIL_REFRESHED_AMOUNTS]
    cases = cases.drop(columns=[c for c in stale if c in cases.columns])
    enriched = apply_post_ingest(cases, source_id=SOURCE_ID, root=root)
    enriched.to_csv(case_path, index=False, encoding="utf-8")
    parties.to_csv(parties_path, index=False, encoding="utf-8")


def _run(
    root=None,
    limit: int | None = None,
    max_runtime: float | None = None,
    include_ambiguous: bool = False,
) -> dict:
    if root is None:
        root = PROJECT_ROOT
    root = Path(root)
    case_path = root / OUT_PATH_REL
    parties_path = root / PARTIES_PATH_REL
    logger = setup_logging("enrich_rdc_details")

    if not case_path.exists():
        msg = f"{OUT_PATH_REL} not found — run scripts/scrape_rdc_demandas.py first"
        logger.error(msg)
        return {"status": "ERROR", "rows": 0, "enriched": 0, "errors": [msg]}

    cases = pd.read_csv(case_path, dtype=str, low_memory=False).fillna("")
    for column in DEMANDA_COLUMNS:
        if column not in cases.columns:
            cases[column] = ""

    if parties_path.exists():
        parties = pd.read_csv(parties_path, dtype=str, low_memory=False).fillna("")
    else:
        parties = pd.DataFrame(columns=PARTY_COLUMNS)

    pending = select_pending(cases, include_ambiguous=include_ambiguous)
    logger.info(f"  {len(pending):,} of {len(cases):,} cases pending detail enrichment")
    if limit is not None:
        pending = pending.head(limit)
        logger.info(f"  bounded to {len(pending):,} this run")

    today = datetime.now(timezone.utc).date().isoformat()
    by_uid = {str(uid): idx for idx, uid in enumerate(cases["rdc_case_uid"])}
    new_party_rows: list[dict] = []
    enriched_uids: set[str] = set()
    started = time.monotonic()
    enriched = 0
    failed = 0

    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    try:
        for count, (_, source_row) in enumerate(pending.iterrows(), start=1):
            if max_runtime is not None and time.monotonic() - started >= max_runtime:
                logger.info(f"  runtime budget reached after {count - 1:,} cases — stopping")
                break

            row = source_row.to_dict()
            uid = str(row["rdc_case_uid"])
            url = row.get("detail_url") or _detail_url(row.get("case_number", ""))

            html = _fetch_detail(session, url, logger)
            if html is None:
                failed += 1
                continue

            parsed = parse_detail(html)
            if not parsed["fields"] and not parsed["parties"]:
                logger.warning(f"  {url} parsed to nothing — leaving pending")
                failed += 1
                continue

            ambiguous = str(row.get("case_number_ambiguous", "false")) == "true"
            cases.loc[by_uid[uid], list(row)] = apply_detail(row, parsed, ambiguous, today)

            for party in parsed["parties"]:
                new_party_rows.append(
                    {
                        "rdc_case_uid": uid,
                        "case_number": row.get("case_number", ""),
                        "party_role": party["party_role"],
                        "party_ordinal": str(party["party_ordinal"]),
                        "party_name": party["party_name"],
                        "source_system": SOURCE_ID,
                        "source_url": url,
                    }
                )
            enriched_uids.add(uid)
            enriched += 1

            if enriched % FLUSH_EVERY == 0:
                merged = _merge_parties(parties, new_party_rows, enriched_uids)
                _write_outputs(cases, merged, case_path, parties_path, root)
                logger.info(f"    flushed at {enriched:,} enriched cases")
    finally:
        session.close()

    merged = _merge_parties(parties, new_party_rows, enriched_uids)
    _write_outputs(cases, merged, case_path, parties_path, root)

    remaining = len(select_pending(cases, include_ambiguous=include_ambiguous))
    logger.info("=" * 60)
    logger.info("RDC DETAIL ENRICHMENT SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Enriched this run: {enriched:,}")
    logger.info(f"  Failed this run:   {failed:,}")
    logger.info(f"  Party rows total:  {len(merged):,}")
    logger.info(f"  Still pending:     {remaining:,}")

    return {
        "status": "OK",
        "rows": len(cases),
        "enriched": enriched,
        "failed": failed,
        "pending": remaining,
        "errors": [],
    }


def _merge_parties(
    existing: pd.DataFrame, new_rows: list[dict], refreshed_uids: set[str]
) -> pd.DataFrame:
    """Replace the party rows of every re-fetched case, keep everything else.

    Dropping by uid rather than appending keeps a re-run from duplicating a
    case's parties, and lets a case that lost a party on the source side lose
    it here too.
    """
    if existing.empty:
        kept = pd.DataFrame(columns=PARTY_COLUMNS)
    elif refreshed_uids:
        kept = existing[~existing["rdc_case_uid"].astype(str).isin(refreshed_uids)]
    else:
        kept = existing
    if not new_rows:
        return kept.reindex(columns=PARTY_COLUMNS)
    added = pd.DataFrame(new_rows, columns=PARTY_COLUMNS)
    return pd.concat([kept.reindex(columns=PARTY_COLUMNS), added], ignore_index=True)


def run(
    root=None,
    limit: int | None = None,
    max_runtime: float | None = None,
    include_ambiguous: bool = False,
) -> dict:
    return _run(
        root=root, limit=limit, max_runtime=max_runtime, include_ambiguous=include_ambiguous
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich RDC cases from their detail pages")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to fetch this run")
    parser.add_argument(
        "--max-runtime", type=float, default=None, help="Stop after this many seconds"
    )
    parser.add_argument(
        "--include-ambiguous",
        action="store_true",
        help="Also fetch cases whose case number is not unique. The detail route "
        "may serve a different case; results are marked review_status=ambiguous_key.",
    )
    args = parser.parse_args()
    result = _run(
        limit=args.limit, max_runtime=args.max_runtime, include_ambiguous=args.include_ambiguous
    )
    if result["status"] == "ERROR":
        print(f"\nRDC detail enrichment failed: {result['errors'][0]}")
        return 1
    print(
        f"\nRDC detail enrichment: {result['enriched']:,} cases enriched, "
        f"{result['pending']:,} still pending"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
