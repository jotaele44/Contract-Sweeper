# Source Update Controller

A registry-driven, per-source update layer available directly and through
`run_all.py --profile incremental`. It
decides *whether a source is due*, isolates per-source failure, detects operator
file-drops by hash, sequences derived sources after their upstreams, validates
output atomically before overwriting, and reports freshness and structured
failure packets.

CLI: `python3 scripts/update_sources.py <command>` (thin wrapper over
`moneysweep.update_controller.cli`).

## Purpose and non-goals

**Purpose** — provide idempotent, per-source scheduling and update control:
triggers, a dependency DAG, freshness SLAs, atomic output validation, and
structured failure reporting, driven entirely by the canonical source registry
plus a thin policy overlay.

**Non-goals** — this controller does **not** replace the full `run_all.py` profile,
which remains the full producer orchestrator with its own strict-preflight stage.
The controller powers the optional incremental profile. It does not itself perform data normalization, entity resolution, or
canonical export — it only decides *when* and *whether* to run a source's
producer and whether the result is acceptable.

## Source-of-truth hierarchy

The effective policy for each canonical source is resolved by precedence:

1. explicit override in `registries/source_update_policy.yaml`
2. `registries/manual_export_registry` entry (operator-gated fallback)
3. canonical `registries/source_registry.json` `authentication` / `manual_drop_dir`
4. readiness `path_type` inference (`scripts/build_source_recovery_matrix.py`).

The overlay is **keyed by `source_id`** and merged against the registry — source
metadata is never hand-copied. There is exactly one effective policy per
canonical source (144/144), and no orphan overrides.

The authoritative count + `source_ids_sha256` are always computed from the live
registry (`reports/materialization_readiness.json` is the authoritative computed
count). Historical narrative counts elsewhere are non-authoritative snapshots.

## Trigger taxonomy

| trigger | due when |
| --- | --- |
| `schedule` | `now >= next_due_at` (first run: never scheduled ⇒ due) |
| `file_drop` | a matching file has a SHA-256 not in the ingestion manifest |
| `dependency` | every parent succeeded **and** ≥1 parent output hash differs from the child's last consumed dependency version |
| `on_drop` | a new producer-to-producer intake artifact is present |
| `manual` | only with explicit `--source` / `--trigger manual` |
| `disabled` | never executable |

## Cadence mapping

Scheduled sources map cadence → default freshness SLA and → the cron of the
matching GitHub Actions workflow. Explicit policy overrides take precedence.

| cadence | default SLA (hours) | scheduled workflow (UTC cron) |
| --- | --- | --- |
| weekly | 192 | `source-update-weekly` — `17 10 * * 1` |
| monthly | 840 | `source-update-monthly` — `23 10 1 * *` |
| quarterly | 2400 | `source-update-quarterly` — `31 10 1 1,4,7,10 *` |
| yearly | 9000 | `source-update-yearly` — `41 10 15 1 *` |
| ad hoc | (no time-based SLA) | — (trigger `manual`) |
| on drop | 168 (after unconsumed-file arrival) | `source-update-drop-scan` (daily audit) |

GitHub schedules are UTC. Puerto Rico is UTC-4 year-round (no DST); the crons
above land ~06:1x–06:4x AST.

## Policy overlay rules

Sources without an explicit override are inferred from their readiness path_type
and cadence:

| registry condition | inferred policy |
| --- | --- |
| `api_adapter` / `api_producer` | `schedule` from `update_cadence` |
| `manual_export` | `file_drop` |
| declared upstream dependency | `dependency` |
| cadence `on_drop` | `on_drop` |
| cadence `ad_hoc` | `manual` |
| `scraper_needed` / `deferred_stub` / `semantic_duplicate` | `disabled` |
| `broken_producer` | invalid → policy/gate failure |

`trigger_type` may also appear as an inferred column in the recovery matrix, but
the `source_update_policy` overlay is authoritative at controller runtime.

## Manual drop workflow

`file_drop` sources are operator-supplied — no credentialed scraping. Drop a
file into the source's declared `watch_paths` (e.g. `data/raw/Cabilderos/` for
`pr_cabilderos`). Then:

```bash
python3 scripts/update_sources.py scan-drops     # report candidate files + hashes (read-only)
python3 scripts/update_sources.py ingest-drops   # ingest only new/unconsumed hashes
```

A file's SHA-256 is recorded as *consumed* only after a successful ingestion, so
a failed ingestion leaves the file eligible on the next run. The scanner never
moves or deletes source files and rejects symlinks that escape the repo root.

## Dependency execution

The dependency DAG is authoritative (spec §7) and cleans up the messier registry
`depends_on` (which carries non-source edges). A `dependency` source is due only
when **every** parent has succeeded and at least one parent's output changed
since the child last consumed it. Execution is topologically ordered (ties broken
by `source_id`). After a `SUCCESS_WITH_CHANGE`, newly-due dependents are
triggered (unless `--no-dependents`).

Soft analytical links (`fec` → FEC cross-reference, `lda` → lobbying enrichment,
`donaciones_pr`, `contralor_electoral`) are **downstream consumers**, not
blocking DAG parents — they never gate source ingestion.

The DAG gate rejects: unknown source IDs, self-dependencies, cycles, dependency
on a disabled source (unless the child is also disabled), dependency on a
semantic-duplicate/terminal source, and edges absent from the policy/inferred set.

## Credential behavior

API-key absence is a **non-fatal, source-level `MISSING_SECRET`** status, never a
structural failure. Secrets are evaluated **by name only** — values are never
read into reports, logs, failure packets, argument arrays, or URLs. CI passes
only the known secret names (see the workflow files).

## Long-running / checkpointed sources

Sources that need a durable context (`ocpr_contracts`, `sam_entities`
full-registry mode) set `execution_backend: self_hosted` and are **excluded from
the GitHub-hosted cron schedules**. Run them via `source-update-dispatch` (which
can target a self-hosted runner) or locally. They may declare a
`checkpoint_strategy` (`page_cursor`, `entity_queue`) and `max_pages_per_run`; a
`CHECKPOINTED` status is a successful-but-incomplete outcome that keeps
`next_due_at` immediately (or within an hour) eligible. Resume with:

```bash
python3 scripts/update_sources.py resume --source ocpr_contracts
```

## Freshness semantics

`freshness` computes per-source status against the SLA and writes
`reports/source_freshness.csv`. Statuses: `FRESH`, `DUE`, `STALE`,
`NEVER_MATERIALIZED`, `BLOCKED_MISSING_SECRET`, `BLOCKED_MANUAL_INPUT`,
`DISABLED`, `TERMINAL`, `UNKNOWN`. Key rules: semantic duplicates are `TERMINAL`
(never stale); deferred/scraper stubs are `DISABLED`; a required manual-export
source with no file is `BLOCKED_MANUAL_INPUT` and only escalates to exit 2 after
its SLA/grace expires; a success with unchanged output refreshes
`last_success_at` but not `last_output_change_at`; `last_materialized_at` moves
only when validated output exists; existing output stays authoritative after a
failed refresh.

Exit codes: `0` all enabled required sources fresh · `1` optional stale /
warnings present · `2` a required source is stale/blocked past its SLA.

## Output atomicity

Producers write their outputs; the controller snapshots each declared output
before and after (size, SHA-256, row count, mtime) and applies the post-run gates
(exists, `min_rows` from the registry `validation_threshold`, non-header-only,
row-regression tolerance, empty-result policy, JSON/JSONL parse, within repo
root). Materialization state is committed **only after** the gates pass. A failed
run never deletes or truncates prior valid output. `atomic_output_required`
additionally verifies no partial `.tmp` shadow file remains. State itself is
written atomically (temp file + `os.replace`).

## Failure packets

Every failed/blocked attempt appends a structured packet to
`reports/source_update_failures.local.jsonl`:

```json
{"command": [...], "exit_code": 1, "last_40_lines": [...],
 "files_recently_changed": [...], "suspected_area": "producer_execution",
 "source_id": "...", "run_id": "uuid", "status": "PRODUCER_EXECUTION_FAILED",
 "retryable": false}
```

`suspected_area` is drawn from a fixed vocabulary (policy, registry, preflight,
missing_secret, dependency, dropzone, producer_import, producer_execution,
timeout, rate_limit, network, output_missing, output_regression, schema,
freshness, checkpoint, state_write, unknown). Packets never include secret
values, auth headers, or secret-bearing URLs.

## GitHub Actions limitations

A GitHub-hosted runner only sees files committed to the repo or mounted into the
checkout — it **cannot** observe an operator's uncommitted local filesystem, so
`source-update-drop-scan` is a committed-drop audit, not a live local-dropzone
watcher. CI uploads reports/state/outputs as **artifacts** and never commits
generated data or state. Scheduled cadence workflows run only github-hosted,
non-long-running, automatable sources; long-running/self-hosted sources are
excluded and run via dispatch.

## Local / self-hosted operating procedure

```bash
python3 scripts/update_sources.py validate-policy      # policy + DAG gates
python3 scripts/update_sources.py plan --due           # what is due (read-only)
python3 scripts/update_sources.py run --due --workers 4 # run due sources in dependency-safe lanes
python3 run_all.py --profile incremental --workers 4   # same controller via the main entry point
python3 scripts/update_sources.py run --source ocpr_contracts   # a self-hosted long-running source
python3 scripts/update_sources.py freshness            # SLA report
```

Runtime ledgers are written to the gitignored `*.local.jsonl` variants; the
committed `reports/source_update_runs.jsonl` / `..._failures.jsonl` are empty
templates. State is committed only if an operator chooses to; CI never does.

## State-file recovery

State lives in `reports/source_update_state.json` (atomic writes). If it is
lost or corrupt, `load`/`state` reinitializes every canonical source to
`NEVER_RUN` from the live registry — no run history is required for correctness
(freshness simply reports `NEVER_MATERIALIZED` until the next successful run).
Sources present in an old state file but no longer canonical are preserved as
`retired` rather than dropped (explicit-migration rule). A change in the
registry's `source_ids_sha256` is detected and surfaced.

## Adding a new source

1. Add the source to `registries/source_registry.yaml` and regenerate the JSON
   (`python scripts/regenerate_registry_json.py`).
2. If the inferred policy is wrong for it, add an override block to
   `registries/source_update_policy.yaml` (schema:
   `schemas/source_update_policy.schema.json`).
3. Run `python3 scripts/update_sources.py validate-policy` — coverage must stay
   at N/N with no orphans and no DAG cycles.
4. Regenerate `reports/materialization_readiness.json`
   (`python3 scripts/build_source_recovery_matrix.py`) and confirm the pinned
   readiness tests still pass.

## Promoting scraper-needed sources

A `scraper_needed` stub (`hacienda_sut_ivu`, `pr_act_154_excise`) is `disabled`
and retains a coverage-gap flag. To promote it: implement a real producer with an
importable entrypoint, let the readiness classifier reclassify it as
`api_producer`, then either let inference schedule it or add an explicit schedule
override. Terminal semantic duplicates (`fpds_report_builder`, `fsrs_subawards`,
`congressional_earmarks`) and deferred NARA stubs stay permanently disabled under
the current readiness invariant.

## Source-count reconciliation

The source count and `source_ids_sha256` are always computed from the live
registry (`build_registry_snapshot`). `reports/materialization_readiness.json`
carries a `source_count_provenance` block; `pipeline_preflight` labels its count
`count_semantics: current live registry at preflight run time`; and
`reports/current_status.json` carries a `source_registry_current` block whose
`total_sources` must equal the live computed count
(`test_no_handmaintained_current_source_count`). Historical counts embedded in
completed narrative entries are snapshots and are explicitly non-authoritative.
