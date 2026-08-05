import pytest

from gpt01.batch import BatchProcessor
from gpt01.errors import OperationCancelled
from gpt01.languages import get_language
from gpt01.session import SessionRepository
from gpt01.storage import load_document


class PrefixTranslator:
    def translate(self, text, cancelled=None):
        return "\n".join(f"translated:{line}" for line in text.splitlines())


def test_batch_translates_multiple_formats_and_reports_progress(tmp_path):
    first = tmp_path / "first.txt"
    first.write_text("one", encoding="utf-8")
    second = tmp_path / "second.srt"
    second.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\ntwo",
        encoding="utf-8",
    )
    updates = []
    processor = BatchProcessor(
        SessionRepository(tmp_path),
        get_language("Spanish"),
        PrefixTranslator(),
    )

    result = processor.process(
        [first, second],
        progress=lambda current, total, message: updates.append((current, total, message)),
    )

    assert len(result.succeeded) == 2
    assert not result.failed
    assert result.succeeded[0].output.name == "first_es.txt"
    assert load_document(result.succeeded[0].output).translation == "translated:one"
    assert updates[0][:2] == (0, 2)
    assert updates[-1][:2] == (2, 2)


def test_batch_does_not_overwrite_existing_export(tmp_path):
    source = tmp_path / "lesson.txt"
    source.write_text("one", encoding="utf-8")
    repository = SessionRepository(tmp_path)
    profile = get_language("French")
    existing = repository.export_path(profile, source.stem, ".txt")
    existing.write_text("keep", encoding="utf-8")
    processor = BatchProcessor(repository, profile, PrefixTranslator())

    result = processor.process([source])

    assert existing.read_text(encoding="utf-8") == "keep"
    assert result.succeeded[0].output.name == "lesson_fr_2.txt"


def test_batch_continues_after_invalid_file(tmp_path):
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"invalid")
    valid = tmp_path / "valid.txt"
    valid.write_text("hello", encoding="utf-8")
    processor = BatchProcessor(
        SessionRepository(tmp_path),
        get_language("English"),
        PrefixTranslator(),
    )

    result = processor.process([broken, valid])

    assert [item.source for item in result.failed] == [broken]
    assert [item.source for item in result.succeeded] == [valid]


def test_batch_honours_cancellation_between_files(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    processor = BatchProcessor(
        SessionRepository(tmp_path),
        get_language("English"),
        PrefixTranslator(),
    )
    updates = []

    with pytest.raises(OperationCancelled):
        processor.process(
            [first, second],
            cancelled=lambda: any(current == 1 for current, _total, _message in updates),
            progress=lambda current, total, message: updates.append((current, total, message)),
        )

    assert len(list((tmp_path / "language_data" / "English").glob("*.txt"))) == 1
