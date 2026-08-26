"""FastAPI routes for the pipeline's local API-key store.

Deliberate exception to this backend's read-only-diagnostic framing (see
dashboard/README.md): the pipeline (run_all.py) and this backend are separate
process lifetimes, so a key submitted here can only ever be staged on disk in
the local .env file for the pipeline to pick up on its next manual invocation
— it never starts, feeds, or authorizes a running pipeline. Never returns a
key value; only ever reports set/not-set, per docs/SECRET_HANDLING_POLICY.md.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class SetKeyRequest(BaseModel):
    value: str


@router.get("")
def list_api_keys() -> list[dict]:
    from scripts.manage_api_keys import key_status

    return key_status()


@router.post("/{name}")
def set_api_key(name: str, body: SetKeyRequest) -> dict:
    from scripts.manage_api_keys import key_status, set_key

    try:
        set_key(name, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    updated = next(row for row in key_status() if row["name"] == name)
    return {"name": name, "is_set": updated["is_set"]}
