from pathlib import Path

from .errors import StorageError
from .models import Document

ORIGINAL_MARKER = "=== ОРИГИНАЛ ==="
TRANSLATION_MARKER = "=== ПЕРЕВОД ==="
LEGACY_TRANSLATION_MARKER = "=== ПЕРЕВОД НА КИТАЙСКИЙ ==="
TRANSCRIPTION_MARKER = "=== ТРАНСКРИПЦИЯ ==="
LEGACY_TRANSCRIPTION_MARKER = "=== ПИНЬИНЬ ==="


def decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


def parse_document(text: str) -> Document:
    marker = next(
        (item for item in (TRANSLATION_MARKER, LEGACY_TRANSLATION_MARKER) if item in text),
        None,
    )
    if ORIGINAL_MARKER in text and marker:
        original, translation = text.split(marker, 1)
        transcription = ""
        transcription_marker = next(
            (
                item
                for item in (TRANSCRIPTION_MARKER, LEGACY_TRANSCRIPTION_MARKER)
                if item in translation
            ),
            None,
        )
        if transcription_marker:
            translation, transcription = translation.split(transcription_marker, 1)
        return Document(
            original.replace(ORIGINAL_MARKER, "").strip(),
            translation.strip(),
            transcription.strip(),
        )
    return Document(original=text)


def serialize_document(document: Document) -> str:
    return (
        f"{ORIGINAL_MARKER}\n{document.original.rstrip()}\n\n"
        f"{TRANSLATION_MARKER}\n{document.translation.rstrip()}\n\n"
        f"{TRANSCRIPTION_MARKER}\n{document.transcription.rstrip()}\n"
    )


def load_document(path: Path) -> Document:
    try:
        return parse_document(decode_text(path.read_bytes()))
    except (OSError, UnicodeError) as exc:
        raise StorageError(f"Не удалось открыть файл: {exc}") from exc


def save_document(path: Path, document: Document) -> None:
    try:
        path.write_text(serialize_document(document), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise StorageError(f"Не удалось сохранить файл: {exc}") from exc
