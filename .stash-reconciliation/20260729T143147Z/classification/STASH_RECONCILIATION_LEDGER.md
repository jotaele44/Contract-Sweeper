# Stash Reconciliation Ledger

- Repository: `/Users/jotaele/Developer/moneysweep-pr`
- Captured: `20260729T143147Z`
- Expected baseline HEAD: `5d72f52e0acb1c25b1fd14a2f4cc6d1e4449f402`
- Current HEAD: `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`
- HEAD match: **no**
- Stash entries captured: **1**
- Destructive operations: **none**
- Stashes dropped: **0**
- GitHub writes: **none**

## Classification summary

| Classification | Count |
|---|---:|
| PARTIAL_OR_CONFLICTING_OVERLAP | 1 |

## Per-stash disposition

| Ref | Subject | Files | Classification |
|---|---|---:|---|
| `stash@{0}` | On main: !!GitHub_Desktop<main> | 192 | `PARTIAL_OR_CONFLICTING_OVERLAP` |

## Safety state

- The audit used no `git stash pop`, `git stash drop`, commit, push, merge, reset, rebase, or force operation.
- The bundle and exported stash trees must be retained until every material stash has been adjudicated.
- `CLEAN_APPLY_CANDIDATE` is not an authorization to apply directly to the active branch; use an isolated worktree.

## Next publication gate

Publication remains blocked until each non-materialized stash has been applied in an isolated worktree, tested, and explicitly approved.
