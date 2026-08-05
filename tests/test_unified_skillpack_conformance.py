from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class TestUnifiedSkillpackConformance(unittest.TestCase):
    def test_conformance(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                str(repository_root / "tools" / "validate_unified_skillpacks.py"),
                "--root",
                str(repository_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + "\n" + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
