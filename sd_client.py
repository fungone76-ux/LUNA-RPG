"""
Client ottimizzato per Stable Diffusion (SD-Next / Automatic1111).
- Fix Sampler: impostato su 'Euler a' per compatibilità Diffusers (RTX 4090).
- AUTENTICAZIONE COMPLETAMENTE RIMOSSA per evitare errore 401.
"""

from __future__ import annotations
import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
import requests
from dotenv import load_dotenv # Richiede: pip install python-dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

# Recupera l'URL dal .env (es. http://166.113.52.39:42420)
SD_URL = _get_env("SD_URL", "http://127.0.0.1:7860").rstrip("/")
SD_TXT2IMG_ENDPOINT = f"{SD_URL}/sdapi/v1/txt2img"
SD_OPTIONS_ENDPOINT = f"{SD_URL}/sdapi/v1/options"

SD_UNLOAD_ENDPOINT = f"{SD_URL}/sdapi/v1/unload-checkpoint"
SD_RELOAD_ENDPOINT = f"{SD_URL}/sdapi/v1/reload-checkpoint"

OUTPUT_DIR = Path(_get_env("SD_OUTPUT_DIR", "storage/images"))
TIMEOUT_SECONDS = int(_get_env("SD_TIMEOUT_SECONDS", "720") or "720")
VERIFY_TLS = _get_env("SD_VERIFY_TLS", "1") not in ("0", "false", "False", "no", "NO")

# --- RIMOZIONE TOTALE AUTENTICAZIONE ---
AUTH = None

# Sessione requests forzata senza auth e senza header sporchi
_SESSION = requests.Session()
_SESSION.auth = None
_SESSION.headers.update({"Authorization": ""})
# ---------------------------------------

def unload_checkpoint() -> bool:
    try:
        print("[SD] Richiesta Unload Checkpoint...")
        r = _SESSION.post(SD_UNLOAD_ENDPOINT, timeout=15, verify=VERIFY_TLS)
        return r.status_code == 200
    except Exception as e:
        print(f"[SD] Errore unload: {e}")
        return False

def reload_checkpoint() -> bool:
    try:
        print("[SD] Richiesta Reload Checkpoint...")
        r = _SESSION.post(SD_RELOAD_ENDPOINT, timeout=15, verify=VERIFY_TLS)
        return r.status_code == 200
    except Exception as e:
        print(f"[SD] Errore reload: {e}")
        return False

def check_connection() -> bool:
    try:
        r = _SESSION.get(SD_OPTIONS_ENDPOINT, timeout=10, verify=VERIFY_TLS)
        return r.status_code == 200
    except Exception:
        return False

def choose_image_size(
    image_subject: Optional[str] = None,
    visual_en: str = "",
    tags_en: Optional[List[str]] = None,
) -> Tuple[int, int]:
    tags_en = tags_en or []
    text_context = (str(visual_en) + " " + " ".join(tags_en)).lower()
    PORTRAIT = (896, 1152)
    LANDSCAPE = (1152, 896)

    if image_subject == "environment":
        return LANDSCAPE
    landscape_keywords = ["group", "crowd", "people", "tavern", "room", "hall", "city", "street", "panorama", "wide view", "table", "landscape"]
    if any(k in text_context for k in landscape_keywords):
        return LANDSCAPE
    return PORTRAIT

def generate_image_from_prompts(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 896,
    height: int = 1152,
    seed: int = -1,
) -> Optional[str]:
    """Invia la richiesta di generazione e salva l'immagine."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # FIX: Sampler cambiato in "Euler a" per compatibilità SD-Next/Diffusers
    payload = {
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": seed,
        "sampler_name": "Euler a",
        "steps": 24,
        "cfg_scale": 7,
        "override_settings": {
            "sd_model_checkpoint": os.getenv("SD_CHECKPOINT", "cyberrealisticPony_v7_final.safetensors")
        }
    }

    print(f"[SD] Connessione a: {SD_URL}")
    print(f"[SD] Generazione in corso...")

    try:
        response = _SESSION.post(
            SD_TXT2IMG_ENDPOINT,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            verify=VERIFY_TLS,
        )
        response.raise_for_status()
        r = response.json()

        if "images" not in r or not r["images"]:
            print("[SD] Errore: Nessuna immagine ricevuta.")
            return None

        image_data = r["images"][0].split(",")[-1]
        image_bytes = base64.b64decode(image_data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scene_{timestamp}.png"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        print(f"[SD] Immagine salvata: {filepath}")
        return str(filepath)

    except Exception as e:
        print(f"[SD] Errore critico: {e}")
        return None

if __name__ == "__main__":
    print(f"[SD] Stato Connessione: {'ONLINE' if check_connection() else 'OFFLINE'}")