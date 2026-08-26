"""Signed writes to the OCI S3-compatible endpoint."""

import hashlib
import io
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import sonia.integrations.object_store as object_store_module
from sonia.integrations.object_store import (
    MAX_ATTEMPTS,
    NullObjectStore,
    OciObjectStore,
    object_store_from_environment,
)

NAMESPACE = "id39lkzyqahe"
BUCKET = "bucketDemosWEB"
REGION = "us-ashburn-1"
WHEN = datetime(2026, 8, 26, 17, 30, 0, tzinfo=UTC)


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _Opener:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    def __call__(self, request: Request, timeout: int = 0) -> _Response:
        self.requests.append(request)
        return _Response()


def _store(
    opener: Callable[..., _Response] | None = None, secret: str = "s3cret"
) -> OciObjectStore:
    return OciObjectStore(NAMESPACE, BUCKET, REGION, "AKID", secret, opener)


def test_bucket_with_capitals_is_addressed_by_path() -> None:
    """Virtual-host style folds the bucket into a hostname and DNS lowercases it."""
    opener = _Opener()

    url = _store(opener).put("audit/2026/08/26/run_1.jsonl.gz", b"payload", "application/gzip")

    assert url == (
        f"https://{NAMESPACE}.compat.objectstorage.{REGION}.oraclecloud.com"
        f"/{BUCKET}/audit/2026/08/26/run_1.jsonl.gz"
    )
    assert BUCKET in url
    assert opener.requests[0].get_method() == "PUT"


def test_the_payload_digest_is_signed_with_the_request() -> None:
    body = b"one line\n"
    headers = _store()._headers("audit/x.gz", body, "application/gzip", WHEN)

    assert headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert headers["x-amz-date"] == "20260826T173000Z"
    assert (
        "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date"
        in (headers["authorization"])
    )
    assert f"Credential=AKID/20260826/{REGION}/s3/aws4_request" in headers["authorization"]


def _signature(headers: dict[str, str]) -> str:
    return headers["authorization"].split("Signature=")[1]


def test_the_signature_covers_body_key_secret_and_time() -> None:
    """Any change to what is stored must produce a different signature."""
    base = _store()._headers("audit/x.gz", b"body", "application/gzip", WHEN)

    assert _signature(base) == _signature(
        _store()._headers("audit/x.gz", b"body", "application/gzip", WHEN)
    )
    assert _signature(base) != _signature(
        _store()._headers("audit/x.gz", b"other", "application/gzip", WHEN)
    )
    assert _signature(base) != _signature(
        _store()._headers("audit/y.gz", b"body", "application/gzip", WHEN)
    )
    assert _signature(base) != _signature(
        _store(secret="rotated")._headers("audit/x.gz", b"body", "application/gzip", WHEN)
    )
    assert _signature(base) != _signature(
        _store()._headers("audit/x.gz", b"body", "application/gzip", WHEN.replace(day=27))
    )


def test_transport_failures_surface_as_runtime_errors() -> None:
    def broken(request: Request, timeout: int = 0) -> _Response:
        raise TimeoutError

    with pytest.raises(RuntimeError, match="unreachable"):
        _store(broken).put("audit/x.gz", b"body", "application/gzip")


def test_incomplete_credentials_disable_storage_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment without a bucket keeps running; auditing is simply off."""
    for name in ("NAMESPACE", "BUCKET", "REGION", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"):
        monkeypatch.delenv(f"SONIA_OCI_{name}", raising=False)
    monkeypatch.setenv("SONIA_OCI_NAMESPACE", NAMESPACE)
    monkeypatch.setenv("SONIA_OCI_BUCKET", BUCKET)

    store = object_store_from_environment()

    assert isinstance(store, NullObjectStore)
    assert store.configured is False
    assert store.put("k", b"v", "application/gzip") is None


def test_complete_credentials_build_the_oci_store(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("NAMESPACE", NAMESPACE),
        ("BUCKET", BUCKET),
        ("REGION", REGION),
        ("ACCESS_KEY_ID", "AKID"),
        ("SECRET_ACCESS_KEY", "secret"),
    ):
        monkeypatch.setenv(f"SONIA_OCI_{name}", value)

    store = object_store_from_environment()

    assert isinstance(store, OciObjectStore)
    assert store.configured is True
    assert store.host == f"{NAMESPACE}.compat.objectstorage.{REGION}.oraclecloud.com"


def _http_error(code: int, error_code: str) -> HTTPError:
    payload = f"<Error><Code>{error_code}</Code></Error>".encode()
    return HTTPError("https://example.invalid", code, "denied", {}, io.BytesIO(payload))


class _FlakyOpener:
    """Reject the first attempts the way a freshly issued key is rejected."""

    def __init__(self, failures: int, error: HTTPError | None = None) -> None:
        self.remaining, self.calls = failures, 0
        self._error = error

    def __call__(self, request: Request, timeout: int = 0) -> _Response:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self._error or _http_error(403, "SignatureDoesNotMatch")
        return _Response()


def test_a_propagating_credential_is_retried_until_it_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OCI rejects a correctly signed request while the secret key replicates."""
    monkeypatch.setattr(object_store_module, "BACKOFF_SECONDS", 0)
    opener = _FlakyOpener(2)

    url = _store(opener).put("audit/x.gz", b"body", "application/gzip")

    assert url is not None
    assert opener.calls == 3


def test_retries_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(object_store_module, "BACKOFF_SECONDS", 0)
    opener = _FlakyOpener(MAX_ATTEMPTS + 5)

    with pytest.raises(RuntimeError, match="SignatureDoesNotMatch"):
        _store(opener).put("audit/x.gz", b"body", "application/gzip")

    assert opener.calls == MAX_ATTEMPTS


def test_a_missing_bucket_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying a permanent rejection only delays the failure."""
    monkeypatch.setattr(object_store_module, "BACKOFF_SECONDS", 0)
    opener = _FlakyOpener(3, _http_error(404, "NoSuchBucket"))

    with pytest.raises(RuntimeError, match="NoSuchBucket"):
        _store(opener).put("audit/x.gz", b"body", "application/gzip")

    assert opener.calls == 1


def test_each_attempt_is_signed_afresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """The signature covers the timestamp, so a stale one would fail forever."""
    monkeypatch.setattr(object_store_module, "BACKOFF_SECONDS", 0)
    opener = _Opener()
    store = _store(opener)

    store.put("audit/x.gz", b"body", "application/gzip")
    store.put("audit/x.gz", b"body", "application/gzip")

    dates = [request.get_header("X-amz-date") for request in opener.requests]
    assert all(dates) and len(dates) == 2
