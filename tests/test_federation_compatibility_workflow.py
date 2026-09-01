from pathlib import Path


WORKFLOW = Path(".github/workflows/federation-compatibility.yml")


def test_federation_compatibility_workflow_pins_runtime_dependencies() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in text
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in text
    assert 'python-version: "3.12"' in text


def test_federation_compatibility_workflow_binds_push_commit_range() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.before" in text
    assert "github.sha" in text
    assert "missing authoritative event commit range" in text
    assert "base+'..'+head" in text
