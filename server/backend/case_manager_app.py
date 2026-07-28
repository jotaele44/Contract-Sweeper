"""Standalone Case Manager Phase 1 FastAPI application.

This app is intentionally separate from the canonical CSV dashboard read service. It has no
route capable of changing canonical evidence.
"""

from fastapi import FastAPI

from .case_manager_api import router

app = FastAPI(
    title="MoneySweep Case Manager API",
    version="0.12.0",
    description=(
        "Command-oriented investigative case service. Canonical evidence is read by identifier "
        "only; generic PATCH and DELETE operations are intentionally absent."
    ),
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "case-manager-phase-1"}
