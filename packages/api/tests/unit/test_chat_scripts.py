"""The canned chat streams, and the rule that picks one.

Two kinds of check here. The selection rule is ordinary pure-function testing.
The rest are assertions *about the fixtures* — that they end the way the
contract says a stream ends, that every step is closed, that between them they
exercise the whole progress vocabulary. A fixture nobody checks is a fixture
that quietly stops matching the thing it stands in for.
"""

from __future__ import annotations

import pytest
from agents.chat import (
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)

from api.config import ChatScript
from api.dev.chat_scripts import (
    DIRECT_SCRIPT_MAX_WORDS,
    SCRIPTS,
    ScriptedFrame,
    select_script,
    stream_text,
)


def _events(script: ChatScript) -> list:
    return [frame.event for frame in SCRIPTS[script]]


def _token_texts(frames: list[ScriptedFrame]) -> list[str]:
    """The text of every frame, asserting each is in fact a token frame."""
    texts = []
    for frame in frames:
        assert isinstance(frame.event, TokenEvent)
        texts.append(frame.event.text)
    return texts


class TestSelectScript:
    def test_off_runs_the_real_agent(self):
        assert select_script(ChatScript.OFF, "Vad gäller vid jäv?") is None

    @pytest.mark.parametrize(
        "setting",
        [ChatScript.RESEARCH, ChatScript.DIRECT, ChatScript.ERROR],
    )
    def test_a_named_script_ignores_the_message(self, setting: ChatScript):
        assert select_script(setting, "tack") is setting
        assert select_script(setting, "en betydligt längre fråga om jäv") is setting

    def test_auto_picks_direct_for_a_short_message(self):
        assert select_script(ChatScript.AUTO, "tack") is ChatScript.DIRECT

    def test_auto_picks_research_for_a_question(self):
        question = "Vad gäller vid jäv i kyrkoval?"
        assert select_script(ChatScript.AUTO, question) is ChatScript.RESEARCH

    def test_auto_boundary_is_inclusive(self):
        """Exactly at the limit is still a conversational turn."""
        at_limit = " ".join(["ord"] * DIRECT_SCRIPT_MAX_WORDS)
        over = " ".join(["ord"] * (DIRECT_SCRIPT_MAX_WORDS + 1))

        assert select_script(ChatScript.AUTO, at_limit) is ChatScript.DIRECT
        assert select_script(ChatScript.AUTO, over) is ChatScript.RESEARCH

    def test_auto_never_picks_the_failure(self):
        """A stray short question looking broken would be worse than useless."""
        for message in ["", "hej", "en lite längre fråga om jäv och kyrkoval"]:
            assert select_script(ChatScript.AUTO, message) is not ChatScript.ERROR

    def test_every_selectable_script_has_frames(self):
        for setting in ChatScript:
            selected = select_script(setting, "en fråga om jäv i kyrkoval")
            if selected is not None:
                assert SCRIPTS[selected], f"{selected} has no frames"


class TestStreamText:
    def test_the_pieces_rejoin_to_the_original(self):
        """Dropped spaces would make every scripted answer subtly wrong."""
        text = "Jäv bedöms utifrån om den som deltagit haft en koppling."

        assert "".join(_token_texts(stream_text(text))) == text

    def test_one_frame_per_word(self):
        assert len(stream_text("ett två tre")) == 3

    def test_a_single_word_streams_as_one_frame(self):
        assert _token_texts(stream_text("Ja.")) == ["Ja."]


class TestScriptShapes:
    @pytest.mark.parametrize("script", [ChatScript.RESEARCH, ChatScript.DIRECT])
    def test_a_successful_script_ends_on_done(self, script: ChatScript):
        events = _events(script)
        assert isinstance(events[-1], DoneEvent)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    def test_the_error_script_ends_on_error_and_never_reaches_done(self):
        """`error` is terminal; a client that waits for a `done` after it hangs."""
        events = _events(ChatScript.ERROR)
        assert isinstance(events[-1], ErrorEvent)
        assert not any(isinstance(event, DoneEvent) for event in events)

    @pytest.mark.parametrize("script", list(SCRIPTS))
    def test_every_call_is_closed_by_a_result(self, script: ChatScript):
        events = _events(script)
        calls = [e.id for e in events if isinstance(e, ToolCallEvent)]
        results = [e.id for e in events if isinstance(e, ToolResultEvent)]

        assert calls == results

    @pytest.mark.parametrize("script", list(SCRIPTS))
    def test_no_frame_pauses_absurdly(self, script: ChatScript):
        """A stray delay here is a hung UI, not a slow one."""
        assert all(0.0 <= frame.delay <= 5.0 for frame in SCRIPTS[script])

    def test_the_scripts_cover_the_whole_progress_vocabulary(self):
        """Every label the client holds Swedish words for is reachable on screen.

        The other half of this pairing is `progress-labels.test.ts`, which reads
        the enum and fails when the client is missing a word for one.
        """
        seen = {
            event.label
            for script in SCRIPTS
            for event in _events(script)
            if isinstance(event, (ToolCallEvent, ToolResultEvent))
        }

        assert seen == set(ProgressLabel)

    def test_a_frame_is_a_delay_and_an_event(self):
        frame = SCRIPTS[ChatScript.DIRECT][0]
        assert isinstance(frame, ScriptedFrame)
        assert frame.delay >= 0.0
