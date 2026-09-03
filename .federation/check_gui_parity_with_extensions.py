#!/usr/bin/env python3
"""Run GUI parity against the base manifest plus reviewed extension fragments.

Extension fragments may only append capability/exception objects. Discovery and
validation semantics remain owned by scripts/check_gui_parity.py; this wrapper
does not suppress candidates or modify the committed debt baseline.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
check_gui_parity = importlib.import_module("scripts.check_gui_parity")

BASE = ROOT / ".federation" / "gui-capabilities.json"
EXTENSIONS = ROOT / ".federation" / "gui-capabilities.extensions"
MERGED = ROOT / "artifacts" / "gui-capabilities-merged.json"


def merge_manifest() -> Path:
    manifest = json.loads(BASE.read_text(encoding="utf-8"))
    capabilities = list(manifest.get("capabilities", []))
    exceptions = list(manifest.get("exceptions", []))
    for path in sorted(EXTENSIONS.glob("*.json")) if EXTENSIONS.exists() else []:
        fragment = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(fragment, dict):
            raise ValueError(f"{path}: extension must be a JSON object")
        extra_capabilities = fragment.get("capabilities", [])
        extra_exceptions = fragment.get("exceptions", [])
        if not isinstance(extra_capabilities, list) or not isinstance(extra_exceptions, list):
            raise ValueError(f"{path}: capabilities/exceptions must be lists")
        capabilities.extend(extra_capabilities)
        exceptions.extend(extra_exceptions)
    manifest["capabilities"] = capabilities
    manifest["exceptions"] = exceptions
    MERGED.parent.mkdir(parents=True, exist_ok=True)
    MERGED.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return MERGED


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--manifest" not in args:
        merged = merge_manifest().relative_to(ROOT).as_posix()
        args = ["--manifest", merged, *args]
    return check_gui_parity.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
