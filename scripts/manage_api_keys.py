"""
Read/write access to pipeline API keys, shared by scripts/set_api_key.py (CLI)
and server/backend/api_keys.py (dashboard endpoint).

.env.example is the source of truth for *which* keys exist (parsed at call
time, so the registry can't drift out of sync with the documented list); .env
is the source of truth for their *values*. Callers never see a stored value
back from this module except set_key()'s own caller, who already has it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.config import PROJECT_ROOT, _load_dotenv

ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

# .env.example's own placeholder sentinel (see its header comment). A fresh
# .env seeded from .env.example, or one a contributor created by literally
# following SETUP.md's `cp .env.example .env`, carries this value verbatim —
# it must never count as "set".
PLACEHOLDER_VALUE = "paste_your_key_here"


@dataclass(frozen=True)
class KeyInfo:
    name: str
    description: str
    required: bool


def known_keys(example_path: Path | None = None) -> list[KeyInfo]:
    """Parse .env.example into the registry of known credential vars.

    Each KEY=value line's required-ness comes from the first word of its
    preceding comment block ("Required..." vs "Recommended"/"Optional...");
    its description is that block's last comment line.
    """
    # Resolved here (not as a `= ENV_EXAMPLE_PATH` default) so that patching
    # the module-level path after import — e.g. tests monkeypatching
    # ENV_EXAMPLE_PATH — is actually honored. A literal default is bound once
    # at def time and would silently ignore any later reassignment.
    if example_path is None:
        example_path = ENV_EXAMPLE_PATH
    if not example_path.exists():
        return []

    keys: list[KeyInfo] = []
    comment_block: list[str] = []
    for raw in example_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            # A blank line ends a comment block. Consecutive KEY=value lines
            # with no blank line between them (e.g. FINANCIALDATA_API_KEY /
            # FINANCIALDATA_LICENSE_APPROVED) intentionally share one block.
            comment_block = []
            continue
        if line.startswith("#"):
            comment_block.append(line.lstrip("#").strip())
            continue
        if "=" in line:
            name = line.split("=", 1)[0].strip()
            description = comment_block[-1] if comment_block else ""
            # Scan the whole block (not just its first line) for the nearest
            # Required/Optional/Recommended marker: unrelated file-header
            # comments can precede the first key's block with no blank-line
            # separator (a bare "#" line doesn't count as blank), so the
            # marker isn't always line 0.
            required = False
            for comment_line in comment_block:
                lowered = comment_line.lower()
                if lowered.startswith("required"):
                    required = True
                elif lowered.startswith(("optional", "recommended")):
                    required = False
            keys.append(KeyInfo(name=name, description=description, required=required))
    return keys


def key_status(env_path: Path | None = None, example_path: Path | None = None) -> list[dict]:
    """Presence-only status for every known key. Never returns a value."""
    if env_path is None:
        env_path = ENV_PATH
    values = _load_dotenv(env_path)
    return [
        {
            "name": key.name,
            "description": key.description,
            "required": key.required,
            "is_set": _is_real_value(values.get(key.name, "")),
        }
        for key in known_keys(example_path)
    ]


def _is_real_value(value: str) -> bool:
    value = value.strip()
    return bool(value) and value != PLACEHOLDER_VALUE


def set_key(
    name: str,
    value: str,
    env_path: Path | None = None,
    example_path: Path | None = None,
) -> None:
    """Write/update `name` in .env, preserving all other content.

    Raises ValueError for any name not in the known registry, so this can
    never be used to write an arbitrary env var.
    """
    if env_path is None:
        env_path = ENV_PATH
    if example_path is None:
        example_path = ENV_EXAMPLE_PATH
    valid_names = {key.name for key in known_keys(example_path)}
    if name not in valid_names:
        raise ValueError(f"unknown key: {name!r}")

    value = value.strip()
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    elif example_path.exists():
        lines = example_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    replaced = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith(f"{name}=") or line == name:
            lines[i] = f"{name}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{name}={value}")

    tmp_path = env_path.with_suffix(env_path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(env_path)
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
