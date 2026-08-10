import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel  # noqa: E402

from app import MainWindow  # noqa: E402
from gpt01.cards import CardField, FlashcardsDialog  # noqa: E402
from gpt01.rows import build_sentence_translation_rows  # noqa: E402
from gpt01.session import SessionRepository  # noqa: E402
from gpt01.timed_audio import (  # noqa: E402
    TimedAudioManifest,
    TimedLine,
    save_manifest,
    save_srt,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_last_visible_text_window_cannot_be_hidden(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window._set_translation_window_visible(False)
    window._set_transcription_window_visible(False)

    window._set_source_window_visible(False)

    assert not window.source_box.isHidden()
    assert window._t("last_window_required") == window.statusBar().currentMessage()

    window._set_translation_window_visible(True)
    window._set_source_window_visible(False)
    assert window.source_box.isHidden()
    assert window.source_toggle_button.text().startswith("+")
    window._dirty = False
    window.close()


def test_switch_windows_uses_translation_for_european_languages(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.language_combo.setCurrentIndex(window.language_combo.findData("English"))

    window.switch_editor_windows()

    assert window.editors.widget(0) is window.translation_box
    assert window.editors.widget(1) is window.source_box
    assert window.editors.widget(2) is window.transcription_box
    window._dirty = False
    window.close()


def test_switch_windows_uses_romaji_or_pinyin_for_asian_languages(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.language_combo.setCurrentIndex(window.language_combo.findData("Japan"))

    window.switch_editor_windows()

    assert window.editors.widget(0) is window.transcription_box
    assert window.editors.widget(1) is window.source_box
    assert window.editors.widget(2) is window.translation_box
    window._dirty = False
    window.close()


def test_card_field_order_follows_window_switch_and_visibility(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.language_combo.setCurrentIndex(window.language_combo.findData("English"))
    window.source_edit.setPlainText("source")
    window.translation_edit.setPlainText("translation")
    window.transcription_edit.setPlainText("phonetics")

    assert [field.text for field in window._card_fields(0)] == [
        "source",
        "translation",
        "phonetics",
    ]
    window.switch_editor_windows()
    assert [field.text for field in window._card_fields(0)] == [
        "translation",
        "source",
        "phonetics",
    ]
    window._set_transcription_window_visible(False)
    assert [field.text for field in window._card_fields(0)] == [
        "translation",
        "source",
    ]
    assert window._card_fields(0)[0].primary
    window._set_source_window_visible(False)
    assert [field.text for field in window._card_fields(0)] == ["translation"]
    window._dirty = False
    window.close()


def test_cards_use_only_ab_range_and_start_at_source_caret(
    qapp, tmp_path, monkeypatch
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo\nthree\nfour")
    window.translation_edit.setPlainText("0\n1\n2\n3\n4")
    block = window.source_edit.document().findBlockByNumber(2)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(block.position())
    window.source_edit.setTextCursor(cursor)
    window._range_a_line = 3
    window._range_b_line = 1
    window._ab_repeat_ready = True
    window._update_ab_controls()
    assert window.ab_repeat_shortcut.isEnabled()
    spoken = []
    cycles = []
    captured = {}
    window._play_card_row = lambda row: spoken.append(row.index)
    window._play_card_range_cycle = lambda rows=None: cycles.append(
        [(row.index, row.source) for row in rows or []]
    )

    def inspect_cards(dialog: FlashcardsDialog) -> QDialog.DialogCode:
        captured["lines"] = list(dialog._line_numbers)
        captured["initial"] = dialog.current_line
        captured["badge"] = dialog.mode_badge.text()
        captured["hint"] = dialog.hint_label.text()
        captured["main_space_disabled"] = not window.ab_repeat_shortcut.isEnabled()
        captured["initial_fields"] = [
            field.text for field in dialog.current_fields()[:2]
        ]
        dialog.next_card()
        dialog.next_card()
        dialog.repeat_card()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlashcardsDialog, "exec", inspect_cards)
    window.open_cards()

    assert captured == {
        "lines": [0, 1, 2],
        "initial": 1,
        "initial_fields": ["two", "2"],
        "badge": "A–B · lines 2–4",
        "hint": (
            "← → or < > — navigate and speak   •   Space — play one A–B cycle"
            "   •   ↑ — show supporting text · ↓ — hide supporting text"
        ),
        "main_space_disabled": True,
    }
    assert spoken == [3, 1]
    assert cycles == [[(1, "one"), (2, "two"), (3, "three")]]
    assert window.ab_repeat_shortcut.isEnabled()
    window._dirty = False
    window.close()


def test_opening_ab_cards_immediately_splits_long_line_into_sentences(
    qapp, tmp_path, monkeypatch
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("First. Second. Third.")
    window.translation_edit.setPlainText("Первое. Второе. Третье.")
    window._range_a_line = 0
    window._range_b_line = 0
    captured = {}

    def inspect_cards(dialog: FlashcardsDialog) -> QDialog.DialogCode:
        captured["cards"] = list(dialog._line_numbers)
        captured["fields"] = [field.text for field in dialog.current_fields()[:2]]
        captured["position"] = dialog.position_label.text()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlashcardsDialog, "exec", inspect_cards)
    window.open_cards()

    assert captured == {
        "cards": [0, 1, 2],
        "fields": ["First.", "Первое."],
        "position": "1 / 3",
    }
    window._dirty = False
    window.close()


def test_cards_without_ab_also_open_and_navigate_by_sentence(
    qapp, tmp_path, monkeypatch
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("First. Second. Third.")
    window.translation_edit.setPlainText("Первое. Второе. Третье.")
    spoken = []
    captured = {}
    window._play_card_row = lambda row: spoken.append(row.source)

    def inspect_cards(dialog: FlashcardsDialog) -> QDialog.DialogCode:
        captured["cards"] = list(dialog._line_numbers)
        captured["fields"] = [field.text for field in dialog.current_fields()[:2]]
        captured["position"] = dialog.position_label.text()
        dialog.next_card()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlashcardsDialog, "exec", inspect_cards)
    window.open_cards()

    assert captured == {
        "cards": [0, 1, 2],
        "fields": ["First.", "Первое."],
        "position": "1 / 3",
    }
    assert spoken == ["Second."]
    window._dirty = False
    window.close()


def test_open_cards_ab_space_uses_frozen_range_only(qapp, tmp_path, monkeypatch):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("Outside zero.\nFirst. Second.\nThird.\nOutside four.")
    window.translation_edit.setPlainText("0.\nПервое. Второе.\nТретье.\n4.")
    window._range_a_line = 1
    window._range_b_line = 2
    captured = []

    def capture_cycle(rows=None):
        captured.append([(row.index, row.source) for row in rows or []])

    window._play_card_range_cycle = capture_cycle

    def inspect_cards(dialog: FlashcardsDialog) -> QDialog.DialogCode:
        dialog.repeat_card()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlashcardsDialog, "exec", inspect_cards)
    window.open_cards()

    assert captured == [[(1, "First."), (1, "Second."), (2, "Third.")]]
    window._dirty = False
    window.close()


def test_cards_ab_respect_sentence_markers_inside_one_paragraph(
    qapp, tmp_path, monkeypatch
):
    window = MainWindow(SessionRepository(tmp_path))
    source = "First. Second. Third. Fourth. Fifth."
    window.source_edit.setPlainText(source)
    window.translation_edit.setPlainText("Un. Deux. Trois. Quatre. Cinq.")
    cursor = window.source_edit.textCursor()
    cursor.setPosition(source.index("Second") + 1)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_a()
    cursor.setPosition(source.index("Fourth") + 1)
    window.source_edit.setTextCursor(cursor)
    window.set_range_marker_b()
    captured = {}

    def capture_cycle(rows=None):
        captured["cycle"] = [row.source for row in rows or []]

    window._play_card_range_cycle = capture_cycle

    def inspect_cards(dialog: FlashcardsDialog) -> QDialog.DialogCode:
        captured["count"] = len(dialog._line_numbers)
        captured["first"] = dialog.current_fields()[0].text
        captured["badge"] = dialog.mode_badge.text()
        dialog.repeat_card()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FlashcardsDialog, "exec", inspect_cards)
    window.open_cards()

    assert captured == {
        "count": 3,
        "first": "Fourth.",
        "badge": "A–B · sentences 2–4",
        "cycle": ["Second.", "Third.", "Fourth."],
    }
    window._dirty = False
    window.close()


def test_flashcard_keyboard_navigation_and_repeat(qapp):
    spoken = []
    dialog = FlashcardsDialog(
        [2, 4],
        2,
        lambda line: [CardField("Source", str(line), True)],
        spoken.append,
        title="Cards",
        close_text="Close",
    )
    dialog.show()

    QTest.keyClick(dialog, Qt.Key.Key_Right)
    QTest.keyClick(dialog, Qt.Key.Key_Space)
    QTest.keyClick(dialog, Qt.Key.Key_Left)
    QTest.mouseClick(dialog.next_button, Qt.MouseButton.LeftButton)
    QTest.keyClick(dialog, Qt.Key.Key_Space)

    assert spoken == [4, 4, 2, 4, 4]
    assert dialog.current_line == 4
    assert dialog.progress_bar.value() == 2
    dialog.close()


def test_up_and_down_toggle_supporting_card_fields_without_affecting_primary(qapp):
    dialog = FlashcardsDialog(
        [0],
        0,
        lambda _line: [
            CardField("Translation", "Primary", True, "translation"),
            CardField("Source", "Supporting", False, "source"),
            CardField("Transcription", "Phonetics", False, "transcription"),
        ],
        lambda _line: None,
        title="Cards",
        close_text="Close",
        visibility_hint="↑ show · ↓ hide",
    )
    dialog.show()

    QTest.keyClick(dialog, Qt.Key.Key_Down)
    assert not dialog.secondary_fields_visible
    visible_values = [
        label.text()
        for label in dialog.card_container.findChildren(QLabel, "cardValue")
        if not label.isHidden()
    ]
    assert visible_values == ["Primary"]

    QTest.keyClick(dialog, Qt.Key.Key_Up)
    assert dialog.secondary_fields_visible
    visible_values = [
        label.text()
        for label in dialog.card_container.findChildren(QLabel, "cardValue")
        if not label.isHidden()
    ]
    assert visible_values == ["Primary", "Supporting", "Phonetics"]
    assert "↑ show · ↓ hide" in dialog.hint_label.text()
    dialog.close()


def test_flashcard_external_line_sync_does_not_start_duplicate_audio(qapp):
    spoken = []
    dialog = FlashcardsDialog(
        [0, 2, 4],
        0,
        lambda line: [CardField("Source", str(line), True)],
        spoken.append,
        title="Cards",
        close_text="Close",
    )

    dialog.show_line(4)

    assert dialog.current_line == 4
    assert dialog.progress_bar.value() == 3
    assert spoken == []
    dialog.close()


def test_ab_flashcards_cycle_at_navigation_boundaries(qapp):
    spoken = []
    repeated = []
    dialog = FlashcardsDialog(
        [1, 3],
        3,
        lambda line: [CardField("Source", str(line), True)],
        spoken.append,
        repeat_action=lambda: repeated.append("range"),
        title="Cards",
        close_text="Close",
        cycle_navigation=True,
    )

    dialog.next_card()
    dialog.previous_card()
    dialog.repeat_card()

    assert spoken == [1, 3]
    assert repeated == ["range"]
    assert dialog.current_line == 3
    dialog.close()


def test_fast_cards_use_separate_cache_and_repeat_without_new_tts(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one")
    window.translation_edit.setPlainText("un")
    synthesized = []

    def synthesize(text, _voice, output, _cancelled, *, settings=None):
        synthesized.append(text)
        output.write_bytes(b"audio")

    window.speech.synthesize = synthesize
    window._run_task = lambda function, on_result, *_args: on_result(
        function(lambda: False)
    )
    window._play_file = lambda _filename: None

    window._play_card_line(0)
    window._media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    window._play_card_line(0)

    assert synthesized == ["un"]
    assert window.card_audio_cache.has_files
    assert not window.ab_audio_cache.has_files
    assert not window.reset_ab_button.isEnabled()
    window._stop_sequence()
    window._dirty = False
    window.close()


def test_complete_package_cards_seek_to_current_line_timestamps(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window.translation_edit.setPlainText("un\ndeux")
    audio = tmp_path / "cards.mp3"
    manifest_path = tmp_path / "cards.json"
    srt_path = tmp_path / "cards.srt"
    audio.write_bytes(b"audio")
    manifest = TimedAudioManifest.create(
        window.current_language.key,
        window.selected_voice(),
        window.tts_settings,
        [
            TimedLine(0, 0, 800, "one", "un", "un"),
            TimedLine(1, 800, 1700, "two", "deux", "deux"),
        ],
    )
    save_manifest(manifest_path, manifest)
    save_srt(srt_path, manifest)
    window.audio_path = audio
    window.audio_manifest_path = manifest_path
    window.audio_srt_path = srt_path
    window.timed_manifest = manifest
    started = []
    window._start_timed_playback = lambda start, stop, scope: started.append(
        (start, stop, scope)
    )

    window._play_card_line(1)

    assert started == [(800, 1700, "cards")]
    window._range_a_line = 0
    window._range_b_line = 1
    window._play_card_range_cycle()
    assert started[-1] == (0, 1700, "cards_range")
    window._timed_playback_active = True
    window._timed_playback_scope = "cards_range"
    window._play_card_range_cycle()
    assert started.count((0, 1700, "cards_range")) == 1
    window._timed_playback_scope = "cards"
    window.stop_audio = lambda: setattr(window, "_timed_playback_active", False)
    window._play_card_range_cycle()
    assert started.count((0, 1700, "cards_range")) == 2
    window.audio_path = None
    window._dirty = False
    window.close()


def test_fast_card_space_plays_one_ab_cycle_and_waits_for_completion(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo")
    window.translation_edit.setPlainText("0\n1\n2")
    window._range_a_line = 2
    window._range_b_line = 0
    started = []

    def begin(rows, scope):
        started.append(([row.index for row in rows], scope))
        window.sequence.active = True

    window._begin_sequence = begin

    window._play_card_range_cycle()
    window._play_card_range_cycle()
    window.sequence.active = False
    window._play_card_range_cycle()

    assert started == [([0, 1, 2], "cards_range"), ([0, 1, 2], "cards_range")]
    window.sequence.active = False
    window._dirty = False
    window.close()


def test_card_ab_cycle_displays_each_sentence_even_on_the_same_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("First. Second.\nThird.")
    window.translation_edit.setPlainText("Первое. Второе.\nТретье.")
    window._range_a_line = 0
    window._range_b_line = 1
    rows = window._card_playback_rows()
    dialog = FlashcardsDialog(
        [0, 1],
        0,
        window._card_fields,
        lambda _line: None,
        title="Cards",
        close_text="Close",
        cycle_navigation=True,
    )
    window._active_cards_dialog = dialog
    window._sequence_scope = "cards_range"
    window.sequence.start(rows)

    window._show_synchronized_row(rows[0])
    first = [field.text for field in dialog.current_fields()]
    window.sequence.advance()
    window._show_synchronized_row(rows[1])
    second = [field.text for field in dialog.current_fields()]

    assert first[:2] == ["First.", "Первое."]
    assert second[:2] == ["Second.", "Второе."]
    assert dialog.current_line == 0
    assert dialog.position_label.text() == "2 / 3"

    window.sequence.stop()
    window._sequence_scope = None
    window._active_cards_dialog = None
    dialog.close()
    window._dirty = False
    window.close()


def test_timed_card_ab_cycle_updates_sentences_on_same_line(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    source = "First. Second."
    translation = "Первое. Второе."
    window.source_edit.setPlainText(source)
    window.translation_edit.setPlainText(translation)
    rows = build_sentence_translation_rows(source, translation)
    timed_lines = [
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
    audio = tmp_path / "sentences.mp3"
    manifest_path = tmp_path / "sentences.json"
    srt_path = tmp_path / "sentences.srt"
    audio.write_bytes(b"audio")
    manifest = TimedAudioManifest.create(
        window.current_language.key,
        window.selected_voice(),
        window.tts_settings,
        timed_lines,
    )
    save_manifest(manifest_path, manifest)
    save_srt(srt_path, manifest)
    window.audio_path = audio
    window.audio_manifest_path = manifest_path
    window.audio_srt_path = srt_path
    window.timed_manifest = manifest
    dialog = FlashcardsDialog(
        [0],
        0,
        window._card_fields,
        lambda _line: None,
        title="Cards",
        close_text="Close",
        cycle_navigation=True,
    )
    window._active_cards_dialog = dialog
    window._timed_playback_active = True
    window._timed_playback_scope = "cards_range"

    window._timed_position_changed(0)
    first = [field.text for field in dialog.current_fields()]
    window._timed_position_changed(1500)
    second = [field.text for field in dialog.current_fields()]

    assert first[:2] == ["First.", "Первое."]
    assert second[:2] == ["Second.", "Второе."]
    assert dialog.position_label.text() == "2 / 2"

    window._timed_playback_active = False
    window._active_cards_dialog = None
    dialog.close()
    window._reset_audio_state()
    window._dirty = False
    window.close()
