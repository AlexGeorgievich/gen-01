import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import MainWindow  # noqa: E402
from gpt01.models import TranslationRow  # noqa: E402
from gpt01.session import SessionRepository  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_markers_select_reversed_inclusive_range_and_enable_space_repeat(
    qapp,
    tmp_path,
):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\n\nthree\nfour")
    window.translation_edit.setPlainText("0\n1\n\n3\n4")
    window._last_source_pointer_line = 4
    window.set_range_marker_a()
    window._last_source_pointer_line = 1
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


def test_marker_button_uses_last_line_pointed_to_by_mouse(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo\nthree")
    window.show()
    qapp.processEvents()
    block = window.source_edit.document().findBlockByNumber(2)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(block.position())

    QTest.mouseMove(window.source_edit.viewport(), window.source_edit.cursorRect(cursor).center())
    qapp.processEvents()
    window.mark_a_button.click()

    assert window._range_a_line == 2
    assert window.mark_a_button.text() == "A:3"

    window._dirty = False
    window.close()


def test_marker_button_uses_blinking_text_cursor_without_mouse_move(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("zero\none\ntwo\nthree")
    window._last_source_pointer_line = None
    block = window.source_edit.document().findBlockByNumber(3)
    cursor = window.source_edit.textCursor()
    cursor.setPosition(block.position())

    window.source_edit.setTextCursor(cursor)
    qapp.processEvents()
    window.mark_b_button.click()

    assert window._range_b_line == 3
    assert window.mark_b_button.text() == "B:4"

    window._dirty = False
    window.close()


def test_source_change_resets_markers_and_space_repeat(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("one\ntwo")
    window._last_source_pointer_line = 0
    window.set_range_marker_a()
    window._last_source_pointer_line = 1
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
