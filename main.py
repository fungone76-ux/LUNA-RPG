# file: main.py
import sys
from PySide6.QtWidgets import QApplication
from gui_window import GameWindow


def main():
    # Crea le cartelle necessarie se non esistono
    import pathlib
    pathlib.Path("storage/images").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/saves").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/audio").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/videos").mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)

    # Crea e mostra la finestra principale
    window = GameWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()