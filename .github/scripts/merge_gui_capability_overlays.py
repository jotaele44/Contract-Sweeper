#!/usr/bin/env python3
"""Deterministically merge additive GUI-capability manifest overlays.

The canonical manifest remains .federation/gui-capabilities.json. Overlay files may
only add ``capabilities`` and ``exceptions``; they cannot mutate discovery policy,
baseline policy, repository identity, or schema version. This keeps the parity
ratchet intact while allowing narrowly scoped internal pipelines to declare their
candidate bindings without rewriting the large canonical manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_OVERLAY_KEYS = frozenset({"capabilities", "exceptions"})


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing manifest input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _ids(rows: list[Any], *, kind: str, path: Path) -> list[str]:
    result: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RuntimeError(f"{path}: {kind}[{index}] must be an object")
        value = str(row.get("id") or "").strip()
        if not value:
            raise RuntimeError(f"{path}: {kind}[{index}] missing id")
        result.append(value)
    return result


def merge(base_path: Path, overlay_dir: Path) -> dict[str, Any]:
    merged = _load_object(base_path)
    capabilities = list(merged.get("capabilities") or [])
    exceptions = list(merged.get("exceptions") or [])
    if not isinstance(merged.get("capabilities"), list):
        raise RuntimeError(f"{base_path}: capabilities must be a list")
    if not isinstance(merged.get("exceptions", []), list):
        raise RuntimeError(f"{base_path}: exceptions must be a list")

    cap_ids = set(_ids(capabilities, kind="capabilities", path=base_path))
    exc_ids = set(_ids(exceptions, kind="exceptions", path=base_path))

    for path in sorted(overlay_dir.glob("*.json")) if overlay_dir.exists() else []:
        overlay = _load_object(path)
        unexpected = sorted(set(overlay) - ALLOWED_OVERLAY_KEYS)
        if unexpected:
            raise RuntimeError(
                f"{path}: overlays may not override canonical manifest fields: {unexpected}"
            )
        new_caps = overlay.get("capabilities") or []
        new_excs = overlay.get("exceptions") or []
        if not isinstance(new_caps, list) or not isinstance(new_excs, list):
            raise RuntimeError(f"{path}: capabilities/exceptions must be lists")

        new_cap_ids = _ids(new_caps, kind="capabilities", path=path)
        new_exc_ids = _ids(new_excs, kind="exceptions", path=path)
        duplicate_caps = sorted(cap_ids & set(new_cap_ids))
        duplicate_excs = sorted(exc_ids & set(new_exc_ids))
        if len(new_cap_ids) != len(set(new_cap_ids)):
            duplicate_caps.extend(sorted({x for x in new_cap_ids if new_cap_ids.count(x) > 1}))
        if len(new_exc_ids) != len(set(new_exc_ids)):
            duplicate_excs.extend(sorted({x for x in new_exc_ids if new_exc_ids.count(x) > 1}))
        if duplicate_caps or duplicate_excs:
            raise RuntimeError(
                f"{path}: duplicate ids capabilities={sorted(set(duplicate_caps))} "
                f"exceptions={sorted(set(duplicate_excs))}"
            )

        capabilities.extend(new_caps)
        exceptions.extend(new_excs)
        cap_ids.update(new_cap_ids)
        exc_ids.update(new_exc_ids)

    merged["capabilities"] = capabilities
    merged["exceptions"] = exceptions
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=".federation/gui-capabilities.json")
    parser.add_argument("--overlay-dir", default=".federation/gui-capabilities.d")
    parser.add_argument("--output", default="artifacts/gui-capabilities-merged.json")
    args = parser.parse_args()

    base = Path(args.base)
    overlay_dir = Path(args.overlay_dir)
    output = Path(args.output)
    merged = merge(base, overlay_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"merged gui capability manifest: capabilities={len(merged['capabilities'])} "
        f"exceptions={len(merged['exceptions'])} -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
