"""Registry-driven source update controller.

A per-source update layer that sits *beside* ``run_all.py`` (the full producer
orchestrator) — it does not replace it. The controller decides whether a source
is due, isolates per-source failure, detects operator file-drops by hash,
sequences derived sources after their upstreams, validates output atomically
before overwriting, and reports freshness and structured failure packets.

Public entrypoint: ``moneysweep.update_controller.cli.main`` (wrapped by
``scripts/update_sources.py``).
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
