# file: main.py
import sys
import pathlib
import os


def _load_env():
    """
    FORZATURA MANUALE DEGLI INDIRIZZI RUNPOD
    Sostituisci questi URL se il Pod cambia ID.
    """
    # URL STABLE DIFFUSION (Immagini)
    os.environ['SD_BASE_URL'] = "https://rm8uzrhpf356kc-7860.proxy.runpod.net"

    # URL COMFYUI (Video)
    os.environ['COMFY_URL'] = "https://rm8uzrhpf356kc-8188.proxy.runpod.net"

    # WORKFLOW
    os.environ['COMFY_WORKFLOW_FILE'] = "workflow_game_i2v.json"

    # API KEY GEMINI (Lasciala qui o assicurati che sia nel codice se serve)
    os.environ['GEMINI_API_KEY'] = "AIzaSyC_7TCGhBTaD2lEtPpsm-iGvOch13rM11c"

    # PARAMETRI
    os.environ['INPUT_IMAGE_NAME'] = "placeholder.png"
    os.environ['OUTPUT_VIDEO_FOLDER'] = "./output_videos"
    os.environ['GEN_WIDTH'] = "832"
    os.environ['GEN_HEIGHT'] = "480"

    print("[ENV] Configurazione RunPod CARICATA MANUALMENTE!")


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
