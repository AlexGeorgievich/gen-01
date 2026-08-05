import html
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .errors import StorageError
from .models import Document

ORIGINAL_MARKER = "=== ОРИГИНАЛ ==="
TRANSLATION_MARKER = "=== ПЕРЕВОД ==="
LEGACY_TRANSLATION_MARKER = "=== ПЕРЕВОД НА КИТАЙСКИЙ ==="
TRANSCRIPTION_MARKER = "=== ТРАНСКРИПЦИЯ ==="
LEGACY_TRANSCRIPTION_MARKER = "=== ПИНЬИНЬ ==="
MAX_DOCX_XML_SIZE = 10 * 1024 * 1024
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_SRT_TIMING = re.compile(
    r"^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
_SRT_TAG = re.compile(r"<[^>]+>")


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


def parse_srt(text: str) -> Document:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return Document()
    cues: list[str] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next(
            (index for index, line in enumerate(lines) if _SRT_TIMING.match(line)),
            None,
        )
        if timing_index is None:
            continue
        cue_lines = [line for line in lines[timing_index + 1 :] if line]
        if cue_lines:
            cue = html.unescape(_SRT_TAG.sub("", " ".join(cue_lines))).strip()
            if cue:
                cues.append(cue)
    if not cues:
        raise StorageError("SRT-файл не содержит распознаваемых субтитров.")
    return Document(original="\n".join(cues))


def load_docx(path: Path) -> Document:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_SIZE:
                raise StorageError("DOCX-файл слишком велик для безопасного импорта.")
            root = ElementTree.fromstring(archive.read(info))
    except StorageError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise StorageError(f"Не удалось прочитать DOCX-файл: {exc}") from exc

    paragraph_tag = f"{{{WORD_NAMESPACE}}}p"
    text_tag = f"{{{WORD_NAMESPACE}}}t"
    tab_tag = f"{{{WORD_NAMESPACE}}}tab"
    break_tags = {f"{{{WORD_NAMESPACE}}}br", f"{{{WORD_NAMESPACE}}}cr"}
    paragraphs: list[str] = []
    for paragraph in root.iter(paragraph_tag):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == text_tag and node.text:
                parts.append(node.text)
            elif node.tag == tab_tag:
                parts.append("\t")
            elif node.tag in break_tags:
                parts.append("\n")
        paragraphs.append("".join(parts))
    return Document(original="\n".join(paragraphs).strip("\n"))


def load_document(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return load_docx(path)
    try:
        text = decode_text(path.read_bytes())
        return parse_srt(text) if suffix == ".srt" else parse_document(text)
    except StorageError:
        raise
    except (OSError, UnicodeError) as exc:
        raise StorageError(f"Не удалось открыть файл: {exc}") from exc


def save_document(path: Path, document: Document) -> None:
    try:
        path.write_text(serialize_document(document), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise StorageError(f"Не удалось сохранить файл: {exc}") from exc
