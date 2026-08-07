import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QTextBrowser

from app import MainWindow
from gpt01.preferences import Preferences
from gpt01.session import SessionRepository


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_gui_defaults_to_english_and_can_be_retranslated_to_russian(tmp_path) -> None:
    _app()
    repository = SessionRepository(tmp_path)
    repository.save_preferences(Preferences(interface_language="en"))
    window = MainWindow(repository)

    assert window.windowTitle().startswith("VoiceGun — Multilingual")
    assert window.open_button.text() == "Open…"
    assert window.source_title.text() == "Source text"
    assert window.language_combo.itemText(window.language_combo.findData("Japan")) == (
        "Japanese"
    )

    window.preferences.interface_language = "ru"
    window._apply_interface_language()

    assert window.windowTitle().startswith("VoiceGun — многоязычный")
    assert window.open_button.text() == "Открыть…"
    assert window.source_title.text() == "Исходный текст"
    window._dirty = False
    window.close()


def test_hidden_translation_has_accessible_restore_button(tmp_path) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))

    window._set_translation_window_visible(False)

    assert window.translation_box.isHidden()
    assert window.translation_toggle_button.text() == "+ Translation"
    assert window.translation_toggle_button.parentWidget() is not window.translation_box

    window._set_translation_window_visible(True)

    assert not window.translation_box.isHidden()
    assert window.translation_toggle_button.text() == "−"
    window._dirty = False
    window.close()


def test_help_uses_local_english_guide_and_f1(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured: dict[str, str] = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        browser = dialog.findChild(QTextBrowser)
        captured["text"] = browser.toPlainText()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    window.open_help()

    assert "VoiceGun User Guide" in captured["text"]
    assert window.help_shortcut.key().toString() == "F1"
    window._dirty = False
    window.close()


def test_column_export_layout_is_enabled_by_default(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured: dict[str, bool] = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        checkbox = dialog.findChild(QCheckBox)
        captured["checked"] = checkbox.isChecked()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    assert window._select_export_kind() is None

    assert captured["checked"] is True
    window._dirty = False
    window.close()
