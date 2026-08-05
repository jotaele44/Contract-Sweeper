---
name: moneysweep-pr-unified-live-skillpack
description: "Compiled non-activating dispatch contract for shared and moneysweep-pr capabilities."
version: 1.0.0
compatibility: claude
repository: moneysweep-pr
---

# moneysweep-pr Unified Live Skillpack

Pinned base: `e14b9b8f4eb05b446a2da2072b0e247486b58e1e`.

## Execution contract

- Exact capability identifiers only; unknown identifiers fail closed.
- Runtime activation, automatic dispatch, live polling, notifications, external writes, promotion, control actions, merge, and release are disabled.
- Source module semantics remain cryptographically bound in `MANIFEST.json`; this file is the compiled live dispatcher.
- Repository-specific authority overrides shared defaults.

## Capability dispatch

| Capability | Module | Status | Preserved responsibility |
|---|---|---|---|
| `repo-state-reader` | `repository-governance` | `` |  |
| `repo-identity-guard` | `repository-governance` | `` |  |
| `branch-guard` | `repository-governance` | `` |  |
| `task-scope-guard` | `repository-governance` | `` |  |
| `git-action-guard` | `repository-governance` | `` |  |
| `skill-authoring-template` | `skill-lifecycle` | `` |  |
| `skill-package-builder` | `skill-lifecycle` | `` |  |
| `validation-gate-runner` | `validation-and-recovery` | `` |  |
| `failure-packet-builder` | `validation-and-recovery` | `` |  |
| `delta-reporter` | `reporting-and-receipts` | `` |  |
| `status-writer` | `reporting-and-receipts` | `` |  |
| `foia-correspondence-manager` | `foia-operations` | `` |  |
| `foia-request-sender` | `foia-operations` | `` |  |
| `contract-sweeper-operator` | `orchestration` | `` |  |
| `moneysweep-operator` | `orchestration` | `` |  |
| `contract-sweeper-workflow` | `orchestration` | ``; alias of `contract-sweeper-operator` |  |
| `moneysweep-strict-preflight` | `source-acquisition` | `` |  |
| `moneysweep-source-recovery` | `source-acquisition` | `` |  |
| `moneysweep-source-update-controller` | `source-acquisition` | `` |  |
| `moneysweep-manual-source-intake` | `source-acquisition` | `` |  |
| `moneysweep-entity-resolution` | `entity-and-matter-resolution` | `` |  |
| `moneysweep-public-matter-matcher` | `entity-and-matter-resolution` | `` |  |
| `moneysweep-financial-gap-audit` | `financial-gap-analysis` | `` |  |
| `moneysweep-canonical-export` | `export-and-promotion` | `` |  |
| `moneysweep-production-promotion` | `export-and-promotion` | `` |  |

## Required output fields

Every execution receipt must include `capability_id`, `repository`, `pinned_base_commit`, `inputs`, `outputs`, `validation`, `limitations`, `authority`, and `next_action`.

## Non-activation boundary

This binding does not invoke repository code. A later runtime adapter requires separate design, tests, review, and explicit authorization.
