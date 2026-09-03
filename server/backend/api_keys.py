"""FastAPI routes for the pipeline's local API-key store.

Deliberate exception to this backend's read-only-diagnostic framing (see
dashboard/README.md): the pipeline (run_all.py) and this backend are separate
process lifetimes, so a key submitted here can only ever be staged on disk in
the local .env file for the pipeline to pick up on its next manual invocation
— it never starts, feeds, or authorizes a running pipeline. Never returns a
key value; only ever reports set/not-set, per docs/SECRET_HANDLING_POLICY.md.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["api-keys"])
_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$")


def _require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="API-key writes require loopback")
    origin = request.headers.get("origin")
    if origin and not _LOCAL_ORIGIN.fullmatch(origin):
        raise HTTPException(status_code=403, detail="untrusted request origin")


class SetKeyRequest(BaseModel):
    value: str


@router.get("/api-keys")
def list_api_keys(request: Request) -> list[dict]:
    from scripts.manage_api_keys import key_status

    _require_local_request(request)
    return key_status()


@router.post("/api-keys/{name}")
def set_api_key(name: str, body: SetKeyRequest, request: Request) -> dict:
    from scripts.manage_api_keys import (
        InvalidKeyValueError,
        UnknownKeyError,
        key_status,
        set_key,
    )

    _require_local_request(request)
    try:
        set_key(name, body.value)
    except UnknownKeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidKeyValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = next(row for row in key_status() if row["name"] == name)
    return {"name": name, "is_set": updated["is_set"]}
