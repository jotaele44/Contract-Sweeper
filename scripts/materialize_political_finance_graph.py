#!/usr/bin/env python3
"""Materialize the canonical political-finance graph from available datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from moneysweep.political_finance.flow_graph import build_political_finance_graph, find_flow_paths


DEFAULT_PROCESSED = Path("data/staging/processed")


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, low_memory=False) if path.exists() else pd.DataFrame()


def run(root: Path = Path(".")) -> dict[str, int]:
    processed = root / DEFAULT_PROCESSED
    out = processed / "political_finance"
    out.mkdir(parents=True, exist_ok=True)

    entity_frames = [
        ("resolved", _read(processed / "entities_resolved.csv")),
        ("awards", _read(processed / "pr_contracts_master.csv")),
        ("ngos", _read(processed / "ngos_master.csv")),
        ("lobbying_clients", _read(processed / "lda_clients.csv")),
        ("committees", _read(processed / "pr_fec_committees.csv")),
    ]
    graph = build_political_finance_graph(
        contributions=_read(processed / "pr_fec_contributions.csv"),
        committees=_read(processed / "pr_fec_committees.csv"),
        disbursements=_read(processed / "pr_fec_disbursements.csv"),
        independent_expenditures=_read(processed / "pr_fec_independent_expenditures.csv"),
        oce_donations=_read(processed / "pr_oce_donations.csv"),
        cee_donations=_read(processed / "pr_donaciones.csv"),
        entity_frames=entity_frames,
    )
    filenames = {
        "entities": "political_entities.csv",
        "edges": "political_transactions.csv",
        "resolutions": "political_recipient_resolution.csv",
        "correlations": "political_contract_lobbying_correlations.csv",
    }
    for key, frame in graph.items():
        frame.to_csv(out / filenames[key], index=False, encoding="utf-8")

    paths = []
    donors = graph["entities"].loc[graph["entities"]["entity_type"] == "DONOR", "entity_id"]
    for donor in donors:
        paths.append(find_flow_paths(graph["edges"], donor, max_hops=4))
    flow_paths = pd.concat(paths, ignore_index=True) if paths else pd.DataFrame(
        columns=["origin_entity_id", "terminal_entity_id", "hop_count", "path"]
    )
    flow_paths.to_csv(out / "political_flow_paths.csv", index=False, encoding="utf-8")

    counts = {key: len(frame) for key, frame in graph.items()}
    counts["flow_paths"] = len(flow_paths)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    counts = run(args.root)
    print("Political-finance graph materialized:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
