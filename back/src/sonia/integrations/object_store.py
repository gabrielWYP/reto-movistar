"""Object storage boundary and its OCI S3-compatible adapter.

OCI's native SDK is a heavy dependency for a read-only slim image, and the
compatibility endpoint speaks the same signed protocol every S3 client uses, so
requests are signed here with the standard library alone.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 1.5
# A freshly issued Customer Secret Key is not on every regional replica yet, so a
# correctly signed request can still be rejected while it propagates.
_RETRYABLE_CODES = ("SignatureDoesNotMatch", "RequestTimeTooSkewed", "InternalError")
_SIGNED_HEADERS = ("content-type", "host", "x-amz-content-sha256", "x-amz-date")


class HttpResponse(Protocol):
    """The slice of an HTTP response this adapter reads."""

    status: int

    def __enter__(self) -> HttpResponse: ...

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class ObjectStore(Protocol):
    """Write-only boundary; nothing in the run path reads objects back."""

    @property
    def configured(self) -> bool: ...

    def put(self, key: str, body: bytes, content_type: str) -> str | None: ...


class NullObjectStore:
    """Accept and drop writes so an unconfigured deployment keeps working."""

    @property
    def configured(self) -> bool:
        return False

    def put(self, key: str, body: bytes, content_type: str) -> str | None:
        logger.debug("object_store_disabled", extra={"key": key, "bytes": len(body)})
        return None


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, stamp: str, region: str) -> bytes:
    initial = _sign(f"AWS4{secret}".encode(), stamp)
    return _sign(_sign(_sign(initial, region), SERVICE), "aws4_request")


class OciObjectStore:
    """Put objects into one OCI bucket through its S3-compatible endpoint."""

    def __init__(
        self,
        namespace: str,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        opener: Callable[..., HttpResponse] | None = None,
    ) -> None:
        self.namespace, self.bucket, self.region = namespace, bucket, region
        self._access_key_id, self._secret = access_key_id, secret_access_key
        self._opener = opener or urlopen

    @property
    def configured(self) -> bool:
        return True

    @property
    def host(self) -> str:
        return f"{self.namespace}.compat.objectstorage.{self.region}.oraclecloud.com"

    def _canonical_uri(self, key: str) -> str:
        """Address the bucket by path.

        A virtual-host style request encodes the bucket into the hostname, and
        DNS is case-insensitive, so a bucket whose name carries capitals is only
        addressable this way.
        """
        return "/" + quote(f"{self.bucket}/{key}", safe="/~")

    def _headers(self, key: str, body: bytes, content_type: str, now: datetime) -> dict[str, str]:
        stamp, timestamp = now.strftime("%Y%m%d"), now.strftime("%Y%m%dT%H%M%SZ")
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = {
            "content-type": content_type,
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": timestamp,
        }
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in _SIGNED_HEADERS)
        signed_headers = ";".join(_SIGNED_HEADERS)
        canonical_request = "\n".join(
            (
                "PUT",
                self._canonical_uri(key),
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            )
        )
        scope = f"{stamp}/{self.region}/{SERVICE}/aws4_request"
        to_sign = "\n".join(
            (
                ALGORITHM,
                timestamp,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            )
        )
        signature = hmac.new(
            _signing_key(self._secret, stamp, self.region),
            to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["authorization"] = (
            f"{ALGORITHM} Credential={self._access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers

    def _attempt(self, url: str, key: str, body: bytes, content_type: str) -> None:
        headers = self._headers(key, body, content_type, datetime.now(UTC))
        request = Request(url, data=body, headers=headers, method="PUT")
        with self._opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            logger.info(
                "object_stored",
                extra={"key": key, "bytes": len(body), "status": response.status},
            )

    def put(self, key: str, body: bytes, content_type: str) -> str | None:
        """Store one immutable object, returning its URL.

        Each attempt is signed afresh, because the signature covers the timestamp.
        """
        url = f"https://{self.host}{self._canonical_uri(key)}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                self._attempt(url, key, body, content_type)
                return url
            except HTTPError as error:
                detail = _error_code(error)
                if attempt == MAX_ATTEMPTS or not (error.code >= 500 or detail in _RETRYABLE_CODES):
                    raise RuntimeError(
                        f"Object storage returned HTTP {error.code} ({detail})"
                    ) from error
                reason: str = detail
            except (TimeoutError, URLError) as error:
                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError("Object storage is unreachable") from error
                reason = type(error).__name__
            logger.warning(
                "object_store_retry",
                extra={"key": key, "attempt": attempt, "reason": reason},
            )
            time.sleep(BACKOFF_SECONDS * attempt)
        return url


def _error_code(error: HTTPError) -> str:
    """Read the S3-style error code so a transient rejection is distinguishable."""
    try:
        payload = error.read().decode("utf-8", "replace")
    except OSError:
        return "unreadable"
    if "<Code>" not in payload:
        return "unknown"
    return payload.split("<Code>", 1)[1].split("</Code>", 1)[0][:64]


def object_store_from_environment() -> ObjectStore:
    """Build the configured store, or a disabled one when credentials are absent."""
    values = {
        name: os.environ.get(f"SONIA_OCI_{name.upper()}", "").strip()
        for name in ("namespace", "bucket", "region", "access_key_id", "secret_access_key")
    }
    if not all(values.values()):
        missing = sorted(name for name, value in values.items() if not value)
        logger.info("object_store_not_configured", extra={"missing": ",".join(missing)})
        return NullObjectStore()
    return OciObjectStore(
        values["namespace"],
        values["bucket"],
        values["region"],
        values["access_key_id"],
        values["secret_access_key"],
    )
