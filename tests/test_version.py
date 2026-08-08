from gpt01 import __version__
from gpt01.version import APP_AUTHOR, APP_DISPLAY_NAME, APP_ID, APP_NAME


def test_release_metadata_is_complete() -> None:
    assert tuple(int(part) for part in __version__.split(".")) >= (0, 3, 0)
    assert APP_NAME == "VoiceGun"
    assert APP_DISPLAY_NAME == "VoiceGun"
    assert APP_AUTHOR
    assert APP_ID.count(".") >= 2
