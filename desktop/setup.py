"""One-time setup for the desktop wrapper (stdlib only).

Creates a private .venv, installs the backend + desktop requirements, and
builds the frontend for same-origin serving (empty VITE_API_BASE). Idempotent:
re-runs are skipped via a marker file unless --force is given.

Usage:
  python desktop/setup.py            run setup (skips when already complete)
  python desktop/setup.py --ensure   quiet fast-path used by the launchers
  python desktop/setup.py --force    redo setup from scratch
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import config  # noqa: E402
from desktop.config import DIST_DIR, FRONTEND_DIR, REPO_ROOT, REQUIREMENT_FILES  # noqa: E402

VENV_DIR = REPO_ROOT / ".venv"
MARKER = Path(__file__).resolve().parent / ".setup-complete"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def is_complete() -> bool:
    return MARKER.exists() and venv_python().exists() and (DIST_DIR / "index.html").exists()


MIN_PYTHON = (3, 10)


def setup_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f"Python 3.10+ required, found {sys.version.split()[0]}")
    if not venv_python().exists():
        print(f"Creating virtual environment at {VENV_DIR} …")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)
    pip = [str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "--quiet"]
    run(pip)
    install = [str(venv_python()), "-m", "pip", "install", "--quiet"]
    for req in REQUIREMENT_FILES:
        install += ["-r", str(req)]
    run(install)
    # Repos whose backend imports the repo's own package list extra pip specs
    # (e.g. an editable install with extras) in desktop/config.py.
    extra = list(getattr(config, "EXTRA_PIP_SPECS", []))
    if extra:
        run([str(venv_python()), "-m", "pip", "install", "--quiet", *extra])


def setup_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "npm not found. Install Node.js (https://nodejs.org) and re-run python desktop/setup.py"
        )
    env = dict(os.environ)
    # Empty base makes the SPA call its API on the same origin it was served
    # from. Process env beats any developer .env.local at Vite build time;
    # repos with differently-named base vars add them via EXTRA_BUILD_ENV.
    env["VITE_API_BASE"] = ""
    env.update(getattr(config, "EXTRA_BUILD_ENV", {}))
    if (FRONTEND_DIR / "package-lock.json").exists():
        run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, env=env)
    else:
        run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, env=env)
    run([npm, "run", "build"], cwd=FRONTEND_DIR, env=env)
    if not (DIST_DIR / "index.html").exists():
        raise SystemExit(f"Frontend build did not produce {DIST_DIR / 'index.html'}")


def main() -> None:
    args = set(sys.argv[1:])
    if "--force" in args:
        MARKER.unlink(missing_ok=True)
    if is_complete():
        if "--ensure" not in args:
            print("Setup already complete (use --force to redo).")
        return
    setup_python()
    setup_frontend()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("Desktop setup complete.")


if __name__ == "__main__":
    main()
