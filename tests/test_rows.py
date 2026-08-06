from gpt01.models import TranslationRow
from gpt01.rows import build_translation_rows, rows_between


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
