#!/usr/bin/env python3
"""Offline Federation operator scaffold.

Generates a repo-local offline package without localhost, external JavaScript,
or live network access. This is an additive operator layer; native pipelines can
replace the scaffold defaults later.
"""
from __future__ import annotations

import argparse, csv, hashlib, html, json, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOCUS = {
    "skywatcher-pr": "Airspace, SATIM, FR24, and platform normalization.",
    "moneysweep-pr": "Contracts, procurement, permits, legislation, and public finance signals.",
    "aguayluz-pr": "Water, electric, and infrastructure dependency records.",
    "centinelas-pr": "Source-neutral watch queries, alert matching, and repo routing.",
    "ovnis-pr": "Puerto Rico anomaly case registry and pattern-convergence records.",
    "spiderweb-pr": "Entity, relationship, dependency, and graph exports.",
}
DIMS = ["repo_structure", "schema_contracts", "source_registry", "data_pipeline", "validation_gates", "evidence_ledger", "operator_report", "offline_dashboard", "hub_compatibility", "production_status", "security_secrets", "documentation", "blocker_tracking", "release_packaging"]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo() -> str:
    return Path.cwd().name


def git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def jwrite(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def jread(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def out(argv: list[str] | None) -> Path:
    p = argparse.ArgumentParser(add_help=False); p.add_argument("--output", default="exports/federation")
    ns, _ = p.parse_known_args(argv); return Path(ns.output)


def make_readiness(name: str, stamp: str) -> dict[str, Any]:
    dims = []
    for d in DIMS:
        c = 50 if d in {"operator_report", "offline_dashboard", "blocker_tracking", "release_packaging"} else 25
        dims.append({"id": d, "label": d.replace("_", " ").title(), "completion_pct": c, "status": "yellow" if c >= 50 else "unknown", "required": True, "blockers": [], "evidence_refs": []})
    overall = round(sum(x["completion_pct"] for x in dims) / len(dims))
    return {"schema_version": "federation.readiness.v1", "repo": name, "generated_at": stamp, "overall_status": "red" if overall < 40 else "yellow", "overall_completion_pct": overall, "dimensions": dims}


def make_blockers(name: str, stamp: str) -> dict[str, Any]:
    return {"schema_version": "federation.blockers.v1", "repo": name, "generated_at": stamp, "blockers": [{"id": "BLOCKER-REPO-INTEGRATION", "severity": "medium", "status": "open", "scope": "export", "title": "Connect offline scaffold to repo-native artifacts", "impact": "Offline contract exists; repo-specific outputs still need to be mapped into readiness and evidence files.", "resolution": "Replace scaffold defaults with native export, validation, and evidence outputs.", "evidence_refs": []}]}


def make_sources(name: str, stamp: str) -> dict[str, Any]:
    cats = ["manual_upload", "derived", "official", "media"]
    return {"schema_version": "federation.sources.v1", "repo": name, "generated_at": stamp, "sources": [{"source_id": f"SOURCE-{i:03d}", "name": c.replace("_", " ").title(), "category": c, "access_method": "manual", "scope": "puerto_rico", "authority_level": "unknown", "cadence": "unknown", "status": "candidate", "notes": "Scaffold placeholder; replace with repo-native source registry entries."} for i, c in enumerate(cats, 1)]}


def refresh_manifest(path: Path, name: str) -> None:
    r = jread(path / "readiness.json", {}); b = jread(path / "blockers.json", {"blockers": []}); s = jread(path / "sources.json", {"sources": []})
    files = [{"path": p.name, "type": p.suffix.lstrip(".") or "file", "sha256": sha(p)} for p in sorted(path.glob("*")) if p.is_file() and not p.name.endswith("_federation_package.zip")]
    m = {"schema_version": "federation.offline_package.v1", "repo": name, "node_type": "producer", "package_id": f"{name}_{now()}", "generated_at": now(), "commit_sha": git(["rev-parse", "HEAD"]), "branch": git(["rev-parse", "--abbrev-ref", "HEAD"]), "data_mode": "diagnostic_seed", "production_status": "diagnostic", "offline_ready": True, "localhost_required": False, "summary": {"records": 0, "sources": len(s.get("sources", [])), "blockers_open": sum(1 for x in b.get("blockers", []) if x.get("status") == "open"), "critical_blockers_open": 0, "evidence_items": 4, "overall_completion_pct": r.get("overall_completion_pct", 0)}, "files": files, "gates": {"tests": "unknown", "schema_validation": "unknown", "export_generated": "pass", "offline_dashboard_generated": "pass" if (path / "dashboard.html").exists() else "fail", "hub_ingest_compatible": "unknown"}}
    jwrite(path / "manifest.json", m)


def export_cmd(argv: list[str] | None = None) -> int:
    path, name, stamp = out(argv), repo(), now(); path.mkdir(parents=True, exist_ok=True); (path / "artifacts").mkdir(exist_ok=True)
    r, b, s = make_readiness(name, stamp), make_blockers(name, stamp), make_sources(name, stamp)
    jwrite(path / "readiness.json", r); jwrite(path / "blockers.json", b); jwrite(path / "sources.json", s)
    with (path / "evidence_ledger.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["evidence_id", "repo", "evidence_tier", "claim", "artifact_path", "artifact_type", "generated_by", "validation_status", "sha256", "notes"]); w.writerow(["EVID-001", name, "T1", "Offline scaffold generated", "manifest.json", "manifest", "scripts/offline_operator.py", "generated", "", stamp])
    (path / "operator_report.md").write_text(f"# {name} Offline Operator Report\n\n{FOCUS.get(name, 'Federation offline package.')}\n\n- Completion: `{r['overall_completion_pct']}%`\n- Localhost required: `false`\n- Production status: `diagnostic`\n\n## Open Blockers\n\n- `BLOCKER-REPO-INTEGRATION`: connect scaffold to repo-native artifacts.\n", encoding="utf-8")
    refresh_manifest(path, name); print(f"exported offline contract to {path}"); return 0


def dashboard_cmd(argv: list[str] | None = None) -> int:
    path, name = out(argv), repo(); r = jread(path / "readiness.json", make_readiness(name, now())); b = jread(path / "blockers.json", make_blockers(name, now())); s = jread(path / "sources.json", make_sources(name, now()))
    dim_rows = "".join(f"<tr><td>{html.escape(x['id'])}</td><td>{html.escape(x['status'])}</td><td>{x['completion_pct']}%</td></tr>" for x in r.get("dimensions", []))
    block_rows = "".join(f"<tr><td>{html.escape(x['id'])}</td><td>{html.escape(x['severity'])}</td><td>{html.escape(x['status'])}</td><td>{html.escape(x['title'])}</td></tr>" for x in b.get("blockers", []))
    src_rows = "".join(f"<tr><td>{html.escape(x['source_id'])}</td><td>{html.escape(x['name'])}</td><td>{html.escape(x['category'])}</td><td>{html.escape(x['status'])}</td></tr>" for x in s.get("sources", []))
    data = json.dumps({"readiness": r, "blockers": b, "sources": s}).replace("</", "<\\/")
    doc = f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(name)} Offline Dashboard</title><style>body{{font-family:system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:.4rem}}th{{background:#f5f5f5}}.card{{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}}</style></head><body><h1>{html.escape(name)} Offline Dashboard</h1><p><strong>localhost_required=false</strong></p><section class='card'><h2>Summary</h2><p>Status: {r.get('overall_status')}</p><p>Completion: {r.get('overall_completion_pct')}%</p><p>Sources: {len(s.get('sources', []))}</p></section><section class='card'><h2>Readiness</h2><table><tr><th>Dimension</th><th>Status</th><th>Completion</th></tr>{dim_rows}</table></section><section class='card'><h2>Blockers</h2><table><tr><th>ID</th><th>Severity</th><th>Status</th><th>Title</th></tr>{block_rows}</table></section><section class='card'><h2>Sources</h2><table><tr><th>ID</th><th>Name</th><th>Category</th><th>Status</th></tr>{src_rows}</table></section><script id='offline-data' type='application/json'>{data}</script></body></html>\n"
    path.mkdir(parents=True, exist_ok=True); (path / "dashboard.html").write_text(doc, encoding="utf-8"); refresh_manifest(path, name); print(f"wrote {path / 'dashboard.html'}"); return 0


def package_cmd(argv: list[str] | None = None) -> int:
    path, name = out(argv), repo(); refresh_manifest(path, name); z = path / f"{name}_federation_package.zip"; z.unlink(missing_ok=True)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(path.rglob("*")):
            if p.is_file() and p != z and p.name != "package.sha256": bundle.write(p, p.relative_to(path.parent))
    (path / "package.sha256").write_text(f"{sha(z)}  {z.name}\n", encoding="utf-8"); refresh_manifest(path, name); print(f"packaged {z}"); return 0


def validate_cmd(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--output", default="exports/federation"); p.add_argument("--allow-unpackaged", action="store_true"); ns = p.parse_args(argv); path = Path(ns.output)
    req = ["manifest.json", "readiness.json", "blockers.json", "sources.json", "evidence_ledger.csv", "operator_report.md", "dashboard.html"] + ([] if ns.allow_unpacked else ["package.sha256"])
    errors = [f"missing {x}" for x in req if not (path / x).exists()]
    m = jread(path / "manifest.json", {}) if (path / "manifest.json").exists() else {}
    if m.get("localhost_required") is not False: errors.append("manifest.localhost_required must be false")
    if m.get("offline_ready") is not True: errors.append("manifest.offline_ready must be true")
    for e in errors: print(f"FAIL: {e}", file=sys.stderr)
    if not errors: print(f"validation passed for {path}")
    return 1 if errors else 0


def run(cmd: str, argv: list[str] | None = None) -> int:
    return {"export": export_cmd, "dashboard": dashboard_cmd, "package": package_cmd, "validate": validate_cmd}[cmd](argv)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["export", "dashboard", "package", "validate"]); ns, rest = parser.parse_known_args(); raise SystemExit(run(ns.command, rest))
