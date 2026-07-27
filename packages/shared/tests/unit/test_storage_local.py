import multiprocessing
from concurrent.futures import ThreadPoolExecutor

import pytest

from shared.storage.local import LocalStorageBackend


def test_store_retrieve_roundtrip(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("file.pdf", b"hello world")
    assert backend.retrieve("file.pdf") == b"hello world"


def test_exists_true_after_store(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("doc.txt", b"data")
    assert backend.exists("doc.txt")


def test_exists_false_after_delete(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("doc.txt", b"data")
    backend.delete("doc.txt")
    assert not backend.exists("doc.txt")


def test_retrieve_raises_file_not_found(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        backend.retrieve("nonexistent.pdf")


def test_delete_missing_key_is_noop(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.delete("nonexistent.pdf")  # should not raise


def test_get_url_returns_path(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("file.pdf", b"data")
    url = backend.get_url("file.pdf")
    assert "file.pdf" in url


def test_nested_key_creates_directories(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.store("documents/abc-123/original.pdf", b"content")
    assert backend.exists("documents/abc-123/original.pdf")
    assert (tmp_path / "documents" / "abc-123").is_dir()


# A payload comfortably above PIPE_BUF (4096), where O_APPEND alone stops being
# atomic and the exclusive lock is what keeps lines intact.
LARGE_PAYLOAD = "x" * 65536

CONCURRENT_WRITERS = 10


def test_add_json_creates_jsonl_stream_file(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    location = backend.add_json("llm-traces/2026-07-27", {"operation": "generate"})
    assert location.endswith("llm-traces/2026-07-27.jsonl")
    assert (tmp_path / "llm-traces" / "2026-07-27.jsonl").is_file()


def test_add_json_appends_one_line_per_record(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.add_json("traces/day", {"n": 1})
    backend.add_json("traces/day", {"n": 2})

    content = (tmp_path / "traces" / "day.jsonl").read_text(encoding="utf-8")
    assert content.count("\n") == 2
    assert [record["n"] for record in backend.iter_json("traces/")] == [1, 2]


def test_add_json_preserves_swedish_characters(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.add_json("traces/day", {"content": "Överklagande av beslut i Växjö"})

    raw = (tmp_path / "traces" / "day.jsonl").read_text(encoding="utf-8")
    assert "Överklagande av beslut i Växjö" in raw

    records = list(backend.iter_json("traces/"))
    assert records[0]["content"] == "Överklagande av beslut i Växjö"


def test_iter_json_reads_across_streams_in_key_order(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.add_json("traces/2026-07-28", {"day": 28})
    backend.add_json("traces/2026-07-27", {"day": 27})

    assert [record["day"] for record in backend.iter_json("traces/")] == [27, 28]


def test_iter_json_ignores_streams_outside_the_prefix(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.add_json("traces/day", {"n": 1})
    backend.add_json("other/day", {"n": 2})

    assert [record["n"] for record in backend.iter_json("traces/")] == [1]


def test_iter_json_on_missing_prefix_yields_nothing(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    assert list(backend.iter_json("nothing-here/")) == []


def test_add_json_serializes_unrepresentable_values(tmp_path):
    backend = LocalStorageBackend(tmp_path)
    backend.add_json("traces/day", {"context": {"document_id": object()}})

    records = list(backend.iter_json("traces/"))
    assert isinstance(records[0]["context"]["document_id"], str)


def test_concurrent_thread_appends_stay_line_intact(tmp_path):
    backend = LocalStorageBackend(tmp_path)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WRITERS) as pool:
        list(
            pool.map(
                lambda n: backend.add_json("traces/day", {"n": n, "d": LARGE_PAYLOAD}),
                range(CONCURRENT_WRITERS),
            )
        )

    records = list(backend.iter_json("traces/"))
    assert len(records) == CONCURRENT_WRITERS
    assert sorted(record["n"] for record in records) == list(range(CONCURRENT_WRITERS))
    assert all(record["d"] == LARGE_PAYLOAD for record in records)


def _append_large_record(base_path, index):
    LocalStorageBackend(base_path).add_json(
        "traces/day", {"n": index, "d": LARGE_PAYLOAD}
    )


def test_concurrent_process_appends_stay_line_intact(tmp_path):
    context = multiprocessing.get_context("fork")
    processes = [
        context.Process(target=_append_large_record, args=(tmp_path, n))
        for n in range(CONCURRENT_WRITERS)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    records = list(LocalStorageBackend(tmp_path).iter_json("traces/"))
    assert len(records) == CONCURRENT_WRITERS
    assert sorted(record["n"] for record in records) == list(range(CONCURRENT_WRITERS))
    assert all(record["d"] == LARGE_PAYLOAD for record in records)
