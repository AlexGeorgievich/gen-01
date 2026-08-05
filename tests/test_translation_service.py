import pytest

from gpt01.errors import NetworkServiceError
from gpt01.services import GoogleTranslationProvider


class FakeGoogleTranslator:
    responses = []
    calls = 0

    def __init__(self, source, target):
        self.source = source
        self.target = target

    def translate(self, text):
        type(self).calls += 1
        response = type(self).responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def install_fake(monkeypatch, responses):
    FakeGoogleTranslator.responses = list(responses)
    FakeGoogleTranslator.calls = 0
    monkeypatch.setattr("gpt01.services.GoogleTranslator", FakeGoogleTranslator)


def test_translator_retries_error_page_returned_as_text(monkeypatch):
    install_fake(
        monkeypatch,
        ["Error 500 (Server Error)!! That's an error.", "trois"],
    )
    provider = GoogleTranslationProvider("fr", retry_delays=(0,))

    assert provider.translate("три") == "trois"
    assert FakeGoogleTranslator.calls == 2


def test_translator_retries_temporary_exception(monkeypatch):
    install_fake(monkeypatch, [RuntimeError("temporary"), "quatre"])
    provider = GoogleTranslationProvider("fr", retry_delays=(0,))

    assert provider.translate("четыре") == "quatre"


def test_translator_never_returns_server_error_page(monkeypatch):
    error_page = "Error 500 (Server Error)!!1500. That's an error."
    install_fake(monkeypatch, [error_page, error_page, error_page])
    provider = GoogleTranslationProvider("fr", retry_delays=(0, 0))

    with pytest.raises(NetworkServiceError, match="после 3 попыток"):
        provider.translate("пять")
