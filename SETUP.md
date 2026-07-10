# Setup Guide — moneysweep-pr

**Tested on:** Python 3.10+ · Ubuntu/Debian · macOS  
**Estimated setup time:** 5 minutes (no data download required for tests)

> Baseline is **Python 3.10** (ruff/mypy target `py310`; the lockfile is compiled
> for 3.10; CI tests 3.10–3.12). Use **Python 3.11** locally (see `.python-version`)
> for the recommended dev interpreter — newer interpreters (3.14+) can produce
> false test failures in R4.8 backfill tests due to dict-ordering changes.

---

## 1. Clone

```bash
git clone https://github.com/jotaele44/moneysweep-pr.git
cd moneysweep-pr
```

No special credentials are needed to clone — the repository is public.

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` carries the loose minimums below (it is kept identical to
`requirements.in`). For a **reproducible, fully-pinned** environment matching CI,
install from the compiled lockfile instead:

```bash
pip install -r requirements.lock     # exact pins, regenerated via `make lock`
```

To add the lint/type/test tooling (ruff, mypy, pytest-cov, pre-commit) that the
quality gates need, use the dev set — or the Makefile, which wraps the same
commands CI runs (`make install-dev`, then `make check`):

```bash
pip install -r requirements-dev.txt  # or: make install-dev
```

Core runtime dependencies (all available via pip, no compiled extensions required):

| Package | Version | Purpose |
|---------|---------|---------|
| pandas | ≥2.0.0 | DataFrame processing |
| requests | ≥2.34.2 | HTTP downloads |
| lxml | ≥6.1.1 | XML/HTML parsing |
| pytest | ≥9.1.1 | Test runner |
| pytest-cov | ≥7.1.0 | Coverage instrumentation |
| rapidfuzz | ≥3.14.5 | Fuzzy entity matching |
| python-dotenv | ≥1.2.2 | `.env` loading |
| pyarrow | ≥24.0.0 | Parquet I/O |
| PyYAML | ≥6.0.3 | Registry files |
| networkx | ≥3.6.1 (py≥3.11) | Graph analysis |
| pdfplumber | ≥0.11.10 | ACT/ACUDEN PDF extraction |
| openpyxl | ≥3.1.0 | SBA disaster-loan workbook importer |
| prii-maintenance | git (pinned SHA) | Shared federation maintenance core (from `thehub-pr`) |

---

## 3. Configure API Keys (Optional for Tests)

```bash
cp .env.example .env
# Edit .env and fill in your keys
```

Tests do **not** require real API keys. Keys are only needed to run live data downloads.  
See `.env.example` for which keys are required vs. optional.  
See `docs/SECRET_HANDLING_POLICY.md` for key storage rules.

---

## 4. Run Tests

```bash
python3 -m pytest tests/ -q
```

The full suite runs fully offline with no API keys required. A small number of
tests are skipped on a clean clone (they need live network access or large data
files). The last recorded full baseline is in `README.md` (**2018 passed,
6 skipped, 0 failed**) — treat that as the single source of truth rather than
re-copying a count here.

---

## 5. Directory Structure for Data (Optional)

The `data/` directory is gitignored but its structure is tracked via `.gitkeep` files. To initialize:

```bash
python3 scripts/setup_directories.py
```

This creates all required subdirectories without downloading any data.

---

## 6. Verify Configuration

```bash
python3 -c "from scripts.config import *; print('Config OK')"
```

---

## 7. Manual-Source Drops (Operator-Gated Sources)

Five required sources are operator-supplied (portals are JS-gated, credentialed,
or export-only). See `docs/MANUAL_SOURCE_OPERATIONS.md` for what to export, the
drop directories, update cadence, and the `source_freshness` staleness gate.

## 8. Run the Full Pipeline (Requires Source Data)

The production pipeline is currently **paused** pending delivery of 21 missing source files.  
See `STATUS.md` and `reports/gap_analysis_report.csv` before running.

```bash
# Do NOT run this until sources are delivered and unfreeze conditions are met:
python3 run_all.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'scripts'` | Run from the repo root, not a subdirectory |
| `ImportError: No module named 'pandas'` | Run `pip install -r requirements.txt` |
| Tests fail with `FileNotFoundError` | Run `python3 scripts/setup_directories.py` first |
| API key errors during downloads | Copy `.env.example` to `.env` and fill in keys |

---

## Key Entry Points

| Script | Purpose |
|--------|---------|
| `run_all.py` | Full pipeline orchestrator |
| `scripts/config.py` | Central configuration (read first) |
| `scripts/build_unified_master.py` | Core ETL — builds the awards master |
| `scripts/auto_download.py` | Automated bulk downloader |
| `scripts/generate_report.py` | Report generation |
| `scripts/run_production_status_gate.py` | Check current production readiness |
