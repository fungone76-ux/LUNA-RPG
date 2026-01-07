"""
Client ottimizzato per Stable Diffusion (Automatic1111).
- Supporta SD remoto (RunPod) via variabili ambiente.
- Supporta Basic Auth (opzionale).
- Mantiene la logica originale di scelta risoluzione e salvataggio immagini.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from requests.auth import HTTPBasicAuth


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


SD_URL = _get_env("SD_URL", "http://127.0.0.1:7860").rstrip("/")
SD_TXT2IMG_ENDPOINT = f"{SD_URL}/sdapi/v1/txt2img"
SD_OPTIONS_ENDPOINT = f"{SD_URL}/sdapi/v1/options"

OUTPUT_DIR = Path(_get_env("SD_OUTPUT_DIR", "storage/images"))

# Timeout lungo (tu vuoi 720s)
TIMEOUT_SECONDS = int(_get_env("SD_TIMEOUT_SECONDS", "720") or "720")

# TLS verify (di default True; se proprio ti serve disabilitarlo: SD_VERIFY_TLS=0)
VERIFY_TLS = _get_env("SD_VERIFY_TLS", "1") not in ("0", "false", "False", "no", "NO")

# Basic auth opzionale (se avvii A1111 con --api-auth user:pass)
_SD_API_AUTH = _get_env("SD_API_AUTH", "")
AUTH = None
if _SD_API_AUTH and ":" in _SD_API_AUTH:
    u, p = _SD_API_AUTH.split(":", 1)
    AUTH = HTTPBasicAuth(u, p)

# Sessione requests (un filo più stabile/performante)
_SESSION = requests.Session()


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------

def check_connection() -> bool:
    """
    Verifica rapida se l'API A1111 è raggiungibile.
    Usa un endpoint API reale (options), non la root.
    """
    try:
        r = _SESSION.get(SD_OPTIONS_ENDPOINT, timeout=8, auth=AUTH, verify=VERIFY_TLS)
        return r.status_code == 200
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Scelta formato (tua logica invariata)
# ---------------------------------------------------------------------------

def choose_image_size(
    image_subject: Optional[str] = None,
    visual_en: str = "",
    tags_en: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """
    Decide se l'immagine deve essere Verticale (Portrait) o Orizzontale (Landscape).
    """
    tags_en = tags_en or []
    text_context = (str(visual_en) + " " + " ".join(tags_en)).lower()

    PORTRAIT = (896, 1152)
    LANDSCAPE = (1152, 896)

    if image_subject == "environment":
        return LANDSCAPE

    landscape_keywords = [
        "group", "crowd", "people", "tavern", "room", "hall",
        "city", "street", "panorama", "wide view", "table", "landscape"
    ]
    if any(k in text_context for k in landscape_keywords):
        return LANDSCAPE

    portrait_keywords = [
        "portrait", "close-up", "face", "bust", "full body", "standing", "1girl", "solo"
    ]
    if any(k in text_context for k in portrait_keywords):
        return PORTRAIT

    return PORTRAIT


# ---------------------------------------------------------------------------
# txt2img
# ---------------------------------------------------------------------------

def generate_image_from_prompts(
    positive_prompt: str,
    negative_prompt: str,
    width: int = 896,
    height: int = 1152,
    seed: int = -1,
) -> Optional[str]:
    """
    Invia la richiesta a Automatic1111 e salva l'immagine.
    Parametri: DPM++ 2M Karras, Steps 24, CFG 7 (come il tuo).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": seed,
        "sampler_name": "DPM++ 2M Karras",
        "steps": 24,
        "cfg_scale": 7,
        "batch_size": 1,
        "n_iter": 1,
        "restore_faces": False,
        "tiling": False,
    }

    print(f"[SD] URL: {SD_URL}")
    print(f"[SD] Richiesta generazione: {width}x{height}...")

    try:
        response = _SESSION.post(
            SD_TXT2IMG_ENDPOINT,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            auth=AUTH,
            verify=VERIFY_TLS,
        )
        response.raise_for_status()
        r = response.json()

        if "images" not in r or not r["images"]:
            print("[SD] Errore: Nessuna immagine ricevuta dall'API.")
            return None

        image_data = r["images"][0]
        if "," in image_data:
            image_data = image_data.split(",", 1)[-1]

        image_bytes = base64.b64decode(image_data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"scene_{timestamp}.png"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        print(f"[SD] Immagine salvata correttamente: {filepath}")
        return str(filepath)

    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        body = getattr(e.response, "text", "")
        print(f"[SD] HTTP error: status={status}")
        if body:
            print(f"[SD] Risposta (prime 400): {body[:400]}")
        # 401 = auth sbagliata/mancante
        return None

    except requests.exceptions.ConnectionError:
        print(f"[SD] ERRORE: Impossibile connettersi a {SD_URL}.")
        print("     Controlla che A1111 sia avviato con '--api' e che la porta 7860 sia esposta su RunPod.")
        return None

    except requests.exceptions.Timeout:
        print(f"[SD] TIMEOUT dopo {TIMEOUT_SECONDS}s su {SD_URL}.")
        print("     Se usi proxy RunPod e fai job pesanti, valuta TCP mapping oppure alza SD_TIMEOUT_SECONDS.")
        return None

    except Exception as e:
        print(f"[SD] Errore generico durante la generazione: {e}")
        return None


# ---------------------------------------------------------------------------
# Mini test manuale
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[SD] check_connection():", check_connection())
