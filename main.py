# file: main.py
import sys
import pathlib
import os


def _load_env():
    """
    Carica .env PRIMA di importare il resto del progetto (GameWindow, sd_client, ecc).
    Se python-dotenv non è installato, non esplode: semplicemente non carica il file.
    """
    try:
        from dotenv import load_dotenv  # pip install python-dotenv
        load_dotenv()  # cerca .env nella working dir
    except Exception as e:
        # non blocchiamo l'avvio: se non hai dotenv, puoi comunque usare variabili ambiente "normali"
        print(f"[ENV] python-dotenv non disponibile o errore caricamento .env: {e}")


def main():
    _load_env()

    # Crea le cartelle necessarie se non esistono
    pathlib.Path("storage/images").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/saves").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/audio").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/videos").mkdir(parents=True, exist_ok=True)

    # Import QUI, dopo load_dotenv()
    from PySide6.QtWidgets import QApplication
    from gui_window import GameWindow

    app = QApplication(sys.argv)

    window = GameWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
