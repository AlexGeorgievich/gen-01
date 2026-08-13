from __future__ import annotations

import struct
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtMultimedia import QAudioBuffer, QAudioDecoder, QAudioFormat
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class WaveformWidget(QWidget):
    selectionChanged = Signal(int, int)

    def __init__(self, duration_ms: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.duration_ms = max(1, duration_ms)
        self.amplitudes: list[float] = []
        self.selection_start_ms = 0
        self.selection_end_ms = self.duration_ms
        self.selection_state = "none"
        self.playhead_ms = 0
        self._dragging: str | None = None
        self._drag_origin_ms = 0
        self._drag_start_ms = 0
        self._drag_end_ms = self.duration_ms
        self._base_width = 820
        self._zoom = 1.0
        self.setMinimumHeight(260)
        self.setMinimumWidth(self._base_width)
        self.setMouseTracking(True)

    def set_amplitudes(self, values: list[float]) -> None:
        self.amplitudes = values
        self.update()

    def set_playhead(self, value_ms: int) -> None:
        self.playhead_ms = min(max(0, value_ms), self.duration_ms)
        self.update()

    def reset_selection(self) -> None:
        self.selection_start_ms = 0
        self.selection_end_ms = self.duration_ms
        self.selection_state = "none"
        self.selectionChanged.emit(0, self.duration_ms)
        self.update()

    def _time_at(self, x: float) -> int:
        return round(min(max(0.0, x / max(1, self.width())), 1.0) * self.duration_ms)

    def _x_at(self, value_ms: int) -> float:
        return self.width() * value_ms / self.duration_ms

    def mousePressEvent(self, event: QMouseEvent) -> None:
        value = self._time_at(event.position().x())
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            anchor = self.selection_start_ms if self.selection_state != "none" else 0
            self.selection_start_ms, self.selection_end_ms = sorted((anchor, value))
            if self.selection_end_ms - self.selection_start_ms < 50:
                self.selection_end_ms = min(
                    self.duration_ms, self.selection_start_ms + 50
                )
            self.selection_state = "complete"
            self._emit_selection()
            return
        if (
            self.selection_state == "complete"
            and self.selection_start_ms <= value <= self.selection_end_ms
        ):
            self._dragging = "selection"
            self._drag_origin_ms = value
            self._drag_start_ms = self.selection_start_ms
            self._drag_end_ms = self.selection_end_ms
            return
        self.selection_start_ms = value
        self.selection_end_ms = self.duration_ms
        self.selection_state = "anchor"
        self._dragging = None
        self._emit_selection()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._move_selection(self._time_at(event.position().x()))

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._dragging = None

    def _move_selection(self, value: int) -> None:
        delta = value - self._drag_origin_ms
        duration = self._drag_end_ms - self._drag_start_ms
        start = min(max(0, self._drag_start_ms + delta), self.duration_ms - duration)
        self.selection_start_ms = start
        self.selection_end_ms = start + duration
        self._emit_selection()

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(self.selection_start_ms, self.selection_end_ms)
        self.update()

    def zoom_in(self) -> None:
        self._set_zoom(min(8.0, self._zoom * 1.25))

    def zoom_out(self) -> None:
        self._set_zoom(max(1.0, self._zoom / 1.25))

    def _set_zoom(self, value: float) -> None:
        self._zoom = value
        self.setMinimumWidth(round(self._base_width * value))
        self.resize(self.minimumWidth(), self.height())
        self.updateGeometry()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#102b43"))
        start_x = self._x_at(self.selection_start_ms)
        end_x = self._x_at(self.selection_end_ms)
        if self.selection_state != "none":
            painter.fillRect(
                QRectF(start_x, 0, end_x - start_x, self.height()),
                QColor(46, 168, 210, 95),
            )
        middle = self.height() / 2
        if self.amplitudes:
            painter.setPen(QPen(QColor("#65d8e8"), 1.4))
            step = self.width() / max(1, len(self.amplitudes) - 1)
            for index, amplitude in enumerate(self.amplitudes):
                x = index * step
                height = amplitude * (self.height() * 0.42)
                painter.drawLine(QPointF(x, middle - height), QPointF(x, middle + height))
        else:
            painter.setPen(QColor("#a8bfd2"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "…")
        if self.selection_state != "none":
            painter.setPen(QPen(QColor("#ffd166"), 3))
            painter.drawLine(QPointF(start_x, 0), QPointF(start_x, self.height()))
            if self.selection_state == "complete":
                painter.drawLine(QPointF(end_x, 0), QPointF(end_x, self.height()))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        play_x = self._x_at(self.playhead_ms)
        painter.drawLine(QPointF(play_x, 0), QPointF(play_x, self.height()))


class WaveformDialog(QDialog):
    def __init__(
        self,
        audio_path: Path,
        absolute_start_ms: int,
        absolute_end_ms: int,
        source_text: str,
        translation_text: str,
        play_range: Callable[[int, int], None],
        stop: Callable[[], None],
        *,
        title: str,
        play_text: str,
        reset_text: str,
        close_text: str,
        hint_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(920, 470)
        self.setMinimumSize(680, 380)
        self.absolute_start_ms = absolute_start_ms
        self.absolute_end_ms = absolute_end_ms
        self._play_range = play_range
        self._stop = stop
        self._decoder = QAudioDecoder(self)
        self._bins = [0.0] * 1000
        self._decode_complete = False

        root = QVBoxLayout(self)
        translation_label = QLabel(translation_text)
        translation_label.setWordWrap(True)
        translation_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #087a6d;"
        )
        root.addWidget(translation_label)
        source_label = QLabel(source_text)
        source_label.setWordWrap(True)
        source_label.setStyleSheet("font-size: 15px; color: #52677d;")
        root.addWidget(source_label)
        self.waveform = WaveformWidget(absolute_end_ms - absolute_start_ms, self)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.waveform)
        root.addWidget(self.scroll_area, 1)
        self.range_label = QLabel()
        root.addWidget(self.range_label)
        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #52677d;")
        root.addWidget(hint)
        controls = QHBoxLayout()
        play_button = QPushButton(play_text)
        reset_button = QPushButton(reset_text)
        close_button = QPushButton(close_text)
        controls.addWidget(play_button)
        controls.addWidget(reset_button)
        controls.addStretch(1)
        controls.addWidget(close_button)
        root.addLayout(controls)
        play_button.clicked.connect(self.play_selection)
        reset_button.clicked.connect(self.waveform.reset_selection)
        close_button.clicked.connect(self.reject)
        self.waveform.selectionChanged.connect(self._update_range_label)
        self._update_range_label(0, self.waveform.duration_ms)

        self._decoder.bufferReady.connect(self._read_buffer)
        self._decoder.finished.connect(self._decoding_finished)
        self._decoder.setSource(QUrl.fromLocalFile(str(audio_path)))
        self._decoder.start()

    def _update_range_label(self, start_ms: int, end_ms: int) -> None:
        self.range_label.setText(f"{start_ms / 1000:.3f} s — {end_ms / 1000:.3f} s")

    def _read_buffer(self) -> None:
        buffer = self._decoder.read()
        if not buffer.isValid():
            return
        self._accumulate(buffer)

    def _accumulate(self, buffer: QAudioBuffer) -> None:
        fmt = buffer.format()
        channels = max(1, fmt.channelCount())
        sample_format = fmt.sampleFormat()
        specs = {
            QAudioFormat.SampleFormat.UInt8: ("B", 128.0, 128.0),
            QAudioFormat.SampleFormat.Int16: ("h", 0.0, 32768.0),
            QAudioFormat.SampleFormat.Int32: ("i", 0.0, 2147483648.0),
            QAudioFormat.SampleFormat.Float: ("f", 0.0, 1.0),
        }
        spec = specs.get(sample_format)
        if spec is None or fmt.sampleRate() <= 0:
            return
        code, center, scale = spec
        raw = bytes(buffer.data())
        size = struct.calcsize(code)
        usable = len(raw) - len(raw) % size
        values = struct.iter_unpack("<" + code, raw[:usable])
        start_ms = buffer.startTime() / 1000
        if start_ms > self.absolute_end_ms:
            self._decoder.stop()
            self._decoding_finished()
            return
        frame = 0
        channel_peak = 0.0
        for sample_index, (sample,) in enumerate(values):
            channel_peak = max(channel_peak, min(1.0, abs(float(sample) - center) / scale))
            if (sample_index + 1) % channels:
                continue
            position_ms = start_ms + frame * 1000 / fmt.sampleRate()
            frame += 1
            if self.absolute_start_ms <= position_ms <= self.absolute_end_ms:
                relative = position_ms - self.absolute_start_ms
                index = min(999, int(relative * 1000 / self.waveform.duration_ms))
                self._bins[index] = max(self._bins[index], channel_peak)
            channel_peak = 0.0

    def _decoding_finished(self) -> None:
        if self._decode_complete:
            return
        self._decode_complete = True
        maximum = max(self._bins, default=0.0)
        if maximum > 0:
            self.waveform.set_amplitudes([value / maximum for value in self._bins])

    def play_selection(self) -> None:
        self._play_range(
            self.absolute_start_ms + self.waveform.selection_start_ms,
            self.absolute_start_ms + self.waveform.selection_end_ms,
        )

    def set_absolute_playhead(self, position_ms: int) -> None:
        self.waveform.set_playhead(position_ms - self.absolute_start_ms)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.play_selection()
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() in {Qt.Key.Key_Plus, Qt.Key.Key_Equal}:
                self.waveform.zoom_in()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Minus:
                self.waveform.zoom_out()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self) -> None:
        self._decoder.stop()
        self._stop()
        super().reject()
