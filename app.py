from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import edge_tts
from PySide6.QtCore import QByteArray, QEvent, QObject, Qt, QUrl, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QIcon,
    QKeySequence,
    QShortcut,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gpt01.audio_cache import LineAudioCache
from gpt01.batch import BatchProcessor, BatchResult
from gpt01.cards import CardField, FlashcardsDialog
from gpt01.errors import AppError, OperationCancelled
from gpt01.exporting import (
    ExportKind,
    ExportLayout,
    export_document,
)
from gpt01.french_grammar import FrenchArticleMode
from gpt01.i18n import ui_text
from gpt01.language_controller import LanguageController
from gpt01.languages import LANGUAGES
from gpt01.models import Document, SubtitleCue, TranslationRow
from gpt01.packages import (
    PackageHistoryEntry,
    discover_packages,
    load_offline_package,
    load_package_history,
    save_package_document,
    save_package_history,
    touch_package_history,
)
from gpt01.playback import PlaybackSequence
from gpt01.preferences import AudioPreparationMode, Preferences
from gpt01.rows import (
    build_sentence_translation_rows,
    build_translation_rows,
    rows_between,
)
from gpt01.sentences import sentence_spans
from gpt01.services import EdgeSpeechProvider
from gpt01.session import SessionRepository
from gpt01.state import AppState
from gpt01.storage import load_document, save_document
from gpt01.structured_translation import (
    StructuredTranslationResult,
    translate_preserving_layout,
)
from gpt01.tasks import TaskManager
from gpt01.timed_audio import (
    TimedAudioManifest,
    TimedAudioPackage,
    TimedLine,
    build_timed_audio_package,
    load_manifest,
)
from gpt01.tts import TtsSettings
from gpt01.version import (
    APP_AUTHOR,
    APP_DISPLAY_NAME,
    APP_NAME,
    APP_ORGANIZATION,
    __version__,
)
from gpt01.waveform import WaveformDialog

APP_TITLE = APP_DISPLAY_NAME
VOICE_LOAD_TIMEOUT_SECONDS = 15
TTS_TIMEOUT_SECONDS = 90
APPLICATION_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_ICON_PATH = BUNDLE_ROOT / "assets" / "voicegun-icon-v2.png"
HELP_PATHS = {
    "en": BUNDLE_ROOT / "docs" / "USER_GUIDE_EN.md",
    "ru": BUNDLE_ROOT / "docs" / "USER_GUIDE_RU.md",
}
SMOKE_TEST_MODE = "--smoke-test" in sys.argv
LOG_PATH = (
    Path(tempfile.gettempdir()) / "voicegun_smoke.log"
    if SMOKE_TEST_MODE
    else APPLICATION_ROOT / "voicegun.log"
)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _span(start: int | None, end: int | None) -> tuple[int, int] | None:
    if start is None or end is None or end <= start:
        return None
    return start, end


def _row_overlaps_span(row: TranslationRow, span: tuple[int, int]) -> bool:
    if row.source_start is None or row.source_end is None:
        return False
    return row.source_start < span[1] and row.source_end > span[0]


def _timed_matches_row(timed: TimedLine, row: TranslationRow) -> bool:
    if timed.line != row.index:
        return False
    if timed.source_start is not None and row.source_start is not None:
        return timed.source_start == row.source_start
    return True


class MainWindow(QMainWindow):
    def __init__(self, repository: SessionRepository | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1280, 760)
        self.tasks = TaskManager(self)
        self._closing = False
        self._dirty = False
        self._loading_document = False
        self._hover_line_number: int | None = None
        self._marker_candidate_line: int | None = None
        self._marker_candidate_span: tuple[int, int] | None = None
        self._audio_line_number: int | None = None
        self._replay_highlight_line: int | None = None
        self._replay_source_span: tuple[int, int] | None = None
        self._replay_translation_span: tuple[int, int] | None = None
        self._replay_transcription_span: tuple[int, int] | None = None
        self._range_a_line: int | None = None
        self._range_b_line: int | None = None
        self._range_a_span: tuple[int, int] | None = None
        self._range_b_span: tuple[int, int] | None = None
        self._range_a_sentence_number: int | None = None
        self._range_b_sentence_number: int | None = None
        self._sequence_scope: str | None = None
        self._sequence_audio_parts: list[Path] = []
        self._ab_repeat_ready = False
        self.ab_audio_cache = LineAudioCache()
        self.card_audio_cache = LineAudioCache()
        self.sequence = PlaybackSequence()
        self._switching_language = False
        self.panels_swapped = False
        self._active_cards_dialog: FlashcardsDialog | None = None
        self._active_waveform_dialog: WaveformDialog | None = None
        self.repository = repository or SessionRepository.for_application(APPLICATION_ROOT)
        self.preferences = self.repository.load_preferences()
        self.language_controller = LanguageController(
            self.repository.load_selected_language(),
            self.preferences.source_language_key,
            self.preferences.french_article_mode,
            self.repository.french_lexicon_path(),
        )
        self.current_source_path: Path | None = None
        self._active_package_name: str | None = None
        self.subtitle_cues: tuple[SubtitleCue, ...] = ()
        self.audio_path: Path | None = None
        self.audio_manifest_path: Path | None = None
        self.audio_srt_path: Path | None = None
        self.timed_manifest: TimedAudioManifest | None = None
        self._timed_playback_active = False
        self._timed_playback_scope: str | None = None
        self._timed_stop_ms: int | None = None
        self._timed_pending_start_ms: int | None = None
        self._audio_is_complete_document = False
        self._offline_package_active = False
        self._network_unavailable = False
        self._busy_indicator_active = False
        self._study_mode = False
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.9)
        self.speech = EdgeSpeechProvider(TTS_TIMEOUT_SECONDS)
        self.tts_settings = TtsSettings()
        self.audio_preparation_mode = AudioPreparationMode.FAST_LINE.value

        self.source_edit = QTextEdit()
        self.source_edit.setPlaceholderText(self._t("source_placeholder"))
        self.source_edit.viewport().setMouseTracking(True)
        self.source_edit.viewport().installEventFilter(self)
        self.source_edit.installEventFilter(self)
        self.translation_edit = QTextEdit()
        self.translation_edit.setPlaceholderText(self._t("translation_placeholder"))
        self.translation_edit.setAcceptRichText(False)
        self.transcription_edit = QTextEdit()
        self.transcription_edit.setPlaceholderText(self._t("transcription_placeholder"))
        self.transcription_edit.setAcceptRichText(False)

        self.source_title = QLabel(self._t("source_text"))
        self.translation_title = QLabel(self._t("translation"))
        self.transcription_title = QLabel(self._t("transcription"))
        for title in (self.source_title, self.translation_title, self.transcription_title):
            title.setStyleSheet("font-weight: 600;")
        self.source_clear_button = QPushButton(self._t("clear"))
        self.edit_source_button = QPushButton(self._t("edit_source"))
        self.edit_source_button.setToolTip(self._t("edit_source_tip"))
        self.translation_clear_button = QPushButton(self._t("clear"))
        self.transcription_clear_button = QPushButton(self._t("clear"))
        for button in (
            self.source_clear_button,
            self.translation_clear_button,
            self.transcription_clear_button,
        ):
            button.setMaximumWidth(90)

        self.open_button = QPushButton(self._t("open"))
        self.open_menu = QMenu(self.open_button)
        self.open_text_action = self.open_menu.addAction(self._t("open_text_menu"))
        self.batch_translation_action = self.open_menu.addAction(
            self._t("batch_translation")
        )
        self.text_packages_menu = self.open_menu.addMenu(self._t("text_packages"))
        self.open_package_action = self.text_packages_menu.addAction(
            self._t("open_package")
        )
        self.package_history_action = self.text_packages_menu.addAction(
            self._t("package_history")
        )
        self.open_button.setMenu(self.open_menu)
        self.translate_button = QPushButton(self._t("translate"))
        self.speak_button = QPushButton(self._t("speak"))
        self.replay_button = QPushButton(self._t("replay"))
        self.replay_button.setEnabled(False)
        self.stop_button = QPushButton(self._t("stop"))
        self.stop_button.setEnabled(False)
        self.cancel_button = QPushButton(self._t("cancel_operation"))
        self.cancel_button.setEnabled(False)
        self.save_audio_button = QPushButton(self._t("save_mp3"))
        self.save_audio_button.setEnabled(False)
        self.save_button = QPushButton(self._t("save_text"))
        self.settings_button = QPushButton(self._t("settings"))
        self.help_button = QPushButton(self._t("help"))

        self.language_combo = QComboBox()
        self.voice_combo = QComboBox()
        self.voice_status = QLabel()
        self.voice_status.setWordWrap(True)
        self.reload_voices_button = QPushButton(self._t("refresh_voices"))
        self.transcription_toggle_button = QPushButton("−")
        self.transcription_toggle_button.setToolTip(self._t("hide_transcription"))
        self.transcription_toggle_button.setFixedWidth(32)
        self.translation_toggle_button = QPushButton("−")
        self.translation_toggle_button.setToolTip(self._t("hide_translation"))
        self.translation_toggle_button.setFixedWidth(32)
        self.source_toggle_button = QPushButton("−")
        self.source_toggle_button.setToolTip(self._t("hide_source"))
        self.source_toggle_button.setFixedWidth(32)
        self.switch_windows_button = QPushButton(self._t("switch_windows"))
        self.cards_button = QPushButton(self._t("cards"))
        self.mark_a_button = QPushButton("A")
        self.mark_a_button.setToolTip(self._t("mark_a_tip"))
        self.mark_b_button = QPushButton("B")
        self.mark_b_button.setToolTip(self._t("mark_b_tip"))
        self.play_ab_button = QPushButton("A–B")
        self.play_ab_button.setToolTip(self._t("play_ab_tip"))
        self.play_ab_button.setEnabled(False)
        self.reset_ab_button = QPushButton(self._t("reset"))
        self.reset_ab_button.setToolTip(self._t("reset_ab_tip"))
        self.reset_ab_button.setEnabled(False)
        for button in (
            self.mark_a_button,
            self.mark_b_button,
            self.play_ab_button,
            self.reset_ab_button,
        ):
            button.setMinimumWidth(48)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._build_ui()
        self._populate_languages()
        self._connect_signals()
        self.repository.ensure_language_directory(self.current_language)
        cached_voices = self._load_cached_voices()
        self._populate_voices(cached_voices)
        if self.repository.voice_cache_path(self.current_language).exists():
            self.voice_status.setText(self._t("cached_voices", count=len(cached_voices)))
        else:
            self.voice_status.setText(self._t("built_in_voices"))
        self._update_language_labels()
        self._restore_app_state()
        self._apply_editor_font_size()
        self._update_ab_controls()
        self._apply_interface_language()

    @property
    def current_language(self):
        return self.language_controller.profile

    def _t(self, key: str, **values: object) -> str:
        return ui_text(self.preferences.interface_language, key, **values)

    def _language_label(self, key: str) -> str:
        return self._t(f"language_{key}")

    @property
    def translator(self):
        return self.language_controller.translator

    def _apply_editor_font_size(self) -> None:
        for editor in (self.source_edit, self.translation_edit, self.transcription_edit):
            font = editor.font()
            font.setPointSize(self.preferences.editor_font_size)
            editor.setFont(font)
            editor.document().setDefaultFont(font)

    def _populate_languages(self) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        selected_index = 0
        for index, profile in enumerate(LANGUAGES):
            self.language_combo.addItem(self._language_label(profile.key), profile.key)
            if profile.key == self.current_language.key:
                selected_index = index
        self.language_combo.setCurrentIndex(selected_index)
        self.language_combo.blockSignals(False)

    def _language_export_path(self, selected: str, extension: str) -> Path:
        """Place a user-named export in the active language directory."""
        return self.repository.export_path(self.current_language, selected, extension)

    def _open_dialog_directory(self) -> str:
        directory = Path(self.preferences.last_open_directory)
        return str(directory) if self.preferences.last_open_directory and directory.is_dir() else ""

    def _export_dialog_path(self, stem: str, extension: str) -> Path:
        suggested = self._language_export_path(stem, extension)
        remembered = Path(self.preferences.last_export_directory)
        if self.preferences.last_export_directory and remembered.is_dir():
            try:
                if remembered.resolve() == suggested.parent.resolve():
                    return remembered / suggested.name
            except OSError:
                pass
        return suggested

    def _remember_directory(self, field: str, directory: Path) -> None:
        value = str(directory.resolve())
        if getattr(self.preferences, field) == value:
            return
        setattr(self.preferences, field, value)
        try:
            self.repository.save_preferences(self.preferences)
        except OSError:
            LOGGER.warning("Could not save recent directory: %s", directory)

    def _update_language_labels(self) -> None:
        self.translation_title.setText(
            f"{self._t('translation')} — {self._language_label(self.current_language.key)}"
        )
        mode_names_en = {
            "pinyin": "Pinyin",
            "romaji": "Romaji",
            "ipa_en": "IPA (English)",
            "ipa_fr": "IPA (French)",
            "ipa_es": "IPA (Spanish)",
            "ipa_de": "IPA (German)",
            "ipa_it": "IPA (Italian)",
            "ipa_tr": "IPA (Turkish)",
            "ipa_ru": "IPA (Russian)",
        }
        mode_names_ru = {**mode_names_en, "pinyin": "пиньинь", "romaji": "ромадзи"}
        mode_names = (
            mode_names_ru if self.preferences.interface_language == "ru" else mode_names_en
        )
        mode_name = mode_names[self.current_language.transcription_mode]
        self.transcription_title.setText(f"{self._t('transcription')} — {mode_name}")

    def _apply_interface_language(self) -> None:
        self.setWindowTitle(self._t("app_title"))
        self.source_edit.setPlaceholderText(self._t("source_placeholder"))
        self.translation_edit.setPlaceholderText(self._t("translation_placeholder"))
        self.transcription_edit.setPlaceholderText(self._t("transcription_placeholder"))
        self.source_title.setText(self._t("source_text"))
        self.edit_source_button.setText(self._t("edit_source"))
        self.edit_source_button.setToolTip(self._t("edit_source_tip"))
        self.open_button.setText(self._t("open"))
        self.open_text_action.setText(self._t("open_text_menu"))
        self.text_packages_menu.setTitle(self._t("text_packages"))
        self.open_package_action.setText(self._t("open_package"))
        self.package_history_action.setText(self._t("package_history"))
        self.batch_translation_action.setText(self._t("batch_translation"))
        self.translate_button.setText(self._t("translate"))
        self.speak_button.setText(self._t("speak"))
        self.replay_button.setText(self._t("replay"))
        self.stop_button.setText(self._t("stop"))
        self.cancel_button.setText(self._t("cancel_operation"))
        self.save_audio_button.setText(self._t("save_mp3"))
        self.save_button.setText(self._t("save_text"))
        self.settings_button.setText(self._t("settings"))
        self.help_button.setText(self._t("help"))
        for button in (
            self.source_clear_button,
            self.translation_clear_button,
            self.transcription_clear_button,
        ):
            button.setText(self._t("clear"))
        self.voice_box.setTitle(self._t("language_and_voice"))
        self.language_label.setText(self._t("language"))
        self.voice_label.setText(self._t("voice"))
        self.reload_voices_button.setText(self._t("refresh_voices"))
        self.range_control_label.setText(self._t("playback_range"))
        self.mark_a_button.setToolTip(self._t("mark_a_tip"))
        self.mark_b_button.setToolTip(self._t("mark_b_tip"))
        self.play_ab_button.setToolTip(self._t("play_ab_tip"))
        self.reset_ab_button.setText(self._t("reset"))
        self.reset_ab_button.setToolTip(self._t("reset_ab_tip"))
        self.switch_windows_button.setText(self._t("switch_windows"))
        self.cards_button.setText(self._t("cards"))
        self._populate_languages()
        cached_voices = self._load_cached_voices()
        self.voice_status.setText(self._t("cached_voices", count=len(cached_voices)))
        self._update_language_labels()
        self._set_translation_window_visible(not self.translation_box.isHidden())
        self._set_transcription_window_visible(not self.transcription_box.isHidden())
        self._set_source_window_visible(not self.source_box.isHidden())
        self._update_voice_tooltip()
        self._update_document_status()

    @Slot()
    def _on_language_changed(self) -> None:
        if self._switching_language:
            return
        key = str(self.language_combo.currentData() or "")
        profile = next((item for item in LANGUAGES if item.key == key), self.current_language)
        if profile.key == self.current_language.key:
            return

        self._switching_language = True
        try:
            self.stop_current_operation()
            self._save_app_state()
            previous_audio = self.audio_path
            self.player.setSource(QUrl())
            self.repository.delete_temporary_audio(previous_audio)
            self.audio_path = None

            self.language_controller.select_target(profile.key)
            self.repository.ensure_language_directory(self.current_language)
            self._update_language_labels()
            self._populate_voices(self._load_cached_voices())
            self._restore_app_state()
            self.repository.save_selected_language(profile.key)
            voices = self._load_cached_voices()
            self.voice_status.setText(self._t("cached_voices", count=len(voices)))
        except OSError as exc:
            LOGGER.exception("Could not switch language")
            self._show_error(str(exc))
        finally:
            self._switching_language = False

    def _load_cached_voices(self) -> list[dict[str, Any]]:
        return self.repository.load_voices(self.current_language)

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Commands")
        toolbar.setMovable(False)
        toolbar.addWidget(self.open_button)
        toolbar.addSeparator()
        toolbar.addWidget(self.translate_button)
        toolbar.addWidget(self.speak_button)
        toolbar.addWidget(self.replay_button)
        toolbar.addWidget(self.stop_button)
        toolbar.addWidget(self.cancel_button)
        toolbar.addSeparator()
        toolbar.addWidget(self.save_audio_button)
        toolbar.addWidget(self.save_button)
        toolbar.addSeparator()
        toolbar.addWidget(self.settings_button)
        toolbar_spacer = QWidget()
        toolbar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(toolbar_spacer)
        toolbar.addWidget(self.help_button)

        self.source_box = QGroupBox()
        self.source_box.setObjectName("sourcePanel")
        source_layout = QVBoxLayout(self.source_box)
        self.source_header = QHBoxLayout()
        self.source_header.addWidget(self.source_title)
        self.source_header.addStretch(1)
        self.source_header.addWidget(self.edit_source_button)
        self.source_header.addWidget(self.source_toggle_button)
        self.source_header.addWidget(self.source_clear_button)
        source_layout.addLayout(self.source_header)
        source_layout.addWidget(self.source_edit)

        self.translation_box = QGroupBox()
        self.translation_box.setObjectName("translationPanel")
        translation_layout = QVBoxLayout(self.translation_box)
        self.translation_header = QHBoxLayout()
        self.translation_header.addWidget(self.translation_title)
        self.translation_header.addStretch(1)
        self.translation_header.addWidget(self.translation_toggle_button)
        self.translation_header.addWidget(self.translation_clear_button)
        translation_layout.addLayout(self.translation_header)
        translation_layout.addWidget(self.translation_edit)

        self.transcription_box = QGroupBox()
        self.transcription_box.setObjectName("transcriptionPanel")
        transcription_layout = QVBoxLayout(self.transcription_box)
        self.transcription_header = QHBoxLayout()
        self.transcription_header.addWidget(self.transcription_title)
        self.transcription_header.addStretch(1)
        self.transcription_header.addWidget(self.transcription_toggle_button)
        self.transcription_header.addWidget(self.transcription_clear_button)
        transcription_layout.addLayout(self.transcription_header)
        transcription_layout.addWidget(self.transcription_edit)

        self.editors = QSplitter()
        self.editors.addWidget(self.source_box)
        self.editors.addWidget(self.translation_box)
        self.editors.addWidget(self.transcription_box)
        self.editors.setSizes([420, 420, 420])
        self.editors.setHandleWidth(7)

        window_controls = QHBoxLayout()
        self.collapsed_panels_layout = QHBoxLayout()
        window_controls.addLayout(self.collapsed_panels_layout)
        window_controls.addWidget(self.switch_windows_button)
        window_controls.addWidget(self.cards_button)
        window_controls.addSpacing(10)
        self.range_control_label = QLabel(self._t("playback_range"))
        self.range_control_label.setStyleSheet("font-weight: 600;")
        window_controls.addWidget(self.range_control_label)
        window_controls.addWidget(self.mark_a_button)
        window_controls.addWidget(self.mark_b_button)
        window_controls.addWidget(self.play_ab_button)
        window_controls.addWidget(self.reset_ab_button)
        window_controls.addStretch(1)

        self.voice_box = QGroupBox(self._t("language_and_voice"))
        self.voice_box.setObjectName("voicePanel")
        voice_box_layout = QHBoxLayout(self.voice_box)
        voice_box_layout.setContentsMargins(10, 8, 10, 8)
        self.language_label = QLabel(self._t("language"))
        self.voice_label = QLabel(self._t("voice"))
        voice_box_layout.addWidget(self.language_label)
        voice_box_layout.addWidget(self.language_combo)
        voice_box_layout.addWidget(self.voice_label)
        voice_box_layout.addWidget(self.voice_combo)
        voice_box_layout.addStretch(1)
        voice_box_layout.addWidget(self.voice_status)
        voice_box_layout.addWidget(self.reload_voices_button)
        self.language_combo.setMinimumWidth(105)
        self.voice_combo.setFixedWidth(380)
        self.voice_status.setMaximumWidth(245)

        central = QWidget()
        central.setObjectName("centralWorkspace")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(7)
        layout.addWidget(self.voice_box)
        layout.addLayout(window_controls)
        layout.addWidget(self.editors, 1)
        self.setCentralWidget(central)
        central.setStyleSheet(
            "QWidget#centralWorkspace { background: #e9eff7; }"
            "QGroupBox#voicePanel { background: #f8fbff; border: 1px solid #b8c9dc; "
            "border-radius: 9px; margin-top: 7px; padding-top: 7px; }"
            "QGroupBox#voicePanel::title { color: #29445f; subcontrol-origin: margin; "
            "left: 12px; padding: 0 5px; font-weight: 600; }"
            "QGroupBox#sourcePanel { background: #eef4ff; border: 2px solid #7aa7e8; "
            "border-radius: 10px; }"
            "QGroupBox#translationPanel { background: #edf9f6; border: 2px solid #65b9aa; "
            "border-radius: 10px; }"
            "QGroupBox#transcriptionPanel { background: #f5f0ff; border: 2px solid #a98add; "
            "border-radius: 10px; }"
            "QTextEdit { background: #ffffff; color: #172433; border: 1px solid #bdcad8; "
            "border-radius: 7px; padding: 6px; selection-background-color: #ffd65a; "
            "selection-color: #172433; }"
            "QTextEdit:focus { border: 2px solid #397dcc; }"
            "QPushButton { background: #f8fbff; color: #20364d; border: 1px solid #aebfd1; "
            "border-radius: 5px; padding: 4px 9px; }"
            "QPushButton:hover { background: #e0ecfa; border-color: #5f8fc4; }"
            "QPushButton:pressed { background: #cbdff4; }"
            "QPushButton:disabled { color: #8996a5; background: #e7ecf2; "
            "border-color: #cad3dc; }"
            "QComboBox, QSpinBox { background: white; color: #172433; "
            "border: 1px solid #aebfd1; border-radius: 5px; padding: 4px 7px; }"
            "QComboBox QAbstractItemView { background: #ffffff; color: #172433; "
            "selection-background-color: #397dcc; selection-color: #ffffff; "
            "border: 1px solid #8fa8c1; outline: 0; }"
            "QComboBox QAbstractItemView::item { color: #172433; "
            "background: #ffffff; min-height: 24px; padding: 3px 7px; }"
            "QComboBox QAbstractItemView::item:selected { color: #ffffff; "
            "background: #397dcc; }"
        )
        self.source_title.setStyleSheet("color: #245ea8; font-weight: 700;")
        self.translation_title.setStyleSheet("color: #087a6d; font-weight: 700;")
        self.transcription_title.setStyleSheet("color: #6841a5; font-weight: 700;")
        self._apply_panel_shadows()
        toolbar.setStyleSheet(
            "QToolBar { background: #274761; border: none; spacing: 4px; padding: 6px; }"
            "QToolBar QPushButton { background: #365d7b; color: #f7fbff; "
            "border: 1px solid #527895; border-radius: 5px; padding: 5px 10px; }"
            "QToolBar QPushButton:hover { background: #44779b; border-color: #86b2d0; }"
            "QToolBar QPushButton:pressed { background: #1f3b52; }"
            "QToolBar QPushButton:disabled { background: #304c63; color: #91a4b4; "
            "border-color: #466278; }"
            "QToolBar::separator { background: #69859a; width: 1px; margin: 5px 4px; }"
        )
        self.translate_button.setStyleSheet(
            "QPushButton { background: #1487d4; color: white; font-weight: 700; "
            "padding: 5px 13px; border: 1px solid #60b7ec; border-radius: 5px; }"
            "QPushButton:hover { background: #22a0ed; }"
            "QPushButton:pressed { background: #0c6fab; }"
            "QPushButton:disabled { background: #42647f; color: #8fa5b7; "
            "border-color: #526f87; }"
        )

        status = QStatusBar()
        self.document_status_label = QLabel()
        self.document_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.document_status_label.setMinimumWidth(260)
        self.connection_status_label = QLabel()
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.connection_status_label.setMinimumWidth(150)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.hide()
        status.addPermanentWidget(self.document_status_label, 1)
        status.addPermanentWidget(self.connection_status_label)
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)
        self.statusBar().showMessage(self._t("ready"))
        self._update_document_status()

    def _apply_panel_shadows(self) -> None:
        self._panel_shadows: list[QGraphicsDropShadowEffect] = []
        for panel in (
            self.source_box,
            self.translation_box,
            self.transcription_box,
        ):
            shadow = QGraphicsDropShadowEffect(panel)
            shadow.setBlurRadius(22.0)
            shadow.setOffset(0.0, 4.0)
            shadow.setColor(QColor(27, 52, 77, 72))
            panel.setGraphicsEffect(shadow)
            self._panel_shadows.append(shadow)

    def _connect_signals(self) -> None:
        self.open_text_action.triggered.connect(self.open_file)
        self.open_package_action.triggered.connect(self.open_package)
        self.package_history_action.triggered.connect(self.open_package_history)
        self.batch_translation_action.triggered.connect(self.batch_process_files)
        self.translate_button.clicked.connect(self.translate_text)
        self.edit_source_button.clicked.connect(self.enable_source_editing)
        self.speak_button.clicked.connect(self.speak_text)
        self.replay_button.clicked.connect(self.replay_audio)
        self.stop_button.clicked.connect(self.stop_current_operation)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.save_audio_button.clicked.connect(self.save_audio)
        self.save_button.clicked.connect(self.save_file)
        self.settings_button.clicked.connect(self.open_settings)
        self.help_button.clicked.connect(self.open_help)
        self.reload_voices_button.clicked.connect(self.load_voices)
        self.transcription_toggle_button.clicked.connect(self._toggle_transcription_window)
        self.translation_toggle_button.clicked.connect(self._toggle_translation_window)
        self.source_toggle_button.clicked.connect(self._toggle_source_window)
        self.switch_windows_button.clicked.connect(self.switch_editor_windows)
        self.cards_button.clicked.connect(self.open_cards)
        self.mark_a_button.clicked.connect(self.set_range_marker_a)
        self.mark_b_button.clicked.connect(self.set_range_marker_b)
        self.play_ab_button.clicked.connect(self.play_ab_range)
        self.reset_ab_button.clicked.connect(self.reset_ab_range)
        self.source_clear_button.clicked.connect(self.clear_source_window)
        self.translation_clear_button.clicked.connect(self.clear_translation_window)
        self.transcription_clear_button.clicked.connect(self.clear_transcription_window)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.voice_combo.currentTextChanged.connect(self._update_voice_tooltip)
        self.translation_edit.textChanged.connect(self._on_translation_changed)
        self.source_edit.textChanged.connect(self._on_source_text_changed)
        self.transcription_edit.textChanged.connect(self._on_text_changed)
        self.line_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.line_shortcut.activated.connect(self.speak_line_at_cursor)
        self.ab_repeat_shortcut = QShortcut(QKeySequence("Space"), self)
        self.waveform_shortcut = QShortcut(QKeySequence("F10"), self)
        self.ab_repeat_shortcut.setEnabled(False)
        self.ab_repeat_shortcut.activated.connect(self.repeat_ab_range)
        self.waveform_shortcut.activated.connect(self.open_current_waveform)
        self.open_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.open_shortcut.activated.connect(self.open_file)
        self.help_shortcut = QShortcut(QKeySequence("F1"), self)
        self.help_shortcut.activated.connect(self.open_help)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.positionChanged.connect(self._timed_position_changed)
        self.player.errorOccurred.connect(
            lambda _error, message: self._show_error(
                self._t("playback_error", message=message)
            )
        )

    @Slot()
    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("settings_title"))
        dialog.setMinimumWidth(440)
        form = QFormLayout(dialog)

        interface_combo = QComboBox(dialog)
        interface_combo.addItem("English", "en")
        interface_combo.addItem("Русский", "ru")
        interface_index = interface_combo.findData(self.preferences.interface_language)
        interface_combo.setCurrentIndex(max(0, interface_index))

        source_combo = QComboBox(dialog)
        source_combo.addItem(self._t("auto_detect"), "auto")
        for profile in LANGUAGES:
            source_combo.addItem(self._language_label(profile.key), profile.key)
        source_index = source_combo.findData(self.preferences.source_language_key)
        source_combo.setCurrentIndex(max(0, source_index))

        font_size = QSpinBox(dialog)
        font_size.setRange(8, 32)
        font_size.setSuffix(" pt")
        font_size.setValue(self.preferences.editor_font_size)

        card_primary_font_size = QSpinBox(dialog)
        card_primary_font_size.setObjectName("cardPrimaryFontSizeSpin")
        card_primary_font_size.setRange(16, 48)
        card_primary_font_size.setSuffix(" pt")
        card_primary_font_size.setValue(self.preferences.card_primary_font_size)

        card_secondary_font_size = QSpinBox(dialog)
        card_secondary_font_size.setObjectName("cardSecondaryFontSizeSpin")
        card_secondary_font_size.setRange(12, 40)
        card_secondary_font_size.setSuffix(" pt")
        card_secondary_font_size.setValue(self.preferences.card_secondary_font_size)

        french_articles = QComboBox(dialog)
        french_articles.addItem(self._t("articles_auto"), FrenchArticleMode.AUTO.value)
        french_articles.addItem(self._t("articles_definite"), FrenchArticleMode.DEFINITE.value)
        french_articles.addItem(
            self._t("articles_indefinite"),
            FrenchArticleMode.INDEFINITE.value,
        )
        french_articles.addItem(self._t("articles_off"), FrenchArticleMode.OFF.value)
        article_index = french_articles.findData(self.preferences.french_article_mode)
        french_articles.setCurrentIndex(max(0, article_index))

        audio_mode = QComboBox(dialog)
        audio_mode.setObjectName("audioPreparationModeCombo")
        audio_mode.addItem(
            self._t("audio_mode_line"),
            AudioPreparationMode.FAST_LINE.value,
        )
        audio_mode.addItem(
            self._t("audio_mode_package"),
            AudioPreparationMode.COMPLETE_PACKAGE.value,
        )
        audio_mode_index = audio_mode.findData(self.audio_preparation_mode)
        audio_mode.setCurrentIndex(max(0, audio_mode_index))

        speech_rate = QSpinBox(dialog)
        speech_rate.setRange(-100, 100)
        speech_rate.setSuffix(" %")
        speech_rate.setValue(self.tts_settings.rate)

        speech_pitch = QSpinBox(dialog)
        speech_pitch.setRange(-100, 100)
        speech_pitch.setSuffix(" Hz")
        speech_pitch.setValue(self.tts_settings.pitch)

        speech_volume = QSpinBox(dialog)
        speech_volume.setRange(-100, 100)
        speech_volume.setSuffix(" %")
        speech_volume.setValue(self.tts_settings.volume)

        form.addRow(self._t("interface_language"), interface_combo)
        form.addRow(self._t("source_language"), source_combo)
        form.addRow(self._t("font_size"), font_size)
        form.addRow(self._t("card_primary_font_size"), card_primary_font_size)
        form.addRow(self._t("card_secondary_font_size"), card_secondary_font_size)
        form.addRow(self._t("french_articles"), french_articles)
        form.addRow(self._t("audio_preparation_mode"), audio_mode)
        form.addRow(self._t("tts_rate"), speech_rate)
        form.addRow(self._t("tts_pitch"), speech_pitch)
        form.addRow(self._t("tts_volume"), speech_volume)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        previous_article_mode = self.preferences.french_article_mode
        previous_audio_mode = self.audio_preparation_mode
        self.preferences = Preferences(
            source_language_key=str(source_combo.currentData()),
            editor_font_size=font_size.value(),
            french_article_mode=str(french_articles.currentData()),
            last_open_directory=self.preferences.last_open_directory,
            last_export_directory=self.preferences.last_export_directory,
            interface_language=str(interface_combo.currentData()),
            card_primary_font_size=card_primary_font_size.value(),
            card_secondary_font_size=card_secondary_font_size.value(),
        )
        self.audio_preparation_mode = str(audio_mode.currentData())
        updated_tts_settings = TtsSettings.normalized(
            speech_rate.value(), speech_pitch.value(), speech_volume.value()
        )
        tts_changed = updated_tts_settings != self.tts_settings
        self.tts_settings = updated_tts_settings
        self.language_controller.set_french_article_mode(
            self.preferences.french_article_mode
        )
        self.language_controller.select_source(self.preferences.source_language_key)
        self._apply_editor_font_size()
        self._apply_interface_language()
        if (
            tts_changed
            or previous_article_mode != self.preferences.french_article_mode
            or previous_audio_mode != self.audio_preparation_mode
        ):
            self._reset_audio_state()
        try:
            self.repository.save_preferences(self.preferences)
            self._save_app_state()
            self.statusBar().showMessage(self._t("settings_saved"))
        except OSError as exc:
            self._show_error(self._t("settings_save_failed", error=exc))

    @Slot()
    def open_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("help_title"))
        dialog.resize(820, 680)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        help_font = browser.font()
        base_point_size = help_font.pointSizeF()
        if base_point_size > 0:
            help_font.setPointSizeF(base_point_size + 2.0)
            browser.setFont(help_font)
        help_path = HELP_PATHS[self.preferences.interface_language]
        try:
            browser.setMarkdown(help_path.read_text(encoding="utf-8"))
        except OSError:
            browser.setPlainText(self._t("help_unavailable", path=help_path))
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button:
            close_button.setText(self._t("close"))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _run_task(
        self,
        fn: Callable[[Callable[[], bool]], Any],
        on_result: Callable[[Any], None],
        busy_text: str,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._set_busy(True, busy_text)

        def _finished() -> None:
            self._set_busy(False, self._t("ready"))

        self.tasks.start(fn, on_result, on_error or self._show_error, _finished)

    def _run_progress_task(
        self,
        fn: Callable[
            [Callable[[], bool], Callable[[int, int, str], None]],
            Any,
        ],
        on_result: Callable[[Any], None],
        busy_text: str,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._set_busy(True, busy_text, determinate=True)

        def _finished() -> None:
            self._set_busy(False, self._t("ready"))

        self.tasks.start_with_progress(
            fn,
            on_result,
            on_error or self._show_error,
            _finished,
            self._update_progress,
        )

    @Slot(int, int, str)
    def _update_progress(self, current: int, total: int, message: str) -> None:
        maximum = max(1, total)
        self.progress.setRange(0, maximum)
        self.progress.setValue(min(max(0, current), maximum))
        self.progress.setFormat("%v / %m")
        self.statusBar().showMessage(message)

    def _set_busy(self, busy: bool, message: str, *, determinate: bool = False) -> None:
        self._busy_indicator_active = busy
        if busy:
            self._network_unavailable = False
        self.progress.setVisible(busy)
        if busy and determinate:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFormat("%v / %m")
        elif busy:
            self.progress.setRange(0, 0)
            self.progress.setFormat("")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat("")
        self.translate_button.setEnabled(not busy and not self._study_mode)
        self.edit_source_button.setEnabled(not busy and self._study_mode)
        self.speak_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.batch_translation_action.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.language_combo.setEnabled(not busy and self.reload_voices_button.isEnabled())
        self.cancel_button.setEnabled(busy)
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.stop_button.setEnabled(
            busy or playing or self.sequence.active or self._timed_playback_active
        )
        self.replay_button.setEnabled(
            not busy and not self.sequence.active and bool(self.source_edit.toPlainText().strip())
        )
        self._update_save_audio_button(busy=busy)
        self._update_ab_controls()
        self.statusBar().showMessage(message)
        self._update_document_status()

    @Slot()
    def open_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._t("open_text"),
            self._open_dialog_directory(),
            self._t("documents_filter"),
        )
        if not filename:
            return
        try:
            document = load_document(Path(filename))
            self._loading_document = True
            self.source_edit.setPlainText(document.original)
            self.translation_edit.setPlainText(document.translation)
            self.transcription_edit.setPlainText(
                document.transcription or self.language_controller.transcribe(document.translation)
            )
            self.subtitle_cues = document.subtitles
            self._loading_document = False
            self._dirty = False
            self.current_source_path = Path(filename)
            self._active_package_name = None
            self._update_document_status()
            self._remember_directory("last_open_directory", self.current_source_path.parent)
            self.statusBar().showMessage(self._t("opened", path=filename))
            self._set_study_mode(False)
        except AppError as exc:
            self._loading_document = False
            self._show_error(str(exc))

    @Slot()
    def open_package(self) -> None:
        if not self._confirm_discard_changes():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("open_package"))
        form = QFormLayout(dialog)
        language_combo = QComboBox(dialog)
        package_combo = QComboBox(dialog)
        for profile in LANGUAGES:
            language_combo.addItem(profile.label, profile.key)
        current_index = language_combo.findData(self.current_language.key)
        if current_index >= 0:
            language_combo.setCurrentIndex(current_index)

        def populate_packages() -> None:
            package_combo.clear()
            language_key = str(language_combo.currentData())
            profile = next(item for item in LANGUAGES if item.key == language_key)
            for package in discover_packages(
                self.repository.language_directory(profile), language_key
            ):
                package_combo.addItem(package.stem, str(package.audio_path))

        language_combo.currentIndexChanged.connect(populate_packages)
        populate_packages()
        form.addRow(self._t("package_language"), language_combo)
        form.addRow(self._t("package_name"), package_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(
            package_combo.count() > 0
        )
        language_combo.currentIndexChanged.connect(
            lambda: buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(
                package_combo.count() > 0
            )
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if package_combo.count() <= 0:
            QMessageBox.information(self, self.windowTitle(), self._t("no_packages"))
            return
        self._open_offline_package(
            Path(str(package_combo.currentData())),
            str(language_combo.currentData()),
        )

    def _open_offline_package(self, audio_path: Path, language_key: str) -> bool:
        try:
            package = load_offline_package(audio_path, language_key)
            language_index = self.language_combo.findData(language_key)
            if language_index < 0:
                raise ValueError(f"Unknown language: {language_key}")
            self._dirty = False
            self.language_combo.setCurrentIndex(language_index)
            self._reset_audio_state()
            self._loading_document = True
            self.source_edit.setPlainText(package.document.original)
            self.translation_edit.setPlainText(package.document.translation)
            self.transcription_edit.setPlainText(package.document.transcription)
            self._loading_document = False
            self.current_source_path = package.text_path
            self._active_package_name = package.stem
            self.subtitle_cues = ()
            self.tts_settings = TtsSettings(
                rate=package.manifest.rate,
                pitch=package.manifest.pitch,
                volume=package.manifest.volume,
            )
            voice_index = self.voice_combo.findData(package.manifest.voice)
            if voice_index >= 0:
                self.voice_combo.setCurrentIndex(voice_index)
            self.audio_path = package.audio_path
            self.audio_manifest_path = package.manifest_path
            self.audio_srt_path = package.srt_path
            self.timed_manifest = package.manifest
            self._audio_is_complete_document = True
            self._offline_package_active = True
            self._update_document_status()
            self.player.setSource(QUrl.fromLocalFile(str(package.audio_path)))
            self._reset_range_markers()
            self._dirty = False
            self._remember_directory("last_open_directory", package.audio_path.parent)
            touch_package_history(
                self.repository.package_history_path,
                language_key,
                package.audio_path,
            )
            self._update_save_audio_button()
            self.replay_button.setEnabled(True)
            self.statusBar().showMessage(
                self._t("package_opened", name=package.stem)
            )
            self._set_study_mode(True)
            return True
        except (AppError, OSError, ValueError) as exc:
            self._loading_document = False
            self._show_error(str(exc))
            return False

    @Slot()
    def open_package_history(self) -> None:
        entries = load_package_history(self.repository.package_history_path)
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("package_history"))
        dialog.resize(680, 360)
        layout = QVBoxLayout(dialog)
        history_list = QListWidget(dialog)
        layout.addWidget(history_list, 1)
        controls = QHBoxLayout()
        open_button = QPushButton(self._t("history_open"), dialog)
        remove_button = QPushButton(self._t("history_remove"), dialog)
        clear_button = QPushButton(self._t("history_clear"), dialog)
        close_button = QPushButton(self._t("close"), dialog)
        controls.addWidget(open_button)
        controls.addWidget(remove_button)
        controls.addWidget(clear_button)
        controls.addStretch(1)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        def refill() -> None:
            history_list.clear()
            current_entries = load_package_history(self.repository.package_history_path)
            for entry in current_entries:
                exists = Path(entry.audio_path).is_file()
                suffix = "" if exists else f" — {self._t('history_missing')}"
                item = QListWidgetItem(
                    f"{entry.name} · {entry.language} · {entry.last_used}{suffix}"
                )
                item.setData(Qt.ItemDataRole.UserRole, entry)
                history_list.addItem(item)
            enabled = history_list.count() > 0
            open_button.setEnabled(enabled)
            remove_button.setEnabled(enabled)
            clear_button.setEnabled(enabled)

        def selected_entry() -> PackageHistoryEntry | None:
            item = history_list.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def open_selected() -> None:
            entry = selected_entry()
            if entry is None or not self._confirm_discard_changes():
                return
            if self._open_offline_package(Path(entry.audio_path), entry.language):
                dialog.accept()

        def remove_selected() -> None:
            entry = selected_entry()
            if entry is None:
                return
            remaining = [item for item in load_package_history(
                self.repository.package_history_path
            ) if item.audio_path != entry.audio_path]
            save_package_history(self.repository.package_history_path, remaining)
            refill()

        open_button.clicked.connect(open_selected)
        history_list.itemDoubleClicked.connect(lambda _item: open_selected())
        remove_button.clicked.connect(remove_selected)
        def clear_history() -> None:
            save_package_history(self.repository.package_history_path, [])
            refill()

        clear_button.clicked.connect(clear_history)
        close_button.clicked.connect(dialog.reject)
        refill()
        if not entries:
            self.statusBar().showMessage(self._t("history_empty"))
        dialog.exec()

    @Slot()
    def batch_process_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            self._t("select_batch"),
            self._open_dialog_directory(),
            self._t("documents_filter"),
        )
        if not filenames:
            return
        paths = [Path(filename) for filename in filenames]
        self._remember_directory("last_open_directory", paths[0].parent)
        processor = BatchProcessor(self.repository, self.current_language, self.translator)

        def process(
            cancelled: Callable[[], bool],
            report: Callable[[int, int, str], None],
        ) -> BatchResult:
            return processor.process(paths, cancelled, report)

        self._run_progress_task(
            process,
            self._batch_completed,
            self._t("batch_progress", total=len(paths)),
        )

    def _batch_completed(self, result: BatchResult) -> None:
        succeeded = result.succeeded
        failed = result.failed
        if succeeded and succeeded[-1].output:
            self._remember_directory("last_export_directory", succeeded[-1].output.parent)
        summary = self._t("batch_success", count=len(succeeded), total=len(result.items))
        if failed:
            details = "\n".join(
                f"• {item.source.name}: {item.error}" for item in failed[:5]
            )
            if len(failed) > 5:
                details += "\n" + self._t("more_errors", count=len(failed) - 5)
            QMessageBox.warning(
                self,
                self.windowTitle(),
                f"{self._t('batch_complete')}\n\n{summary}\n\n{details}",
            )
        else:
            QMessageBox.information(
                self,
                self.windowTitle(),
                f"{self._t('batch_complete')}\n\n{summary}",
            )
        self.statusBar().showMessage(summary)

    @Slot()
    def translate_text(self) -> None:
        text = self.source_edit.toPlainText()
        if not text.strip():
            QMessageBox.information(self, self.windowTitle(), self._t("enter_source"))
            return
        voice = self.selected_voice()
        tts_settings = self.tts_settings
        language_key = self.current_language.key
        prepare_complete_package = (
            self.audio_preparation_mode
            == AudioPreparationMode.COMPLETE_PACKAGE.value
        )

        def translate_and_prepare_audio(
            cancelled: Callable[[], bool],
            report: Callable[[int, int, str], None],
        ) -> tuple[
            StructuredTranslationResult,
            str,
            TimedAudioPackage | None,
            str,
        ]:
            translated = translate_preserving_layout(
                text,
                self.translator,
                cancelled,
                lambda current, total: report(
                    current,
                    total,
                    self._t("translation_progress", current=current, total=total),
                ),
            )
            transcription = self.language_controller.transcribe(translated.text)
            if not prepare_complete_package:
                return translated, transcription, None, ""
            rows = build_sentence_translation_rows(text, translated.text, transcription)
            if not voice:
                return translated, transcription, None, self._t("voice_not_selected")
            audio_path, manifest_path, srt_path = self._temporary_audio_package_paths()
            try:
                package = build_timed_audio_package(
                    rows,
                    audio_path,
                    manifest_path,
                    srt_path,
                    language_key,
                    voice,
                    tts_settings,
                    lambda speech_text, output: self.speech.synthesize_timed(
                        speech_text,
                        voice,
                        output,
                        cancelled,
                        settings=tts_settings,
                    ),
                    speech_text=self.language_controller.prepare_speech,
                    progress=lambda current, total: report(
                        current,
                        total,
                        self._t(
                            "audio_package_progress",
                            current=current,
                            total=total,
                        ),
                    ),
                    resume_root=(
                        self.repository.ensure_language_directory(
                            self.current_language
                        )
                        / "tts_jobs"
                    ),
                )
                return translated, transcription, package, ""
            except OperationCancelled:
                raise
            except Exception as exc:
                return translated, transcription, None, str(exc)

        self._run_progress_task(
            translate_and_prepare_audio,
            self._set_translation_audio_result,
            self._t("translation_preparing"),
        )

    def _set_translation_audio_result(
        self,
        result: tuple[
            StructuredTranslationResult,
            str,
            TimedAudioPackage | None,
            str,
        ],
    ) -> None:
        translation, transcription, package, audio_error = result
        self._set_translation(translation.text)
        self.transcription_edit.blockSignals(True)
        self.transcription_edit.setPlainText(transcription)
        self.transcription_edit.blockSignals(False)
        if package:
            self.audio_path = package.audio_path
            self.audio_manifest_path = package.manifest_path
            self.audio_srt_path = package.srt_path
            self.timed_manifest = package.manifest
            self._audio_is_complete_document = True
            self.player.setSource(QUrl.fromLocalFile(str(package.audio_path)))
            self._update_save_audio_button()
        self.statusBar().showMessage(
            self._t(
                "translation_audio_complete" if package else "translation_complete",
                lines=translation.translated_lines,
                parts=translation.translated_chunks,
            )
        )
        if audio_error:
            self._show_error(self._t("translation_audio_failed", error=audio_error))
        self._set_study_mode(True)

    @staticmethod
    def _temporary_audio_package_paths() -> tuple[Path, Path, Path]:
        fd, filename = tempfile.mkstemp(prefix="gpt01_timed_", suffix=".mp3")
        os.close(fd)
        audio_path = Path(filename)
        return audio_path, audio_path.with_suffix(".json"), audio_path.with_suffix(".srt")

    @Slot()
    def load_voices(self) -> None:
        profile = self.current_language

        async def fetch() -> tuple[str, list[dict[str, Any]]]:
            voices = await asyncio.wait_for(
                edge_tts.list_voices(), timeout=VOICE_LOAD_TIMEOUT_SECONDS
            )
            filtered = self.language_controller.filter_voices(voices)
            return profile.key, filtered

        self.reload_voices_button.setEnabled(False)
        self.language_combo.setEnabled(False)
        self.voice_status.setText(
            self._t("refreshing_voices", seconds=VOICE_LOAD_TIMEOUT_SECONDS)
        )
        def _finished() -> None:
            self.reload_voices_button.setEnabled(True)
            self.language_combo.setEnabled(not self.progress.isVisible())

        self.tasks.start(
            lambda _cancelled: asyncio.run(fetch()),
            self._voices_loaded,
            self._voices_load_failed,
            _finished,
            foreground=False,
        )

    def _voices_loaded(self, result: tuple[str, list[dict[str, Any]]]) -> None:
        language_key, voices = result
        if language_key != self.current_language.key:
            return
        if voices:
            try:
                self.repository.save_voices(self.current_language, voices)
            except OSError:
                pass
            self._populate_voices(voices)
            self.voice_status.setText(self._t("network_voices", count=len(voices)))
        else:
            self.voice_status.setText(self._t("voice_service_empty"))

    @Slot(str)
    def _voices_load_failed(self, message: str) -> None:
        if isinstance(message, str) and message.strip():
            short_message = message.strip().splitlines()[0][:140]
        else:
            short_message = self._t("timeout")
        self.voice_status.setText(self._t("voice_refresh_failed", reason=short_message))
        self._network_unavailable = True
        self._update_document_status()
        self.statusBar().showMessage(self._t("tts_unavailable"))

    def _populate_voices(self, voices: list[dict[str, Any]]) -> None:
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        selected_index = 0
        for idx, voice in enumerate(voices):
            name = str(voice.get("ShortName", ""))
            gender = str(voice.get("Gender", ""))
            locale = str(voice.get("Locale", ""))
            self.voice_combo.addItem(f"{name} ({locale} · {gender})", userData=name)
            if name == self.current_language.default_voice:
                selected_index = idx
        if self.voice_combo.count() > 0:
            self.voice_combo.setCurrentIndex(selected_index)
        self.voice_combo.blockSignals(False)

    def selected_voice(self) -> str | None:
        return self.voice_combo.currentData()

    @Slot(str)
    def _update_voice_tooltip(self, text: str = "") -> None:
        self.voice_combo.setToolTip(text or self.voice_combo.currentText())

    def _update_document_status(self) -> None:
        if not hasattr(self, "document_status_label"):
            return
        if self._active_package_name:
            text = self._t("status_package", name=self._active_package_name)
        elif self.current_source_path:
            text = self._t("status_file", name=self.current_source_path.name)
        else:
            text = self._t("status_new_document")
        if self._dirty:
            text += f" • {self._t('status_modified')}"
        self.document_status_label.setText(text)
        self.document_status_label.setToolTip(text)
        if self._offline_package_active:
            connection_key = "status_offline"
        elif self._busy_indicator_active:
            connection_key = "status_connecting"
        elif self._network_unavailable:
            connection_key = "status_unavailable"
        else:
            connection_key = "status_online"
        connection = self._t(connection_key)
        self.connection_status_label.setText(connection)
        self.connection_status_label.setToolTip(connection)

    @Slot()
    def speak_text(self) -> None:
        if self._range_a_line is not None and self._range_b_line is not None:
            self._start_ab_sequence()
            return
        if self._timed_audio_ready():
            start_ms = self._timed_start_for_current_row()
            self._start_timed_playback(start_ms, None, "all")
        else:
            self._start_sequence()

    @Slot()
    def speak_line_at_cursor(self) -> None:
        mouse_pos_src = self.source_edit.viewport().mapFromGlobal(QCursor.pos())
        mouse_pos_trans = self.translation_edit.viewport().mapFromGlobal(QCursor.pos())
        rows = build_sentence_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )

        if self.source_edit.viewport().rect().contains(mouse_pos_src):
            cursor = self.source_edit.cursorForPosition(mouse_pos_src)
            row = self._sentence_row_at_cursor(
                rows, cursor.position(), cursor.blockNumber(), "source"
            )
            needs_translation = True
        elif self.translation_edit.viewport().rect().contains(mouse_pos_trans):
            cursor = self.translation_edit.cursorForPosition(mouse_pos_trans)
            row = self._sentence_row_at_cursor(
                rows, cursor.position(), cursor.blockNumber(), "translation"
            )
            needs_translation = False
        else:
            cursor = self.source_edit.textCursor()
            row = self._sentence_row_at_cursor(
                rows, cursor.position(), cursor.blockNumber(), "source"
            )
            needs_translation = True

        if row is None:
            self.statusBar().showMessage(self._t("empty_hover_line"))
            return
        line_number = row.index
        source_line_text = row.source
        line_text = row.source if needs_translation else row.translation

        if not line_text:
            self.statusBar().showMessage(self._t("empty_hover_line"))
            return

        if self._timed_audio_ready() and self.timed_manifest:
            timed_line = next(
                (
                    line
                    for line in self.timed_manifest.lines
                    if line.line == line_number
                    and (
                        row.source_start is None
                        or line.source_start == row.source_start
                    )
                ),
                None,
            )
            if timed_line:
                self._start_timed_playback(
                    timed_line.start_ms,
                    timed_line.end_ms,
                    "line",
                )
                return

        if self._offline_package_active:
            self._show_offline_marker_error()
            return

        voice = self.selected_voice()
        if not voice:
            QMessageBox.information(self, self.windowTitle(), self._t("select_voice"))
            return
        tts_settings = self.tts_settings

        self.stop_audio()

        def translate_and_synthesize(cancelled: Callable[[], bool]) -> tuple[str, str]:
            target_text = line_text
            if needs_translation:
                target_text = self.translator.translate(line_text, cancelled)
            else:
                target_text = self.language_controller.prepare_translation(
                    source_line_text,
                    target_text,
                )

            fd, filename = tempfile.mkstemp(prefix="gpt01_line_tts_", suffix=".mp3")
            os.close(fd)
            output = Path(filename)

            self.speech.synthesize(
                self.language_controller.prepare_speech(target_text),
                voice,
                output,
                cancelled,
                settings=tts_settings,
            )
            return (str(output), target_text)

        def on_ready(result: tuple[str, str]) -> None:
            filename, translated_line = result
            translation_cursor = self.translation_edit.document().findBlockByNumber(
                line_number
            )
            existing_translation = (
                translation_cursor.text() if translation_cursor.isValid() else ""
            )
            if translated_line != existing_translation:
                self._set_parallel_line(
                    self.translation_edit,
                    line_number,
                    translated_line,
                )
                self._set_parallel_line(
                    self.transcription_edit,
                    line_number,
                    self.language_controller.transcribe(translated_line),
                )
                self._dirty = True
            self._audio_line_number = line_number
            self._show_synchronized_row(row)
            self.statusBar().showMessage(self._t("line_result", text=translated_line))
            self._play_file(filename)

        self._run_task(
            translate_and_synthesize,
            on_ready,
            self._t("line_synthesis", text=f"{line_text[:25]}…"),
        )

    @staticmethod
    def _sentence_row_at_cursor(
        rows: list[TranslationRow],
        position: int,
        line_number: int,
        field: str,
    ) -> TranslationRow | None:
        start_name = f"{field}_start"
        end_name = f"{field}_end"
        for row in rows:
            start = getattr(row, start_name)
            end = getattr(row, end_name)
            if start is not None and end is not None and start <= position <= end:
                return row
        return next((row for row in rows if row.index == line_number), None)

    def _play_file(self, filename: str) -> None:
        previous_audio = self.audio_path
        self.audio_path = Path(filename)
        self.audio_manifest_path = None
        self.audio_srt_path = None
        self.timed_manifest = None
        self._audio_is_complete_document = False
        self._offline_package_active = False
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.player.play()
        self.statusBar().showMessage(self._t("playing"))
        self.replay_button.setEnabled(not self.sequence.active)
        self._update_save_audio_button()
        if (
            previous_audio
            and previous_audio != self.audio_path
            and not self._line_audio_cache_contains(previous_audio)
            and previous_audio not in self._sequence_audio_parts
        ):
            self.repository.delete_temporary_audio(previous_audio)

    @Slot()
    def _on_voice_changed(self) -> None:
        self._reset_audio_state()

    @Slot()
    def _on_text_changed(self) -> None:
        if not self._loading_document:
            self._dirty = True
        self._reset_audio_state()
        self._update_document_status()

    def _set_study_mode(self, enabled: bool) -> None:
        self._study_mode = enabled
        self.source_edit.setReadOnly(enabled)
        busy = self.tasks.foreground is not None
        self.translate_button.setEnabled(not busy and not enabled)
        self.edit_source_button.setEnabled(not busy and enabled)
        self.source_clear_button.setEnabled(not busy and not enabled)

    @Slot()
    def enable_source_editing(self) -> None:
        if not self._study_mode:
            return
        self.stop_current_operation()
        self._reset_range_markers()
        self._reset_audio_state()
        self._set_study_mode(False)
        self._active_package_name = None
        self._update_document_status()
        self.source_edit.setFocus()

    @Slot()
    def _on_source_text_changed(self) -> None:
        self._on_text_changed()
        self._reset_range_markers()

    @Slot()
    def _on_translation_changed(self) -> None:
        self._on_text_changed()
        transcription = self.language_controller.transcribe(self.translation_edit.toPlainText())
        self.transcription_edit.blockSignals(True)
        self.transcription_edit.setPlainText(transcription)
        self.transcription_edit.blockSignals(False)

    @Slot()
    def clear_source_window(self) -> None:
        editors = (
            self.source_edit,
            self.translation_edit,
            self.transcription_edit,
        )
        if not any(editor.toPlainText() for editor in editors):
            return
        for editor in editors:
            editor.blockSignals(True)
        try:
            for editor in editors:
                editor.clear()
        finally:
            for editor in editors:
                editor.blockSignals(False)
        self._on_source_text_changed()

    @Slot()
    def clear_translation_window(self) -> None:
        if not self.translation_edit.toPlainText():
            return
        self.translation_edit.blockSignals(True)
        self.translation_edit.clear()
        self.translation_edit.blockSignals(False)
        self._on_text_changed()

    @Slot()
    def clear_transcription_window(self) -> None:
        self.transcription_edit.clear()

    def _set_translation(self, text: str) -> None:
        self.translation_edit.setPlainText(text)

    @Slot()
    def _toggle_transcription_window(self) -> None:
        self._set_transcription_window_visible(self.transcription_box.isHidden())

    @Slot()
    def _toggle_translation_window(self) -> None:
        self._set_translation_window_visible(self.translation_box.isHidden())

    @Slot()
    def _toggle_source_window(self) -> None:
        self._set_source_window_visible(self.source_box.isHidden())

    def _may_change_panel_visibility(self, panel: QWidget, visible: bool) -> bool:
        if visible or panel.isHidden():
            return True
        visible_count = sum(
            not item.isHidden()
            for item in (
                self.source_box,
                self.translation_box,
                self.transcription_box,
            )
        )
        if visible_count > 1:
            return True
        self.statusBar().showMessage(self._t("last_window_required"))
        return False

    def _set_source_window_visible(self, visible: bool) -> None:
        if not self._may_change_panel_visibility(self.source_box, visible):
            return
        self.source_header.removeWidget(self.source_toggle_button)
        self.collapsed_panels_layout.removeWidget(self.source_toggle_button)
        if visible:
            self.source_header.insertWidget(
                max(0, self.source_header.count() - 1),
                self.source_toggle_button,
            )
        else:
            self.collapsed_panels_layout.addWidget(self.source_toggle_button)
        self.source_box.setVisible(visible)
        self.source_toggle_button.setFixedWidth(32 if visible else 126)
        self.source_toggle_button.setText(
            "−" if visible else f"+ {self._t('source_text')}"
        )
        self.source_toggle_button.setToolTip(
            self._t("hide_source") if visible else self._t("show_source")
        )
        self._resize_visible_editor_windows()

    def _set_transcription_window_visible(self, visible: bool) -> None:
        if not self._may_change_panel_visibility(self.transcription_box, visible):
            return
        self.transcription_header.removeWidget(self.transcription_toggle_button)
        self.collapsed_panels_layout.removeWidget(self.transcription_toggle_button)
        if visible:
            self.transcription_header.insertWidget(
                max(0, self.transcription_header.count() - 1),
                self.transcription_toggle_button,
            )
        else:
            self.collapsed_panels_layout.addWidget(self.transcription_toggle_button)
        self.transcription_box.setVisible(visible)
        self.transcription_toggle_button.setFixedWidth(32 if visible else 126)
        self.transcription_toggle_button.setText(
            "−" if visible else f"+ {self._t('transcription')}"
        )
        self.transcription_toggle_button.setToolTip(
            self._t("hide_transcription") if visible else self._t("show_transcription")
        )
        if visible:
            self._resize_visible_editor_windows()

    def _set_translation_window_visible(self, visible: bool) -> None:
        if not self._may_change_panel_visibility(self.translation_box, visible):
            return
        self.translation_header.removeWidget(self.translation_toggle_button)
        self.collapsed_panels_layout.removeWidget(self.translation_toggle_button)
        if visible:
            self.translation_header.insertWidget(
                max(0, self.translation_header.count() - 1),
                self.translation_toggle_button,
            )
        else:
            self.collapsed_panels_layout.addWidget(self.translation_toggle_button)
        self.translation_box.setVisible(visible)
        self.translation_toggle_button.setFixedWidth(32 if visible else 126)
        self.translation_toggle_button.setText(
            "−" if visible else f"+ {self._t('translation')}"
        )
        self.translation_toggle_button.setToolTip(
            self._t("hide_translation") if visible else self._t("show_translation")
        )
        if visible:
            self._resize_visible_editor_windows()

    def _resize_visible_editor_windows(self) -> None:
        panels = [self.editors.widget(index) for index in range(self.editors.count())]
        visible_indices = [
            index for index, panel in enumerate(panels) if not panel.isHidden()
        ]
        if not visible_indices:
            return

        total_width = max(sum(self.editors.sizes()), self.editors.width(), 3)
        width = total_width // len(visible_indices)
        self.editors.setSizes(
            [width if index in visible_indices else 0 for index in range(len(panels))]
        )

    def _desired_panel_order(self) -> list[QWidget]:
        if not self.panels_swapped:
            return [self.source_box, self.translation_box, self.transcription_box]
        if self.current_language.key in {"Chine", "Japan"}:
            return [self.transcription_box, self.source_box, self.translation_box]
        return [self.translation_box, self.source_box, self.transcription_box]

    def _apply_panel_order(self) -> None:
        for index, panel in enumerate(self._desired_panel_order()):
            self.editors.insertWidget(index, panel)
        self._resize_visible_editor_windows()

    @Slot()
    def switch_editor_windows(self) -> None:
        self.panels_swapped = not self.panels_swapped
        self._apply_panel_order()
        self.statusBar().showMessage(
            self._t("windows_switched" if self.panels_swapped else "windows_restored")
        )

    def _card_rows(self) -> list[TranslationRow]:
        rows = build_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )
        if self._range_a_line is not None and self._range_b_line is not None:
            return rows_between(rows, self._range_a_line, self._range_b_line)
        return rows

    def _card_playback_rows(self) -> list[TranslationRow]:
        rows = build_sentence_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )
        return self._rows_in_ab_range(rows) if self._has_ab_range() else rows

    def _initial_card_line(self, line_numbers: list[int]) -> int:
        candidates = (
            self._replay_highlight_line,
            self._hover_line_number,
            self.source_edit.textCursor().blockNumber(),
        )
        return next(
            (line for line in candidates if line is not None and line in line_numbers),
            line_numbers[0],
        )

    @staticmethod
    def _editor_line(editor: QTextEdit, line_number: int) -> str:
        block = editor.document().findBlockByNumber(line_number)
        return block.text().strip() if block.isValid() else ""

    def _card_fields(self, line_number: int) -> list[CardField]:
        return self._ordered_card_fields(
            self._editor_line(self.source_edit, line_number),
            self._editor_line(self.translation_edit, line_number),
            self._editor_line(self.transcription_edit, line_number),
        )

    def _card_fields_for_row(self, row: TranslationRow) -> list[CardField]:
        return self._ordered_card_fields(
            row.source,
            row.translation,
            row.transcription,
        )

    def _ordered_card_fields(
        self,
        source_text: str,
        translation_text: str,
        transcription_text: str,
    ) -> list[CardField]:
        source = CardField(self._t("source_text"), source_text, kind="source")
        translation = CardField(
            self.translation_title.text(), translation_text, kind="translation"
        )
        transcription = CardField(
            self.transcription_title.text(), transcription_text, kind="transcription"
        )
        visible = {
            "source": not self.source_box.isHidden(),
            "translation": not self.translation_box.isHidden(),
            "transcription": not self.transcription_box.isHidden(),
        }
        if not self.panels_swapped:
            candidates = (
                ("source", source),
                ("translation", translation),
                ("transcription", transcription),
            )
        elif self.current_language.key in {"Chine", "Japan"}:
            candidates = (
                ("transcription", transcription),
                ("source", source),
                ("translation", translation),
            )
        else:
            candidates = (
                ("translation", translation),
                ("source", source),
                ("transcription", transcription),
            )
        ordered = [field for key, field in candidates if visible[key]]
        return [
            CardField(
                field.title,
                field.text,
                primary=index == 0,
                kind=field.kind,
            )
            for index, field in enumerate(ordered)
        ]

    def _play_card_line(self, line_number: int) -> None:
        rows = [row for row in self._card_playback_rows() if row.index == line_number]
        if not rows:
            return
        self._show_synchronized_line(line_number)
        if self._timed_audio_ready() and self.timed_manifest:
            interval = self.timed_manifest.interval(line_number, line_number)
            if interval:
                self._start_timed_playback(
                    interval[0],
                    interval[1],
                    "cards",
                )
                return
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        self._begin_sequence(rows, "cards")

    def _play_card_row(self, row: TranslationRow) -> None:
        self._show_synchronized_row(row)
        if self._timed_audio_ready() and self.timed_manifest:
            timed_line = next(
                (
                    item
                    for item in self.timed_manifest.lines
                    if item.line == row.index
                    and (
                        row.source_start is None
                        or item.source_start == row.source_start
                    )
                ),
                None,
            )
            if timed_line:
                self._start_timed_playback(
                    timed_line.start_ms,
                    timed_line.end_ms,
                    "cards",
                )
                return
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        self._begin_sequence([row], "cards")

    def _play_card_range_cycle(
        self,
        selected_rows: list[TranslationRow] | None = None,
    ) -> None:
        if self._timed_playback_active:
            if self._timed_playback_scope == "cards_range":
                return
            if self._timed_playback_scope == "cards":
                self.stop_audio()
            else:
                return
        if self.sequence.active:
            if self._sequence_scope == "cards_range":
                return
            if self._sequence_scope == "cards":
                self._stop_sequence()
            else:
                return
        rows = list(selected_rows) if selected_rows is not None else self._card_playback_rows()
        if not rows:
            return
        if self._timed_audio_ready() and self.timed_manifest:
            interval = self._timed_interval_for_rows(rows)
            if interval:
                self._start_timed_playback(interval[0], interval[1], "cards_range")
                return
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        self._begin_sequence(rows, "cards_range")

    def _stop_card_playback(self) -> None:
        if self._timed_playback_active and self._timed_playback_scope in {
            "cards",
            "cards_range",
        }:
            self.stop_audio()
        elif self.sequence.active and self._sequence_scope in {"cards", "cards_range"}:
            self._stop_sequence()

    @Slot()
    def open_current_waveform(self) -> None:
        if not self._timed_audio_ready() or not self.audio_path or not self.timed_manifest:
            QMessageBox.information(
                self, self.windowTitle(), self._t("waveform_package_required")
            )
            return
        playback_rows = self._card_playback_rows()
        row = self._current_study_row()
        if row not in playback_rows and playback_rows:
            row = playback_rows[0]
        timed_lines = [
            next(
                (
                    item
                    for item in self.timed_manifest.lines
                    if _timed_matches_row(item, candidate)
                ),
                None,
            )
            for candidate in playback_rows
        ]
        timed_line = timed_lines[playback_rows.index(row)] if row in playback_rows else None
        if row is None or timed_line is None:
            QMessageBox.information(
                self, self.windowTitle(), self._t("waveform_package_required")
            )
            return
        self.stop_audio()

        def play_range(start_ms: int, end_ms: int) -> None:
            self._start_timed_playback(start_ms, end_ms, "waveform")

        def stop_waveform() -> None:
            if self._timed_playback_scope == "waveform":
                self.stop_audio()

        def set_waveform_speed(speed: float) -> None:
            self.player.setPlaybackRate(speed)

        current_position = playback_rows.index(row)

        def navigate_waveform(offset: int):
            nonlocal current_position
            target = current_position + offset
            if self._has_ab_range():
                target %= len(playback_rows)
            elif target < 0 or target >= len(playback_rows):
                return None
            target_timed = timed_lines[target]
            if target_timed is None:
                return None
            current_position = target
            target_row = playback_rows[target]
            self._select_study_row(target_row)
            self._start_timed_playback(
                target_timed.start_ms, target_timed.end_ms, "waveform"
            )
            return (
                target_timed.start_ms,
                target_timed.end_ms,
                target_row.source,
                target_row.translation,
                target + 1,
                len(playback_rows),
            )

        dialog = WaveformDialog(
            self.audio_path,
            timed_line.start_ms,
            timed_line.end_ms,
            row.source,
            row.translation,
            play_range,
            stop_waveform,
            set_waveform_speed,
            title=self._t("waveform_title"),
            play_text=self._t("waveform_play"),
            reset_text=self._t("waveform_reset"),
            close_text=self._t("close"),
            hint_text=self._t("waveform_hint"),
            speed_text=self._t("waveform_speed"),
            navigate=navigate_waveform,
            current_position=current_position + 1,
            total_positions=len(playback_rows),
            cyclic_navigation=self._has_ab_range(),
            parent=self,
        )
        self._active_waveform_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._active_waveform_dialog = None

    @Slot()
    def open_cards(self) -> None:
        playback_rows = self._card_playback_rows()
        if not playback_rows:
            QMessageBox.information(self, self.windowTitle(), self._t("no_card_lines"))
            return
        self.stop_current_operation()
        line_numbers = list(dict.fromkeys(row.index for row in playback_rows))
        initial_line = self._initial_card_line(line_numbers)
        has_ab_range = self._range_a_line is not None and self._range_b_line is not None
        cursor_position = self.source_edit.textCursor().position()
        self._show_synchronized_line(initial_line)
        card_numbers = list(range(len(playback_rows)))
        initial_card = next(
            (
                position
                for position, row in enumerate(playback_rows)
                if row.index == initial_line
                and (
                    row.source_start is None
                    or row.source_start <= cursor_position <= row.source_end
                )
            ),
            next(
                (
                    position
                    for position, row in enumerate(playback_rows)
                    if row.index == initial_line
                ),
                0,
            ),
        )

        def fields_for_card(position: int) -> list[CardField]:
            return self._card_fields_for_row(playback_rows[position])

        def speak_card(position: int) -> None:
            self._play_card_row(playback_rows[position])

        def repeat_cards_range() -> None:
            self._play_card_range_cycle(playback_rows)

        dialog = FlashcardsDialog(
            card_numbers,
            initial_card,
            fields_for_card,
            speak_card,
            lambda: self.tasks.foreground is None,
            repeat_cards_range if has_ab_range else None,
            title=self._t("cards_title"),
            close_text=self._t("close"),
            mode_text=(
                self._t(
                    "cards_ab_sentence_badge",
                    start=min(
                        self._range_a_sentence_number,
                        self._range_b_sentence_number,
                    ),
                    end=max(
                        self._range_a_sentence_number,
                        self._range_b_sentence_number,
                    ),
                )
                if self._uses_sentence_markers()
                else self._t(
                    "cards_ab_badge",
                    start=min(self._range_a_line, self._range_b_line) + 1,
                    end=max(self._range_a_line, self._range_b_line) + 1,
                )
                if has_ab_range
                else self._t("cards_all_badge")
            ),
            navigation_hint=self._t("cards_navigation_hint"),
            space_hint=self._t(
                "cards_space_range_hint" if has_ab_range else "cards_space_line_hint"
            ),
            visibility_hint=self._t("cards_visibility_hint"),
            primary_font_size=self.preferences.card_primary_font_size,
            secondary_font_size=self.preferences.card_secondary_font_size,
            cycle_navigation=has_ab_range,
            item_ids_are_lines=False,
            parent=self,
        )
        self._active_cards_dialog = dialog
        self.ab_repeat_shortcut.setEnabled(False)
        try:
            dialog.exec()
        finally:
            self._active_cards_dialog = None
            self._stop_card_playback()
            self._update_ab_controls()

    @Slot()
    def set_range_marker_a(self) -> None:
        self._set_range_marker("A")

    @Slot()
    def set_range_marker_b(self) -> None:
        self._set_range_marker("B")

    def _set_range_marker(self, marker: str) -> None:
        cursor = self.source_edit.textCursor()
        block = cursor.block()
        if not block.isValid():
            self.statusBar().showMessage(self._t("marker_caret", marker=marker))
            return
        all_spans = sentence_spans(self.source_edit.toPlainText())
        selected_span = None
        if self._marker_candidate_span is not None:
            selected_span = next(
                (
                    span
                    for span in all_spans
                    if (span.start, span.end) == self._marker_candidate_span
                ),
                None,
            )
        if selected_span is None:
            selected_span = next(
                (
                    span
                    for span in all_spans
                    if span.start <= cursor.position() <= span.end
                ),
                next((span for span in all_spans if span.line == block.blockNumber()), None),
            )
        if selected_span is None:
            self.statusBar().showMessage(self._t("marker_caret", marker=marker))
            return
        line_number = selected_span.line
        sentence_number = all_spans.index(selected_span) + 1
        span_range = (selected_span.start, selected_span.end)
        line_sentence_count = sum(span.line == line_number for span in all_spans)
        display_number = sentence_number if line_sentence_count > 1 else line_number + 1
        button_text = (
            f"{marker}:S{display_number}"
            if line_sentence_count > 1
            else f"{marker}:{display_number}"
        )
        if marker == "A":
            self._range_a_line = line_number
            self._range_a_span = span_range
            self._range_a_sentence_number = sentence_number
            self.mark_a_button.setText(button_text)
        else:
            self._range_b_line = line_number
            self._range_b_span = span_range
            self._range_b_sentence_number = sentence_number
            self.mark_b_button.setText(button_text)
        self._marker_candidate_line = None
        self._marker_candidate_span = None
        self._ab_repeat_ready = False
        self._render_source_highlights()
        self._update_ab_controls()
        self.statusBar().showMessage(
            self._t("marker_set", marker=marker, line=display_number)
        )

    def _reset_range_markers(self) -> None:
        self._range_a_line = None
        self._range_b_line = None
        self._range_a_span = None
        self._range_b_span = None
        self._range_a_sentence_number = None
        self._range_b_sentence_number = None
        self._marker_candidate_line = None
        self._marker_candidate_span = None
        self._ab_repeat_ready = False
        self.mark_a_button.setText("A")
        self.mark_b_button.setText("B")
        self.ab_audio_cache.clear()
        self.card_audio_cache.clear()
        self._render_source_highlights()
        self._update_ab_controls()

    @Slot()
    def reset_ab_range(self) -> None:
        if self._timed_playback_active and self._timed_playback_scope == "ab":
            self.stop_audio()
        elif self.sequence.active and self._sequence_scope == "ab":
            self._stop_sequence(self._t("range_stopped"))
        elif self.ab_audio_cache.contains(self.audio_path):
            self.stop_audio()
            self.audio_path = None
        self._reset_range_markers()
        self.statusBar().showMessage(self._t("range_reset"))

    def _update_ab_controls(self) -> None:
        if not hasattr(self, "mark_a_button"):
            return
        busy = hasattr(self, "progress") and self.progress.isVisible()
        has_source = bool(self.source_edit.toPlainText().strip())
        idle = not busy and not self.sequence.active and not self._timed_playback_active
        self.mark_a_button.setEnabled(idle and has_source)
        self.mark_b_button.setEnabled(idle and has_source)
        has_range = self._range_a_line is not None and self._range_b_line is not None
        self.play_ab_button.setEnabled(idle and has_source and has_range)
        has_ab_state = has_range or self.ab_audio_cache.has_files or (
            self.sequence.active and self._sequence_scope == "ab"
        )
        self.reset_ab_button.setEnabled(has_ab_state)
        if hasattr(self, "ab_repeat_shortcut"):
            self.ab_repeat_shortcut.setEnabled(
                idle
                and has_source
                and has_range
                and self._ab_repeat_ready
                and self._active_cards_dialog is None
            )

    def _has_ab_range(self) -> bool:
        return self._range_a_line is not None and self._range_b_line is not None

    def _uses_sentence_markers(self) -> bool:
        return bool(
            self._has_ab_range()
            and self._range_a_line == self._range_b_line
            and self._range_a_span != self._range_b_span
            and self._range_a_sentence_number is not None
            and self._range_b_sentence_number is not None
        )

    def _rows_in_ab_range(
        self,
        rows: list[TranslationRow],
    ) -> list[TranslationRow]:
        if not self._has_ab_range():
            return rows
        if self._range_a_span and self._range_b_span:
            first_span, last_span = sorted(
                (self._range_a_span, self._range_b_span), key=lambda span: span[0]
            )
            first_matches = [
                index
                for index, row in enumerate(rows)
                if _row_overlaps_span(row, first_span)
            ]
            last_matches = [
                index
                for index, row in enumerate(rows)
                if _row_overlaps_span(row, last_span)
            ]
            if first_matches and last_matches:
                start = min(first_matches)
                end = max(last_matches)
                return rows[min(start, end) : max(start, end) + 1]
        return rows_between(
            rows,
            self._range_a_line or 0,
            self._range_b_line or 0,
        )

    def _timed_interval_for_rows(
        self,
        rows: list[TranslationRow],
    ) -> tuple[int, int] | None:
        timed_rows = self._timed_lines_for_rows(rows)
        if not timed_rows:
            return None
        return timed_rows[0].start_ms, timed_rows[-1].end_ms

    def _timed_lines_for_rows(
        self,
        rows: list[TranslationRow],
    ) -> list[TimedLine]:
        if not rows or not self.timed_manifest:
            return []
        first_match = next(
            (
                index
                for index, timed in enumerate(self.timed_manifest.lines)
                if _timed_matches_row(timed, rows[0])
            ),
            None,
        )
        last_match = next(
            (
                index
                for index in range(len(self.timed_manifest.lines) - 1, -1, -1)
                if _timed_matches_row(self.timed_manifest.lines[index], rows[-1])
            ),
            None,
        )
        if first_match is None or last_match is None:
            return []
        start, end = sorted((first_match, last_match))
        return list(self.timed_manifest.lines[start : end + 1])

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self.source_edit
            and self._study_mode
            and event.type() == QEvent.Type.KeyPress
        ):
            key = event.key()  # type: ignore[attr-defined]
            if key in {
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Space,
            }:
                if event.isAutoRepeat():  # type: ignore[attr-defined]
                    return True
                if key == Qt.Key.Key_Space:
                    self._speak_current_study_row()
                else:
                    self._move_study_cursor(
                        1 if key in {Qt.Key.Key_Right, Qt.Key.Key_Down} else -1
                    )
                return True
        if watched is self.source_edit.viewport():
            if event.type() in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress}:
                position = event.position().toPoint()  # type: ignore[attr-defined]
                cursor = self.source_edit.cursorForPosition(position)
                if event.type() == QEvent.Type.MouseButtonPress:
                    self._hover_line_number = None
                    selected = next(
                        (
                            span
                            for span in sentence_spans(self.source_edit.toPlainText())
                            if span.start <= cursor.position() <= span.end
                        ),
                        None,
                    )
                    self._marker_candidate_line = (
                        selected.line if selected is not None else cursor.blockNumber()
                    )
                    self._marker_candidate_span = (
                        (selected.start, selected.end) if selected is not None else None
                    )
                else:
                    self._hover_line_number = cursor.blockNumber()
                self._render_source_highlights()
            elif event.type() == QEvent.Type.Leave:
                self._hover_line_number = None
                self._render_source_highlights()
        return super().eventFilter(watched, event)

    def _study_rows(self) -> list[TranslationRow]:
        return build_sentence_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )

    def _current_study_row(self) -> TranslationRow | None:
        cursor = self.source_edit.textCursor()
        return self._sentence_row_at_cursor(
            self._study_rows(), cursor.position(), cursor.blockNumber(), "source"
        )

    def _select_study_row(self, row: TranslationRow) -> None:
        cursor = self.source_edit.textCursor()
        position = row.source_start
        if position is None:
            block = self.source_edit.document().findBlockByNumber(row.index)
            position = block.position() if block.isValid() else 0
        cursor.setPosition(position)
        self.source_edit.setTextCursor(cursor)
        self._show_synchronized_row(row)

    def _move_study_cursor(self, offset: int) -> None:
        rows = self._study_rows()
        current = self._current_study_row()
        if not rows or current is None:
            return
        index = rows.index(current)
        target = rows[min(max(0, index + offset), len(rows) - 1)]
        self._select_study_row(target)
        self._play_study_row(target)

    def _speak_current_study_row(self) -> None:
        row = self._current_study_row()
        if row is not None:
            self._select_study_row(row)
            self._play_study_row(row)

    def _play_study_row(self, row: TranslationRow) -> None:
        if self._timed_audio_ready() and self.timed_manifest:
            timed_line = next(
                (item for item in self.timed_manifest.lines if _timed_matches_row(item, row)),
                None,
            )
            if timed_line:
                self._start_timed_playback(timed_line.start_ms, timed_line.end_ms, "line")
                return
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        self._begin_sequence([row], "line")

    def _render_source_highlights(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        if (
            self._range_a_line is not None
            and self._range_a_line == self._range_b_line
            and self._range_a_span == self._range_b_span
        ):
            marker_highlights = (
                (self._range_a_line, self._range_a_span, QColor("#d1c4e9")),
            )
        else:
            marker_highlights = (
                (self._range_a_line, self._range_a_span, QColor("#c8e6c9")),
                (self._range_b_line, self._range_b_span, QColor("#bbdefb")),
            )
        for line_number, span, color in marker_highlights:
            if line_number is None:
                continue
            selections.append(
                self._text_or_line_selection(
                    self.source_edit,
                    span,
                    line_number,
                    color,
                )
            )
        for line_number, color in ((self._hover_line_number, QColor("#fff59d")),):
            if line_number is None:
                continue
            block = self.source_edit.document().findBlockByNumber(line_number)
            if not block.isValid():
                continue
            cursor = self.source_edit.textCursor()
            cursor.setPosition(block.position())
            cursor.clearSelection()
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        if self._marker_candidate_line is not None:
            selections.append(
                self._text_or_line_selection(
                    self.source_edit,
                    self._marker_candidate_span,
                    self._marker_candidate_line,
                    QColor("#ffe082"),
                )
            )
        if self._replay_highlight_line is not None:
            selections.append(
                self._text_or_line_selection(
                    self.source_edit,
                    self._replay_source_span,
                    self._replay_highlight_line,
                    QColor("#ffd54f"),
                )
            )
        self.source_edit.setExtraSelections(selections)
        self._set_text_or_line_highlight(
            self.translation_edit,
            self._replay_translation_span,
            self._replay_highlight_line,
            QColor("#ffd54f"),
        )
        self._set_text_or_line_highlight(
            self.transcription_edit,
            self._replay_transcription_span,
            self._replay_highlight_line,
            QColor("#ffd54f"),
        )

    def _show_synchronized_line(self, line_number: int) -> None:
        self._set_replay_spans(None, None, None)
        self._replay_highlight_line = line_number
        self._render_source_highlights()
        if self._active_cards_dialog:
            self._active_cards_dialog.show_line(line_number)
        for editor in (
            self.source_edit,
            self.translation_edit,
            self.transcription_edit,
        ):
            self._scroll_editor_to_line(editor, line_number)

    def _show_synchronized_row(
        self,
        row: TranslationRow,
        card_progress: tuple[int, int] | None = None,
    ) -> None:
        self._replay_highlight_line = row.index
        if self._study_mode and self._active_cards_dialog is None:
            cursor = self.source_edit.textCursor()
            if row.source_start is not None:
                cursor.setPosition(row.source_start)
            else:
                block = self.source_edit.document().findBlockByNumber(row.index)
                if block.isValid():
                    cursor.setPosition(block.position())
            self.source_edit.setTextCursor(cursor)
        self._set_replay_spans(
            _span(row.source_start, row.source_end),
            _span(row.translation_start, row.translation_end),
            _span(row.transcription_start, row.transcription_end),
        )
        self._render_source_highlights()
        if self._active_cards_dialog:
            if card_progress:
                current, total = card_progress
            elif self.sequence.active and self._sequence_scope in {
                "cards",
                "cards_range",
            }:
                current, total = self.sequence.progress
            else:
                current = total = None
            self._active_cards_dialog.show_playback_fields(
                row.index,
                self._card_fields_for_row(row),
                current,
                total,
            )
        self._scroll_editor_to_span(self.source_edit, self._replay_source_span, row.index)
        self._scroll_editor_to_span(
            self.translation_edit,
            self._replay_translation_span,
            row.index,
        )
        self._scroll_editor_to_span(
            self.transcription_edit,
            self._replay_transcription_span,
            row.index,
        )

    def _set_replay_spans(
        self,
        source: tuple[int, int] | None,
        translation: tuple[int, int] | None,
        transcription: tuple[int, int] | None,
    ) -> None:
        self._replay_source_span = source
        self._replay_translation_span = translation
        self._replay_transcription_span = transcription

    @classmethod
    def _scroll_editor_to_span(
        cls,
        editor: QTextEdit,
        span: tuple[int, int] | None,
        fallback_line: int,
    ) -> None:
        if not span:
            cls._scroll_editor_to_line(editor, fallback_line)
            return
        cursor = editor.textCursor()
        cursor.setPosition(min(span[0], editor.document().characterCount() - 1))
        cursor_rect = editor.cursorRect(cursor)
        if editor.viewport().rect().contains(cursor_rect.center()) and editor.isVisible():
            return
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

    @staticmethod
    def _scroll_editor_to_line(editor: QTextEdit, line_number: int) -> None:
        block = editor.document().findBlockByNumber(line_number)
        if not block.isValid():
            return
        cursor = editor.textCursor()
        cursor.setPosition(block.position())
        cursor_rect = editor.cursorRect(cursor)
        if editor.viewport().rect().contains(cursor_rect.center()) and editor.isVisible():
            return
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

    @staticmethod
    def _set_line_highlight(editor: QTextEdit, line_number: int | None, color: QColor) -> None:
        if line_number is None:
            editor.setExtraSelections([])
            return
        block = editor.document().findBlockByNumber(line_number)
        if not block.isValid():
            editor.setExtraSelections([])
            return
        cursor = editor.textCursor()
        cursor.setPosition(block.position())
        cursor.clearSelection()
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        editor.setExtraSelections([selection])

    @classmethod
    def _set_text_or_line_highlight(
        cls,
        editor: QTextEdit,
        span: tuple[int, int] | None,
        line_number: int | None,
        color: QColor,
    ) -> None:
        if line_number is None:
            editor.setExtraSelections([])
            return
        editor.setExtraSelections(
            [cls._text_or_line_selection(editor, span, line_number, color)]
        )

    @staticmethod
    def _text_or_line_selection(
        editor: QTextEdit,
        span: tuple[int, int] | None,
        line_number: int,
        color: QColor,
    ) -> QTextEdit.ExtraSelection:
        cursor = editor.textCursor()
        selection = QTextEdit.ExtraSelection()
        if span and span[0] < span[1]:
            maximum = max(0, editor.document().characterCount() - 1)
            cursor.setPosition(min(span[0], maximum))
            cursor.setPosition(min(span[1], maximum), QTextCursor.MoveMode.KeepAnchor)
        else:
            block = editor.document().findBlockByNumber(line_number)
            if block.isValid():
                cursor.setPosition(block.position())
            cursor.clearSelection()
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = cursor
        selection.format.setBackground(color)
        return selection

    @Slot()
    def cancel_operation(self) -> None:
        if self.sequence.active:
            self.stop_current_operation()
            return
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
            self.statusBar().showMessage(self._t("canceling"))
            self.cancel_button.setEnabled(False)

    def _reset_audio_state(self) -> None:
        if self.sequence.active:
            self._stop_sequence()
        self.stop_audio()
        self._audio_line_number = None
        self._replay_highlight_line = None
        self._render_source_highlights()
        if self.audio_path:
            old_path = self.audio_path
            self.audio_path = None
            self.repository.delete_temporary_audio(old_path)
        self.audio_manifest_path = None
        self.audio_srt_path = None
        self.timed_manifest = None
        self._timed_playback_active = False
        self._timed_playback_scope = None
        self._timed_stop_ms = None
        self._audio_is_complete_document = False
        self._offline_package_active = False
        self.ab_audio_cache.clear()
        self.replay_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        self._update_save_audio_button()
        if not self.progress.isVisible():
            self.speak_button.setEnabled(True)
            self.translate_button.setEnabled(not self._study_mode)
            self.open_button.setEnabled(True)

    @Slot()
    def replay_audio(self) -> None:
        if self._range_a_line is not None and self._range_b_line is not None:
            self._start_ab_sequence()
            return
        if self._timed_audio_ready():
            self._start_timed_playback(
                self._timed_start_for_current_row(), None, "all"
            )
        else:
            self._start_sequence()

    def _start_sequence(self) -> None:
        rows = build_sentence_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )
        if not rows:
            if self.audio_path and self.audio_path.exists():
                self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
                self.player.setPosition(0)
                self.player.play()
                self.statusBar().showMessage(self._t("replay_saved"))
            else:
                QMessageBox.information(
                    self, self.windowTitle(), self._t("no_speech_lines")
                )
            return
        if self._study_mode:
            current = self._current_study_row()
            if current in rows:
                rows = rows[rows.index(current) :]
        self._begin_sequence(rows, "all")

    @Slot()
    def play_ab_range(self) -> None:
        self._start_ab_sequence()

    @Slot()
    def repeat_ab_range(self) -> None:
        if not self._ab_repeat_ready:
            return
        self._start_ab_sequence()

    def _start_ab_sequence(self) -> None:
        if self._range_a_line is None or self._range_b_line is None:
            QMessageBox.information(
                self, self.windowTitle(), self._t("set_markers_first")
            )
            return
        rows = self._rows_in_ab_range(
            build_sentence_translation_rows(
                self.source_edit.toPlainText(),
                self.translation_edit.toPlainText(),
                self.transcription_edit.toPlainText(),
            )
        )
        if self._timed_audio_ready() and self.timed_manifest:
            interval = self._timed_interval_for_rows(rows)
            if interval:
                self._ab_repeat_ready = False
                self._start_timed_playback(interval[0], interval[1], "ab")
                return
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        if not rows:
            QMessageBox.information(
                self,
                self.windowTitle(),
                self._t("empty_range"),
            )
            return
        self._begin_sequence(rows, "ab")

    def _begin_sequence(self, rows: list[TranslationRow], scope: str) -> None:
        if self._offline_package_active:
            self._show_offline_marker_error()
            return
        if not self.selected_voice():
            QMessageBox.information(self, self.windowTitle(), self._t("select_voice"))
            return

        self._stop_sequence()
        self._sequence_scope = scope
        self._ab_repeat_ready = False
        generation = self.sequence.start(rows)
        self.replay_button.setEnabled(False)
        self._update_save_audio_button()
        self.stop_button.setEnabled(True)
        self._update_ab_controls()
        self._play_next_sequence_line(generation)

    def _ab_audio_cache_key(
        self,
        line_number: int,
        source_text: str,
        speech_text: str,
        voice: str,
        settings: TtsSettings,
    ) -> str:
        return "\x1f".join(
            (
                self.current_language.key,
                voice,
                str(settings.rate),
                str(settings.pitch),
                str(settings.volume),
                str(line_number),
                source_text,
                speech_text,
            )
        )

    def _line_audio_cache_contains(self, path: Path | None) -> bool:
        return self.ab_audio_cache.contains(path) or self.card_audio_cache.contains(path)

    def _play_next_sequence_line(self, generation: int) -> None:
        if not self.sequence.matches(generation):
            return
        row = self.sequence.current
        if row is None:
            self._finish_sequence()
            return

        line_number = row.index
        source_text = row.source
        self._show_synchronized_row(row)
        current, total = self.sequence.progress
        prefix = "A–B · " if self._sequence_scope == "ab" else ""
        self.statusBar().showMessage(
            self._t(
                "line_preparing",
                prefix=prefix,
                current=current,
                total=total,
            )
        )

        translated_text = row.translation
        voice = self.selected_voice()
        if not voice:
            self._stop_sequence(self._t("voice_not_selected"))
            return
        tts_settings = self.tts_settings
        line_cache = None
        if self._sequence_scope == "ab":
            line_cache = self.ab_audio_cache
        elif self._sequence_scope in {"cards", "cards_range"}:
            line_cache = self.card_audio_cache

        def prepare_line(cancelled: Callable[[], bool]) -> tuple[str, str, bool, bool]:
            target_text = translated_text or self.translator.translate(source_text, cancelled)
            target_text = self.language_controller.prepare_translation(
                source_text,
                target_text,
            )
            speech_text = self.language_controller.prepare_speech(target_text)
            cache_key: str | None = None
            if line_cache:
                cache_key = self._ab_audio_cache_key(
                    line_number,
                    source_text,
                    speech_text,
                    voice,
                    tts_settings,
                )
                cached = line_cache.get(cache_key)
                if cached:
                    return str(cached), target_text, target_text != translated_text, True
                output = line_cache.path_for(cache_key)
            else:
                fd, filename = tempfile.mkstemp(
                    prefix="gpt01_sequence_tts_",
                    suffix=".mp3",
                )
                os.close(fd)
                output = Path(filename)
            try:
                self.speech.synthesize(
                    speech_text,
                    voice,
                    output,
                    cancelled,
                    settings=tts_settings,
                )
            except Exception:
                if cache_key and line_cache:
                    line_cache.discard(cache_key)
                else:
                    output.unlink(missing_ok=True)
                raise
            return str(output), target_text, target_text != translated_text, False

        def play_line(result: tuple[str, str, bool, bool]) -> None:
            filename, target_text, translation_changed, cache_hit = result
            if not self.sequence.matches(generation):
                output = Path(filename)
                if not self._line_audio_cache_contains(output):
                    output.unlink(missing_ok=True)
                return
            if translation_changed:
                self._set_parallel_line(self.translation_edit, line_number, target_text)
                self._set_parallel_line(
                    self.transcription_edit,
                    line_number,
                    self.language_controller.transcribe(target_text),
                )
                self._dirty = True
                self._show_synchronized_line(line_number)
            self._audio_line_number = line_number
            if self._sequence_scope == "speak":
                self._sequence_audio_parts.append(Path(filename))
            self._play_file(filename)
            self.stop_button.setEnabled(True)
            self.statusBar().showMessage(
                self._t(
                    "line_playing",
                    prefix=prefix,
                    current=current,
                    total=total,
                    mode=self._t("from_cache") if cache_hit else self._t("playback"),
                )
            )

        def sequence_error(message: str) -> None:
            self._stop_sequence(self._t("sequence_error"))
            self._show_error(message)

        self._run_task(
            prepare_line,
            play_line,
            self._t("line_synthesizing", current=current, total=total),
            sequence_error,
        )

    @staticmethod
    def _set_parallel_line(editor: QTextEdit, line_number: int, text: str) -> None:
        lines = editor.toPlainText().split("\n")
        if len(lines) <= line_number:
            lines.extend("" for _ in range(line_number + 1 - len(lines)))
        lines[line_number] = text
        editor.blockSignals(True)
        editor.setPlainText("\n".join(lines))
        editor.blockSignals(False)

    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if (
            status
            in {
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            }
            and self._timed_playback_active
            and self._timed_pending_start_ms is not None
        ):
            start_ms = self._timed_pending_start_ms
            self._timed_pending_start_ms = None
            self.player.setPosition(start_ms)
            self._timed_position_changed(start_ms)
            self.player.play()
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._timed_playback_active:
            self._finish_timed_playback()
            return
        if not self.sequence.active:
            return
        generation = self.sequence.generation
        if self.sequence.advance() is None:
            self._finish_sequence()
            return
        self._play_next_sequence_line(generation)

    def _finish_sequence(self) -> None:
        completed_scope = self._sequence_scope
        self.sequence.complete()
        self._sequence_scope = None
        if completed_scope == "speak":
            self._finalize_speak_sequence_audio()
        self._ab_repeat_ready = completed_scope == "ab"
        self._replay_highlight_line = None
        self._render_source_highlights()
        self.replay_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._update_save_audio_button()
        self._update_ab_controls()
        if self._ab_repeat_ready:
            self.statusBar().showMessage(self._t("range_complete"))
        else:
            self.statusBar().showMessage(self._t("sequence_complete"))

    def _stop_sequence(self, message: str | None = None) -> None:
        was_active = self.sequence.stop()
        self._sequence_scope = None
        self._ab_repeat_ready = False
        self._replay_highlight_line = None
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
        self.player.stop()
        self.player.setSource(QUrl())
        self._discard_speak_sequence_audio()
        self._render_source_highlights()
        if was_active:
            self.replay_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
            self.stop_button.setEnabled(False)
            self.statusBar().showMessage(message or self._t("sequence_stopped"))
        self._update_ab_controls()

    def _finalize_speak_sequence_audio(self) -> None:
        parts = [path for path in self._sequence_audio_parts if path.exists()]
        if not parts:
            self._sequence_audio_parts.clear()
            return
        fd, filename = tempfile.mkstemp(prefix="gpt01_tts_", suffix=".mp3")
        os.close(fd)
        output = Path(filename)
        try:
            with output.open("wb") as destination:
                for part in parts:
                    destination.write(part.read_bytes())
        except OSError:
            output.unlink(missing_ok=True)
            self._sequence_audio_parts.clear()
            return
        self.player.setSource(QUrl())
        self.audio_path = output
        self._audio_is_complete_document = True
        for part in parts:
            self.repository.delete_temporary_audio(part)
        self._sequence_audio_parts.clear()
        self._update_save_audio_button()

    def _discard_speak_sequence_audio(self) -> None:
        parts = tuple(self._sequence_audio_parts)
        for part in parts:
            self.repository.delete_temporary_audio(part)
        if self.audio_path in parts:
            self.audio_path = None
            self._audio_is_complete_document = False
        self._sequence_audio_parts.clear()
        self._update_save_audio_button()

    def _update_save_audio_button(self, *, busy: bool | None = None) -> None:
        if busy is None:
            busy = self.tasks.foreground is not None
        complete_audio = bool(
            self._audio_is_complete_document
            and self.audio_path
            and self.audio_path.exists()
        )
        can_generate = bool(
            self.translation_edit.toPlainText().strip() and self.selected_voice()
        )
        self.save_audio_button.setEnabled(
            not busy and not self.sequence.active and (complete_audio or can_generate)
        )

    @Slot()
    def stop_current_operation(self) -> None:
        if self.sequence.active:
            self._stop_sequence()
            return
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
        self.stop_audio()
        self.statusBar().showMessage(self._t("operation_stopped"))

    @Slot()
    def save_audio(self) -> None:
        audio_scope = self._select_audio_export_scope()
        if audio_scope is None:
            return
        translation = self.translation_edit.toPlainText()
        complete_audio = bool(
            audio_scope == "full"
            and self._timed_audio_ready()
        )
        if not complete_audio and not translation.strip():
            QMessageBox.information(
                self, self.windowTitle(), self._t("need_translation")
            )
            return
        voice = self.selected_voice()
        if not complete_audio and not voice:
            QMessageBox.information(self, self.windowTitle(), self._t("select_voice"))
            return
        suggested_stem = self._t("audio_stem")
        if self.current_source_path:
            suggested_stem = self.current_source_path.stem
        suggested = self._export_dialog_path(suggested_stem, ".mp3")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._t("save_mp3_title"),
            str(suggested),
            self._t("mp3_filter"),
        )
        if not filename:
            return
        target = self._language_export_path(filename, ".mp3")
        if complete_audio and self.audio_path:
            self._save_audio_package(
                TimedAudioPackage(
                    self.audio_path,
                    self.audio_manifest_path,  # type: ignore[arg-type]
                    self.audio_srt_path,  # type: ignore[arg-type]
                    self.timed_manifest,  # type: ignore[arg-type]
                ),
                target,
            )
            return

        source_text = self.source_edit.toPlainText()
        selected_rows = build_sentence_translation_rows(
            source_text,
            translation,
            self.transcription_edit.toPlainText(),
        )
        if audio_scope == "range":
            selected_rows = self._rows_in_ab_range(selected_rows)
            if not selected_rows:
                QMessageBox.information(
                    self,
                    self.windowTitle(),
                    self._t("empty_range"),
                )
                return
        tts_settings = self.tts_settings
        language_key = self.current_language.key

        def build_package(
            cancelled: Callable[[], bool],
            report: Callable[[int, int, str], None],
        ) -> TimedAudioPackage:
            prepared_rows: list[TranslationRow] = []
            for row in selected_rows:
                target_text = row.translation or self.translator.translate(
                    row.source,
                    cancelled,
                )
                target_text = self.language_controller.prepare_translation(
                    row.source,
                    target_text,
                )
                prepared_rows.append(
                    TranslationRow(
                        row.index,
                        row.source,
                        target_text,
                        row.transcription
                        or self.language_controller.transcribe(target_text),
                    )
                )
            audio_path, manifest_path, srt_path = self._temporary_audio_package_paths()
            return build_timed_audio_package(
                prepared_rows,
                audio_path,
                manifest_path,
                srt_path,
                language_key,
                voice,
                tts_settings,
                lambda speech_text, output: self.speech.synthesize_timed(
                    speech_text,
                    voice,
                    output,
                    cancelled,
                    settings=tts_settings,
                ),
                speech_text=self.language_controller.prepare_speech,
                progress=lambda current, total: report(
                    current,
                    total,
                    self._t(
                        "audio_package_progress",
                        current=current,
                        total=total,
                        ),
                    ),
                resume_root=(
                    self.repository.ensure_language_directory(self.current_language)
                    / "tts_jobs"
                ),
            )

        def save_generated_package(package: TimedAudioPackage) -> None:
            if audio_scope == "range":
                self._save_audio_package(package, target, register_package=False)
                self.repository.delete_temporary_audio(package.audio_path)
                self._update_save_audio_button()
                return
            previous_audio = self.audio_path
            self.audio_path = package.audio_path
            self.audio_manifest_path = package.manifest_path
            self.audio_srt_path = package.srt_path
            self.timed_manifest = package.manifest
            self._audio_is_complete_document = True
            if previous_audio and previous_audio != self.audio_path:
                self.repository.delete_temporary_audio(previous_audio)
            self._save_audio_package(package, target)
            self._update_save_audio_button()

        self._run_progress_task(
            build_package,
            save_generated_package,
            self._t("synthesizing"),
        )

    def _select_audio_export_scope(self) -> str | None:
        if self._range_a_line is None or self._range_b_line is None:
            return "full"
        first, last = sorted((self._range_a_line, self._range_b_line))
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("save_mp3_title"))
        form = QFormLayout(dialog)
        scope_combo = QComboBox(dialog)
        if self._uses_sentence_markers():
            range_text = self._t(
                "audio_scope_sentence_range",
                start=min(
                    self._range_a_sentence_number,
                    self._range_b_sentence_number,
                ),
                end=max(
                    self._range_a_sentence_number,
                    self._range_b_sentence_number,
                ),
            )
        else:
            range_text = self._t(
                "audio_scope_range", start=first + 1, end=last + 1
            )
        scope_combo.addItem(range_text, "range")
        scope_combo.addItem(self._t("audio_scope_full"), "full")
        form.addRow(self._t("audio_scope_prompt"), scope_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(scope_combo.currentData())

    def _save_audio_package(
        self,
        package: TimedAudioPackage,
        target: Path,
        *,
        register_package: bool = True,
    ) -> None:
        try:
            json_target = target.with_suffix(".json")
            srt_target = target.with_suffix(".srt")
            self._copy_package_file(package.audio_path, target)
            self._copy_package_file(package.manifest_path, json_target)
            self._copy_package_file(package.srt_path, srt_target)
            if register_package:
                save_package_document(
                    target,
                    self.current_language.key,
                    Document(
                        self.source_edit.toPlainText(),
                        self.translation_edit.toPlainText(),
                        self.transcription_edit.toPlainText(),
                    ),
                )
                touch_package_history(
                    self.repository.package_history_path,
                    self.current_language.key,
                    target,
                )
                self.current_source_path = target.with_suffix(".txt")
                self._active_package_name = target.stem
                self._offline_package_active = True
                self._dirty = False
                self._update_document_status()
            self._remember_directory("last_export_directory", target.parent)
            self.statusBar().showMessage(
                self._t("package_saved", name=target.stem)
                if register_package
                else self._t(
                    "audio_package_saved", mp3=target, json=json_target.name, srt=srt_target.name
                )
            )
        except (AppError, OSError) as exc:
            self._show_error(self._t("save_audio_failed", error=exc))

    @staticmethod
    def _copy_package_file(source: Path, target: Path) -> None:
        """Copy one package member unless it already is the selected target."""
        if source.resolve() == target.resolve():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    @Slot()
    def stop_audio(self) -> None:
        was_timed = self._timed_playback_active
        self._timed_playback_active = False
        self._timed_playback_scope = None
        self._timed_stop_ms = None
        self._timed_pending_start_ms = None
        self.player.stop()
        self.player.setSource(QUrl())
        if was_timed:
            self._replay_highlight_line = None
            self._render_source_highlights()
            self._update_ab_controls()

    def _timed_audio_ready(self) -> bool:
        return bool(
            self.audio_path
            and self.audio_path.exists()
            and self.timed_manifest
            and self.audio_manifest_path
            and self.audio_manifest_path.exists()
            and self.audio_srt_path
            and self.audio_srt_path.exists()
        )

    def _start_timed_playback(
        self,
        start_ms: int,
        stop_ms: int | None,
        scope: str,
    ) -> None:
        if not self._timed_audio_ready() or not self.audio_path:
            return
        if self.sequence.active:
            self._stop_sequence()
        desired_source = QUrl.fromLocalFile(str(self.audio_path))
        self.player.stop()
        self._timed_playback_active = True
        self._timed_playback_scope = scope
        self._timed_stop_ms = stop_ms
        self._ab_repeat_ready = False
        requested_start = max(0, start_ms)
        self._timed_position_changed(requested_start)
        if (
            self.player.source() != desired_source
            or self.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadingMedia
        ):
            self._timed_pending_start_ms = requested_start
            if self.player.source() != desired_source:
                self.player.setSource(desired_source)
        else:
            self._timed_pending_start_ms = None
            self.player.setPosition(requested_start)
            self.player.play()
        self.stop_button.setEnabled(True)
        self._update_ab_controls()

    @Slot(int)
    def _timed_position_changed(self, position_ms: int) -> None:
        if not self._timed_playback_active or not self.timed_manifest:
            return
        if self._active_waveform_dialog:
            self._active_waveform_dialog.set_absolute_playhead(position_ms)
        if self._timed_stop_ms is not None and position_ms >= self._timed_stop_ms:
            self._finish_timed_playback()
            return
        timed_line = self.timed_manifest.line_at(position_ms)
        if timed_line and (
            timed_line.line != self._replay_highlight_line
            or _span(timed_line.source_start, timed_line.source_end)
            != self._replay_source_span
        ):
            self._show_synchronized_timed_line(timed_line)

    def _timed_start_for_current_row(self) -> int:
        if not self._study_mode or not self.timed_manifest:
            return 0
        current = self._current_study_row()
        timed_line = next(
            (
                item
                for item in self.timed_manifest.lines
                if current is not None and _timed_matches_row(item, current)
            ),
            None,
        )
        return timed_line.start_ms if timed_line else 0

    def _show_synchronized_timed_line(self, timed_line: TimedLine) -> None:
        row = TranslationRow(
                index=timed_line.line,
                source=timed_line.source,
                translation=timed_line.translation,
                transcription=timed_line.transcription,
                source_start=timed_line.source_start,
                source_end=timed_line.source_end,
                translation_start=timed_line.translation_start,
                translation_end=timed_line.translation_end,
                transcription_start=timed_line.transcription_start,
                transcription_end=timed_line.transcription_end,
            )
        card_progress = None
        if self._active_cards_dialog and self.timed_manifest:
            candidates = list(self.timed_manifest.lines)
            if (
                self._timed_playback_scope == "cards_range"
                and self._has_ab_range()
            ):
                candidates = self._timed_lines_for_rows(self._card_playback_rows())
            elif self._timed_playback_scope == "cards":
                candidates = [
                    item for item in candidates if item.line == timed_line.line
                ]
            try:
                current = candidates.index(timed_line) + 1
            except ValueError:
                current = 1
            card_progress = current, max(1, len(candidates))
        self._show_synchronized_row(row, card_progress)

    def _finish_timed_playback(self) -> None:
        completed_scope = self._timed_playback_scope
        self.player.pause()
        self._timed_playback_active = False
        self._timed_playback_scope = None
        self._timed_stop_ms = None
        self._timed_pending_start_ms = None
        self._replay_highlight_line = None
        self._render_source_highlights()
        self._ab_repeat_ready = completed_scope == "ab"
        self.stop_button.setEnabled(False)
        self._update_ab_controls()
        if self._ab_repeat_ready:
            self.statusBar().showMessage(self._t("range_complete"))
        else:
            self.statusBar().showMessage(self._t("sequence_complete"))

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        busy = self.progress.isVisible()
        self.stop_button.setEnabled(
            playing or busy or self.sequence.active or self._timed_playback_active
        )
        if (
            not playing
            and not busy
            and not self.sequence.active
            and not self._timed_playback_active
        ):
            if self._ab_repeat_ready:
                self.statusBar().showMessage(self._t("range_complete"))
            else:
                self.statusBar().showMessage(self._t("ready"))

    @Slot()
    def save_file(self) -> None:
        original = self.source_edit.toPlainText()
        translation = self.translation_edit.toPlainText()
        transcription = self.transcription_edit.toPlainText()
        if not original and not translation and not transcription:
            QMessageBox.information(
                self, self.windowTitle(), self._t("no_text_to_save")
            )
            return
        if self.subtitle_cues:
            self._save_subtitle_file(original, translation, transcription)
            return
        export_selection = self._select_export_kind()
        if export_selection is None:
            return
        export_kind, export_layout = export_selection
        if export_kind == ExportKind.LEARNING_KIT and (
            not self.audio_path or not self.audio_path.is_file()
        ):
            QMessageBox.information(
                self,
                self.windowTitle(),
                self._t("learning_audio_first"),
            )
            return
        suggested_stem = self._t("translation_stem")
        if self.current_source_path:
            suggested_stem = self.current_source_path.stem
        suggested = self._export_dialog_path(suggested_stem, ".txt")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._export_label(export_kind),
            str(suggested),
            self._t("text_filter"),
        )
        if not filename:
            return
        target = self._language_export_path(filename, ".txt")
        try:
            result = export_document(
                target,
                Document(original, translation, transcription),
                export_kind,
                self.audio_path,
                layout=export_layout,
                profile=self.current_language,
            )
            self._remember_directory("last_export_directory", target.parent)
            if export_kind in {ExportKind.FULL, ExportKind.LEARNING_KIT}:
                self._dirty = False
            message = self._t("saved", path=result.text_path)
            if result.audio_path:
                message += f"; {result.audio_path.name}"
            self.statusBar().showMessage(message)
        except AppError as exc:
            self._show_error(str(exc))

    def _save_subtitle_file(
        self,
        original: str,
        translation: str,
        transcription: str,
    ) -> None:
        if not translation.strip():
            QMessageBox.information(
                self,
                self.windowTitle(),
                self._t("translate_subtitles_first"),
            )
            return
        suggested_stem = (
            self.current_source_path.stem
            if self.current_source_path
            else self._t("subtitles_stem")
        )
        suggested = self._export_dialog_path(suggested_stem, ".srt")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._t("save_subtitles"),
            str(suggested),
            self._t("srt_filter"),
        )
        if not filename:
            return
        target = self._language_export_path(filename, ".srt")
        try:
            save_document(
                target,
                Document(
                    original,
                    translation,
                    transcription,
                    self.subtitle_cues,
                ),
            )
            self._remember_directory("last_export_directory", target.parent)
            self._dirty = False
            self.statusBar().showMessage(self._t("subtitles_saved", path=target))
        except AppError as exc:
            self._show_error(str(exc))

    def _select_export_kind(self) -> tuple[ExportKind, ExportLayout] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("export_format"))
        form = QFormLayout(dialog)
        kind_combo = QComboBox(dialog)
        for kind in ExportKind:
            kind_combo.addItem(self._export_label(kind), kind.value)
        form.addRow(self._t("file_contents"), kind_combo)
        columns_checkbox = QCheckBox(
            self._t("column_layout"),
            dialog,
        )
        columns_checkbox.setChecked(True)
        columns_checkbox.setToolTip(self._t("column_layout_tip"))
        form.addRow(self._t("document_layout"), columns_checkbox)

        def update_layout_availability() -> None:
            columns_checkbox.setEnabled(
                str(kind_combo.currentData()) != ExportKind.SOURCE.value
            )

        kind_combo.currentIndexChanged.connect(update_layout_availability)
        update_layout_availability()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        kind = ExportKind(str(kind_combo.currentData()))
        layout = (
            ExportLayout.THREE_COLUMNS
            if columns_checkbox.isChecked()
            else ExportLayout.SEQUENTIAL
        )
        return kind, layout

    def _export_label(self, kind: ExportKind) -> str:
        keys = {
            ExportKind.FULL: "export_full",
            ExportKind.SOURCE: "export_source",
            ExportKind.TRANSLATION: "export_translation",
            ExportKind.BILINGUAL: "export_bilingual",
            ExportKind.LEARNING_KIT: "export_learning",
        }
        return self._t(keys[kind])

    @Slot(str)
    def _show_error(self, message: str) -> None:
        LOGGER.error("User-visible error: %s", message)
        lowered = message.casefold()
        if any(
            marker in lowered
            for marker in (
                "connection timeout",
                "connection error",
                "request timed out",
                "сервис перевода недоступен",
                "сервис перевода не ответил",
                "сервис синтеза речи недоступен",
                "сервис синтеза речи не ответил",
                "недоступности сети",
            )
        ):
            self._network_unavailable = True
            self._update_document_status()
        QMessageBox.critical(
            self,
            self.windowTitle(),
            self._t("operation_failed", message=message, log=LOG_PATH),
        )

    def _show_offline_marker_error(self) -> None:
        message = self._t("offline_marker_missing")
        LOGGER.error("Offline package timestamp mismatch")
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, self.windowTitle(), message)

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            self.windowTitle(),
            self._t("unsaved_changes"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _restore_app_state(self) -> None:
        restored = self.repository.load_session(self.current_language)
        state = restored.state
        self._loading_document = True
        self.source_edit.setPlainText(state.original)
        self.translation_edit.setPlainText(state.translation)
        self.transcription_edit.setPlainText(state.transcription)
        self._loading_document = False
        self._dirty = False

        if state.selected_voice:
            voice_index = self.voice_combo.findData(state.selected_voice)
            if voice_index >= 0:
                self.voice_combo.setCurrentIndex(voice_index)
        self.audio_output.setVolume(state.volume)
        self.tts_settings = state.tts_settings
        self.audio_preparation_mode = state.audio_preparation_mode
        self._set_source_window_visible(True)
        self._set_translation_window_visible(True)
        self._set_transcription_window_visible(True)
        self._set_source_window_visible(state.source_visible)
        self._set_translation_window_visible(state.translation_window_visible)
        self._set_transcription_window_visible(state.transcription_visible)
        self.panels_swapped = state.panels_swapped
        self._apply_panel_order()
        if len(state.splitter_sizes) == 3:
            self.editors.setSizes(state.splitter_sizes)
        if state.window_geometry:
            try:
                encoded = base64.b64decode(state.window_geometry.encode("ascii"))
                self.restoreGeometry(QByteArray(encoded))
            except (ValueError, TypeError):
                LOGGER.warning("Saved window geometry is invalid")
        self.current_source_path = (
            Path(state.current_source_path) if state.current_source_path else None
        )
        self.subtitle_cues = self._restore_subtitle_cues(self.current_source_path)
        self.audio_path = restored.audio_path
        self.audio_manifest_path = (
            self.audio_path.with_suffix(".json") if self.audio_path else None
        )
        self.audio_srt_path = self.audio_path.with_suffix(".srt") if self.audio_path else None
        self.timed_manifest = (
            load_manifest(self.audio_manifest_path)
            if self.audio_manifest_path and self.audio_manifest_path.exists()
            else None
        )
        self._audio_is_complete_document = self._timed_audio_ready()
        self._offline_package_active = False
        if self.audio_path:
            self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
        self._update_save_audio_button()
        self.replay_button.setEnabled(
            bool(self.source_edit.toPlainText().strip())
            or bool(self.audio_path and self.audio_path.exists())
        )
        self._set_study_mode(
            bool(self.source_edit.toPlainText().strip())
            and bool(self.translation_edit.toPlainText().strip())
        )
        self._active_package_name = None
        self._update_document_status()

    @staticmethod
    def _restore_subtitle_cues(path: Path | None) -> tuple[SubtitleCue, ...]:
        if not path or path.suffix.lower() != ".srt" or not path.is_file():
            return ()
        try:
            return load_document(path).subtitles
        except AppError:
            LOGGER.warning("Could not restore SRT timing template: %s", path)
            return ()

    def _save_app_state(self) -> None:
        geometry = base64.b64encode(bytes(self.saveGeometry())).decode("ascii")
        state = AppState(
            original=self.source_edit.toPlainText(),
            translation=self.translation_edit.toPlainText(),
            transcription=self.transcription_edit.toPlainText(),
            selected_voice=self.selected_voice() or "",
            source_visible=not self.source_box.isHidden(),
            transcription_visible=not self.transcription_box.isHidden(),
            translation_window_visible=not self.translation_box.isHidden(),
            panels_swapped=self.panels_swapped,
            splitter_sizes=self.editors.sizes(),
            window_geometry=geometry,
            volume=self.audio_output.volume(),
            current_source_path=str(self.current_source_path or ""),
            tts_rate=self.tts_settings.rate,
            tts_pitch=self.tts_settings.pitch,
            tts_volume=self.tts_settings.volume,
            audio_preparation_mode=self.audio_preparation_mode,
        )
        try:
            self.repository.save_session(self.current_language, state, self.audio_path)
        except OSError:
            LOGGER.exception("Could not save application state")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_changes():
            event.ignore()
            return
        self._closing = True
        self.tasks.cancel_all()
        self.player.stop()
        self._save_app_state()
        self.player.setSource(QUrl())
        if self.audio_path:
            self.repository.delete_temporary_audio(self.audio_path)
        self.ab_audio_cache.clear()
        self.card_audio_cache.clear()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setDesktopFileName(APP_AUTHOR + "." + APP_NAME)
    if APP_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    smoke_test = SMOKE_TEST_MODE
    if smoke_test:
        from gpt01.transcription import to_ipa, to_pinyin, to_romaji

        if any(not path.is_file() for path in HELP_PATHS.values()):
            raise RuntimeError("Packaged user guides are missing")
        transcription_checks = (
            (to_ipa("hello", "en-us"), "hello"),
            (to_ipa("bonjour", "fr-fr"), "bonjour"),
            (to_ipa("hola", "es-es"), "hola"),
            (to_pinyin("你好"), "你好"),
            (to_romaji("日本"), "日本"),
        )
        if any(not result or result == source for result, source in transcription_checks):
            raise RuntimeError("Не загружены данные транскрипции дистрибутива")
        with tempfile.TemporaryDirectory(prefix="voicegun_smoke_") as storage:
            repository = SessionRepository(Path(storage))
            window = MainWindow(repository)
            window.tasks.cancel_all()
            window.player.stop()
            window.ab_audio_cache.clear()
            return 0
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
