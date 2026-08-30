#!/usr/bin/env python3
"""Freeze the exact SEC Form 13F bulk archives for the BPOP golden window."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from scripts.config import PROJECT_ROOT

USER_AGENT = "MoneySweep research@pr-pipeline.org"
ARCHIVES = (
    ("2024Q2", "01jun2024-31aug2024_form13f.zip"),
    ("2024Q3", "01sep2024-30nov2024_form13f.zip"),
    ("2024Q4", "01dec2024-28feb2025_form13f.zip"),
    ("2025Q1", "01mar2025-31may2025_form13f.zip"),
    ("2025Q2", "01jun2025-31aug2025_form13f.zip"),
    ("2025Q3", "01sep2025-30nov2025_form13f.zip"),
    ("2025Q4", "01dec2025-28feb2026_form13f.zip"),
    ("2026Q1", "01mar2026-31may2026_form13f.zip"),
)
BASE = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets"
REQUIRED_MEMBERS = {"SUBMISSION.TSV", "COVERPAGE.TSV", "SUMMARYPAGE.TSV", "INFOTABLE.TSV"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_member_sha256(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with zf.open(info, "r") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_audit(path: Path) -> dict[str, object]:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a ZIP archive: {path}")
    members: list[dict[str, object]] = []
    present: set[str] = set()
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            present.add(Path(info.filename).name.upper())
            members.append(
                {
                    "path": info.filename,
                    "uncompressed_size": info.file_size,
                    "sha256": _zip_member_sha256(zf, info),
                }
            )
    missing = sorted(REQUIRED_MEMBERS - present)
    if missing:
        raise ValueError(f"{path.name}: missing required members {missing}")
    return {
        "filename": path.name,
        "byte_size": path.stat().st_size,
        "sha256": sha256_file(path),
        "required_members_present": True,
        "members": sorted(members, key=lambda row: str(row["path"])),
    }


def _download_zip(session: requests.Session, *, url: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with session.get(url, timeout=180, stream=True) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        if not zipfile.is_zipfile(temporary):
            raise ValueError(f"{url}: response is not a ZIP archive")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def run(*, root: Path, refresh: bool = False) -> dict[str, object]:
    raw_dir = root / "data" / "staging" / "raw" / "sec13f_bulk" / "bpop_8q_v1"
    manifest_path = root / "data" / "manifests" / "capital_control" / "bpop_8q_freeze_manifest.json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/zip,*/*"})
    audits: list[dict[str, object]] = []
    try:
        for quarter, filename in ARCHIVES:
            path = raw_dir / filename
            url = f"{BASE}/{filename}"
            origin = "REUSED_FROZEN"
            if refresh or not path.is_file():
                _download_zip(session, url=url, path=path)
                origin = "DOWNLOADED"
            audit = archive_audit(path)
            audit.update({"quarter": quarter, "source_url": url, "origin": origin})
            audits.append(audit)
    finally:
        session.close()

    if len(audits) != 8 or {row["quarter"] for row in audits} != {q for q, _ in ARCHIVES}:
        raise AssertionError("exact eight-quarter archive denominator failed")
    manifest = {
        "manifest_id": "BPOP_SEC13F_8Q_FREEZE_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_authority": "U.S. Securities and Exchange Commission",
        "scope": "BPOP golden window 2024Q2-2026Q1",
        "archive_count": 8,
        "refresh_requested": refresh,
        "archives": audits,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        manifest = run(root=args.root, refresh=args.refresh)
    except (OSError, requests.RequestException, ValueError) as exc:
        print(f"SEC 13F freeze failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"archive_count": manifest["archive_count"], "state": "FROZEN"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
