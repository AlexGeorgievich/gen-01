from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class CardField:
    title: str
    text: str
    primary: bool = False
    kind: str = "source"


class FlashcardsDialog(QDialog):
    """Keyboard- and mouse-friendly modal navigator for synchronized lines."""

    def __init__(
        self,
        line_numbers: list[int],
        initial_line: int,
        fields_for_line: Callable[[int], list[CardField]],
        speak_line: Callable[[int], None],
        can_navigate: Callable[[], bool] | None = None,
        repeat_action: Callable[[], None] | None = None,
        *,
        title: str,
        close_text: str,
        mode_text: str = "",
        navigation_hint: str = "",
        space_hint: str = "",
        primary_font_size: int = 24,
        secondary_font_size: int = 18,
        cycle_navigation: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not line_numbers:
            raise ValueError("flashcards require at least one source line")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(960, 640)
        self.setMinimumSize(760, 500)
        self._line_numbers = line_numbers
        self._position = (
            line_numbers.index(initial_line) if initial_line in line_numbers else 0
        )
        self._fields_for_line = fields_for_line
        self._speak_line = speak_line
        self._can_navigate = can_navigate or (lambda: True)
        self._repeat_action = repeat_action
        self._primary_font_size = primary_font_size
        self._secondary_font_size = secondary_font_size
        self._cycle_navigation = cycle_navigation

        self.setStyleSheet(
            "QDialog { background: #edf2f8; }"
            "QLabel#modeBadge { background: #dce9f7; color: #285474; "
            "border: 1px solid #a9c3dc; border-radius: 12px; padding: 5px 11px; "
            "font-weight: 700; }"
            "QLabel#modeBadge[rangeActive=\"true\"] { background: #fff0c7; "
            "color: #725108; border-color: #e5bd59; }"
            "QLabel#cardPosition { color: #38536d; font-weight: 700; }"
            "QPushButton#previousCardButton, QPushButton#nextCardButton { "
            "background: #2f6fa6; color: white; border: 2px solid #7eadd2; "
            "border-radius: 34px; font-size: 34px; font-weight: 800; }"
            "QPushButton#previousCardButton:hover, QPushButton#nextCardButton:hover { "
            "background: #3986c4; border-color: #b4d7f0; }"
            "QPushButton#previousCardButton:pressed, QPushButton#nextCardButton:pressed { "
            "background: #24577f; }"
            "QPushButton#previousCardButton:disabled, QPushButton#nextCardButton:disabled { "
            "background: #c9d4df; color: #80909f; border-color: #d7e0e8; }"
            "QFrame#cardFooter { background: #f8fbff; border: 1px solid #c7d5e3; "
            "border-radius: 9px; }"
            "QLabel#cardHint { color: #52677d; }"
            "QPushButton#closeCardsButton { background: #f8fbff; color: #274761; "
            "border: 1px solid #8da9c0; border-radius: 6px; padding: 7px 20px; "
            "font-weight: 700; }"
            "QPushButton#closeCardsButton:hover { background: #e0ecf7; }"
            "QProgressBar { background: #dbe4ed; border: none; border-radius: 5px; "
            "height: 10px; color: #29445f; text-align: center; font-weight: 700; }"
            "QProgressBar::chunk { background: #3f87bd; border-radius: 5px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        self.mode_badge = QLabel(mode_text)
        self.mode_badge.setObjectName("modeBadge")
        self.mode_badge.setProperty("rangeActive", cycle_navigation)
        header.addWidget(self.mode_badge)
        header.addStretch(1)
        self.position_label = QLabel()
        self.position_label.setObjectName("cardPosition")
        header.addWidget(self.position_label)
        root.addLayout(header)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("<")
        self.previous_button.setObjectName("previousCardButton")
        self.previous_button.setFixedSize(68, 68)
        self.previous_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button = QPushButton(">")
        self.next_button.setObjectName("nextCardButton")
        self.next_button.setFixedSize(68, 68)
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.card_container = QWidget(self)
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(18, 8, 18, 8)
        self.card_layout.setSpacing(12)
        navigation.addWidget(self.previous_button, 0, Qt.AlignmentFlag.AlignVCenter)
        navigation.addWidget(self.card_container, 1)
        navigation.addWidget(self.next_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(navigation, 1)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(1, len(self._line_numbers))
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

        footer = QFrame(self)
        footer.setObjectName("cardFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(13, 8, 10, 8)
        self.hint_label = QLabel(
            "   •   ".join(item for item in (navigation_hint, space_hint) if item)
        )
        self.hint_label.setObjectName("cardHint")
        self.hint_label.setWordWrap(True)
        footer_layout.addWidget(self.hint_label, 1)
        self.close_button = QPushButton(close_text)
        self.close_button.setObjectName("closeCardsButton")
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setMinimumWidth(130)
        footer_layout.addWidget(self.close_button)
        root.addWidget(footer)

        self.previous_button.clicked.connect(self.previous_card)
        self.next_button.clicked.connect(self.next_card)
        self.close_button.clicked.connect(self.accept)
        self._render()
        self.setFocus()

    @property
    def current_line(self) -> int:
        return self._line_numbers[self._position]

    def show_line(self, line_number: int) -> None:
        """Display a synchronized line without starting another playback."""
        if line_number not in self._line_numbers or line_number == self.current_line:
            return
        self._position = self._line_numbers.index(line_number)
        self._render()

    def current_fields(self) -> list[CardField]:
        return self._fields_for_line(self.current_line)

    def previous_card(self) -> None:
        if not self._can_navigate():
            return
        if self._position <= 0:
            if not self._cycle_navigation or len(self._line_numbers) < 2:
                return
            self._position = len(self._line_numbers) - 1
        else:
            self._position -= 1
        self._render()
        self._speak_line(self.current_line)

    def next_card(self) -> None:
        if not self._can_navigate():
            return
        if self._position >= len(self._line_numbers) - 1:
            if not self._cycle_navigation or len(self._line_numbers) < 2:
                return
            self._position = 0
        else:
            self._position += 1
        self._render()
        self._speak_line(self.current_line)

    def repeat_card(self) -> None:
        if self._can_navigate():
            if self._repeat_action:
                self._repeat_action()
            else:
                self._speak_line(self.current_line)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat() and event.key() in {
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Space,
        }:
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self.previous_card()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self.next_card()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space:
            self.repeat_card()
            event.accept()
            return
        super().keyPressEvent(event)

    def _render(self) -> None:
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        fields = self.current_fields()
        self.card_layout.addStretch(1)
        palettes = {
            "source": ("#eaf3ff", "#5c91cf"),
            "translation": ("#e9f8f3", "#55aa99"),
            "transcription": ("#f3edff", "#9a7bd0"),
        }
        for field in fields:
            background, border = palettes.get(
                field.kind, ("#f8fbff", "#9fb3c6")
            )
            panel = QFrame(self.card_container)
            panel.setObjectName(f"{field.kind}CardField")
            panel.setStyleSheet(
                f"QFrame {{ background: {background}; "
                f"border: {2 if field.primary else 1}px solid {border}; "
                "border-radius: 12px; }"
                "QLabel { background: transparent; border: none; }"
            )
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 11, 18, 14)
            panel_layout.setSpacing(5)
            title = QLabel(field.title, panel)
            title.setStyleSheet(
                "font-size: 10px; font-weight: 600; color: #60758a;"
            )
            value = QLabel(field.text or "—")
            value.setObjectName("cardValue")
            value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            point_size = (
                self._primary_font_size
                if field.primary
                else self._secondary_font_size
            )
            value.setStyleSheet(
                f"font-size: {point_size}px; color: #14263a;"
            )
            value.setMinimumHeight(78 if field.primary else 54)
            panel_layout.addWidget(title)
            panel_layout.addWidget(value, 1)
            self.card_layout.addWidget(panel)
        self.card_layout.addStretch(1)
        self.position_label.setText(f"{self._position + 1} / {len(self._line_numbers)}")
        self.progress_bar.setValue(self._position + 1)
        can_cycle = self._cycle_navigation and len(self._line_numbers) > 1
        self.previous_button.setEnabled(self._position > 0 or can_cycle)
        self.next_button.setEnabled(
            self._position < len(self._line_numbers) - 1 or can_cycle
        )
