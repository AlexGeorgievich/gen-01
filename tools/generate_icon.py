"""Generate the Windows ICO from the canonical SVG using Qt."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets" / "gpt01.svg"
ICO_PATH = ROOT / "assets" / "gpt01.ico"


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    icon = QIcon(str(SVG_PATH))
    if icon.isNull():
        raise RuntimeError(f"Не удалось загрузить {SVG_PATH}")
    pixmap = icon.pixmap(256, 256)
    if not pixmap.save(str(ICO_PATH), "ICO"):
        # Some Qt installations do not ship an ICO writer. PNG data in an
        # .ico file is not valid, so fail explicitly instead of hiding it.
        raise RuntimeError("Qt не поддерживает запись ICO в этой установке")
    app.quit()


if __name__ == "__main__":
    main()
