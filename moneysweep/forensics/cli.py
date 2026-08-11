from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import ForensicsLedger


def _ledger(root: Path) -> ForensicsLedger:
    ledger = ForensicsLedger(
        root / "data" / "forensics" / "contract_forensics.duckdb", root / "migrations" / "forensics"
    )
    ledger.migrate()
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(prog="contract-forensics")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    e = sub.add_parser("export")
    e.add_argument("--output")
    c = sub.add_parser("coverage")
    c.add_argument("entity_id")
    p = sub.add_parser("proposals")
    p.add_argument("--status")
    args = parser.parse_args()
    root = Path(args.root)
    with _ledger(root) as ledger:
        if args.command == "init":
            print(
                json.dumps(
                    {
                        "database": str(ledger.db_path),
                        "migrations": ledger.table_count("schema_migrations"),
                    }
                )
            )
        elif args.command == "status":
            print(
                json.dumps(
                    {
                        r[0]: ledger.table_count(r[0])
                        for r in ledger.conn.execute("SHOW TABLES").fetchall()
                    },
                    indent=2,
                )
            )
        elif args.command == "export":
            print(
                json.dumps(
                    {
                        "exported": [
                            str(x)
                            for x in ledger.export_parquet(
                                Path(args.output)
                                if args.output
                                else root / "data" / "forensics" / "parquet"
                            )
                        ]
                    },
                    indent=2,
                )
            )
        elif args.command == "coverage":
            print(
                ledger.conn.execute(
                    "SELECT * FROM coverage_state WHERE entity_id=? ORDER BY domain",
                    [args.entity_id],
                )
                .fetchdf()
                .to_json(orient="records", indent=2)
            )
        elif args.command == "proposals":
            q = "SELECT * FROM skill_improvement_proposals"
            params = []
            if args.status:
                q += " WHERE status=?"
                params = [args.status]
            q += " ORDER BY created_at"
            print(ledger.conn.execute(q, params).fetchdf().to_json(orient="records", indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
