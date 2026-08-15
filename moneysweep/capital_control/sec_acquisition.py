from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import urlparse

import requests


_ALLOWED_SEC_HOSTS = frozenset({"sec.gov", "www.sec.gov", "data.sec.gov"})
_RETRYABLE_STATUS_CODES = frozenset({403, 429, 500, 502, 503, 504})


class SECAcquisitionError(RuntimeError):
    """Fail-closed acquisition error for authoritative SEC resources."""


@dataclass(frozen=True)
class SECUserAgent:
    application: str
    contact: str

    def header_value(self) -> str:
        application = self.application.strip()
        contact = self.contact.strip()
        if not application or not contact:
            raise SECAcquisitionError("SEC user agent requires application and contact")
        if any(char in application + contact for char in "\r\n"):
            raise SECAcquisitionError("SEC user agent cannot contain line breaks")
        return f"{application} {contact}"


@dataclass(frozen=True)
class SECRequestPolicy:
    max_requests_per_second: float = 5.0
    timeout_seconds: float = 30.0
    max_attempts: int = 4
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    allowed_content_types: tuple[str, ...] = (
        "text/xml",
        "application/xml",
        "text/plain",
        "application/json",
        "application/octet-stream",
    )

    def validate(self) -> None:
        if not 0 < self.max_requests_per_second <= 10:
            raise SECAcquisitionError(
                "max_requests_per_second must be > 0 and <= SEC fair-access limit"
            )
        if self.timeout_seconds <= 0:
            raise SECAcquisitionError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise SECAcquisitionError("max_attempts must be >= 1")
        if self.base_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise SECAcquisitionError("backoff values must be nonnegative")
        if self.base_backoff_seconds > self.max_backoff_seconds:
            raise SECAcquisitionError("base_backoff_seconds exceeds max_backoff_seconds")
        if not self.allowed_content_types:
            raise SECAcquisitionError("allowed_content_types cannot be empty")


class SECTransportResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    url: str


class SECTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> SECTransportResponse: ...


class RequestsSECTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> requests.Response:
        return self._session.get(url, headers=dict(headers), timeout=timeout)


@dataclass(frozen=True)
class SECFetchReceipt:
    request_url: str
    response_url: str
    status_code: int
    retrieval_utc: datetime
    attempts: int
    content_type: str | None
    content_length_header: str | None
    etag: str | None
    last_modified: str | None
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class SECFrozenResource:
    receipt: SECFetchReceipt
    path: Path
    write_status: str


class SECFairAccessClient:
    """Rate-limited, provenance-preserving SEC fetcher with fail-closed freezing."""

    def __init__(
        self,
        user_agent: SECUserAgent,
        *,
        policy: SECRequestPolicy | None = None,
        transport: SECTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.policy = policy or SECRequestPolicy()
        self.policy.validate()
        self.user_agent.header_value()
        self._transport = transport or RequestsSECTransport()
        self._sleep = sleeper
        self._monotonic = monotonic
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self._last_request_monotonic: float | None = None

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise SECAcquisitionError("SEC acquisition requires HTTPS")
        hostname = (parsed.hostname or "").lower()
        if hostname not in _ALLOWED_SEC_HOSTS:
            raise SECAcquisitionError(f"non-SEC host rejected: {hostname or '<empty>'}")
        if not parsed.path:
            raise SECAcquisitionError("SEC URL must include a path")

    def _rate_limit(self) -> None:
        interval = 1.0 / self.policy.max_requests_per_second
        now = self._monotonic()
        if self._last_request_monotonic is not None:
            remaining = interval - (now - self._last_request_monotonic)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_monotonic = now

    @staticmethod
    def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
        if not value:
            return None
        stripped = value.strip()
        try:
            return max(0.0, float(stripped))
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(stripped)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at.astimezone(timezone.utc) - now).total_seconds())

    def _backoff_seconds(
        self,
        attempt: int,
        headers: Mapping[str, str],
        now: datetime,
    ) -> float:
        retry_after = self._retry_after_seconds(headers.get("Retry-After"), now)
        if retry_after is not None:
            return min(retry_after, self.policy.max_backoff_seconds)
        exponential = self.policy.base_backoff_seconds * (2 ** max(0, attempt - 1))
        return min(exponential, self.policy.max_backoff_seconds)

    def fetch_bytes(
        self,
        url: str,
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> tuple[bytes, SECFetchReceipt]:
        self._validate_url(url)
        if expected_size is not None and expected_size < 0:
            raise SECAcquisitionError("expected_size must be nonnegative")
        if expected_sha256 is not None and (
            len(expected_sha256) != 64
            or any(char not in "0123456789abcdef" for char in expected_sha256)
        ):
            raise SECAcquisitionError("expected_sha256 must be 64 lowercase hex characters")

        headers = {
            "User-Agent": self.user_agent.header_value(),
            "Accept-Encoding": "gzip, deflate",
            "Accept": "*/*",
        }
        response: SECTransportResponse | None = None

        for attempt in range(1, self.policy.max_attempts + 1):
            self._rate_limit()
            response = self._transport.get(
                url,
                headers=headers,
                timeout=self.policy.timeout_seconds,
            )
            retrieval_utc = self._now_utc()
            if retrieval_utc.tzinfo is None or retrieval_utc.utcoffset() is None:
                raise SECAcquisitionError("now_utc must return timezone-aware UTC datetime")
            retrieval_utc = retrieval_utc.astimezone(timezone.utc)

            if 200 <= response.status_code < 300:
                content = bytes(response.content)
                if not content:
                    raise SECAcquisitionError("SEC response body is empty")

                raw_content_type = response.headers.get("Content-Type")
                content_type = (
                    raw_content_type.split(";", 1)[0].strip().lower()
                    if raw_content_type
                    else None
                )
                allowed = {item.lower() for item in self.policy.allowed_content_types}
                if content_type is not None and content_type not in allowed:
                    raise SECAcquisitionError(
                        f"unexpected SEC content type: {content_type}"
                    )

                digest = hashlib.sha256(content).hexdigest()
                if expected_size is not None and len(content) != expected_size:
                    raise SECAcquisitionError(
                        f"SEC byte-size mismatch: expected {expected_size}, got {len(content)}"
                    )
                if expected_sha256 is not None and digest != expected_sha256:
                    raise SECAcquisitionError("SEC SHA-256 mismatch")

                receipt = SECFetchReceipt(
                    request_url=url,
                    response_url=response.url,
                    status_code=response.status_code,
                    retrieval_utc=retrieval_utc,
                    attempts=attempt,
                    content_type=content_type,
                    content_length_header=response.headers.get("Content-Length"),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    byte_size=len(content),
                    sha256=digest,
                )
                return content, receipt

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                raise SECAcquisitionError(
                    f"SEC request failed with HTTP {response.status_code}"
                )
            if attempt == self.policy.max_attempts:
                break
            delay = self._backoff_seconds(attempt, response.headers, retrieval_utc)
            if delay > 0:
                self._sleep(delay)

        status = response.status_code if response is not None else "NO_RESPONSE"
        raise SECAcquisitionError(
            f"SEC request exhausted {self.policy.max_attempts} attempts; last status={status}"
        )

    def freeze(
        self,
        url: str,
        destination: Path,
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> SECFrozenResource:
        content, receipt = self.fetch_bytes(
            url,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            existing = destination.read_bytes()
            existing_sha = hashlib.sha256(existing).hexdigest()
            if existing_sha == receipt.sha256 and len(existing) == receipt.byte_size:
                return SECFrozenResource(
                    receipt=receipt,
                    path=destination,
                    write_status="EXISTING_MATCH",
                )
            raise SECAcquisitionError(
                "destination already exists with different bytes; refusing overwrite"
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".part",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        frozen = destination.read_bytes()
        if len(frozen) != receipt.byte_size:
            raise SECAcquisitionError("post-write byte-size verification failed")
        if hashlib.sha256(frozen).hexdigest() != receipt.sha256:
            raise SECAcquisitionError("post-write SHA-256 verification failed")

        return SECFrozenResource(
            receipt=receipt,
            path=destination,
            write_status="WRITTEN",
        )
