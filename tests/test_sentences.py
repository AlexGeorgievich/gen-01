from gpt01.sentences import sentence_spans


def test_multiple_sentences_keep_exact_document_offsets():
    text = "Добрый день. Направляю документы.\n\nПодтвердите получение!"

    spans = sentence_spans(text)

    assert [span.text for span in spans] == [
        "Добрый день.",
        "Направляю документы.",
        "Подтвердите получение!",
    ]
    assert [(span.start, span.end, span.line) for span in spans] == [
        (0, 12, 0),
        (13, 33, 0),
        (35, 57, 2),
    ]
    assert [text[span.start : span.end] for span in spans] == [
        span.text for span in spans
    ]


def test_abbreviations_initials_numbers_and_addresses_do_not_split_sentences():
    text = (
        "А. С. Пушкин указал стоимость 3.14 руб. "
        "См. данные на example.com. Следующее предложение."
    )

    assert [span.text for span in sentence_spans(text)] == [
        "А. С. Пушкин указал стоимость 3.14 руб. См. данные на example.com.",
        "Следующее предложение.",
    ]


def test_unpunctuated_nonempty_lines_remain_independent_units():
    assert [span.text for span in sentence_spans("Первая строка\nВторая строка")] == [
        "Первая строка",
        "Вторая строка",
    ]
