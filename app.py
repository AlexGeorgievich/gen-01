from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import edge_tts
from PySide6.QtCore import QByteArray, QEvent, QObject, QRunnable, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
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
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gpt01.errors import AppError, OperationCancelled
from gpt01.languages import (
    LANGUAGES,
    LanguageProfile,
    get_language,
    load_selected_language,
    save_selected_language,
)
from gpt01.models import Document
from gpt01.services import EdgeSpeechProvider, GoogleTranslationProvider
from gpt01.state import AppState, load_app_state, save_app_state
from gpt01.storage import load_document, save_document
from gpt01.text import numbered_nonempty_lines
from gpt01.transcription import transcribe

APP_TITLE = "Многоязычный переводчик + Microsoft TTS"
VOICE_LOAD_TIMEOUT_SECONDS = 15
TTS_TIMEOUT_SECONDS = 90
TEXT_FILTER = "Текстовые файлы (*.txt);;Все файлы (*.*)"
LOG_PATH = Path(__file__).parent / "gpt01.log"
LEGACY_STATE_PATH = Path(__file__).parent / "app_state.json"
LEGACY_AUDIO_PATH = Path(__file__).parent / "last_audio.mp3"
LANGUAGE_DATA_ROOT = Path(__file__).parent / "language_data"
LANGUAGE_SELECTION_PATH = Path(__file__).parent / "language_selection.json"
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[[Callable[[], bool]], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(self._cancelled.is_set)
            if not self._cancelled.is_set():
                self.signals.result.emit(result)
        except OperationCancelled:
            LOGGER.info("Background operation cancelled")
        except Exception as exc:  # Показываем пользователю понятное сообщение.
            LOGGER.exception("Background operation failed")
            self.signals.error.emit(str(exc) or type(exc).__name__)
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 760)
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()
        self._foreground_worker: Worker | None = None
        self._closing = False
        self._dirty = False
        self._loading_document = False
        self._hover_line_number: int | None = None
        self._audio_line_number: int | None = None
        self._replay_highlight_line: int | None = None
        self._sequence_active = False
        self._sequence_lines: list[tuple[int, str]] = []
        self._sequence_index = 0
        self._sequence_generation = 0
        self._switching_language = False
        self.current_language = get_language(load_selected_language(LANGUAGE_SELECTION_PATH))
        self.current_source_path: Path | None = None
        self.audio_path: Path | None = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.9)
        self.translator = GoogleTranslationProvider(self.current_language.translation_code)
        self.speech = EdgeSpeechProvider(TTS_TIMEOUT_SECONDS)

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

        self.open_button = QPushButton("Открыть…")
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

        self.language_combo = QComboBox()
        self.voice_combo = QComboBox()
        self.voice_status = QLabel()
        self.voice_status.setWordWrap(True)
        self.reload_voices_button = QPushButton("Обновить список голосов из сети")
        self.transcription_toggle_button = QPushButton("−")
        self.transcription_toggle_button.setToolTip("Скрыть окно транскрипции")
        self.transcription_toggle_button.setFixedWidth(32)

        self._build_ui()
        self._populate_languages()
        self._connect_signals()
        self._ensure_language_directory()
        cached_voices = self._load_cached_voices()
        self._populate_voices(cached_voices)
        if self._voice_cache_path().exists():
            self.voice_status.setText(f"Загружено голосов из кэша: {len(cached_voices)}")
        else:
            self.voice_status.setText("Доступны встроенные голоса.")
        self._update_language_labels()
        self._restore_app_state()

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

    def _language_directory(self, profile: LanguageProfile | None = None) -> Path:
        return LANGUAGE_DATA_ROOT / (profile or self.current_language).key

    def _state_path(self) -> Path:
        return self._language_directory() / "app_state.json"

    def _last_audio_path(self) -> Path:
        return self._language_directory() / "last_audio.mp3"

    def _voice_cache_path(self) -> Path:
        return self._language_directory() / "voices_cache.json"

    def _ensure_language_directory(self) -> None:
        try:
            self._language_directory().mkdir(parents=True, exist_ok=True)
        except OSError:
            LOGGER.exception("Could not create language directory: %s", self.current_language.key)

    @staticmethod
    def _delete_temporary_audio(path: Path | None) -> None:
        if not path:
            return
        try:
            temp_root = Path(tempfile.gettempdir()).resolve()
            if path.parent.resolve() == temp_root and path.name.startswith("gpt01_"):
                path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not remove temporary audio: %s", path)

    def _update_language_labels(self) -> None:
        self.translation_box.setTitle(f"Перевод — {self.current_language.label}")
        mode_names = {"pinyin": "пиньинь", "romaji": "ромадзи", "latin": "латиница"}
        mode_name = mode_names[self.current_language.transcription_mode]
        self.transcription_box.setTitle(f"Транскрипция — {mode_name}")

    @Slot()
    def _on_language_changed(self) -> None:
        if self._switching_language:
            return
        key = str(self.language_combo.currentData() or "")
        profile = get_language(key)
        if profile.key == self.current_language.key:
            return

        self._switching_language = True
        try:
            self.stop_current_operation()
            self._save_app_state()
            previous_audio = self.audio_path
            self.player.setSource(QUrl())
            self._delete_temporary_audio(previous_audio)
            self.audio_path = None

            self.current_language = profile
            self.translator = GoogleTranslationProvider(profile.translation_code)
            self._ensure_language_directory()
            self._update_language_labels()
            self._populate_voices(self._load_cached_voices())
            self._restore_app_state()
            save_selected_language(LANGUAGE_SELECTION_PATH, profile.key)
            self.voice_status.setText(f"Выбран язык: {profile.label}")
        except OSError as exc:
            LOGGER.exception("Could not switch language")
            self._show_error(f"Не удалось переключить язык: {exc}")
        finally:
            self._switching_language = False

    def _load_cached_voices(self) -> list[dict[str, Any]]:
        cache_path = self._voice_cache_path()
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return data
            except Exception:
                pass
        return list(self.current_language.fallback_voices)

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Файл")
        toolbar.setMovable(False)
        open_action = QAction("Открыть…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        source_box = QGroupBox("Исходный текст")
        source_layout = QVBoxLayout(source_box)
        source_layout.addWidget(self.source_edit)

        self.translation_box = QGroupBox("Перевод")
        translation_layout = QVBoxLayout(self.translation_box)
        translation_layout.addWidget(self.translation_edit)

        self.transcription_box = QGroupBox("Транскрипция")
        transcription_layout = QVBoxLayout(self.transcription_box)
        transcription_layout.addWidget(self.transcription_edit)

        self.editors = QSplitter()
        self.editors.addWidget(source_box)
        self.editors.addWidget(self.translation_box)
        self.editors.addWidget(self.transcription_box)
        self.editors.setSizes([420, 420, 420])

        transcription_controls = QHBoxLayout()
        transcription_controls.addWidget(QLabel("Окно «Транскрипция»:"))
        transcription_controls.addWidget(self.transcription_toggle_button)
        transcription_controls.addStretch(1)

        voice_box = QGroupBox("Язык и голос Microsoft TTS")
        voice_box_layout = QHBoxLayout(voice_box)
        voice_box_layout.addWidget(QLabel("Язык:"))
        voice_box_layout.addWidget(self.language_combo)
        voice_box_layout.addWidget(QLabel("Голос:"))
        voice_box_layout.addWidget(self.voice_combo, 1)
        voice_box_layout.addWidget(self.voice_status)
        voice_box_layout.addWidget(self.reload_voices_button)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        buttons.addWidget(self.translate_button)
        buttons.addWidget(self.speak_button)
        buttons.addWidget(self.replay_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_audio_button)
        buttons.addWidget(self.save_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(voice_box)
        layout.addLayout(transcription_controls)
        layout.addWidget(self.editors, 1)
        layout.addLayout(buttons)
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
        self.translate_button.clicked.connect(self.translate_text)
        self.speak_button.clicked.connect(self.speak_text)
        self.replay_button.clicked.connect(self.replay_audio)
        self.stop_button.clicked.connect(self.stop_current_operation)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.save_audio_button.clicked.connect(self.save_audio)
        self.save_button.clicked.connect(self.save_file)
        self.reload_voices_button.clicked.connect(self.load_voices)
        self.transcription_toggle_button.clicked.connect(self._toggle_transcription_window)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.translation_edit.textChanged.connect(self._on_translation_changed)
        self.source_edit.textChanged.connect(self._on_text_changed)
        self.transcription_edit.textChanged.connect(self._on_text_changed)
        self.line_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.line_shortcut.activated.connect(self.speak_line_at_cursor)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(
            lambda _error, message: self._show_error(f"Ошибка воспроизведения: {message}")
        )

    def _run_task(
        self,
        fn: Callable[[Callable[[], bool]], Any],
        on_result: Callable[[Any], None],
        busy_text: str,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._set_busy(True, busy_text)
        worker = Worker(fn)
        self._foreground_worker = worker
        self._workers.add(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error or self._show_error)

        def _finished() -> None:
            self._workers.discard(worker)
            if self._foreground_worker is worker:
                self._foreground_worker = None
            self._set_busy(False, "Готово")

        worker.signals.finished.connect(_finished)
        self.thread_pool.start(worker)

    def _set_busy(self, busy: bool, message: str) -> None:
        self.progress.setVisible(busy)
        self.translate_button.setEnabled(not busy)
        self.speak_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.stop_button.setEnabled(busy or playing or self._sequence_active)
        self.replay_button.setEnabled(
            not busy and not self._sequence_active and bool(self.source_edit.toPlainText().strip())
        )
        self.statusBar().showMessage(message)

    @Slot()
    def open_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Открыть текст", "", TEXT_FILTER)
        if not filename:
            return
        try:
            document = load_document(Path(filename))
            self._loading_document = True
            self.source_edit.setPlainText(document.original)
            self.translation_edit.setPlainText(document.translation)
            self.transcription_edit.setPlainText(
                document.transcription
                or transcribe(document.translation, self.current_language.transcription_mode)
            )
            self._loading_document = False
            self._dirty = False
            self.current_source_path = Path(filename)
            self.statusBar().showMessage(f"Открыт: {filename}")
        except AppError as exc:
            self._loading_document = False
            self._show_error(str(exc))

    @Slot()
    def translate_text(self) -> None:
        text = self.source_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, APP_TITLE, "Введите исходный текст.")
            return

        def translate(cancelled: Callable[[], bool]) -> str:
            return self.translator.translate(text, cancelled)

        self._run_task(translate, self._set_translation, "Перевод…")

    @Slot()
    def load_voices(self) -> None:
        profile = self.current_language

        async def fetch() -> tuple[str, list[dict[str, Any]]]:
            voices = await asyncio.wait_for(
                edge_tts.list_voices(), timeout=VOICE_LOAD_TIMEOUT_SECONDS
            )
            filtered = sorted(
                (
                    v
                    for v in voices
                    if str(v.get("Locale", "")).startswith(profile.voice_prefix)
                ),
                key=lambda voice: (
                    str(voice.get("Locale")),
                    str(voice.get("ShortName")),
                ),
            )
            return profile.key, filtered

        self.reload_voices_button.setEnabled(False)
        self.language_combo.setEnabled(False)
        self.voice_status.setText(
            f"Обновление списка голосов (не более {VOICE_LOAD_TIMEOUT_SECONDS} секунд)…"
        )
        worker = Worker(lambda _cancelled: asyncio.run(fetch()))
        self._workers.add(worker)
        worker.signals.result.connect(self._voices_loaded)
        worker.signals.error.connect(self._voices_load_failed)

        def _finished() -> None:
            self._workers.discard(worker)
            self.reload_voices_button.setEnabled(True)
            self.language_combo.setEnabled(True)

        worker.signals.finished.connect(_finished)
        self.thread_pool.start(worker)

    def _voices_loaded(self, result: tuple[str, list[dict[str, Any]]]) -> None:
        language_key, voices = result
        if language_key != self.current_language.key:
            return
        if voices:
            try:
                self._voice_cache_path().write_text(
                    json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8"
                )
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
        text = self.translation_edit.toPlainText().strip()
        voice = self.selected_voice()
        if not text:
            QMessageBox.information(
                self, APP_TITLE, "Сначала переведите или введите текст перевода."
            )
            return
        if not voice:
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
            return
        self.stop_audio()
        self._audio_line_number = None
        self._replay_highlight_line = None
        self._render_source_highlights()
        fd, filename = tempfile.mkstemp(prefix="gpt01_tts_", suffix=".mp3")
        os.close(fd)
        output = Path(filename)

        def synthesize(cancelled: Callable[[], bool]) -> str:
            self.speech.synthesize(text, voice, output, cancelled)
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
            needs_translation = True
        elif self.translation_edit.viewport().rect().contains(mouse_pos_trans):
            cursor = self.translation_edit.cursorForPosition(mouse_pos_trans)
            line_text = cursor.block().text().strip()
            needs_translation = False
        else:
            cursor = self.source_edit.textCursor()
            line_text = cursor.block().text().strip()
            needs_translation = True

        line_number = cursor.blockNumber()

        if not line_text:
            self.statusBar().showMessage("Строка под указателем пуста.")
            return

        voice = self.selected_voice()
        if not voice:
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
            return

        self.stop_audio()

        def translate_and_synthesize(cancelled: Callable[[], bool]) -> tuple[str, str]:
            target_text = line_text
            if needs_translation:
                target_text = self.translator.translate(line_text, cancelled)

            fd, filename = tempfile.mkstemp(prefix="gpt01_line_tts_", suffix=".mp3")
            os.close(fd)
            output = Path(filename)

            self.speech.synthesize(target_text, voice, output, cancelled)
            return (str(output), target_text)

        def on_ready(result: tuple[str, str]) -> None:
            filename, translated_line = result
            self._audio_line_number = line_number
            self._replay_highlight_line = None
            self._render_source_highlights()
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
        self.replay_button.setEnabled(True)
        self.save_audio_button.setEnabled(True)
        if previous_audio and previous_audio != self.audio_path:
            self._delete_temporary_audio(previous_audio)

    @Slot()
    def _on_voice_changed(self) -> None:
        self._reset_audio_state()

    @Slot()
    def _on_text_changed(self) -> None:
        if not self._loading_document:
            self._dirty = True
        self._reset_audio_state()

    @Slot()
    def _on_translation_changed(self) -> None:
        self._on_text_changed()
        transcription = transcribe(
            self.translation_edit.toPlainText(), self.current_language.transcription_mode
        )
        self.transcription_edit.blockSignals(True)
        self.transcription_edit.setPlainText(transcription)
        self.transcription_edit.blockSignals(False)

    def _set_translation(self, text: str) -> None:
        self.translation_edit.setPlainText(text)

    @Slot()
    def _toggle_transcription_window(self) -> None:
        self._set_transcription_window_visible(self.transcription_box.isHidden())

    def _set_transcription_window_visible(self, visible: bool) -> None:
        self.transcription_box.setVisible(visible)
        self.transcription_toggle_button.setText("−" if visible else "+")
        self.transcription_toggle_button.setToolTip(
            "Скрыть окно транскрипции"
            if visible
            else "Открыть окно транскрипции"
        )
        if visible:
            width = max(self.editors.width(), 3)
            self.editors.setSizes([width // 3, width // 3, width // 3])

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.source_edit.viewport():
            if event.type() == QEvent.Type.MouseMove:
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
        highlights = (
            (self._replay_highlight_line, QColor("#ffd54f")),
            (self._hover_line_number, QColor("#fff59d")),
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
        if self._sequence_active:
            self.stop_current_operation()
            return
        if self._foreground_worker:
            self._foreground_worker.cancel()
            self.statusBar().showMessage("Отмена операции…")
            self.cancel_button.setEnabled(False)

    def _reset_audio_state(self) -> None:
        if self._sequence_active:
            self._stop_sequence()
        self.stop_audio()
        self._audio_line_number = None
        self._replay_highlight_line = None
        self._render_source_highlights()
        if self.audio_path:
            old_path = self.audio_path
            self.audio_path = None
            self._delete_temporary_audio(old_path)
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
        lines = numbered_nonempty_lines(self.source_edit.toPlainText())
        if not lines:
            if self.audio_path and self.audio_path.exists():
                self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
                self.player.setPosition(0)
                self.player.play()
                self.statusBar().showMessage("Повтор сохранённого аудио…")
            else:
                QMessageBox.information(self, APP_TITLE, "Нет строк для озвучивания.")
            return
        if not self.selected_voice():
            QMessageBox.information(self, APP_TITLE, "Выберите голос.")
            return

        self._stop_sequence()
        self._sequence_generation += 1
        self._sequence_active = True
        self._sequence_lines = lines
        self._sequence_index = 0
        self.replay_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._play_next_sequence_line(self._sequence_generation)

    def _play_next_sequence_line(self, generation: int) -> None:
        if not self._sequence_active or generation != self._sequence_generation:
            return
        if self._sequence_index >= len(self._sequence_lines):
            self._finish_sequence()
            return

        line_number, source_text = self._sequence_lines[self._sequence_index]
        self._replay_highlight_line = line_number
        self._render_source_highlights()
        current = self._sequence_index + 1
        total = len(self._sequence_lines)
        self.statusBar().showMessage(f"Строка {current} из {total}: подготовка…")

        translated_block = self.translation_edit.document().findBlockByNumber(line_number)
        translated_text = translated_block.text().strip() if translated_block.isValid() else ""
        voice = self.selected_voice()
        if not voice:
            self._stop_sequence("Голос не выбран.")
            return

        def prepare_line(cancelled: Callable[[], bool]) -> tuple[str, str, bool]:
            target_text = translated_text or self.translator.translate(source_text, cancelled)
            fd, filename = tempfile.mkstemp(prefix="gpt01_sequence_tts_", suffix=".mp3")
            os.close(fd)
            output = Path(filename)
            self.speech.synthesize(target_text, voice, output, cancelled)
            return str(output), target_text, not bool(translated_text)

        def play_line(result: tuple[str, str, bool]) -> None:
            filename, target_text, translation_was_missing = result
            if not self._sequence_active or generation != self._sequence_generation:
                Path(filename).unlink(missing_ok=True)
                return
            if translation_was_missing:
                self._set_parallel_line(self.translation_edit, line_number, target_text)
                self._set_parallel_line(
                    self.transcription_edit,
                    line_number,
                    transcribe(target_text, self.current_language.transcription_mode),
                )
                self._dirty = True
            self._audio_line_number = line_number
            self._play_file(filename)
            self.stop_button.setEnabled(True)
            self.statusBar().showMessage(f"Строка {current} из {total}: воспроизведение…")

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
        if status != QMediaPlayer.MediaStatus.EndOfMedia or not self._sequence_active:
            return
        self._sequence_index += 1
        self._play_next_sequence_line(self._sequence_generation)

    def _finish_sequence(self) -> None:
        self._sequence_active = False
        self._sequence_lines = []
        self._replay_highlight_line = None
        self._render_source_highlights()
        self.replay_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Последовательное озвучивание завершено.")

    def _stop_sequence(self, message: str | None = None) -> None:
        was_active = self._sequence_active
        self._sequence_active = False
        self._sequence_generation += 1
        self._sequence_lines = []
        self._replay_highlight_line = None
        if self._foreground_worker:
            self._foreground_worker.cancel()
        self.player.stop()
        self.player.setSource(QUrl())
        self._render_source_highlights()
        if was_active:
            self.replay_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
            self.stop_button.setEnabled(False)
            self.statusBar().showMessage(message or "Последовательное озвучивание остановлено.")

    @Slot()
    def stop_current_operation(self) -> None:
        if self._sequence_active:
            self._stop_sequence()
            return
        if self._foreground_worker:
            self._foreground_worker.cancel()
        self.stop_audio()
        self.statusBar().showMessage("Операция остановлена.")

    @Slot()
    def save_audio(self) -> None:
        if not self.audio_path or not self.audio_path.exists():
            QMessageBox.information(self, APP_TITLE, "Сначала озвучьте текст.")
            return
        suggested = "озвучка.mp3"
        if self.current_source_path:
            suffix = self.current_language.translation_code.lower().replace("-", "_")
            suggested = f"{self.current_source_path.stem}_{suffix}.mp3"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить MP3", suggested, "Аудиофайлы MP3 (*.mp3);;Все файлы (*.*)"
        )
        if not filename:
            return
        if not Path(filename).suffix:
            filename += ".mp3"
        try:
            target = Path(filename)
            target.write_bytes(self.audio_path.read_bytes())
            self.statusBar().showMessage(f"Аудио сохранено: {filename}")
        except OSError as exc:
            self._show_error(f"Не удалось сохранить MP3 файл: {exc}")

    @Slot()
    def stop_audio(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        busy = self.progress.isVisible()
        self.stop_button.setEnabled(playing or busy or self._sequence_active)
        if not playing and not busy and not self._sequence_active:
            self.statusBar().showMessage("Готово")

    @Slot()
    def save_file(self) -> None:
        original = self.source_edit.toPlainText()
        translation = self.translation_edit.toPlainText()
        transcription = self.transcription_edit.toPlainText()
        if not original and not translation and not transcription:
            QMessageBox.information(self, APP_TITLE, "Нет текста для сохранения.")
            return
        suggested = "перевод.txt"
        if self.current_source_path:
            suffix = self.current_language.translation_code.lower().replace("-", "_")
            suggested = f"{self.current_source_path.stem}_{suffix}.txt"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить оригинал и перевод", suggested, TEXT_FILTER
        )
        if not filename:
            return
        if not Path(filename).suffix:
            filename += ".txt"
        try:
            save_document(Path(filename), Document(original, translation, transcription))
            self._dirty = False
            self.current_source_path = Path(filename)
            self.statusBar().showMessage(f"Сохранено: {filename}")
        except AppError as exc:
            self._show_error(str(exc))

    @Slot(str)
    def _show_error(self, message: str) -> None:
        LOGGER.error("User-visible error: %s", message)
        QMessageBox.critical(
            self,
            APP_TITLE,
            f"Операция не выполнена.\n\n{message}\n\nПодробности записаны в gpt01.log.",
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
        state_path = self._state_path()
        load_path = state_path
        if (
            not state_path.exists()
            and self.current_language.key == "Chine"
            and LEGACY_STATE_PATH.exists()
        ):
            load_path = LEGACY_STATE_PATH
        state = load_app_state(load_path)
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
        self._set_transcription_window_visible(state.transcription_visible)
        if len(state.splitter_sizes) == 3:
            self.editors.setSizes(state.splitter_sizes)
        if state.window_geometry:
            try:
                encoded = base64.b64decode(state.window_geometry.encode("ascii"))
                self.restoreGeometry(QByteArray(encoded))
            except (ValueError, TypeError):
                LOGGER.warning("Saved window geometry is invalid")
        if state.current_source_path:
            self.current_source_path = Path(state.current_source_path)
        if state.audio_file:
            restored_audio = load_path.parent / state.audio_file
            if restored_audio.is_file():
                self.audio_path = restored_audio
                self.player.setSource(QUrl.fromLocalFile(str(restored_audio)))
                self.save_audio_button.setEnabled(True)
        elif load_path == LEGACY_STATE_PATH and LEGACY_AUDIO_PATH.is_file():
            self.audio_path = LEGACY_AUDIO_PATH
            self.player.setSource(QUrl.fromLocalFile(str(LEGACY_AUDIO_PATH)))
            self.save_audio_button.setEnabled(True)
        self.replay_button.setEnabled(
            bool(self.source_edit.toPlainText().strip())
            or bool(self.audio_path and self.audio_path.exists())
        )

    def _save_app_state(self) -> None:
        state_path = self._state_path()
        last_audio_path = self._last_audio_path()
        audio_file = ""
        if self.audio_path and self.audio_path.is_file():
            try:
                if self.audio_path.resolve() != last_audio_path.resolve():
                    shutil.copyfile(self.audio_path, last_audio_path)
                audio_file = last_audio_path.name
            except OSError:
                LOGGER.exception("Could not preserve the last audio file")

        geometry = base64.b64encode(bytes(self.saveGeometry())).decode("ascii")
        state = AppState(
            original=self.source_edit.toPlainText(),
            translation=self.translation_edit.toPlainText(),
            transcription=self.transcription_edit.toPlainText(),
            selected_voice=self.selected_voice() or "",
            transcription_visible=not self.transcription_box.isHidden(),
            splitter_sizes=self.editors.sizes(),
            window_geometry=geometry,
            volume=self.audio_output.volume(),
            current_source_path=str(self.current_source_path or ""),
            audio_file=audio_file,
        )
        try:
            save_app_state(state_path, state)
        except OSError:
            LOGGER.exception("Could not save application state")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_changes():
            event.ignore()
            return
        self._closing = True
        for worker in tuple(self._workers):
            worker.cancel()
        self.player.stop()
        self._save_app_state()
        self.player.setSource(QUrl())
        if self.audio_path:
            self._delete_temporary_audio(self.audio_path)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
