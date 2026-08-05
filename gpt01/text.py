def split_text(text: str, limit: int = 4500) -> list[str]:
    """Split text on lines, falling back to fixed-size chunks."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if not text:
        return [""]

    chunks: list[str] = []
    current = ""
    for paragraph in text.splitlines(keepends=True):
        while len(paragraph) > limit:
            head, paragraph = paragraph[:limit], paragraph[limit:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if len(current) + len(paragraph) > limit and current:
            chunks.append(current)
            current = paragraph
        else:
            current += paragraph
    if current:
        chunks.append(current)
    return chunks


def numbered_nonempty_lines(text: str) -> list[tuple[int, str]]:
    """Return stripped non-empty lines together with their original zero-based index."""
    return [(index, line.strip()) for index, line in enumerate(text.split("\n")) if line.strip()]
