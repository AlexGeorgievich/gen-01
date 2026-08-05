import pytest

from gpt01.text import numbered_nonempty_lines, split_text


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("", 10, [""]),
        ("abc", 10, ["abc"]),
        ("abc", 3, ["abc"]),
        ("abcdef", 3, ["abc", "def"]),
        ("a\nb\n", 2, ["a\n", "b\n"]),
        ("ab\ncd", 3, ["ab\n", "cd"]),
    ],
)
def test_split_text(text, limit, expected):
    assert split_text(text, limit) == expected
    assert "".join(split_text(text, limit)) == text


@pytest.mark.parametrize("limit", [0, -1])
def test_split_text_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        split_text("abc", limit)


def test_numbered_nonempty_lines_preserves_indices():
    assert numbered_nonempty_lines("first\n\n third \nfourth") == [
        (0, "first"),
        (2, "third"),
        (3, "fourth"),
    ]


def test_numbered_nonempty_lines_handles_empty_text():
    assert numbered_nonempty_lines("") == []
