"""Repo-specific maintenance adapter for moneysweep-pr.

The generic maintenance core (models/state/detect/corrections/quarantine/report/
runner) now lives in the shared `prii_maintenance` package
(thehub-pr/packages/prii_maintenance, pinned in requirements.txt). Only
`adapters/local.py` — the moneysweep-specific checks — stays vendored here; it is
passed into `prii_maintenance.run_maintenance(..., local_checks=local.run_checks)`.
Run via ``python3 scripts/run_maintenance.py --repo moneysweep-pr --mode audit``.
"""
