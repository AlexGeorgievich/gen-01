"""Small built-in UI catalog for the supported interface languages."""

from __future__ import annotations

SUPPORTED_INTERFACE_LANGUAGES = {"en", "ru"}

_STRINGS: dict[str, tuple[str, str]] = {
    "app_title": (
        "VoiceGun",
        "VoiceGun",
    ),
    "open": ("Open…", "Открыть…"),
    "batch": ("Batch…", "Пакет…"),
    "translate": ("Translate", "Перевести"),
    "speak": ("Speak", "Озвучить"),
    "replay": ("Replay", "Повторить"),
    "stop": ("Stop", "Стоп"),
    "cancel_operation": ("Cancel operation", "Отменить операцию"),
    "save_mp3": ("Save MP3…", "Сохранить MP3…"),
    "save_text": ("Save text…", "Сохранить текст…"),
    "settings": ("Settings", "Настройки"),
    "help": ("Help", "Помощь"),
    "help_title": ("VoiceGun User Guide", "Руководство пользователя VoiceGun"),
    "help_unavailable": (
        "The user guide could not be loaded from {path}.",
        "Не удалось загрузить руководство из {path}.",
    ),
    "close": ("Close", "Закрыть"),
    "clear": ("Clear", "Очистить"),
    "source_text": ("Source text", "Исходный текст"),
    "translation": ("Translation", "Перевод"),
    "transcription": ("Transcription", "Транскрипция"),
    "source_placeholder": (
        "Enter or open the source text…",
        "Введите или откройте исходный текст…",
    ),
    "translation_placeholder": (
        "The translation will appear here…",
        "Здесь появится перевод…",
    ),
    "transcription_placeholder": (
        "The transcription will appear here…",
        "Здесь появится транскрипция…",
    ),
    "language_and_voice": ("Language and Microsoft TTS voice", "Язык и голос Microsoft TTS"),
    "language": ("Language:", "Язык:"),
    "voice": ("Voice:", "Голос:"),
    "refresh_voices": ("Refresh voices", "Обновить голоса"),
    "playback_range": ("Playback range:", "Диапазон воспроизведения:"),
    "reset": ("Reset", "Сброс"),
    "hide_translation": ("Hide translation", "Скрыть перевод"),
    "show_translation": ("Show translation", "Показать перевод"),
    "hide_transcription": ("Hide transcription", "Скрыть транскрипцию"),
    "show_transcription": ("Show transcription", "Показать транскрипцию"),
    "mark_a_tip": (
        "Set the source caret line as marker A",
        "Установить строку курсора как метку A",
    ),
    "mark_b_tip": (
        "Set the source caret line as marker B",
        "Установить строку курсора как метку B",
    ),
    "play_ab_tip": ("Speak all lines from A through B", "Озвучить все строки от A до B"),
    "reset_ab_tip": (
        "Stop A–B playback, clear markers and range audio cache",
        "Остановить A–B, удалить метки и очистить аудиокэш диапазона",
    ),
    "ready": ("Ready", "Готово"),
    "built_in_voices": ("Built-in voices are available.", "Доступны встроенные голоса."),
    "cached_voices": ("Voices loaded from cache: {count}", "Загружено голосов из кэша: {count}"),
    "settings_title": ("Settings", "Настройки"),
    "interface_language": ("Interface language:", "Язык интерфейса:"),
    "english": ("English", "English"),
    "russian": ("Russian", "Русский"),
    "language_English": ("English", "Английский"),
    "language_French": ("French", "Французский"),
    "language_Spanish": ("Spanish", "Испанский"),
    "language_Russian": ("Russian", "Русский"),
    "language_Japan": ("Japanese", "Японский"),
    "language_Chine": ("Chinese", "Китайский"),
    "auto_detect": ("Auto-detect", "Автоопределение"),
    "source_language": ("Source text language:", "Базовый язык первого окна:"),
    "font_size": ("Text editor font size:", "Размер шрифта текстовых окон:"),
    "french_articles": ("French articles:", "Французские артикли:"),
    "articles_auto": ("Automatic (study form)", "Автоматически (учебная форма)"),
    "articles_definite": ("Definite: le, la, l’, les", "Определённые: le, la, l’, les"),
    "articles_indefinite": ("Indefinite: un, une, des", "Неопределённые: un, une, des"),
    "articles_off": ("Do not add", "Не добавлять"),
    "tts_rate": ("TTS rate:", "Скорость TTS:"),
    "tts_pitch": ("TTS pitch:", "Высота тона TTS:"),
    "tts_volume": ("TTS volume:", "Громкость синтеза TTS:"),
    "settings_saved": ("Settings saved.", "Настройки сохранены."),
    "settings_save_failed": (
        "Could not save settings: {error}",
        "Не удалось сохранить настройки: {error}",
    ),
    "open_text": ("Open text", "Открыть текст"),
    "select_batch": (
        "Select documents for batch translation",
        "Выберите документы для пакетного перевода",
    ),
    "enter_source": ("Enter source text.", "Введите исходный текст."),
    "select_voice": ("Select a voice.", "Выберите голос."),
    "need_translation": (
        "Translate or enter the translated text first.",
        "Сначала переведите или введите текст перевода.",
    ),
    "empty_hover_line": ("The line under the pointer is empty.", "Строка под указателем пуста."),
    "refreshing_voices": (
        "Refreshing voices (up to {seconds} seconds)…",
        "Обновление списка голосов (не более {seconds} секунд)…",
    ),
    "network_voices": ("Voices loaded from network: {count}", "Загружено голосов из сети: {count}"),
    "voice_service_empty": (
        "No matching voices were returned. Using the saved list.",
        "Сервис не вернул голоса выбранного языка. Используется сохранённый список.",
    ),
    "voice_refresh_failed": (
        "Could not refresh voices. Using the saved list.\nReason: {reason}",
        "Не удалось обновить список. Используются сохранённые голоса.\nПричина: {reason}",
    ),
    "tts_unavailable": (
        "Ready — Microsoft TTS is temporarily unavailable",
        "Готово — Microsoft TTS временно недоступен",
    ),
    "timeout": ("request timed out", "превышено время ожидания"),
    "synthesizing": ("Synthesizing speech…", "Синтез речи…"),
    "playing": ("Playing…", "Воспроизведение…"),
    "operation_stopped": ("Operation stopped.", "Операция остановлена."),
    "canceling": ("Canceling operation…", "Отмена операции…"),
    "save_mp3_title": ("Save MP3", "Сохранить MP3"),
    "audio_scope_prompt": ("Record:", "Записать:"),
    "audio_scope_range": (
        "A–B interval (lines {start}–{end})",
        "Интервал A–B (строки {start}–{end})",
    ),
    "audio_scope_full": ("Complete text", "Весь текст"),
    "save_audio_first": ("Generate speech first.", "Сначала озвучьте текст."),
    "no_text_to_save": ("There is no text to save.", "Нет текста для сохранения."),
    "export_format": ("Export format", "Формат экспорта"),
    "file_contents": ("File contents:", "Содержимое файла:"),
    "column_layout": (
        "Line-by-line columns in blocks of 10 lines",
        "Построчно по колонкам, блоками по 10 строк",
    ),
    "document_layout": ("Document layout:", "Макет документа:"),
    "unsaved_changes": (
        "There are unsaved changes. Continue without saving?",
        "Есть несохранённые изменения. Продолжить без сохранения?",
    ),
    "operation_failed": (
        "Operation failed.\n\n{message}\n\nDetails were written to {log}.",
        "Операция не выполнена.\n\n{message}\n\nПодробности записаны в {log}.",
    ),
    "documents_filter": (
        "Supported documents (*.txt *.docx *.srt);;Text files (*.txt);;"
        "Word documents (*.docx);;SubRip subtitles (*.srt);;All files (*.*)",
        "Поддерживаемые документы (*.txt *.docx *.srt);;Текстовые файлы (*.txt);;"
        "Документы Word (*.docx);;Субтитры SubRip (*.srt);;Все файлы (*.*)",
    ),
    "text_filter": (
        "Text files (*.txt);;All files (*.*)",
        "Текстовые файлы (*.txt);;Все файлы (*.*)",
    ),
    "srt_filter": (
        "SubRip subtitles (*.srt);;All files (*.*)",
        "Субтитры SubRip (*.srt);;Все файлы (*.*)",
    ),
    "mp3_filter": ("MP3 audio (*.mp3);;All files (*.*)", "Аудиофайлы MP3 (*.mp3);;Все файлы (*.*)"),
    "opened": ("Opened: {path}", "Открыт: {path}"),
    "batch_progress": ("Batch translation: 0 of {total}", "Пакетный перевод: 0 из {total}"),
    "batch_success": ("Successful: {count} of {total}.", "Успешно: {count} из {total}."),
    "more_errors": ("…and {count} more errors", "…и ещё ошибок: {count}"),
    "batch_complete": ("Batch processing completed.", "Пакетная обработка завершена."),
    "translation_progress": (
        "Translation: processed {current} of {total} parts",
        "Перевод: обработано частей {current} из {total}",
    ),
    "translation_preparing": (
        "Preparing structured translation…",
        "Подготовка структурированного перевода…",
    ),
    "translation_complete": (
        "Translated lines: {lines}; parts: {parts}.",
        "Переведено строк: {lines}; частей: {parts}.",
    ),
    "playback_error": ("Playback error: {message}", "Ошибка воспроизведения: {message}"),
    "line_synthesis": ("Line synthesis: {text}", "Синтез строки: {text}"),
    "line_result": ("Line: {text}", "Строка: {text}"),
    "marker_caret": (
        "Place the caret on a source line before setting marker {marker}.",
        "Установите курсор на строку исходного текста перед меткой {marker}.",
    ),
    "marker_set": ("Marker {marker}: line {line}.", "Метка {marker}: строка {line}."),
    "range_reset": (
        "A/B markers and range audio cache were reset.",
        "Метки A/B и аудиокэш диапазона сброшены.",
    ),
    "range_stopped": ("A–B playback stopped.", "Воспроизведение A–B остановлено."),
    "voice_not_selected": ("No voice is selected.", "Голос не выбран."),
    "replay_saved": ("Replaying saved audio…", "Повтор сохранённого аудио…"),
    "no_speech_lines": ("There are no lines to speak.", "Нет строк для озвучивания."),
    "set_markers_first": ("Set markers A and B first.", "Сначала установите метки A и B."),
    "empty_range": (
        "There are no non-empty lines between markers A and B.",
        "Между метками A и B нет непустых строк для озвучивания.",
    ),
    "line_preparing": (
        "{prefix}line {current} of {total}: preparing…",
        "{prefix}строка {current} из {total}: подготовка…",
    ),
    "line_playing": (
        "{prefix}line {current} of {total}: {mode}…",
        "{prefix}строка {current} из {total}: {mode}…",
    ),
    "from_cache": ("from cache", "из кэша"),
    "playback": ("playing", "воспроизведение"),
    "line_synthesizing": (
        "Line {current} of {total}: synthesizing…",
        "Строка {current} из {total}: синтез…",
    ),
    "sequence_error": (
        "Sequential playback stopped because of an error.",
        "Последовательное озвучивание прервано из-за ошибки.",
    ),
    "range_complete": (
        "A–B range completed. Press Space to replay.",
        "Диапазон A–B завершён. Нажмите Space для повторного воспроизведения.",
    ),
    "sequence_complete": (
        "Sequential playback completed.",
        "Последовательное озвучивание завершено.",
    ),
    "sequence_stopped": (
        "Sequential playback stopped.",
        "Последовательное озвучивание остановлено.",
    ),
    "audio_saved": ("Audio saved: {path}", "Аудио сохранено: {path}"),
    "audio_stem": ("voice", "озвучка"),
    "translation_stem": ("translation", "перевод"),
    "subtitles_stem": ("subtitles", "субтитры"),
    "save_audio_failed": (
        "Could not save the MP3 file: {error}",
        "Не удалось сохранить MP3 файл: {error}",
    ),
    "learning_audio_first": (
        "Generate speech before creating a learning kit.",
        "Для учебного комплекта сначала выполните озвучивание.",
    ),
    "saved": ("Saved: {path}", "Сохранено: {path}"),
    "translate_subtitles_first": (
        "Translate the subtitles first.",
        "Сначала выполните перевод субтитров.",
    ),
    "save_subtitles": ("Save translated subtitles", "Сохранить переведённые субтитры"),
    "subtitles_saved": ("Subtitles saved: {path}", "Субтитры сохранены: {path}"),
    "column_layout_tip": (
        "The selected mode produces one, two or three columns. For Chine and Japan, "
        "the bilingual layout uses Pinyin or Romaji instead of characters. When this "
        "option is off, data is saved as sequential sections.",
        "В зависимости от режима выводится одна, две или три колонки. Для Chine и "
        "Japan в двухколоночном режиме выводятся пиньинь и ромадзи вместо иероглифов. "
        "Если выключено, данные сохраняются последовательными разделами.",
    ),
    "export_full": (
        "Full document: source + translation + transcription",
        "Полный документ: оригинал + перевод + транскрипция",
    ),
    "export_source": ("Source text only", "Сохранить только текст"),
    "export_translation": ("Translation only", "Только перевод"),
    "export_bilingual": (
        "Bilingual document: source + translation/transcription",
        "Двуязычный документ: оригинал + перевод/транскрипция",
    ),
    "export_learning": (
        "Learning kit: full TXT + MP3",
        "Учебный комплект: полный TXT + MP3",
    ),
}


def normalize_interface_language(value: object) -> str:
    language = str(value).lower()
    return language if language in SUPPORTED_INTERFACE_LANGUAGES else "en"


def ui_text(language: str, key: str, **values: object) -> str:
    """Return a formatted UI string, falling back to English."""
    english, russian = _STRINGS[key]
    template = russian if normalize_interface_language(language) == "ru" else english
    return template.format(**values)
