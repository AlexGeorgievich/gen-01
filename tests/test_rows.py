from gpt01.models import TranslationRow
from gpt01.rows import (
    build_sentence_translation_rows,
    build_translation_rows,
    rows_between,
)


def test_rows_keep_source_line_indices():
    rows = build_translation_rows("one\n\nthree", "uno\n\ntres", "uno\n\ntres")
    assert rows == [
        TranslationRow(0, "one", "uno", "uno"),
        TranslationRow(2, "three", "tres", "tres"),
    ]


def test_rows_allow_missing_parallel_text():
    assert build_translation_rows("one\ntwo", "uno") == [
        TranslationRow(0, "one", "uno", ""),
        TranslationRow(1, "two", "", ""),
    ]


def test_rows_between_is_inclusive_and_independent_of_marker_order():
    rows = build_translation_rows("zero\none\n\nthree\nfour")

    assert rows_between(rows, 4, 1) == [
        TranslationRow(1, "one"),
        TranslationRow(3, "three"),
        TranslationRow(4, "four"),
    ]


def test_sentence_rows_align_multiple_sentences_inside_one_editor_line():
    rows = build_sentence_translation_rows(
        "Hello. See you soon!",
        "Bonjour. À bientôt !",
        "bonjour. a bjɛ̃to !",
    )

    assert [(row.index, row.source, row.translation) for row in rows] == [
        (0, "Hello.", "Bonjour."),
        (0, "See you soon!", "À bientôt !"),
    ]
    assert rows[0].source_start == 0
    assert rows[0].source_end == 6
    assert rows[1].source_start == 7
    assert rows[1].source_end == 20
    assert rows[1].translation_start == 9


def test_sentence_rows_follow_translation_sentences_when_counts_differ():
    rows = build_sentence_translation_rows(
        "First. Second. Third.",
        "Première partie. Deuxième partie.",
    )

    assert [row.source for row in rows] == ["First.", "Second. Third."]
    assert [row.translation for row in rows] == [
        "Première partie.",
        "Deuxième partie.",
    ]


def test_extra_translation_sentences_remain_separate_without_losing_source():
    rows = build_sentence_translation_rows(
        "Combined source. Final source.",
        "Part one. Part two. Part three.",
    )

    assert [row.translation for row in rows] == [
        "Part one.",
        "Part two.",
        "Part three.",
    ]
    assert [row.source for row in rows] == [
        "Combined source.",
        "Combined source.",
        "Final source.",
    ]
