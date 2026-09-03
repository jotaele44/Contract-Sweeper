"""
Interactive CLI for setting pipeline API keys without hand-editing .env.

Usage:
    python3 scripts/set_api_key.py --list          # show set/missing status
    python3 scripts/set_api_key.py SAM_API_KEY      # prompt (masked) and save

Never accepts a key value as a CLI argument (it would land in shell history);
always prompts via getpass. Never prints a stored value back.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.manage_api_keys import known_keys, key_status, set_key  # noqa: E402


def _print_status() -> int:
    rows = key_status()
    name_width = max(len(row["name"]) for row in rows)
    for row in rows:
        req = "required" if row["required"] else "optional"
        state = "SET" if row["is_set"] else "MISSING"
        print(f"{row['name']:<{name_width}}  {req:<8}  {state:<7}  {row['description']}")
    return 0


def _prompt_and_save(name: str) -> int:
    valid_names = {key.name for key in known_keys()}
    if name not in valid_names:
        print(f"Unknown key: {name!r}", file=sys.stderr)
        print("Known keys:", file=sys.stderr)
        for valid_name in sorted(valid_names):
            print(f"  {valid_name}", file=sys.stderr)
        return 1

    value = getpass.getpass(f"Enter value for {name} (input hidden): ")
    if not value.strip():
        print("Empty value — nothing saved.", file=sys.stderr)
        return 1

    set_key(name, value)
    print(f"Saved — {name} is now set.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="show status (set/missing) for every known key"
    )
    parser.add_argument(
        "name", nargs="?", help="the key to set, e.g. SAM_API_KEY (prompts for the value)"
    )
    args = parser.parse_args(argv)

    if args.list or not args.name:
        return _print_status()
    return _prompt_and_save(args.name)


if __name__ == "__main__":
    sys.exit(main())
