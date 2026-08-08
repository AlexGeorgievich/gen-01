import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import MainWindow  # noqa: E402
from gpt01.models import TranslationRow  # noqa: E402
from gpt01.session import SessionRepository  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def set_caret_line(window, line_number):
    block = window.source_edit.document().findBlockByNumber(line_number)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(block.position())
    window.source_edit.setTextCursor(cursor)


def test_markers_select_reversed_inclusive_range_and_enable_space_repeat(
    qapp,
    tmp_path,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\n\nthree\nfour")
    window.translation_edit.setPlainText("0\n1\n\n3\n4")
    set_caret_line(window, 4)
    window.set_range_marker_a()
    set_caret_line(window, 1)
    window.set_range_marker_b()

    assert window.mark_a_button.text() == "A:5"
    assert window.mark_b_button.text() == "B:2"
    assert window.play_ab_button.isEnabled()
    assert {
        selection.cursor.blockNumber()
        for selection in window.source_edit.extraSelections()
    } == {1, 4}

    generations = []
    window._play_next_sequence_line = generations.append
    window.play_ab_range()

    assert window.sequence.rows == [
        TranslationRow(1, "one", "1", "1"),
        TranslationRow(3, "three", "3", "3"),
        TranslationRow(4, "four", "4", "4"),
    ]
    assert window._sequence_scope == "ab"
    assert generations == [window.sequence.generation]
    assert not window.play_ab_button.isEnabled()

    window._finish_sequence()

    assert window._ab_repeat_ready
    assert window.ab_repeat_shortcut.isEnabled()
    assert "Space" in window.statusBar().currentMessage()

    window.ab_repeat_shortcut.activated.emit()

    assert window.sequence.active
    assert window._sequence_scope == "ab"
    assert len(generations) == 2
    assert not window.ab_repeat_shortcut.isEnabled()
    window._stop_sequence()

    window._dirty = False
    window.close()


def test_mouse_path_to_button_does_not_replace_blinking_caret_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo\nthree")
    window.show()
    qapp.processEvents()
    set_caret_line(window, 2)
    first_block = window.source_edit.document().findBlockByNumber(0)
    first_cursor = window.source_edit.textCursor()
    first_cursor.setPosition(first_block.position())

    QTest.mouseMove(
        window.source_edit.viewport(),
        window.source_edit.cursorRect(first_cursor).center(),
    )
    qapp.processEvents()
    window.mark_a_button.click()

    assert window._range_a_line == 2
    assert window.mark_a_button.text() == "A:3"

    window._dirty = False
    window.close()


def test_marker_button_uses_blinking_text_cursor_without_mouse_move(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo\nthree")

    set_caret_line(window, 3)
    qapp.processEvents()
    window.mark_b_button.click()

    assert window._range_b_line == 3
    assert window.mark_b_button.text() == "B:4"

    window._dirty = False
    window.close()


def test_source_change_resets_markers_and_space_repeat(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    set_caret_line(window, 0)
    window.set_range_marker_a()
    set_caret_line(window, 1)
    window.set_range_marker_b()
    window._ab_repeat_ready = True
    window._update_ab_controls()
    assert window.ab_repeat_shortcut.isEnabled()

    window.source_edit.append("three")

    assert window._range_a_line is None
    assert window._range_b_line is None
    assert window.mark_a_button.text() == "A"
    assert window.mark_b_button.text() == "B"
    assert not window.play_ab_button.isEnabled()
    assert not window.ab_repeat_shortcut.isEnabled()

    window._dirty = False
    window.close()


def test_stop_does_not_arm_space_repeat(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window._range_a_line = 0
    window._range_b_line = 1
    window._play_next_sequence_line = lambda _generation: None
    window.play_ab_range()

    window.stop_current_operation()

    assert not window.sequence.active
    assert not window._ab_repeat_ready
    assert not window.ab_repeat_shortcut.isEnabled()

    window._dirty = False
    window.close()


def test_reset_button_stops_active_ab_sequence_and_removes_markers(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    set_caret_line(window, 0)
    window.set_range_marker_a()
    set_caret_line(window, 1)
    window.set_range_marker_b()
    window._play_next_sequence_line = lambda _generation: None
    window.play_ab_range()

    window.reset_ab_button.click()

    assert not window.sequence.active
    assert window._range_a_line is None
    assert window._range_b_line is None
    assert not window.reset_ab_button.isEnabled()

    window._dirty = False
    window.close()


def test_ab_repeat_reuses_cached_line_audio_and_reset_removes_it(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("一\n二")
    set_caret_line(window, 0)
    window.set_range_marker_a()
    set_caret_line(window, 1)
    window.set_range_marker_b()
    synthesized = []
    played = []

    def synthesize(text, _voice, output, _cancelled, *, settings=None):
        synthesized.append((text, settings))
        output.write_bytes(b"mp3")

    window.speech.synthesize = synthesize
    window._run_task = lambda function, on_result, *_args: on_result(
        function(lambda: False)
    )
    window._play_file = played.append

    window.play_ab_range()
    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    first_cycle = list(played)
    assert len(synthesized) == 2
    assert window._ab_repeat_ready
    assert window.ab_audio_cache.has_files

    window.repeat_ab_range()
    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    assert len(synthesized) == 2
    assert played[2:] == first_cycle
    cache_directory = window.ab_audio_cache.directory

    window.reset_ab_button.click()

    assert window._range_a_line is None
    assert window._range_b_line is None
    assert not window.ab_audio_cache.has_files
    assert cache_directory is not None
    assert not cache_directory.exists()

    window._dirty = False
    window.close()


def test_speak_plays_source_rows_with_synchronized_highlight_and_combines_audio(
    qapp,
    tmp_path,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    synthesized = []

    def synthesize(text, _voice, output, _cancelled, *, settings=None):
        synthesized.append((text, settings))
        output.write_bytes(text.encode("utf-8"))

    window.speech.synthesize = synthesize
    window._run_task = lambda function, on_result, *_args: on_result(
        function(lambda: False)
    )
    window._play_file = lambda filename: setattr(window, "audio_path", Path(filename))

    window.speak_text()

    assert window._sequence_scope == "speak"
    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        assert editor.extraSelections()[0].cursor.blockNumber() == 0

    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        assert editor.extraSelections()[0].cursor.blockNumber() == 1

    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    assert synthesized == [("un", window.tts_settings), ("deux", window.tts_settings)]
    assert not window.sequence.active
    assert window.audio_path.read_bytes() == b"undeux"
    assert window.save_audio_button.isEnabled()

    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_save_mp3_after_stopping_speak_synthesizes_the_full_translation(
    qapp,
    tmp_path,
    monkeypatch,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    synthesized = []

    def synthesize(text, _voice, output, _cancelled, *, settings=None):
        synthesized.append((text, settings))
        output.write_bytes(text.encode("utf-8"))

    window.speech.synthesize = synthesize
    window._run_task = lambda function, on_result, *_args: on_result(
        function(lambda: False)
    )
    window._play_file = lambda filename: setattr(window, "audio_path", Path(filename))

    window.speak_text()
    window.stop_current_operation()

    assert not window.sequence.active
    assert not window._audio_is_complete_document
    assert window.save_audio_button.isEnabled()

    selected = tmp_path / "lesson.mp3"
    target = window._language_export_path(str(selected), ".mp3")
    monkeypatch.setattr(
        "app.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(selected), ""),
    )
    window.save_audio()

    assert synthesized[-1] == ("un\ndeux", window.tts_settings)
    assert target.read_bytes() == b"un\ndeux"
    assert window._audio_is_complete_document

    window._reset_audio_state()
    window._dirty = False
    window.close()


@pytest.mark.parametrize(
    ("scope", "expected_audio"),
    (("range", b"deux\ntrois"), ("full", b"un\ndeux\ntrois\nquatre")),
)
def test_save_mp3_with_ab_markers_supports_interval_or_full_text(
    qapp,
    tmp_path,
    monkeypatch,
    scope,
    expected_audio,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo\nthree\nfour")
    window.translation_edit.setPlainText("un\ndeux\ntrois\nquatre")
    window._range_a_line = 2
    window._range_b_line = 1
    window._select_audio_export_scope = lambda: scope

    def synthesize(text, _voice, output, _cancelled, *, settings=None):
        output.write_bytes(text.encode("utf-8"))

    window.speech.synthesize = synthesize
    window._run_task = lambda function, on_result, *_args: on_result(
        function(lambda: False)
    )
    selected = tmp_path / f"lesson-{scope}.mp3"
    target = window._language_export_path(str(selected), ".mp3")
    monkeypatch.setattr(
        "app.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(selected), ""),
    )

    window.save_audio()

    assert target.read_bytes() == expected_audio
    assert window._audio_is_complete_document is (scope == "full")
    if scope == "range":
        assert window.audio_path is None

    window._reset_audio_state()
    window._dirty = False
    window.close()
