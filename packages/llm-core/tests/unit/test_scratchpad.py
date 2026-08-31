"""The generic K:V scratchpad: storage, previews, the board, and persistence."""

from __future__ import annotations

from llm_core import Handle, Scratchpad


def test_remember_returns_a_handle_and_recall_gives_the_value_back() -> None:
    pad: Scratchpad[str] = Scratchpad()
    handle = pad.remember("d1", "full value", preview={"case": "12/2024"})
    assert isinstance(handle, Handle)
    assert handle.key == "d1"
    assert handle.preview == {"case": "12/2024"}
    assert pad.recall("d1") == "full value"
    assert "d1" in pad
    assert len(pad) == 1


def test_get_returns_the_default_when_absent() -> None:
    pad: Scratchpad[str] = Scratchpad()
    assert pad.get("missing") is None
    assert pad.get("missing", "fallback") == "fallback"


def test_handle_as_dict_flattens_key_and_preview() -> None:
    handle = Handle(key="c1", preview={"snippet": "…"})
    assert handle.as_dict() == {"key": "c1", "snippet": "…"}
    assert handle.as_dict(key_field="chunk_id") == {"chunk_id": "c1", "snippet": "…"}


def test_entries_keep_insertion_order() -> None:
    pad: Scratchpad[int] = Scratchpad()
    for key in ("b", "a", "c"):
        pad.remember(key, ord(key), preview={})
    assert pad.keys() == ["b", "a", "c"]
    assert [k for k, _ in pad.entries()] == ["b", "a", "c"]


def test_re_remembering_overwrites_in_place_and_keeps_position() -> None:
    pad: Scratchpad[str] = Scratchpad()
    pad.remember("a", "first", preview={"v": 1})
    pad.remember("b", "second", preview={"v": 2})
    pad.remember("a", "updated", preview={"v": 3})
    assert pad.recall("a") == "updated"
    assert pad.keys() == ["a", "b"]  # position of "a" unchanged
    assert pad.preview_of("a") == {"v": 3}


def test_a_kv_entry_renders_its_value_as_its_own_preview() -> None:
    pad: Scratchpad[object] = Scratchpad()
    pad.remember("grounded", True)  # no preview
    pad.remember("cases", ["12/2024", "8/2023"])
    assert pad.digest() == {
        "grounded": {"value": True},
        "cases": {"value": ["12/2024", "8/2023"]},
    }


def test_digest_is_the_previews_in_order() -> None:
    pad: Scratchpad[str] = Scratchpad()
    pad.remember("d1", "x", preview={"case": "12/2024"})
    pad.remember("d2", "y", preview={"case": "8/2023"})
    assert pad.digest() == {"d1": {"case": "12/2024"}, "d2": {"case": "8/2023"}}


def test_render_board_is_empty_for_an_empty_pad() -> None:
    assert Scratchpad().render_board() == ""


def test_render_board_lists_every_entrys_preview() -> None:
    pad: Scratchpad[str] = Scratchpad()
    pad.remember("d1", "x", preview={"case": "12/2024"})
    pad.remember("c1", "y", preview={"snippet": "jäv"})
    board = pad.render_board()
    assert board.splitlines() == [
        'd1  {"case": "12/2024"}',
        'c1  {"snippet": "jäv"}',
    ]


def test_dump_and_load_round_trip_through_a_codec() -> None:
    pad: Scratchpad[int] = Scratchpad()
    pad.remember("a", 1, preview={"n": 1})
    pad.remember("b", 2, preview={"n": 2})

    blob = pad.dump(lambda _k, v: {"raw": v})
    restored = Scratchpad.load(blob, lambda _k, data: data["raw"])

    assert restored.keys() == ["a", "b"]
    assert restored.recall("a") == 1
    assert restored.recall("b") == 2
    assert restored.preview_of("a") == {"n": 1}


def test_load_of_an_empty_or_missing_blob_is_an_empty_pad() -> None:
    assert len(Scratchpad.load({}, lambda _k, v: v)) == 0
    assert len(Scratchpad.load({"entries": []}, lambda _k, v: v)) == 0


def test_restore_replaces_contents_in_place() -> None:
    pad: Scratchpad[int] = Scratchpad()
    pad.remember("stale", 9, preview={"n": 9})

    donor: Scratchpad[int] = Scratchpad()
    donor.remember("new", 5, preview={"n": 5})
    pad.restore(donor.dump(lambda _k, v: v), lambda _k, v: v)

    assert pad.keys() == ["new"]  # the stale entry is gone
    assert pad.recall("new") == 5


def test_dump_cap_keeps_recent_heavy_entries_and_all_kv_entries() -> None:
    pad: Scratchpad[str] = Scratchpad()
    pad.remember("kept-kv", "grounded")  # K=V, exempt from the cap
    for n in range(1, 6):  # five heavy entries d1..d5
        pad.remember(f"d{n}", f"value{n}", preview={"n": n})

    blob = pad.dump(lambda _k, v: v, cap=2)
    kept = [entry["key"] for entry in blob["entries"]]

    # The K=V entry survives; only the two most-recent heavy entries do.
    assert "kept-kv" in kept
    assert [k for k in kept if k.startswith("d")] == ["d4", "d5"]


def test_dump_without_a_cap_keeps_everything() -> None:
    pad: Scratchpad[str] = Scratchpad()
    for n in range(1, 4):
        pad.remember(f"d{n}", f"v{n}", preview={"n": n})
    blob = pad.dump(lambda _k, v: v)
    assert [entry["key"] for entry in blob["entries"]] == ["d1", "d2", "d3"]
