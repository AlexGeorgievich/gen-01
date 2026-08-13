import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gpt01.waveform import WaveformDialog, WaveformWidget  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def test_waveform_boundaries_are_ordered_and_resettable():
    _app()
    widget = WaveformWidget(2000)
    changes = []
    widget.selectionChanged.connect(lambda start, end: changes.append((start, end)))

    widget.selection_state = "complete"
    widget.selection_start_ms = 900
    widget.selection_end_ms = 1300
    widget._dragging = "selection"
    widget._drag_origin_ms = 1000
    widget._drag_start_ms = 900
    widget._drag_end_ms = 1300
    widget._move_selection(1200)

    assert (widget.selection_start_ms, widget.selection_end_ms) == (1100, 1500)
    widget.reset_selection()
    assert changes[-1] == (0, 2000)


def test_space_playback_uses_absolute_selected_range(tmp_path):
    _app()
    audio = tmp_path / "line.mp3"
    audio.write_bytes(b"not-real-audio")
    played = []
    dialog = WaveformDialog(
        audio,
        5000,
        7000,
        "Current sentence",
        "Текущее предложение",
        lambda start, end: played.append((start, end)),
        lambda: None,
        title="Waveform",
        play_text="Play",
        reset_text="Reset",
        close_text="Close",
        hint_text="Hint",
    )
    dialog.waveform.selection_start_ms = 250
    dialog.waveform.selection_end_ms = 1250

    dialog.play_selection()

    assert played == [(5250, 6250)]
    dialog.reject()


def test_click_sets_start_and_shift_click_completes_selection():
    _app()
    widget = WaveformWidget(2000)
    widget.resize(1000, 260)
    widget.show()

    QTest.mouseClick(
        widget, Qt.MouseButton.LeftButton, pos=QPoint(250, 100)
    )
    assert widget.selection_state == "anchor"
    assert (widget.selection_start_ms, widget.selection_end_ms) == (500, 2000)

    QTest.mouseClick(
        widget,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPoint(750, 100),
    )
    assert widget.selection_state == "complete"
    assert (widget.selection_start_ms, widget.selection_end_ms) == (500, 1500)


def test_zoom_changes_virtual_waveform_width():
    _app()
    widget = WaveformWidget(1000)
    initial = widget.minimumWidth()
    widget.zoom_in()
    assert widget.minimumWidth() > initial
    widget.zoom_out()
    assert widget.minimumWidth() == initial
