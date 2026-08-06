from gpt01.audio_cache import LineAudioCache


def test_cache_returns_only_completed_nonempty_audio():
    cache = LineAudioCache()
    path = cache.path_for("line")

    assert cache.get("line") is None
    path.write_bytes(b"mp3")

    assert cache.get("line") == path
    assert cache.contains(path)
    cache.clear()


def test_cache_uses_stable_paths_and_clear_removes_directory():
    cache = LineAudioCache()
    first = cache.path_for("same")
    second = cache.path_for("same")
    directory = cache.directory
    first.write_bytes(b"mp3")

    assert first == second
    assert cache.has_files

    cache.clear()

    assert directory is not None
    assert not directory.exists()
    assert not cache.has_files
