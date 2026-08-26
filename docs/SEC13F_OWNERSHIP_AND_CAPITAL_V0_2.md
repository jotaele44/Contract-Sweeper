#!/usr/bin/env python3
"""Discover, download, and freeze authoritative SEC Form 13F bulk archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

SEC_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
_ZIP_RE = re.compile(
    r"(?:https://www\.sec\.gov)?(?P<path>/files/structureddata/data/form-13f-data-sets/[^\"'<> ]+_form13f\.zip)$",
    re.I,
)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(str(value))


def _request(url: str, *, user_agent: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Accept": "*/*"},
    )


def discover_archives(*, user_agent: str) -> dict[str, str]:
    with urllib.request.urlopen(_request(SEC_INDEX_URL, user_agent=user_agent), timeout=60) as response:
        html = response.read().decode("utf-8", errors="strict")
    parser = _LinkParser()
    parser.feed(html)
    discovered: dict[str, str] = {}
    for href in parser.hrefs:
        match = _ZIP_RE.search(href)
        if not match:
            continue
        path = match.group("path")
        name = Path(path).name
        url = "https://www.sec.gov" + path
        if name in discovered and discovered[name] != url:
            raise RuntimeError(f"conflicting SEC URLs for {name}")
        discovered[name] = url
    if not discovered:
        raise RuntimeError("SEC index yielded no Form 13F bulk ZIP links")
    return discovered


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _freeze_existing(path: Path, url: str) -> dict[str, object]:
    if not zipfile.is_zipfile(path):
        raise RuntimeError(f"existing file is not a ZIP: {path}")
    stat = path.stat()
    return {
        "filename": path.name,
        "source_url": url,
        "container_path": str(path),
        "retrieval_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "raw_bytes_size": stat.st_size,
        "raw_bytes_sha256": _sha256(path),
        "byte_status": "FROZEN",
        "reused_existing_snapshot": True,
    }


def download_one(
    url: str,
    dest: Path,
    *,
    user_agent: str,
    refresh: bool = False,
) -> dict[str, object]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not refresh:
        return _freeze_existing(dest, url)
    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists():
        part.unlink()
    digest = hashlib.sha256()
    size = 0
    retrieved_utc = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(_request(url, user_agent=user_agent), timeout=120) as response:
            with part.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        if not zipfile.is_zipfile(part):
            raise RuntimeError(f"download is not a ZIP: {url}")
        os.replace(part, dest)
    except Exception:
        if part.exists():
            part.unlink()
        raise
    return {
        "filename": dest.name,
        "source_url": url,
        "container_path": str(dest),
        "retrieval_utc": retrieved_utc.isoformat(),
        "raw_bytes_size": size,
        "raw_bytes_sha256": digest.hexdigest(),
        "byte_status": "FROZEN",
        "reused_existing_snapshot": False,
    }


def _load_required(path: Path) -> tuple[str, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = data.get("bpop_eight_quarter_archive_basenames") or []
    if not isinstance(required, list) or not required:
        raise RuntimeError("golden-case registry has no required BPOP archive basenames")
    names = tuple(str(item) for item in required)
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate required archive basename")
    return names


def run(
    *,
    required: Iterable[str],
    dest_dir: Path,
    manifest_path: Path,
    user_agent: str,
    refresh: bool = False,
) -> dict[str, object]:
    discovered = discover_archives(user_agent=user_agent)
    required_names = tuple(required)
    missing = sorted(set(required_names) - set(discovered))
    if missing:
        raise RuntimeError(f"required SEC archives not present on authoritative index: {missing}")
    snapshots = [
        download_one(discovered[name], dest_dir / name, user_agent=user_agent, refresh=refresh)
        for name in required_names
    ]
    if len(snapshots) != len(required_names):
        raise AssertionError("archive count conservation failed")
    if any(len(str(item["raw_bytes_sha256"])) != 64 for item in snapshots):
        raise AssertionError("invalid SHA-256 length")
    manifest = {
        "manifest_version": "sec_13f_bulk_freeze_v0_2",
        "authority": "U.S. Securities and Exchange Commission",
        "index_url": SEC_INDEX_URL,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "required_count": len(required_names),
        "frozen_count": len(snapshots),
        "missing_count": 0,
        "snapshots": snapshots,
        "certification_state": "PASS",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-cases", type=Path, default=Path("registries/capital_control_golden_cases.json"))
    parser.add_argument("--dest-dir", type=Path, default=Path("data/raw/sec/form13f"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/capital_control/sec13f_freeze_manifest.json"))
    parser.add_argument("--archive", action="append", default=[], help="Required archive basename")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT", ""),
        help="SEC-compliant User-Agent; or set SEC_USER_AGENT",
    )
    args = parser.parse_args(argv)
    if not args.user_agent.strip():
        parser.error("--user-agent or SEC_USER_AGENT is required for SEC network access")
    required = tuple(args.archive) if args.archive else _load_required(args.golden_cases)
    try:
        report = run(
            required=required,
            dest_dir=args.dest_dir,
            manifest_path=args.manifest,
            user_agent=args.user_agent.strip(),
            refresh=args.refresh,
        )
    except Exception as exc:
        print(f"SEC 13F freeze failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
