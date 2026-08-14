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
    speeds = []
    dialog = WaveformDialog(
        audio,
        5000,
        7000,
        "Current sentence",
        "Текущее предложение",
        lambda start, end: played.append((start, end)),
        lambda: None,
        speeds.append,
        title="Waveform",
        play_text="Play",
        reset_text="Reset",
        close_text="Close",
        hint_text="Hint",
        speed_text="Speed:",
    )
    dialog.waveform.selection_start_ms = 250
    dialog.waveform.selection_end_ms = 1250

    dialog.play_selection()

    assert played == [(5250, 6250)]
    assert dialog.speed_combo.currentData() == 1.0
    assert dialog.speed_combo.findData(1.75) >= 0
    assert dialog.speed_combo.findData(2.0) >= 0
    dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData(0.75))
    assert speeds == [0.75]
    dialog.reject()
    assert speeds[-1] == 1.0


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


def test_navigation_retains_speed_and_zoom(tmp_path):
    _app()
    audio = tmp_path / "line.mp3"
    audio.write_bytes(b"not-real-audio")
    dialog = WaveformDialog(
        audio, 0, 1000, "one", "un", lambda *_: None, lambda: None, lambda *_: None,
        title="Waveform", play_text="Play", reset_text="Reset", close_text="Close",
        hint_text="Hint", speed_text="Speed:",
        navigate=lambda _offset: (1000, 2200, "two", "deux", 2, 2),
        current_position=1, total_positions=2,
    )
    dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData(1.75))
    dialog.waveform.zoom_in()
    width = dialog.waveform.minimumWidth()
    dialog._navigate(1)
    assert dialog.source_label.text() == "two"
    assert dialog.translation_label.text() == "deux"
    assert dialog.speed_combo.currentData() == 1.75
    assert dialog.waveform.minimumWidth() == width
    assert dialog.waveform.duration_ms == 1200
    dialog.reject()


def test_arrow_shortcuts_work_when_speed_combo_has_focus(tmp_path):
    app = _app()
    audio = tmp_path / "line.mp3"
    audio.write_bytes(b"not-real-audio")
    offsets = []
    dialog = WaveformDialog(
        audio, 0, 1000, "one", "un", lambda *_: None, lambda: None, lambda *_: None,
        title="Waveform", play_text="Play", reset_text="Reset", close_text="Close",
        hint_text="Hint", speed_text="Speed:",
        navigate=lambda offset: offsets.append(offset) or None,
        current_position=1, total_positions=2,
    )
    dialog.show()
    dialog.speed_combo.setFocus()
    QTest.keyClick(dialog.speed_combo, Qt.Key.Key_Right)
    app.processEvents()
    assert offsets == [1]
    dialog.reject()
