# file: main.py
import sys
import pathlib
import os


def _load_env():
    """
    FORZATURA MANUALE DEGLI INDIRIZZI RUNPOD E API KEY
    Configurazione specifica per il Pod: cpc3l0m47g8juf
    """
    # 1. ID DEL POD ATTIVO (Verificato dal tuo screenshot)
    pod_id = "cpc3l0m47g8juf"

    # 2. URL STABLE DIFFUSION (Porta 7860 - Immagini)
    os.environ['SD_BASE_URL'] = f"https://{pod_id}-7860.proxy.runpod.net"
    os.environ['SD_CHECKPOINT'] = "cyber_pony.safetensors"

    # 3. URL COMFYUI (Porta 8188 - Video)
    os.environ['COMFY_URL'] = f"https://{pod_id}-8188.proxy.runpod.net"

    # 4. MODELLI WAN 2.1 (Nomi file verificati sul server)
    os.environ['COMFY_WORKFLOW_FILE'] = "wan21_test.json"
    os.environ['WAN_CHECKPOINT'] = "wan22EnhancedNSFWSVICamera_nolightningSVICfFp8H.safetensors"
    os.environ['WAN_VAE'] = "wan2.1_vae.safetensors"
    os.environ['WAN_CLIP'] = "t5xxl_fp8_e4m3fn.safetensors"

    # 5. API KEY GEMINI (La tua chiave personale)
    os.environ['GEMINI_API_KEY'] = "AIzaSyCMsNxEwfBg0tXFqIshig1nd3NYNUXcuX8"

    # 6. PARAMETRI GENERAZIONE E OUTPUT
    os.environ['GEMINI_MODEL_NAME'] = "gemini-2.0-flash-exp"
    os.environ['INPUT_IMAGE_NAME'] = "placeholder.png"
    os.environ['OUTPUT_VIDEO_FOLDER'] = "./output_videos"
    os.environ['GEN_WIDTH'] = "832"
    os.environ['GEN_HEIGHT'] = "1216"

    # MESSAGGIO DI CONFERMA ALL'AVVIO
    print("=" * 50)
    print(f"🚀 LUNA-RPG CONFIGURATO SU POD: {pod_id}")
    print(f"🔗 URL VIDEO: {os.environ['COMFY_URL']}")
    print("=" * 50)


def main():
    _load_env()

    # Crea le cartelle necessarie se non esistono
    print("[SYSTEM] Verifica cartelle di storage...")
    pathlib.Path("storage/images").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/saves").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/audio").mkdir(parents=True, exist_ok=True)
    pathlib.Path("storage/videos").mkdir(parents=True, exist_ok=True)
    pathlib.Path("./output_videos").mkdir(parents=True, exist_ok=True)

    # Import della GUI
    try:
        from PySide6.QtWidgets import QApplication
        from gui_window import LunaRPGWindow as GameWindow
    except ImportError:
        from PySide6.QtWidgets import QApplication
        from gui_window import GameWindow

    app = QApplication(sys.argv)

    window = GameWindow()
    window.show()

    print("[SYSTEM] Interfaccia avviata. In attesa di comandi...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()