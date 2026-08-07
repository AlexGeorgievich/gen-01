import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app import MainWindow
from gpt01.session import SessionRepository


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_synchronized_line_is_highlighted_and_scrolled_into_view(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    values = "\n".join(f"line {index}" for index in range(100))
    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        editor.setPlainText(values)
        editor.verticalScrollBar().setValue(0)
    window.show()
    qapp.processEvents()

    window._show_synchronized_line(80)
    qapp.processEvents()

    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        selections = editor.extraSelections()
        assert len(selections) == 1
        assert selections[0].cursor.blockNumber() == 80
        assert editor.verticalScrollBar().value() > 0
        assert editor.textCursor().blockNumber() == 80

    window._dirty = False
    window.close()


def test_visible_synchronized_line_does_not_move_scroll_position(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    values = "\n".join(f"line {index}" for index in range(20))
    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        editor.setPlainText(values)
        editor.verticalScrollBar().setValue(0)
    window.show()
    qapp.processEvents()

    window._show_synchronized_line(1)
    qapp.processEvents()

    for editor in (
        window.source_edit,
        window.translation_edit,
        window.transcription_edit,
    ):
        assert editor.verticalScrollBar().value() == 0

    window._dirty = False
    window.close()


def test_clearing_source_window_clears_all_aligned_columns(qapp, tmp_path):
    window = MainWindow(SessionRepository(tmp_path))
    window.source_edit.setPlainText("source")
    window.translation_edit.setPlainText("translation")
    window.transcription_edit.setPlainText("transcription")

    window.source_clear_button.click()

    assert window.source_edit.toPlainText() == ""
    assert window.translation_edit.toPlainText() == ""
    assert window.transcription_edit.toPlainText() == ""
    assert window._dirty is True
    window._dirty = False
    window.close()
