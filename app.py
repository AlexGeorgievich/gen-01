from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import edge_tts
from PySide6.QtCore import QByteArray, QEvent, QObject, QUrl, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QKeySequence,
    QShortcut,
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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gpt01.audio_cache import LineAudioCache
from gpt01.batch import BatchProcessor, BatchResult
from gpt01.errors import AppError
from gpt01.exporting import (
    EXPORT_LABELS,
    ExportKind,
    ExportLayout,
    export_document,
)
from gpt01.french_grammar import FrenchArticleMode
from gpt01.language_controller import LanguageController
from gpt01.languages import LANGUAGES
from gpt01.models import Document, SubtitleCue, TranslationRow
from gpt01.playback import PlaybackSequence
from gpt01.preferences import Preferences
from gpt01.rows import build_translation_rows, rows_between
from gpt01.services import EdgeSpeechProvider
from gpt01.session import SessionRepository, user_data_root
from gpt01.state import AppState
from gpt01.storage import load_document, save_document
from gpt01.structured_translation import (
    StructuredTranslationResult,
    translate_preserving_layout,
)
from gpt01.tasks import TaskManager
from gpt01.tts import TtsSettings

APP_TITLE = "Многоязычный переводчик + Microsoft TTS"
VOICE_LOAD_TIMEOUT_SECONDS = 15
TTS_TIMEOUT_SECONDS = 90
OPEN_FILTER = (
    "Поддерживаемые документы (*.txt *.docx *.srt);;"
    "Текстовые файлы (*.txt);;Документы Word (*.docx);;"
    "Субтитры SubRip (*.srt);;Все файлы (*.*)"
)
TEXT_FILTER = "Текстовые файлы (*.txt);;Все файлы (*.*)"
SRT_FILTER = "Субтитры SubRip (*.srt);;Все файлы (*.*)"
APPLICATION_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
try:
    USER_DATA_ROOT = user_data_root()
    USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_PATH = USER_DATA_ROOT / "gpt01.log"
except OSError:
    LOG_PATH = Path(tempfile.gettempdir()) / "gpt01.log"
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, repository: SessionRepository | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 760)
        self.tasks = TaskManager(self)
        self._closing = False
        self._dirty = False
        self._loading_document = False
        self._hover_line_number: int | None = None
        self._audio_line_number: int | None = None
        self._replay_highlight_line: int | None = None
        self._range_a_line: int | None = None
        self._range_b_line: int | None = None
        self._sequence_scope: str | None = None
        self._ab_repeat_ready = False
        self.ab_audio_cache = LineAudioCache()
        self.sequence = PlaybackSequence()
        self._switching_language = False
        self.repository = repository or SessionRepository.for_application(APPLICATION_ROOT)
        self.preferences = self.repository.load_preferences()
        self.language_controller = LanguageController(
            self.repository.load_selected_language(),
            self.preferences.source_language_key,
            self.preferences.french_article_mode,
            self.repository.french_lexicon_path(),
        )
        self.current_source_path: Path | None = None
        self.subtitle_cues: tuple[SubtitleCue, ...] = ()
        self.audio_path: Path | None = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.9)
        self.speech = EdgeSpeechProvider(TTS_TIMEOUT_SECONDS)
        self.tts_settings = TtsSettings()

        self.source_edit = QTextEdit()
        self.source_edit.setPlaceholderText("Введите или откройте исходный текст…")
        self.source_edit.viewport().setMouseTracking(True)
        self.source_edit.viewport().installEventFilter(self)
        self.translation_edit = QTextEdit()
        self.translation_edit.setPlaceholderText("Здесь появится перевод…")
        self.translation_edit.setAcceptRichText(False)
        self.transcription_edit = QTextEdit()
        self.transcription_edit.setPlaceholderText("Здесь появится транскрипция…")
        self.transcription_edit.setAcceptRichText(False)

        self.source_title = QLabel("Исходный текст")
        self.translation_title = QLabel("Перевод")
        self.transcription_title = QLabel("Транскрипция")
        for title in (self.source_title, self.translation_title, self.transcription_title):
            title.setStyleSheet("font-weight: 600;")
        self.source_clear_button = QPushButton("Очистка")
        self.translation_clear_button = QPushButton("Очистка")
        self.transcription_clear_button = QPushButton("Очистка")
        for button in (
            self.source_clear_button,
            self.translation_clear_button,
            self.transcription_clear_button,
        ):
            button.setMaximumWidth(90)

        self.open_button = QPushButton("Открыть…")
        self.batch_button = QPushButton("Пакет…")
        self.translate_button = QPushButton("Перевести")
        self.speak_button = QPushButton("Озвучить")
        self.replay_button = QPushButton("Повторить")
        self.replay_button.setEnabled(False)
        self.stop_button = QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        self.cancel_button = QPushButton("Отменить операцию")
        self.cancel_button.setEnabled(False)
        self.save_audio_button = QPushButton("Сохранить MP3…")
        self.save_audio_button.setEnabled(False)
        self.save_button = QPushButton("Сохранить текст…")
        self.settings_button = QPushButton("Setting")

        self.language_combo = QComboBox()
        self.voice_combo = QComboBox()
        self.voice_status = QLabel()
        self.voice_status.setWordWrap(True)
        self.reload_voices_button = QPushButton("Обновить список голосов из сети")
        self.transcription_toggle_button = QPushButton("−")
        self.transcription_toggle_button.setToolTip("Скрыть окно транскрипции")
        self.transcription_toggle_button.setFixedWidth(32)
        self.translation_toggle_button = QPushButton("−")
        self.translation_toggle_button.setToolTip("Скрыть окно перевода")
        self.translation_toggle_button.setFixedWidth(32)
        self.mark_a_button = QPushButton("A")
        self.mark_a_button.setToolTip("Зафиксировать строку под указателем как метку A")
        self.mark_b_button = QPushButton("B")
        self.mark_b_button.setToolTip("Зафиксировать строку под указателем как метку B")
        self.play_ab_button = QPushButton("A–B")
        self.play_ab_button.setToolTip("Озвучить строки между метками A и B")
        self.play_ab_button.setEnabled(False)
        self.reset_ab_button = QPushButton("Сброс")
        self.reset_ab_button.setToolTip(
            "Остановить A–B, удалить метки и очистить аудиокэш диапазона"
        )
        self.reset_ab_button.setEnabled(False)
        for button in (
            self.mark_a_button,
            self.mark_b_button,
            self.play_ab_button,
            self.reset_ab_button,
        ):
            button.setMinimumWidth(48)

        self._build_ui()
        self._populate_languages()
        self._connect_signals()
        self.repository.ensure_language_directory(self.current_language)
        cached_voices = self._load_cached_voices()
        self._populate_voices(cached_voices)
        if self.repository.voice_cache_path(self.current_language).exists():
            self.voice_status.setText(f"Загружено голосов из кэша: {len(cached_voices)}")
        else:
            self.voice_status.setText("Доступны встроенные голоса.")
        self._update_language_labels()
        self._restore_app_state()
        self._apply_editor_font_size()
        self._update_ab_controls()

    @property
    def current_language(self):
        return self.language_controller.profile

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
            self.language_combo.addItem(profile.label, profile.key)
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
        self.translation_title.setText(f"Перевод — {self.current_language.label}")
        mode_names = {
            "pinyin": "пиньинь",
            "romaji": "ромадзи",
            "ipa_en": "IPA (English)",
            "ipa_fr": "IPA (French)",
            "ipa_es": "IPA (Spanish)",
            "ipa_ru": "IPA (Russian)",
        }
        mode_name = mode_names[self.current_language.transcription_mode]
        self.transcription_title.setText(f"Транскрипция — {mode_name}")

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
            self.voice_status.setText(f"Выбран язык: {profile.label}")
        except OSError as exc:
            LOGGER.exception("Could not switch language")
            self._show_error(f"Не удалось переключить язык: {exc}")
        finally:
            self._switching_language = False

    def _load_cached_voices(self) -> list[dict[str, Any]]:
        return self.repository.load_voices(self.current_language)

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Команды")
        toolbar.setMovable(False)
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(self.batch_button)
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

        source_box = QGroupBox()
        source_layout = QVBoxLayout(source_box)
        source_header = QHBoxLayout()
        source_header.addWidget(self.source_title)
        source_header.addStretch(1)
        source_header.addWidget(self.source_clear_button)
        source_layout.addLayout(source_header)
        source_layout.addWidget(self.source_edit)

        self.translation_box = QGroupBox()
        translation_layout = QVBoxLayout(self.translation_box)
        translation_header = QHBoxLayout()
        translation_header.addWidget(self.translation_title)
        translation_header.addStretch(1)
        translation_header.addWidget(self.translation_clear_button)
        translation_layout.addLayout(translation_header)
        translation_layout.addWidget(self.translation_edit)

        self.transcription_box = QGroupBox()
        transcription_layout = QVBoxLayout(self.transcription_box)
        transcription_header = QHBoxLayout()
        transcription_header.addWidget(self.transcription_title)
        transcription_header.addStretch(1)
        transcription_header.addWidget(self.transcription_clear_button)
        transcription_layout.addLayout(transcription_header)
        transcription_layout.addWidget(self.transcription_edit)

        self.editors = QSplitter()
        self.editors.addWidget(source_box)
        self.editors.addWidget(self.translation_box)
        self.editors.addWidget(self.transcription_box)
        self.editors.setSizes([420, 420, 420])

        window_controls = QHBoxLayout()
        self.transcription_control_label = QLabel("Транскрипции:")
        self.translation_control_label = QLabel("Перевод:")
        window_controls.addWidget(self.transcription_control_label)
        window_controls.addWidget(self.transcription_toggle_button)
        window_controls.addSpacing(16)
        window_controls.addWidget(self.translation_control_label)
        window_controls.addWidget(self.translation_toggle_button)
        window_controls.addSpacing(16)
        window_controls.addWidget(self.mark_a_button)
        window_controls.addWidget(self.mark_b_button)
        window_controls.addWidget(self.play_ab_button)
        window_controls.addWidget(self.reset_ab_button)
        window_controls.addStretch(1)

        voice_box = QGroupBox("Язык и голос Microsoft TTS")
        voice_box_layout = QHBoxLayout(voice_box)
        voice_box_layout.addWidget(QLabel("Язык:"))
        voice_box_layout.addWidget(self.language_combo)
        voice_box_layout.addWidget(QLabel("Голос:"))
        voice_box_layout.addWidget(self.voice_combo, 1)
        voice_box_layout.addWidget(self.voice_status)
        voice_box_layout.addWidget(self.reload_voices_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(voice_box)
        layout.addLayout(window_controls)
        layout.addWidget(self.editors, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.hide()
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)
        self.statusBar().showMessage("Готово")

    def _connect_signals(self) -> None:
        self.open_button.clicked.connect(self.open_file)
        self.batch_button.clicked.connect(self.batch_process_files)
        self.translate_button.clicked.connect(self.translate_text)
        self.speak_button.clicked.connect(self.speak_text)
        self.replay_button.clicked.connect(self.replay_audio)
        self.stop_button.clicked.connect(self.stop_current_operation)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.save_audio_button.clicked.connect(self.save_audio)
        self.save_button.clicked.connect(self.save_file)
        self.settings_button.clicked.connect(self.open_settings)
        self.reload_voices_button.clicked.connect(self.load_voices)
        self.transcription_toggle_button.clicked.connect(self._toggle_transcription_window)
        self.translation_toggle_button.clicked.connect(self._toggle_translation_window)
        self.mark_a_button.clicked.connect(self.set_range_marker_a)
        self.mark_b_button.clicked.connect(self.set_range_marker_b)
        self.play_ab_button.clicked.connect(self.play_ab_range)
        self.reset_ab_button.clicked.connect(self.reset_ab_range)
        self.source_clear_button.clicked.connect(self.clear_source_window)
        self.translation_clear_button.clicked.connect(self.clear_translation_window)
        self.transcription_clear_button.clicked.connect(self.clear_transcription_window)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.translation_edit.textChanged.connect(self._on_translation_changed)
        self.source_edit.textChanged.connect(self._on_source_text_changed)
        self.transcription_edit.textChanged.connect(self._on_text_changed)
        self.line_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.line_shortcut.activated.connect(self.speak_line_at_cursor)
        self.ab_repeat_shortcut = QShortcut(QKeySequence("Space"), self)
        self.ab_repeat_shortcut.setEnabled(False)
        self.ab_repeat_shortcut.activated.connect(self.repeat_ab_range)
        self.open_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.open_shortcut.activated.connect(self.open_file)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(
            lambda _error, message: self._show_error(f"Ошибка воспроизведения: {message}")
        )

    @Slot()
    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Setting")
        form = QFormLayout(dialog)

        source_combo = QComboBox(dialog)
        source_combo.addItem("Автоопределение", "auto")
        for profile in LANGUAGES:
            source_combo.addItem(profile.label, profile.key)
        source_index = source_combo.findData(self.preferences.source_language_key)
        source_combo.setCurrentIndex(max(0, source_index))

        font_size = QSpinBox(dialog)
        font_size.setRange(8, 32)
        font_size.setSuffix(" pt")
        font_size.setValue(self.preferences.editor_font_size)

        french_articles = QComboBox(dialog)
        french_articles.addItem("Автоматически (учебная форма)", FrenchArticleMode.AUTO.value)
        french_articles.addItem("Определённые: le, la, l’, les", FrenchArticleMode.DEFINITE.value)
        french_articles.addItem(
            "Неопределённые: un, une, des",
            FrenchArticleMode.INDEFINITE.value,
        )
        french_articles.addItem("Не добавлять", FrenchArticleMode.OFF.value)
        article_index = french_articles.findData(self.preferences.french_article_mode)
        french_articles.setCurrentIndex(max(0, article_index))

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

        form.addRow("Базовый язык первого окна:", source_combo)
        form.addRow("Размер шрифта текстовых окон:", font_size)
        form.addRow("Французские артикли:", french_articles)
        form.addRow("Скорость TTS:", speech_rate)
        form.addRow("Высота тона TTS:", speech_pitch)
        form.addRow("Громкость синтеза TTS:", speech_volume)

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
        self.preferences = Preferences(
            source_language_key=str(source_combo.currentData()),
            editor_font_size=font_size.value(),
            french_article_mode=str(french_articles.currentData()),
            last_open_directory=self.preferences.last_open_directory,
            last_export_directory=self.preferences.last_export_directory,
        )
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
        if tts_changed or previous_article_mode != self.preferences.french_article_mode:
            self._reset_audio_state()
        try:
            self.repository.save_preferences(self.preferences)
            self._save_app_state()
            self.statusBar().showMessage("Настройки сохранены.")
        except OSError as exc:
            self._show_error(f"Не удалось сохранить настройки: {exc}")

    def _run_task(
        self,
        fn: Callable[[Callable[[], bool]], Any],
        on_result: Callable[[Any], None],
        busy_text: str,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._set_busy(True, busy_text)

        def _finished() -> None:
            self._set_busy(False, "Готово")

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
            self._set_busy(False, "Готово")

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
        self.translate_button.setEnabled(not busy)
        self.speak_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.batch_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.language_combo.setEnabled(not busy and self.reload_voices_button.isEnabled())
        self.cancel_button.setEnabled(busy)
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.stop_button.setEnabled(busy or playing or self.sequence.active)
        self.replay_button.setEnabled(
            not busy and not self.sequence.active and bool(self.source_edit.toPlainText().strip())
        )
        self._update_ab_controls()
        self.statusBar().showMessage(message)

    @Slot()
    def open_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть текст",
            self._open_dialog_directory(),
            OPEN_FILTER,
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
            self._remember_directory("last_open_directory", self.current_source_path.parent)
            self.statusBar().showMessage(f"Открыт: {filename}")
        except AppError as exc:
            self._loading_document = False
            self._show_error(str(exc))

    @Slot()
    def batch_process_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите документы для пакетного перевода",
            self._open_dialog_directory(),
            OPEN_FILTER,
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
            f"Пакетный перевод: 0 из {len(paths)}",
        )

    def _batch_completed(self, result: BatchResult) -> None:
        succeeded = result.succeeded
        failed = result.failed
        if succeeded and succeeded[-1].output:
            self._remember_directory("last_export_directory", succeeded[-1].output.parent)
        summary = f"Успешно: {len(succeeded)} из {len(result.items)}."
        if failed:
            details = "\n".join(
                f"• {item.source.name}: {item.error}" for item in failed[:5]
            )
            if len(failed) > 5:
                details += f"\n…и ещё ошибок: {len(failed) - 5}"
            QMessageBox.warning(
                self,
                APP_TITLE,
                f"Пакетная обработка завершена.\n\n{summary}\n\n{details}",
            )
        else:
            QMessageBox.information(
                self,
                APP_TITLE,
                f"Пакетная обработка завершена.\n\n{summary}",
            )
        self.statusBar().showMessage(summary)

    @Slot()
    def translate_text(self) -> None:
        text = self.source_edit.toPlainText()
        if not text.strip():
            QMessageBox.information(self, APP_TITLE, "Введите исходный текст.")
            return

        def translate(
            cancelled: Callable[[], bool],
            report: Callable[[int, int, str], None],
        ) -> StructuredTranslationResult:
            return translate_preserving_layout(
                text,
                self.translator,
                cancelled,
                lambda current, total: report(
                    current,
                    total,
                    f"Перевод: обработано частей {current} из {total}",
                ),
            )

        self._run_progress_task(
            translate,
            self._set_structured_translation,
            "Подготовка структурированного перевода…",
        )

    def _set_structured_translation(self, result: StructuredTranslationResult) -> None:
        self._set_translation(result.text)
        self.statusBar().showMessage(
            f"Переведено строк: {result.translated_lines}; частей: {result.translated_chunks}."
        )

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
            f"Обновление списка голосов (не более {VOICE_LOAD_TIMEOUT_SECONDS} секунд)…"
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
            self.voice_status.setText(f"Загружено голосов из сети: {len(voices)} (сохранено в кэш)")
        else:
            self.voice_status.setText(
                "Сервис не вернул голоса выбранного языка. "
                "Используется сохранённый список."
            )

    @Slot(str)
    def _voices_load_failed(self, message: str) -> None:
        if isinstance(message, str) and message.strip():
            short_message = message.strip().splitlines()[0][:140]
        else:
            short_message = "превышено время ожидания"
        self.voice_status.setText(
            "Не удалось обновить список. Используются сохранённые голоса.\n"
            f"Причина: {short_message}"
        )
        self.statusBar().showMessage("Готово — Microsoft TTS временно недоступен")

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

    @Slot()
    def speak_text(self) -> None:
        source_text = self.source_edit.toPlainText()
        current_translation = self.translation_edit.toPlainText()
        prepared_translation = self.language_controller.prepare_translation(
            source_text,
            current_translation,
        )
        if prepared_translation != current_translation:
            self._set_translation(prepared_translation)
        text = prepared_translation.strip()
        voice = self.selected_voice()
        if not text:
            QMessageBox.information(
                self, APP_TITLE, "Сначала переведите или введите текст перевода."
            )
            return
        if not voice:
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
            return
        tts_settings = self.tts_settings
        speech_text = self.language_controller.prepare_speech(text)
        self.stop_audio()
        self._audio_line_number = None
        self._replay_highlight_line = None
        self._render_source_highlights()
        fd, filename = tempfile.mkstemp(prefix="gpt01_tts_", suffix=".mp3")
        os.close(fd)
        output = Path(filename)

        def synthesize(cancelled: Callable[[], bool]) -> str:
            self.speech.synthesize(
                speech_text,
                voice,
                output,
                cancelled,
                settings=tts_settings,
            )
            return str(output)

        self._run_task(
            synthesize, self._play_file, "Синтез речи…"
        )

    @Slot()
    def speak_line_at_cursor(self) -> None:
        mouse_pos_src = self.source_edit.viewport().mapFromGlobal(QCursor.pos())
        mouse_pos_trans = self.translation_edit.viewport().mapFromGlobal(QCursor.pos())

        if self.source_edit.viewport().rect().contains(mouse_pos_src):
            cursor = self.source_edit.cursorForPosition(mouse_pos_src)
            line_text = cursor.block().text().strip()
            source_line_text = line_text
            needs_translation = True
        elif self.translation_edit.viewport().rect().contains(mouse_pos_trans):
            cursor = self.translation_edit.cursorForPosition(mouse_pos_trans)
            line_text = cursor.block().text().strip()
            source_cursor = self.source_edit.document().findBlockByNumber(
                cursor.blockNumber()
            )
            source_line_text = source_cursor.text().strip() if source_cursor.isValid() else ""
            needs_translation = False
        else:
            cursor = self.source_edit.textCursor()
            line_text = cursor.block().text().strip()
            source_line_text = line_text
            needs_translation = True

        line_number = cursor.blockNumber()

        if not line_text:
            self.statusBar().showMessage("Строка под указателем пуста.")
            return

        voice = self.selected_voice()
        if not voice:
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
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
            self._show_synchronized_line(line_number)
            self.statusBar().showMessage(f"Строка: {translated_line}")
            self._play_file(filename)

        self._run_task(
            translate_and_synthesize, on_ready, f"Синтез строки: {line_text[:25]}…"
        )

    def _play_file(self, filename: str) -> None:
        previous_audio = self.audio_path
        self.audio_path = Path(filename)
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.player.play()
        self.statusBar().showMessage("Воспроизведение…")
        self.replay_button.setEnabled(not self.sequence.active)
        self.save_audio_button.setEnabled(True)
        if (
            previous_audio
            and previous_audio != self.audio_path
            and not self.ab_audio_cache.contains(previous_audio)
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
        self.source_edit.clear()

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

    def _set_transcription_window_visible(self, visible: bool) -> None:
        self.transcription_box.setVisible(visible)
        self.transcription_toggle_button.setText("−" if visible else "+")
        self.transcription_toggle_button.setToolTip(
            "Скрыть окно транскрипции"
            if visible
            else "Открыть окно транскрипции"
        )
        if visible:
            self._resize_visible_editor_windows()

    def _set_translation_window_visible(self, visible: bool) -> None:
        self.translation_box.setVisible(visible)
        self.translation_toggle_button.setText("−" if visible else "+")
        self.translation_toggle_button.setToolTip(
            "Скрыть окно перевода" if visible else "Открыть окно перевода"
        )
        if visible:
            self._resize_visible_editor_windows()

    def _resize_visible_editor_windows(self) -> None:
        visible_indices = [0]
        if not self.translation_box.isHidden():
            visible_indices.append(1)
        if not self.transcription_box.isHidden():
            visible_indices.append(2)

        total_width = max(sum(self.editors.sizes()), self.editors.width(), 3)
        width = total_width // len(visible_indices)
        self.editors.setSizes(
            [width if index in visible_indices else 0 for index in range(3)]
        )

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
            self.statusBar().showMessage(
                f"Установите курсор на строку исходного текста перед меткой {marker}."
            )
            return
        line_number = block.blockNumber()
        if marker == "A":
            self._range_a_line = line_number
            self.mark_a_button.setText(f"A:{line_number + 1}")
        else:
            self._range_b_line = line_number
            self.mark_b_button.setText(f"B:{line_number + 1}")
        self._ab_repeat_ready = False
        self._render_source_highlights()
        self._update_ab_controls()
        self.statusBar().showMessage(f"Метка {marker}: строка {line_number + 1}.")

    def _reset_range_markers(self) -> None:
        self._range_a_line = None
        self._range_b_line = None
        self._ab_repeat_ready = False
        self.mark_a_button.setText("A")
        self.mark_b_button.setText("B")
        self.ab_audio_cache.clear()
        self._render_source_highlights()
        self._update_ab_controls()

    @Slot()
    def reset_ab_range(self) -> None:
        if self.sequence.active and self._sequence_scope == "ab":
            self._stop_sequence("Воспроизведение A–B остановлено.")
        elif self.ab_audio_cache.contains(self.audio_path):
            self.stop_audio()
            self.audio_path = None
        self._reset_range_markers()
        self.statusBar().showMessage("Метки A/B и аудиокэш диапазона сброшены.")

    def _update_ab_controls(self) -> None:
        if not hasattr(self, "mark_a_button"):
            return
        busy = hasattr(self, "progress") and self.progress.isVisible()
        has_source = bool(self.source_edit.toPlainText().strip())
        idle = not busy and not self.sequence.active
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
                idle and has_source and has_range and self._ab_repeat_ready
            )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.source_edit.viewport():
            if event.type() in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress}:
                position = event.position().toPoint()  # type: ignore[attr-defined]
                cursor = self.source_edit.cursorForPosition(position)
                self._hover_line_number = cursor.blockNumber()
                self._render_source_highlights()
            elif event.type() == QEvent.Type.Leave:
                self._hover_line_number = None
                self._render_source_highlights()
        return super().eventFilter(watched, event)

    def _render_source_highlights(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        if self._range_a_line is not None and self._range_a_line == self._range_b_line:
            marker_highlights = ((self._range_a_line, QColor("#d1c4e9")),)
        else:
            marker_highlights = (
                (self._range_a_line, QColor("#c8e6c9")),
                (self._range_b_line, QColor("#bbdefb")),
            )
        highlights = marker_highlights + (
            (self._hover_line_number, QColor("#fff59d")),
            (self._replay_highlight_line, QColor("#ffd54f")),
        )
        for line_number, color in highlights:
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
        self.source_edit.setExtraSelections(selections)
        self._set_line_highlight(
            self.translation_edit, self._replay_highlight_line, QColor("#ffd54f")
        )
        self._set_line_highlight(
            self.transcription_edit, self._replay_highlight_line, QColor("#ffd54f")
        )

    def _show_synchronized_line(self, line_number: int) -> None:
        self._replay_highlight_line = line_number
        self._render_source_highlights()
        for editor in (
            self.source_edit,
            self.translation_edit,
            self.transcription_edit,
        ):
            self._scroll_editor_to_line(editor, line_number)

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

    @Slot()
    def cancel_operation(self) -> None:
        if self.sequence.active:
            self.stop_current_operation()
            return
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
            self.statusBar().showMessage("Отмена операции…")
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
        self.ab_audio_cache.clear()
        self.replay_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        self.save_audio_button.setEnabled(False)
        if not self.progress.isVisible():
            self.speak_button.setEnabled(True)
            self.translate_button.setEnabled(True)
            self.open_button.setEnabled(True)

    @Slot()
    def replay_audio(self) -> None:
        self._start_sequence()

    def _start_sequence(self) -> None:
        rows = build_translation_rows(
            self.source_edit.toPlainText(),
            self.translation_edit.toPlainText(),
            self.transcription_edit.toPlainText(),
        )
        if not rows:
            if self.audio_path and self.audio_path.exists():
                self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
                self.player.setPosition(0)
                self.player.play()
                self.statusBar().showMessage("Повтор сохранённого аудио…")
            else:
                QMessageBox.information(self, APP_TITLE, "Нет строк для озвучивания.")
            return
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
            QMessageBox.information(self, APP_TITLE, "Сначала установите метки A и B.")
            return
        rows = rows_between(
            build_translation_rows(
                self.source_edit.toPlainText(),
                self.translation_edit.toPlainText(),
                self.transcription_edit.toPlainText(),
            ),
            self._range_a_line,
            self._range_b_line,
        )
        if not rows:
            QMessageBox.information(
                self,
                APP_TITLE,
                "Между метками A и B нет непустых строк для озвучивания.",
            )
            return
        self._begin_sequence(rows, "ab")

    def _begin_sequence(self, rows: list[TranslationRow], scope: str) -> None:
        if not self.selected_voice():
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
            return

        self._stop_sequence()
        self._sequence_scope = scope
        self._ab_repeat_ready = False
        generation = self.sequence.start(rows)
        self.replay_button.setEnabled(False)
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

    def _play_next_sequence_line(self, generation: int) -> None:
        if not self.sequence.matches(generation):
            return
        row = self.sequence.current
        if row is None:
            self._finish_sequence()
            return

        line_number = row.index
        source_text = row.source
        self._show_synchronized_line(line_number)
        current, total = self.sequence.progress
        prefix = "A–B · " if self._sequence_scope == "ab" else ""
        self.statusBar().showMessage(
            f"{prefix}строка {current} из {total}: подготовка…"
        )

        translated_text = row.translation
        voice = self.selected_voice()
        if not voice:
            self._stop_sequence("Голос не выбран.")
            return
        tts_settings = self.tts_settings
        use_ab_cache = self._sequence_scope == "ab"

        def prepare_line(cancelled: Callable[[], bool]) -> tuple[str, str, bool, bool]:
            target_text = translated_text or self.translator.translate(source_text, cancelled)
            target_text = self.language_controller.prepare_translation(
                source_text,
                target_text,
            )
            speech_text = self.language_controller.prepare_speech(target_text)
            cache_key: str | None = None
            if use_ab_cache:
                cache_key = self._ab_audio_cache_key(
                    line_number,
                    source_text,
                    speech_text,
                    voice,
                    tts_settings,
                )
                cached = self.ab_audio_cache.get(cache_key)
                if cached:
                    return str(cached), target_text, target_text != translated_text, True
                output = self.ab_audio_cache.path_for(cache_key)
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
                if cache_key:
                    self.ab_audio_cache.discard(cache_key)
                else:
                    output.unlink(missing_ok=True)
                raise
            return str(output), target_text, target_text != translated_text, False

        def play_line(result: tuple[str, str, bool, bool]) -> None:
            filename, target_text, translation_changed, cache_hit = result
            if not self.sequence.matches(generation):
                output = Path(filename)
                if not self.ab_audio_cache.contains(output):
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
            self._play_file(filename)
            self.stop_button.setEnabled(True)
            self.statusBar().showMessage(
                f"{prefix}строка {current} из {total}: "
                f"{'из кэша' if cache_hit else 'воспроизведение'}…"
            )

        def sequence_error(message: str) -> None:
            self._stop_sequence("Последовательное озвучивание прервано из-за ошибки.")
            self._show_error(message)

        self._run_task(
            prepare_line,
            play_line,
            f"Строка {current} из {total}: синтез…",
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
        if status != QMediaPlayer.MediaStatus.EndOfMedia or not self.sequence.active:
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
        self._ab_repeat_ready = completed_scope == "ab"
        self._replay_highlight_line = None
        self._render_source_highlights()
        self.replay_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._update_ab_controls()
        if self._ab_repeat_ready:
            self.statusBar().showMessage(
                "Диапазон A–B завершён. Нажмите Space для повторного воспроизведения."
            )
        else:
            self.statusBar().showMessage("Последовательное озвучивание завершено.")

    def _stop_sequence(self, message: str | None = None) -> None:
        was_active = self.sequence.stop()
        self._sequence_scope = None
        self._ab_repeat_ready = False
        self._replay_highlight_line = None
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
        self.player.stop()
        self.player.setSource(QUrl())
        self._render_source_highlights()
        if was_active:
            self.replay_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
            self.stop_button.setEnabled(False)
            self.statusBar().showMessage(message or "Последовательное озвучивание остановлено.")
        self._update_ab_controls()

    @Slot()
    def stop_current_operation(self) -> None:
        if self.sequence.active:
            self._stop_sequence()
            return
        if self.tasks.foreground:
            self.tasks.cancel_foreground()
        self.stop_audio()
        self.statusBar().showMessage("Операция остановлена.")

    @Slot()
    def save_audio(self) -> None:
        if not self.audio_path or not self.audio_path.exists():
            QMessageBox.information(self, APP_TITLE, "Сначала озвучьте текст.")
            return
        suggested_stem = "озвучка"
        if self.current_source_path:
            suggested_stem = self.current_source_path.stem
        suggested = self._export_dialog_path(suggested_stem, ".mp3")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить MP3",
            str(suggested),
            "Аудиофайлы MP3 (*.mp3);;Все файлы (*.*)",
        )
        if not filename:
            return
        try:
            target = self._language_export_path(filename, ".mp3")
            target.write_bytes(self.audio_path.read_bytes())
            self._remember_directory("last_export_directory", target.parent)
            self.statusBar().showMessage(f"Аудио сохранено: {target}")
        except OSError as exc:
            self._show_error(f"Не удалось сохранить MP3 файл: {exc}")

    @Slot()
    def stop_audio(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        busy = self.progress.isVisible()
        self.stop_button.setEnabled(playing or busy or self.sequence.active)
        if not playing and not busy and not self.sequence.active:
            if self._ab_repeat_ready:
                self.statusBar().showMessage(
                    "Диапазон A–B завершён. Нажмите Space для повторного воспроизведения."
                )
            else:
                self.statusBar().showMessage("Готово")

    @Slot()
    def save_file(self) -> None:
        original = self.source_edit.toPlainText()
        translation = self.translation_edit.toPlainText()
        transcription = self.transcription_edit.toPlainText()
        if not original and not translation and not transcription:
            QMessageBox.information(self, APP_TITLE, "Нет текста для сохранения.")
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
                APP_TITLE,
                "Для учебного комплекта сначала выполните озвучивание.",
            )
            return
        suggested_stem = "перевод"
        if self.current_source_path:
            suggested_stem = self.current_source_path.stem
        suggested = self._export_dialog_path(suggested_stem, ".txt")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            EXPORT_LABELS[export_kind],
            str(suggested),
            TEXT_FILTER,
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
            message = f"Сохранено: {result.text_path}"
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
                APP_TITLE,
                "Сначала выполните перевод субтитров.",
            )
            return
        suggested_stem = self.current_source_path.stem if self.current_source_path else "субтитры"
        suggested = self._export_dialog_path(suggested_stem, ".srt")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить переведённые субтитры",
            str(suggested),
            SRT_FILTER,
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
            self.statusBar().showMessage(f"Субтитры сохранены: {target}")
        except AppError as exc:
            self._show_error(str(exc))

    def _select_export_kind(self) -> tuple[ExportKind, ExportLayout] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Формат экспорта")
        form = QFormLayout(dialog)
        kind_combo = QComboBox(dialog)
        for kind, label in EXPORT_LABELS.items():
            kind_combo.addItem(label, kind.value)
        form.addRow("Содержимое файла:", kind_combo)
        columns_checkbox = QCheckBox(
            "Построчно по колонкам, блоками по 10 строк",
            dialog,
        )
        columns_checkbox.setToolTip(
            "В зависимости от режима выводится одна, две или три колонки. "
            "Для Chine и Japan в двухколоночном режиме выводятся соответственно "
            "пиньинь и ромадзи вместо иероглифов. "
            "Если выключено, данные сохраняются последовательными разделами."
        )
        form.addRow("Макет документа:", columns_checkbox)
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

    @Slot(str)
    def _show_error(self, message: str) -> None:
        LOGGER.error("User-visible error: %s", message)
        QMessageBox.critical(
            self,
            APP_TITLE,
            f"Операция не выполнена.\n\n{message}\n\nПодробности записаны в {LOG_PATH}.",
        )

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            APP_TITLE,
            "Есть несохранённые изменения. Продолжить без сохранения?",
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
        self._set_transcription_window_visible(state.transcription_visible)
        self._set_translation_window_visible(state.translation_window_visible)
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
        self.save_audio_button.setEnabled(bool(self.audio_path))
        if self.audio_path:
            self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
            self.save_audio_button.setEnabled(True)
        self.replay_button.setEnabled(
            bool(self.source_edit.toPlainText().strip())
            or bool(self.audio_path and self.audio_path.exists())
        )

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
            transcription_visible=not self.transcription_box.isHidden(),
            translation_window_visible=not self.translation_box.isHidden(),
            splitter_sizes=self.editors.sizes(),
            window_geometry=geometry,
            volume=self.audio_output.volume(),
            current_source_path=str(self.current_source_path or ""),
            tts_rate=self.tts_settings.rate,
            tts_pitch=self.tts_settings.pitch,
            tts_volume=self.tts_settings.volume,
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
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
