from pathlib import Path

from .errors import StorageError
from .models import Document

ORIGINAL_MARKER = "=== ОРИГИНАЛ ==="
TRANSLATION_MARKER = "=== ПЕРЕВОД НА КИТАЙСКИЙ ==="
LEGACY_TRANSLATION_MARKER = "=== ПЕРЕВОД ==="
TRANSLITERATION_MARKER = "=== ПИНЬИНЬ ==="


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
        transliteration = ""
        if TRANSLITERATION_MARKER in translation:
            translation, transliteration = translation.split(TRANSLITERATION_MARKER, 1)
        return Document(
            original.replace(ORIGINAL_MARKER, "").strip(),
            translation.strip(),
            transliteration.strip(),
        )
    return Document(original=text)


def serialize_document(document: Document) -> str:
    return (
        f"{ORIGINAL_MARKER}\n{document.original.rstrip()}\n\n"
        f"{TRANSLATION_MARKER}\n{document.translation.rstrip()}\n\n"
        f"{TRANSLITERATION_MARKER}\n{document.transliteration.rstrip()}\n"
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
