"""Tamper-evident audit record of the model calls inside one run."""

import gzip
import json

from sonia.integrations.object_store import NullObjectStore
from sonia.observability.audit import (
    MAX_RECORDS_PER_RUN,
    MAX_TEXT_LENGTH,
    RunAuditLog,
    verify_chain,
)


class StoreStub:
    def __init__(self, fails: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self._fails = fails

    @property
    def configured(self) -> bool:
        return True

    def put(self, key: str, body: bytes, content_type: str) -> str | None:
        if self._fails:
            raise RuntimeError("Object storage is unreachable")
        self.objects[key] = body
        return f"https://example.invalid/{key}"


def _records(store: StoreStub) -> list[dict[str, object]]:
    body = gzip.decompress(next(iter(store.objects.values())))
    return [json.loads(line) for line in body.splitlines() if line]


def _log_two_calls(store: StoreStub) -> RunAuditLog:
    audit = RunAuditLog(store)
    audit.record("run-1", {"kind": "specialist", "phase": "collections", "answer": "hallazgos"})
    audit.record("run-1", {"kind": "judge", "phase": "collections", "verdict": "PASS"})
    return audit


def test_every_line_seals_the_previous_one() -> None:
    store = StoreStub()
    _log_two_calls(store).publish("run-1")

    records = _records(store)

    assert [item["sequence"] for item in records] == [0, 1]
    assert records[0]["prev_sha256"] is None
    assert records[1]["prev_sha256"] == records[0]["sha256"]
    assert verify_chain(records)


def test_editing_a_line_breaks_the_chain() -> None:
    """An auditor recomputing the seals must detect a rewritten verdict."""
    store = StoreStub()
    _log_two_calls(store).publish("run-1")
    records = _records(store)

    records[1]["verdict"] = "MANUAL_REVIEW"

    assert not verify_chain(records)


def test_dropping_a_line_breaks_the_chain() -> None:
    store = StoreStub()
    _log_two_calls(store).publish("run-1")
    records = _records(store)

    assert not verify_chain([records[1]])


def test_the_object_is_compressed_jsonl_under_a_dated_key() -> None:
    store = StoreStub()
    _log_two_calls(store).publish("run-1")

    key = next(iter(store.objects))
    assert key.startswith("audit/") and key.endswith("/run-1.jsonl.gz")
    assert len(key.split("/")) == 5
    assert store.objects[key][:2] == b"\x1f\x8b"


def test_long_answers_are_truncated_with_their_original_length() -> None:
    store = StoreStub()
    audit = RunAuditLog(store)
    audit.record("run-1", {"kind": "specialist", "answer": "x" * (MAX_TEXT_LENGTH + 500)})

    audit.publish("run-1")

    record = _records(store)[0]
    assert len(record["answer"]) == MAX_TEXT_LENGTH
    assert record["answer_truncated_from"] == MAX_TEXT_LENGTH + 500


def test_a_runaway_run_cannot_grow_without_bound() -> None:
    store = StoreStub()
    audit = RunAuditLog(store)
    for index in range(MAX_RECORDS_PER_RUN + 25):
        audit.record("run-1", {"kind": "specialist", "answer": str(index)})

    assert audit.pending("run-1") == MAX_RECORDS_PER_RUN


def test_publishing_releases_the_buffer() -> None:
    store = StoreStub()
    audit = _log_two_calls(store)

    assert audit.publish("run-1") is not None
    assert audit.pending("run-1") == 0
    assert audit.publish("run-1") is None


def test_an_unreachable_bucket_never_fails_the_run() -> None:
    """Losing the audit object is bad; losing the analysis over it is worse."""
    audit = RunAuditLog(StoreStub(fails=True))
    audit.record("run-1", {"kind": "judge", "verdict": "PASS"})

    assert audit.publish("run-1") is None


def test_an_unconfigured_bucket_records_nothing() -> None:
    audit = RunAuditLog(NullObjectStore())
    audit.record("run-1", {"kind": "judge", "verdict": "PASS"})

    assert audit.enabled is False
    assert audit.pending("run-1") == 0
    assert audit.publish("run-1") is None
