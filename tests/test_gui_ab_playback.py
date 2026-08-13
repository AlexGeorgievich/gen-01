import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import MainWindow  # noqa: E402
from gpt01.models import TranslationRow  # noqa: E402
from gpt01.rows import build_sentence_translation_rows  # noqa: E402
from gpt01.session import SessionRepository  # noqa: E402
from gpt01.timed_audio import (  # noqa: E402
    TimedAudioManifest,
    TimedAudioPackage,
    TimedLine,
    save_manifest,
    save_srt,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def set_caret_line(window, line_number):
    block = window.source_edit.document().findBlockByNumber(line_number)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(block.position())
    window.source_edit.setTextCursor(cursor)


def click_source_position(window, position):
    cursor = window.source_edit.textCursor()
    cursor.setPosition(position)
    point = window.source_edit.cursorRect(cursor).center()
    QTest.mouseClick(window.source_edit.viewport(), Qt.MouseButton.LeftButton, pos=point)


def test_study_mode_locks_source_and_uses_arrows_space_and_current_start(
    qapp, tmp_path
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("First. Second. Third.")
    window.translation_edit.setPlainText("Первое. Второе. Третье.")
    window.transcription_edit.setPlainText("one. two. three.")
    window._set_study_mode(True)
    spoken = []
    window._play_study_row = lambda row: spoken.append(row.source)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(0)
    window.source_edit.setTextCursor(cursor)
    window.source_edit.setFocus()

    QTest.keyClick(window.source_edit, Qt.Key.Key_Down)
    QTest.keyClick(window.source_edit, Qt.Key.Key_Space)
    QTest.keyClick(window.source_edit, Qt.Key.Key_Left)

    assert window.source_edit.isReadOnly()
    assert not window.translate_button.isEnabled()
    assert window.edit_source_button.isEnabled()
    assert spoken == ["Second.", "Second.", "First."]

    started = []
    QTest.keyClick(window.source_edit, Qt.Key.Key_Right)
    window._begin_sequence = lambda rows, scope: started.append(
        ([row.source for row in rows], scope)
    )
    window._start_sequence()
    assert started == [(["Second.", "Third."], "all")]

    window.enable_source_editing()
    assert not window.source_edit.isReadOnly()
    assert window.translate_button.isEnabled()
    assert not window.edit_source_button.isEnabled()
    window._dirty = False
    window.close()


def test_compact_voice_field_and_document_status(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))

    assert window.voice_combo.width() == 380
    assert window.voice_combo.toolTip() == window.voice_combo.currentText()
    assert window.document_status_label.text() == window._t("status_new_document")
    assert window.connection_status_label.text() == window._t("status_online")

    window._set_busy(True, "working", determinate=True)
    assert not window.progress.isHidden()
    assert window.connection_status_label.text() == window._t("status_connecting")
    window._set_busy(False, "ready")
    assert window.progress.isHidden()
    assert window.connection_status_label.text() == window._t("status_online")

    window._network_unavailable = True
    window._update_document_status()
    assert window.connection_status_label.text() == window._t("status_unavailable")

    window.current_source_path = tmp_path / "lesson.txt"
    window._dirty = True
    window._update_document_status()
    assert "lesson.txt" in window.document_status_label.text()
    assert window._t("status_modified") in window.document_status_label.text()

    window._active_package_name = "lesson_ru_en"
    window._offline_package_active = True
    window._dirty = False
    window._update_document_status()
    assert window.document_status_label.text() == window._t(
        "status_package", name="lesson_ru_en"
    )
    assert window.connection_status_label.text() == window._t("status_offline")
    window.close()


def install_timed_package(window, tmp_path, lines=None):
    audio = tmp_path / "prepared.mp3"
    manifest_path = tmp_path / "prepared.json"
    srt_path = tmp_path / "prepared.srt"
    audio.write_bytes(b"complete-audio")
    manifest = TimedAudioManifest.create(
        window.current_language.key,
        window.selected_voice(),
        window.tts_settings,
        lines
        or [
            TimedLine(0, 0, 1000, "one", "un", "un"),
            TimedLine(1, 1000, 2200, "two", "deux", "deux"),
        ],
    )
    save_manifest(manifest_path, manifest)
    save_srt(srt_path, manifest)
    window.audio_path = audio
    window.audio_manifest_path = manifest_path
    window.audio_srt_path = srt_path
    window.timed_manifest = manifest
    window._audio_is_complete_document = True
    window._update_save_audio_button()
    return audio, manifest_path, srt_path, manifest


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

    assert [
        (row.index, row.source, row.translation, row.transcription)
        for row in window.sequence.rows
    ] == [
        (1, "one", "1", "1"),
        (3, "three", "3", "3"),
        (4, "four", "4", "4"),
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


def test_main_ab_range_plays_each_sentence_inside_selected_lines(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("First. Second.\nOutside.")
    window.translation_edit.setPlainText("Первое. Второе.\nСнаружи.")
    window._range_a_line = 0
    window._range_b_line = 0
    generations = []
    window._play_next_sequence_line = generations.append

    window.play_ab_range()

    assert [row.source for row in window.sequence.rows] == ["First.", "Second."]
    assert [row.translation for row in window.sequence.rows] == [
        "Первое.",
        "Второе.",
    ]
    assert [row.index for row in window.sequence.rows] == [0, 0]
    assert generations == [window.sequence.generation]

    window._stop_sequence()
    window._dirty = False
    window.close()


def test_markers_select_distinct_sentences_inside_one_realistic_paragraph(
    qapp, tmp_path
):
    window = MainWindow(SessionRepository(tmp_path))
    source = (
        "Заголовок\n\n"
        "Первое предложение. Второе предложение. Третье предложение. "
        "Четвёртое предложение. Пятое предложение.\n\nПодпись"
    )
    translation = (
        "Title\n\nFirst sentence. Second sentence. Third sentence. "
        "Fourth sentence. Fifth sentence.\n\nSignature"
    )
    window.source_edit.setPlainText(source)
    window.translation_edit.setPlainText(translation)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(source.index("Второе") + 2)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_a()
    cursor.setPosition(source.index("Четвёртое") + 2)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_b()

    assert window._range_a_line == window._range_b_line == 2
    assert window._range_a_span != window._range_b_span
    assert window.mark_a_button.text() == "A:S3"
    assert window.mark_b_button.text() == "B:S5"
    assert {
        selection.cursor.selectedText()
        for selection in window.source_edit.extraSelections()
        if selection.cursor.hasSelection()
    } == {"Второе предложение.", "Четвёртое предложение."}

    generations = []
    window._play_next_sequence_line = generations.append
    window.play_ab_range()

    assert [row.source for row in window.sequence.rows] == [
        "Второе предложение.",
        "Третье предложение.",
        "Четвёртое предложение.",
    ]
    assert [row.translation for row in window.sequence.rows] == [
        "Second sentence.",
        "Third sentence.",
        "Fourth sentence.",
    ]
    assert generations == [window.sequence.generation]

    window._stop_sequence()
    window._dirty = False
    window.close()


def test_timed_ab_uses_sentence_boundaries_inside_same_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    source = "First. Second. Third. Fourth. Fifth."
    translation = "Un. Deux. Trois. Quatre. Cinq."
    window.source_edit.setPlainText(source)
    window.translation_edit.setPlainText(translation)
    rows = build_sentence_translation_rows(source, translation)
    lines = [
        TimedLine(
            row.index,
            index * 1000,
            (index + 1) * 1000,
            row.source,
            row.translation,
            row.transcription,
            row.source_start,
            row.source_end,
            row.translation_start,
            row.translation_end,
        )
        for index, row in enumerate(rows)
    ]
    install_timed_package(window, tmp_path, lines)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(source.index("Second") + 2)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_a()
    cursor.setPosition(source.index("Fourth") + 2)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_b()
    started = []
    window._start_timed_playback = lambda start, stop, scope: started.append(
        (start, stop, scope)
    )

    window.play_ab_range()

    assert started == [(1000, 4000, "ab")]
    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_speak_and_replay_respect_active_ab_markers(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo")
    window.translation_edit.setPlainText("0\n1\n2")
    window._range_a_line = 1
    window._range_b_line = 2
    started = []
    window._start_ab_sequence = lambda: started.append("ab")

    window.speak_text()
    window.replay_audio()

    assert started == ["ab", "ab"]
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


def test_mouse_click_previews_sentence_before_each_marker_is_fixed(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    source = "First. Second. Third."
    window.source_edit.setPlainText(source)
    window.show()

    click_source_position(window, source.index("Second") + 2)
    second_span = window._marker_candidate_span
    assert second_span is not None
    assert source[slice(*second_span)] == "Second."

    click_source_position(window, source.index("First") + 2)
    first_span = window._marker_candidate_span
    assert first_span is not None
    assert source[slice(*first_span)] == "First."
    window.mark_a_button.click()
    assert window._range_a_span == first_span
    assert window._marker_candidate_span is None
    assert "#c8e6c9" in {
        selection.format.background().color().name()
        for selection in window.source_edit.extraSelections()
    }

    click_source_position(window, source.index("Third") + 2)
    third_span = window._marker_candidate_span
    assert third_span is not None
    assert window._range_a_span == first_span
    window.mark_b_button.click()
    assert window._range_b_span == third_span
    assert window._marker_candidate_span is None
    window._dirty = False
    window.close()


def test_source_change_resets_markers_and_repeat_state(qapp, tmp_path):
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
    assert not window._ab_repeat_ready
    assert not window.ab_repeat_shortcut.isEnabled()

    window._dirty = False
    window.close()


def test_stop_does_not_arm_ab_repeat(qapp, tmp_path):
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


def test_range_buttons_do_not_consume_space_as_a_button_click(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))

    for button in (
        window.mark_a_button,
        window.mark_b_button,
        window.play_ab_button,
        window.reset_ab_button,
    ):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus

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


def test_speak_uses_prepared_timestamps_for_synchronized_highlight(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)

    window.speak_text()

    assert window._timed_playback_active
    assert window._timed_playback_scope == "all"
    window._timed_position_changed(0)
    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        assert editor.extraSelections()[0].cursor.blockNumber() == 0

    window._timed_position_changed(1500)

    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        assert editor.extraSelections()[0].cursor.blockNumber() == 1

    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

    assert not window._timed_playback_active
    assert window.save_audio_button.isEnabled()


def test_opened_package_speak_and_replay_start_at_selected_study_row(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)
    window._set_study_mode(True)
    set_caret_line(window, 1)
    started = []
    window._start_timed_playback = lambda start, stop, scope: started.append(
        (start, stop, scope)
    )

    window.speak_text()
    window.replay_audio()

    assert started == [(1000, None, "all"), (1000, None, "all")]
    window._dirty = False
    window.close()


def test_offline_package_never_falls_back_to_network_synthesis(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)
    window._offline_package_active = True
    missing_row = TranslationRow(7, "missing", "absent", "absent")
    network_fallback = []
    errors = []
    window._begin_sequence = lambda rows, scope: network_fallback.append((rows, scope))
    window._show_offline_marker_error = lambda: errors.append(True)

    window._play_study_row(missing_row)

    assert errors == [True]
    assert network_fallback == []
    window._dirty = False
    window.close()

    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_sequence_and_highlight_use_sentences_inside_a_single_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("One. Two.")
    window.translation_edit.setPlainText("Un. Deux.")
    window.transcription_edit.setPlainText("Un. Deux.")
    generations = []
    window._play_next_sequence_line = generations.append

    window._start_sequence()

    assert [row.source for row in window.sequence.rows] == ["One.", "Two."]
    assert [row.translation for row in window.sequence.rows] == ["Un.", "Deux."]
    assert generations == [window.sequence.generation]

    window._show_synchronized_row(window.sequence.rows[1])
    assert window.source_edit.extraSelections()[-1].cursor.selectedText() == "Two."
    assert window.translation_edit.extraSelections()[0].cursor.selectedText() == "Deux."
    assert window.transcription_edit.extraSelections()[0].cursor.selectedText() == "Deux."

    window._stop_sequence()
    window._dirty = False
    window.close()


def test_timed_playback_moves_between_sentence_spans_on_same_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("One. Two.")
    window.translation_edit.setPlainText("Un. Deux.")
    rows = build_sentence_translation_rows("One. Two.", "Un. Deux.")
    lines = [
        TimedLine(
            row.index,
            index * 1000,
            (index + 1) * 1000,
            row.source,
            row.translation,
            row.transcription,
            row.source_start,
            row.source_end,
            row.translation_start,
            row.translation_end,
        )
        for index, row in enumerate(rows)
    ]
    install_timed_package(window, tmp_path, lines)

    window.speak_text()
    window._timed_position_changed(1500)

    assert window.source_edit.extraSelections()[-1].cursor.selectedText() == "Two."
    assert window.translation_edit.extraSelections()[0].cursor.selectedText() == "Deux."

    window.stop_audio()
    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_space_repeats_completed_timed_ab_range(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)
    window._range_a_line = 0
    window._range_b_line = 1

    window.play_ab_range()
    assert window._timed_playback_scope == "ab"
    window._finish_timed_playback()

    assert window.ab_repeat_shortcut.isEnabled()
    window.ab_repeat_shortcut.activated.emit()

    assert window._timed_playback_active
    assert window._timed_playback_scope == "ab"
    window.stop_audio()
    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_save_mp3_copies_prepared_mp3_json_and_srt(
    qapp,
    tmp_path,
    monkeypatch,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)

    selected = tmp_path / "lesson.mp3"
    target = window._language_export_path(str(selected), ".mp3")
    monkeypatch.setattr(
        "app.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(selected), ""),
    )
    window.save_audio()

    assert target.read_bytes() == b"complete-audio"
    assert target.with_suffix(".json").is_file()
    assert "\"start_ms\": 0" in target.with_suffix(".json").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in target.with_suffix(".srt").read_text(
        encoding="utf-8"
    )
    assert window._audio_is_complete_document

    window._reset_audio_state()
    window._dirty = False
    window.close()


def test_saving_opened_package_under_same_name_updates_without_same_file_error(
    qapp, tmp_path
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    install_timed_package(window, tmp_path)
    package = TimedAudioPackage(
        window.audio_path,
        window.audio_manifest_path,
        window.audio_srt_path,
        window.timed_manifest,
    )
    errors = []
    window._show_error = errors.append

    window._save_audio_package(package, package.audio_path)

    assert errors == []
    assert package.audio_path.read_bytes() == b"complete-audio"
    assert package.audio_path.with_suffix(".document.json").is_file()
    assert package.audio_path.with_suffix(".txt").is_file()
    window._reset_audio_state()
    window._dirty = False
    window.close()


@pytest.mark.parametrize(
    ("scope", "expected_audio"),
    (("range", b"deuxtrois"), ("full", b"complete-audio")),
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
    install_timed_package(
        window,
        tmp_path,
        [
            TimedLine(0, 0, 500, "one", "un", "un"),
            TimedLine(1, 500, 1000, "two", "deux", "deux"),
            TimedLine(2, 1000, 1500, "three", "trois", "trois"),
            TimedLine(3, 1500, 2000, "four", "quatre", "quatre"),
        ],
    )
    window._range_a_line = 2
    window._range_b_line = 1
    window._select_audio_export_scope = lambda: scope

    def synthesize_timed(text, _voice, output, _cancelled, *, settings=None):
        output.write_bytes(text.encode("utf-8"))
        return 500

    window.speech.synthesize_timed = synthesize_timed
    window._run_progress_task = lambda function, on_result, *_args: on_result(
        function(lambda: False, lambda *_report: None)
    )
    selected = tmp_path / f"lesson-{scope}.mp3"
    target = window._language_export_path(str(selected), ".mp3")
    monkeypatch.setattr(
        "app.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(selected), ""),
    )

    window.save_audio()

    assert target.read_bytes() == expected_audio
    assert target.with_suffix(".json").is_file()
    assert target.with_suffix(".srt").is_file()
    assert window._audio_is_complete_document

    window._reset_audio_state()
    window._dirty = False
    window.close()
