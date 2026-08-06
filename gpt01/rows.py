from .models import TranslationRow


def rows_between(
    rows: list[TranslationRow],
    first_line: int,
    second_line: int,
) -> list[TranslationRow]:
    """Return rows inside an inclusive line range, independent of marker order."""
    start, end = sorted((first_line, second_line))
    return [row for row in rows if start <= row.index <= end]


def build_translation_rows(
    source: str, translation: str = "", transcription: str = ""
) -> list[TranslationRow]:
    """Build stable row mappings from the three editor documents."""
    source_lines = source.split("\n")
    translation_lines = translation.split("\n")
    transcription_lines = transcription.split("\n")
    rows: list[TranslationRow] = []
    for index, source_line in enumerate(source_lines):
        source_text = source_line.strip()
        if not source_text:
            continue
        rows.append(
            TranslationRow(
                index=index,
                source=source_text,
                translation=(
                    translation_lines[index].strip() if index < len(translation_lines) else ""
                ),
                transcription=(
                    transcription_lines[index].strip()
                    if index < len(transcription_lines)
                    else ""
                ),
            )
        )
    return rows
