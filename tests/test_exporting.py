import pytest

from gpt01.errors import StorageError
from gpt01.exporting import (
    ExportKind,
    ExportLayout,
    display_width,
    export_document,
    render_columns,
    render_export,
    render_three_columns,
)
from gpt01.languages import get_language
from gpt01.models import Document
from gpt01.storage import load_document

DOCUMENT = Document("source", "translation", "transcription")


def test_translation_only_export_contains_no_markers():
    assert render_export(DOCUMENT, ExportKind.TRANSLATION) == "translation\n"


@pytest.mark.parametrize(
    "layout",
    (ExportLayout.SEQUENTIAL, ExportLayout.THREE_COLUMNS),
)
def test_source_only_export_is_plain_first_window_text(layout):
    document = Document("first line\n\nsecond\tline", "translation", "transcription")

    rendered = render_export(document, ExportKind.SOURCE, layout)

    assert rendered == "first line\n\nsecond\tline"
    assert "Исходный текст" not in rendered
    assert "|" not in rendered
    assert "+" not in rendered


def test_bilingual_export_omits_transcription():
    rendered = render_export(DOCUMENT, ExportKind.BILINGUAL)

    assert "source" in rendered
    assert "translation" in rendered
    assert "transcription" not in rendered


def test_full_export_round_trip(tmp_path):
    target = tmp_path / "lesson.txt"

    export_document(target, DOCUMENT, ExportKind.FULL)

    assert load_document(target) == DOCUMENT


def test_learning_kit_copies_audio_with_matching_stem(tmp_path):
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"mp3")
    target = tmp_path / "lesson.txt"

    result = export_document(target, DOCUMENT, ExportKind.LEARNING_KIT, audio)

    assert result.audio_path == tmp_path / "lesson.mp3"
    assert result.audio_path.read_bytes() == b"mp3"
    assert load_document(result.text_path) == DOCUMENT


def test_learning_kit_requires_audio(tmp_path):
    with pytest.raises(StorageError, match="создайте аудио"):
        export_document(tmp_path / "lesson.txt", DOCUMENT, ExportKind.LEARNING_KIT)


def test_three_column_export_has_titles_and_synchronised_rows():
    document = Document("one\ntwo", "un\ndeux", "un\ndeux")

    rendered = render_three_columns(document)

    assert rendered.count("Исходный текст") == 1
    assert rendered.count("Перевод") == 1
    assert rendered.count("Транскрипция") == 1
    assert "| one" in rendered and "| un" in rendered
    assert "| two" in rendered and "| deux" in rendered


def test_three_column_export_has_one_title_and_breaks_after_ten_complete_sentences():
    values = "\n".join(f"line {index}." for index in range(21))

    rendered = render_three_columns(Document(values, values, values))

    blocks = rendered.strip().split("\n\n")
    assert len(blocks) == 3
    assert rendered.count("Исходный текст") == 1
    assert "line 9." in blocks[0] and "line 10." in blocks[1]
    assert "line 19." in blocks[1] and "line 20." in blocks[2]


def test_column_break_moves_to_end_of_sentence():
    lines = [f"Sentence {index}." for index in range(9)]
    lines.extend(["Long sentence", "continues", "ends here.", "Next sentence."])
    values = "\n".join(lines)

    rendered = render_three_columns(Document(values, values, values))

    blocks = rendered.strip().split("\n\n")
    assert len(blocks) == 2
    assert "Long sentence" in blocks[0]
    assert "continues" in blocks[0]
    assert "ends here." in blocks[0]
    assert "Next sentence." in blocks[1]


def test_three_column_export_preserves_missing_parallel_lines():
    rendered = render_three_columns(Document("one\ntwo", "un", ""))

    data_lines = [line for line in rendered.splitlines() if line.startswith("|")]
    assert any("one" in line and "un" in line for line in data_lines)
    assert any("two" in line and line.count("|") == 4 for line in data_lines)


def test_learning_kit_supports_three_column_layout(tmp_path):
    audio = tmp_path / "source.mp3"
    audio.write_bytes(b"mp3")
    target = tmp_path / "lesson.txt"

    export_document(
        target,
        DOCUMENT,
        ExportKind.LEARNING_KIT,
        audio,
        layout=ExportLayout.THREE_COLUMNS,
    )

    assert "Исходный текст" in target.read_text(encoding="utf-8")


def test_translation_only_supports_column_layout_and_ten_row_blocks():
    values = "\n".join(f"translation {index}." for index in range(11))

    rendered = render_columns(Document(translation=values), ExportKind.TRANSLATION)

    blocks = rendered.strip().split("\n\n")
    assert rendered.count("Перевод") == 1
    assert "translation 9." in blocks[0]
    assert "translation 10." in blocks[1]
    assert "Исходный текст" not in rendered


def test_bilingual_supports_two_column_layout():
    rendered = render_export(
        Document("one\ntwo", "un\ndeux", "ignored"),
        ExportKind.BILINGUAL,
        ExportLayout.THREE_COLUMNS,
    )

    assert rendered.count("Исходный текст") == 1
    assert rendered.count("Перевод") == 1
    assert "one" in rendered and "un" in rendered
    assert "two" in rendered and "deux" in rendered


def test_chinese_bilingual_columns_use_pinyin_instead_of_han_characters():
    rendered = render_export(
        Document("привет", "你好", "nǐ hǎo"),
        ExportKind.BILINGUAL,
        ExportLayout.THREE_COLUMNS,
        profile=get_language("Chine"),
    )

    assert rendered.count("Пиньинь") == 1
    assert "nǐ hǎo" in rendered
    assert "你好" not in rendered
    assert "Перевод" not in rendered


def test_japanese_bilingual_columns_use_romaji_instead_of_kanji():
    rendered = render_export(
        Document("привет", "こんにちは", "konnichiwa"),
        ExportKind.BILINGUAL,
        ExportLayout.THREE_COLUMNS,
        profile=get_language("Japan"),
    )

    assert rendered.count("Ромадзи") == 1
    assert "konnichiwa" in rendered
    assert "こんにちは" not in rendered
    assert "Перевод" not in rendered


@pytest.mark.parametrize(
    "language",
    ["English", "French", "Spanish", "German", "Italian", "Turkish", "Russian"],
)
def test_european_bilingual_columns_keep_translation(language):
    rendered = render_export(
        Document("исходный", "translated", "transcription"),
        ExportKind.BILINGUAL,
        ExportLayout.THREE_COLUMNS,
        profile=get_language(language),
    )

    assert rendered.count("Перевод") == 1
    assert "translated" in rendered
    assert "transcription" not in rendered


def test_chinese_sequential_bilingual_export_keeps_written_translation():
    rendered = render_export(
        Document("привет", "你好", "nǐ hǎo"),
        ExportKind.BILINGUAL,
        profile=get_language("Chine"),
    )

    assert "你好" in rendered
    assert "nǐ hǎo" not in rendered


def test_fixed_width_table_wraps_long_multilingual_cells_without_mixing():
    document = Document(
        "Очень длинное русское предложение о контроллинге и внутренних затратах компании.",
        "关于 SAP 主题的提案：控制模块负责公司内部成本的核算和分析。",
        "/kənˈtroʊlɪŋ ˈmɒdjuːl ænd ˈɪntənəl kɒsts/",
    )

    rendered = render_three_columns(document)
    table_lines = [line for line in rendered.splitlines() if line]

    assert "\t" not in rendered
    assert len({display_width(line) for line in table_lines}) == 1
    assert max(display_width(line) for line in table_lines) == 79
    assert "контроллинге" in rendered
    assert "控制模块" in rendered


@pytest.mark.parametrize(
    ("kind", "expected_separators"),
    [
        (ExportKind.TRANSLATION, 2),
        (ExportKind.BILINGUAL, 3),
        (ExportKind.FULL, 4),
    ],
)
def test_column_table_fits_80_column_editor(kind, expected_separators):
    document = Document(
        "Предложений по теме SAP: модуль «Контроллинг».",
        "关于 SAP 主题的提案：“控制”模块。",
        "guān yú S A P zhǔ tí de tí àn",
    )

    rendered = render_columns(document, kind)
    table_lines = [line for line in rendered.splitlines() if line]

    assert all(display_width(line) == 79 for line in table_lines)
    assert all(line.count("|") == expected_separators for line in table_lines if line[0] == "|")
