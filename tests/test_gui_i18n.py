import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QSpinBox,
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
    assert window.open_text_action.text() == "Open text…"
    assert window.batch_translation_action.text() == "Batch translation…"
    assert window.text_packages_menu.title() == "Text packages"
    assert window.open_package_action.text() == "Open package…"
    assert window.package_history_action.text() == "Package history"
    assert window.source_title.text() == "Source text"
    assert window.language_combo.itemText(window.language_combo.findData("Japan")) == (
        "Japanese"
    )
    assert window.language_combo.itemText(window.language_combo.findData("German")) == (
        "German"
    )

    window.preferences.interface_language = "ru"
    window._apply_interface_language()

    assert window.windowTitle() == "VoiceGun"
    assert window.open_button.text() == "Открыть…"
    assert window.open_text_action.text() == "Открыть текст…"
    assert window.batch_translation_action.text() == "Пакетный перевод…"
    assert window.text_packages_menu.title() == "Пакеты текста"
    assert window.open_package_action.text() == "Открыть пакет…"
    assert window.package_history_action.text() == "История пакетов"
    assert window.source_title.text() == "Исходный текст"
    assert window.language_combo.itemText(window.language_combo.findData("German")) == (
        "Немецкий"
    )
    window._dirty = False
    window.close()


@pytest.mark.parametrize(
    ("language", "voice"),
    (
        ("German", "de-DE-KatjaNeural"),
        ("Italian", "it-IT-ElsaNeural"),
        ("Turkish", "tr-TR-EmelNeural"),
    ),
)
def test_gui_switches_to_new_language_module_and_creates_its_directory(
    tmp_path,
    language,
    voice,
) -> None:
    _app()
    repository = SessionRepository(tmp_path)
    window = MainWindow(repository)

    window.language_combo.setCurrentIndex(window.language_combo.findData(language))

    assert window.current_language.key == language
    assert window.selected_voice() == voice
    assert repository.language_directory(window.current_language).is_dir()
    assert window.transcription_title.text().endswith(f"IPA ({language})")
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
    combo_style = window.centralWidget().styleSheet()
    assert "QComboBox QAbstractItemView" in combo_style
    assert "selection-background-color: #397dcc" in combo_style
    assert "selection-color: #ffffff" in combo_style
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


def test_voice_selector_uses_compact_fixed_width(tmp_path) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    assert window.voice_combo.minimumWidth() == 380
    assert window.voice_combo.maximumWidth() == 380
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


def test_settings_exposes_fast_and_complete_audio_modes(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured: dict[str, object] = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        combo = dialog.findChild(QComboBox, "audioPreparationModeCombo")
        captured["values"] = [combo.itemData(index) for index in range(combo.count())]
        captured["selected"] = combo.currentData()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    window.open_settings()

    assert captured["values"] == ["line", "package"]
    assert captured["selected"] == "line"
    window._dirty = False
    window.close()


def test_settings_exposes_card_font_sizes(tmp_path, monkeypatch) -> None:
    _app()
    window = MainWindow(SessionRepository(tmp_path))
    captured = {}

    def inspect_dialog(dialog: QDialog) -> QDialog.DialogCode:
        captured["primary"] = dialog.findChild(
            QSpinBox, "cardPrimaryFontSizeSpin"
        ).value()
        captured["secondary"] = dialog.findChild(
            QSpinBox, "cardSecondaryFontSizeSpin"
        ).value()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    window.open_settings()

    assert captured == {"primary": 24, "secondary": 18}
    window._dirty = False
    window.close()


def test_settings_saves_card_font_sizes(tmp_path, monkeypatch) -> None:
    _app()
    repository = SessionRepository(tmp_path)
    window = MainWindow(repository)

    def choose_sizes(dialog: QDialog) -> QDialog.DialogCode:
        dialog.findChild(QSpinBox, "cardPrimaryFontSizeSpin").setValue(32)
        dialog.findChild(QSpinBox, "cardSecondaryFontSizeSpin").setValue(21)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", choose_sizes)
    window.open_settings()

    assert window.preferences.card_primary_font_size == 32
    assert window.preferences.card_secondary_font_size == 21
    restored = repository.load_preferences()
    assert restored.card_primary_font_size == 32
    assert restored.card_secondary_font_size == 21
    window._dirty = False
    window.close()


def test_settings_saves_complete_audio_mode_in_current_language_state(
    tmp_path, monkeypatch
) -> None:
    _app()
    repository = SessionRepository(tmp_path)
    window = MainWindow(repository)

    def select_complete_package(dialog: QDialog) -> QDialog.DialogCode:
        combo = dialog.findChild(QComboBox, "audioPreparationModeCombo")
        combo.setCurrentIndex(combo.findData("package"))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", select_complete_package)
    window.open_settings()

    assert window.audio_preparation_mode == "package"
    assert repository.load_session(window.current_language).state.audio_preparation_mode == (
        "package"
    )
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
