"""Canonical column list for the PR contractor-reference outputs.

This lives on its own so the modules that share the schema do not have to import
each other. ``download_active_contractors`` delegates its ASG tier to
``scrape_asg_suppliers``, and ``scrape_asg_suppliers`` writes this schema — so
holding the constant in either one makes the pair mutually dependent (CodeQL
flags it, and only a lazy import kept it working). Both now import from here.

``download_active_contractors`` re-exports ``CONTRACTOR_COLUMNS`` for the callers
and tests that already import it from there.
"""

from __future__ import annotations

CONTRACTOR_COLUMNS = [
    "entity_name",
    "entity_normalized",
    "registration_id",
    "registration_date",
    "expiry_date",
    "contractor_type",
    "naics_code",
    "municipality",
    "status",
    "source_file",
]
