#!/usr/bin/env python3
"""Materialize the canonical political-finance graph from available datasets."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from moneysweep.political_finance.flow_graph import build_political_finance_graph, find_flow_paths
from moneysweep.political_finance.completion import (
    build_affiliation_edges,
    build_transfer_edges,
    correlate_temporal_activity,
    materialization_accounting,
)

DEFAULT_PROCESSED = Path("data/staging/processed")


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, low_memory=False) if path.exists() else pd.DataFrame()


def run(root: Path = Path(".")) -> dict[str, int]:
    processed = root / DEFAULT_PROCESSED
    out = processed / "political_finance"
    out.mkdir(parents=True, exist_ok=True)

    inputs = {
        "contributions": _read(processed / "pr_fec_contributions.csv"),
        "committees": _read(processed / "pr_fec_committees.csv"),
        "candidates": _read(processed / "pr_fec_candidates.csv"),
        "disbursements": _read(processed / "pr_fec_disbursements.csv"),
        "independent_expenditures": _read(processed / "pr_fec_independent_expenditures.csv"),
        "oce_donations": _read(processed / "pr_oce_donations.csv"),
        "cee_donations": _read(processed / "pr_donaciones.csv"),
        "awards": _read(processed / "pr_contracts_master.csv"),
        "lobbying": _read(processed / "lda_clients.csv"),
    }
    entity_frames = [
        ("resolved", _read(processed / "entities_resolved.csv")),
        ("awards", inputs["awards"]),
        ("ngos", _read(processed / "ngos_master.csv")),
        ("lobbying_clients", inputs["lobbying"]),
        ("committees", inputs["committees"]),
    ]
    graph = build_political_finance_graph(
        contributions=inputs["contributions"], committees=inputs["committees"],
        disbursements=inputs["disbursements"], independent_expenditures=inputs["independent_expenditures"],
        oce_donations=inputs["oce_donations"], cee_donations=inputs["cee_donations"], entity_frames=entity_frames,
    )
    affiliation_edges = build_affiliation_edges(inputs["candidates"], inputs["committees"])
    committee_ids = inputs["committees"].get("committee_id", pd.Series(dtype=str)).dropna().astype(str)
    transfer_edges = build_transfer_edges(inputs["disbursements"], committee_ids)
    graph["edges"] = pd.concat([graph["edges"], affiliation_edges, transfer_edges], ignore_index=True).drop_duplicates("edge_id")

    temporal = correlate_temporal_activity(graph["edges"], graph["entities"], inputs["awards"], inputs["lobbying"])
    graph["correlations"] = pd.concat([graph["correlations"], temporal], ignore_index=True).drop_duplicates()

    filenames = {"entities": "political_entities.csv", "edges": "political_transactions.csv", "resolutions": "political_recipient_resolution.csv", "correlations": "political_contract_lobbying_correlations.csv"}
    for key, filename in filenames.items():
        graph[key].to_csv(out / filename, index=False, encoding="utf-8")

    paths = []
    donors = graph["entities"].loc[graph["entities"]["entity_type"] == "DONOR", "entity_id"]
    for donor in donors:
        paths.append(find_flow_paths(graph["edges"], donor, max_hops=4))
    flow_paths = pd.concat(paths, ignore_index=True) if paths else pd.DataFrame(columns=["origin_entity_id", "terminal_entity_id", "hop_count", "path"])
    flow_paths.to_csv(out / "political_flow_paths.csv", index=False, encoding="utf-8")

    outputs = {**graph, "flow_paths": flow_paths}
    accounting = materialization_accounting(inputs, outputs)
    accounting.to_csv(out / "political_materialization_accounting.csv", index=False, encoding="utf-8")
    counts = {key: len(frame) for key, frame in outputs.items()}
    counts["accounting"] = len(accounting)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print("Political-finance graph materialized:", run(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
