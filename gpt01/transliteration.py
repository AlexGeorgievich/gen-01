from pypinyin import Style, lazy_pinyin


def to_pinyin(text: str) -> str:
    """Convert Chinese text to readable pinyin while preserving line breaks."""
    lines: list[str] = []
    for line in text.split("\n"):
        syllables = lazy_pinyin(
            line,
            style=Style.TONE,
            neutral_tone_with_five=False,
            errors=lambda chars: list(chars),
        )
        lines.append(" ".join(syllables))
    return "\n".join(lines)
