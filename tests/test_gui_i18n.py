import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QTextBrowser,
)

from app import MainWindow
from gpt01.exporting import ExportKind
from gpt01.preferences import Preferences
from gpt01.session import SessionRepository


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_gui_defaults_to_english_and_can_be_retranslated_to_russian(tmp_path) -> None:
    _app()
    repository = SessionRepository(tmp_path)
    repository.save_preferences(Preferences(interface_language="en"))
    window = MainWindow(repository)

    assert window.windowTitle() == "VoiceGun"
    assert window.open_button.text() == "Open…"
    assert window.source_title.text() == "Source text"
    assert window.language_combo.itemText(window.language_combo.findData("Japan")) == (
        "Japanese"
    )

    window.preferences.interface_language = "ru"
    window._apply_interface_language()

    assert window.windowTitle() == "VoiceGun"
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


def test_main_editor_panels_have_distinct_colors_and_soft_shadows(tmp_path) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))

    assert "#eef4ff" in window.centralWidget().styleSheet()
    assert "#edf9f6" in window.centralWidget().styleSheet()
    assert "#f5f0ff" in window.centralWidget().styleSheet()
    for panel in (
        window.source_box,
        window.translation_box,
        window.transcription_box,
    ):
        shadow = panel.graphicsEffect()
        assert isinstance(shadow, QGraphicsDropShadowEffect)
        assert shadow.blurRadius() == 22.0
        assert shadow.offset().y() == 4.0
    window._dirty = False
    window.close()


def test_voice_selector_uses_half_of_the_available_flexible_width(tmp_path) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    layout = window.voice_box.layout()

    assert layout.stretch(3) == 1
    assert layout.stretch(4) == 1
    window._dirty = False
    window.close()


def test_help_uses_local_english_guide_and_f1(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured: dict[str, str | float] = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        browser = dialog.findChild(QTextBrowser)
        captured["text"] = browser.toPlainText()
        captured["point_size"] = browser.font().pointSizeF()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    expected_point_size = window.font().pointSizeF() + 2.0
    window.open_help()

    assert "VoiceGun User Guide" in captured["text"]
    assert "AlexGeorgievich" in captured["text"]
    assert "alex34.st@gmail.com" in captured["text"]
    assert captured["point_size"] == expected_point_size
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


def test_source_only_export_disables_document_layout(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured: dict[str, bool] = {}

    def select_source_only(dialog: QDialog) -> QDialog.DialogCode:
        combo = dialog.findChild(QComboBox)
        checkbox = dialog.findChild(QCheckBox)
        combo.setCurrentIndex(combo.findData(ExportKind.SOURCE.value))
        captured["layout_enabled"] = checkbox.isEnabled()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", select_source_only)
    selection = window._select_export_kind()

    assert selection is not None
    assert selection[0] == ExportKind.SOURCE
    assert captured["layout_enabled"] is False
    assert window._export_label(ExportKind.SOURCE) == "Source text only"
    window._dirty = False
    window.close()


def test_mp3_scope_dialog_defaults_to_marked_ab_interval(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    window._range_a_line = 4
    window._range_b_line = 1
    captured: dict[str, object] = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        combo = dialog.findChild(QComboBox)
        captured["labels"] = [combo.itemText(index) for index in range(combo.count())]
        captured["scope"] = combo.currentData()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)

    assert window._select_audio_export_scope() == "range"
    assert captured["scope"] == "range"
    assert "2–5" in captured["labels"][0]
    assert captured["labels"][1] == "Complete text"
    window._dirty = False
    window.close()
