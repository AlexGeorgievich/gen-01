import html
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .errors import StorageError
from .models import Document, SubtitleCue

ORIGINAL_MARKER = "=== ОРИГИНАЛ ==="
TRANSLATION_MARKER = "=== ПЕРЕВОД ==="
LEGACY_TRANSLATION_MARKER = "=== ПЕРЕВОД НА КИТАЙСКИЙ ==="
TRANSCRIPTION_MARKER = "=== ТРАНСКРИПЦИЯ ==="
LEGACY_TRANSCRIPTION_MARKER = "=== ПИНЬИНЬ ==="
MAX_DOCX_XML_SIZE = 10 * 1024 * 1024
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_SRT_TIMING = re.compile(
    r"^\s*\d+:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d+:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
_SRT_TAG = re.compile(r"<[^>]+>")
_SRT_OUTER_MARKUP = re.compile(
    r"^(?P<opening>(?:<(?!/)[^>]+>)+)(?P<body>.*?)(?P<closing>(?:</[^>]+>)+)$"
)
_SRT_TAG_NAME = re.compile(r"</?\s*([A-Za-z][\w:-]*)")


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
    cues: list[SubtitleCue] = []
    for cue_number, block in enumerate(re.split(r"\n\s*\n", normalized), start=1):
        lines = block.splitlines()
        timing_index = next(
            (index for index, line in enumerate(lines) if _SRT_TIMING.match(line.strip())),
            None,
        )
        if timing_index is None:
            continue
        cue_lines = tuple(line.strip() for line in lines[timing_index + 1 :] if line.strip())
        if cue_lines:
            cue = html.unescape(_SRT_TAG.sub("", " ".join(cue_lines))).strip()
            if cue:
                index = next(
                    (line.strip() for line in lines[:timing_index] if line.strip()),
                    str(cue_number),
                )
                cues.append(
                    SubtitleCue(
                        index=index,
                        timing=lines[timing_index].strip(),
                        source_lines=cue_lines,
                        text=cue,
                    )
                )
    if not cues:
        raise StorageError("SRT-файл не содержит распознаваемых субтитров.")
    return Document(
        original="\n".join(cue.text for cue in cues),
        subtitles=tuple(cues),
    )


def _outer_srt_markup(lines: tuple[str, ...]) -> tuple[str, str]:
    value = " ".join(lines).strip()
    match = _SRT_OUTER_MARKUP.fullmatch(value)
    if not match:
        return "", ""
    opening = match.group("opening")
    closing = match.group("closing")
    opening_names = _SRT_TAG_NAME.findall(opening)
    closing_names = _SRT_TAG_NAME.findall(closing)
    if opening_names != list(reversed(closing_names)):
        return "", ""
    return opening, closing


def serialize_srt(document: Document) -> str:
    if not document.subtitles:
        raise StorageError("Нет исходных тайм-кодов SRT для сохранения.")
    translated = document.translation or document.original
    translated_lines = translated.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(translated_lines) != len(document.subtitles):
        raise StorageError(
            "Количество строк перевода не совпадает с количеством реплик SRT: "
            f"{len(translated_lines)} вместо {len(document.subtitles)}."
        )

    blocks: list[str] = []
    for cue, translated_line in zip(document.subtitles, translated_lines, strict=True):
        opening, closing = _outer_srt_markup(cue.source_lines)
        rendered_text = f"{opening}{translated_line.strip()}{closing}"
        blocks.append(f"{cue.index}\n{cue.timing}\n{rendered_text}")
    return "\n\n".join(blocks) + "\n"


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
        rendered = (
            serialize_srt(document)
            if path.suffix.lower() == ".srt"
            else serialize_document(document)
        )
        path.write_text(rendered, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise StorageError(f"Не удалось сохранить файл: {exc}") from exc
