from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = (
    ROOT / "PRII-MONEYSWEEP.sh",
    ROOT / "PRII-MONEYSWEEP.command",
    ROOT / "PRII-MONEYSWEEP.app" / "Contents" / "MacOS" / "PRII-MONEYSWEEP",
)


def test_launchers_remove_success_logs_before_exec() -> None:
    for launcher in LAUNCHERS:
        source = launcher.read_text(encoding="utf-8")
        setup = source.index("desktop/setup.py --ensure")
        retained_failure_log = max(source.find("Full log: $LOG"), source.find("Details: $LOG"))
        cleanup = source.index('rm -f "$LOG"')
        launch = source.index("exec .venv/bin/python desktop/launch.py")

        assert setup < retained_failure_log < cleanup < launch, launcher
