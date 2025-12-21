# file: sd_client.py
"""
Client ottimizzato per Stable Diffusion (Automatic1111).
Mantiene il 100% delle funzionalità originali:
- Cambio risoluzione intelligente (Portrait/Landscape) in base ai tag.
- Salvataggio locale in storage/images.
- Parametri di generazione specifici (DPM++ 2M Karras).
"""

import base64
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

# --- CONFIGURAZIONE ---
SD_URL = "http://127.0.0.1:7860"
SD_TXT2IMG_ENDPOINT = f"{SD_URL}/sdapi/v1/txt2img"
OUTPUT_DIR = Path("storage/images")

# Timeout esteso per evitare errori su GPU lente
TIMEOUT_SECONDS = 600


def check_connection() -> bool:
    """
    Verifica rapida se Stable Diffusion è raggiungibile.
    Utile per la GUI per mostrare un avviso prima di provare a generare.
    """
    try:
        requests.get(SD_URL, timeout=3)
        return True
    except requests.RequestException:
        return False


def choose_image_size(
        image_subject: Optional[str] = None,
        visual_en: str = "",
        tags_en: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """
    Logica originale preservata al 100%: decide se l'immagine deve essere
    Verticale (Portrait) o Orizzontale (Landscape) analizzando i testi.
    """
    tags_en = tags_en or []
    # Uniamo tutto in minuscolo per la ricerca keyword
    text_context = (str(visual_en) + " " + " ".join(tags_en)).lower()

    # Dimensioni originali richieste
    PORTRAIT = (896, 1152)
    LANDSCAPE = (1152, 896)

    # 1. Priorità assoluta: Ambiente -> Landscape
    if image_subject == "environment":
        return LANDSCAPE

    # 2. Keywords che forzano la vista orizzontale (gruppi, stanze, panorami)
    landscape_keywords = [
        "group", "crowd", "people", "tavern", "room", "hall",
        "city", "street", "panorama", "wide view", "table", "landscape"
    ]
    if any(k in text_context for k in landscape_keywords):
        return LANDSCAPE

    # 3. Keywords che forzano la vista verticale (ritratti)
    portrait_keywords = [
        "portrait", "close-up", "face", "bust", "full body", "standing", "1girl", "solo"
    ]
    if any(k in text_context for k in portrait_keywords):
        return PORTRAIT

    # 4. Default: Verticale (meglio per i personaggi singoli)
    return PORTRAIT


def generate_image_from_prompts(
        positive_prompt: str,
        negative_prompt: str,
        width: int = 896,
        height: int = 1152,
        seed: int = -1,
) -> Optional[str]:
    """
    Invia la richiesta a Automatic1111 e salva l'immagine.
    Mantiene i parametri originali (Sampler DPM++ 2M Karras, Steps 24, CFG 7).
    """
    # Assicuriamo che la cartella esista
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": seed,
        "sampler_name": "DPM++ 2M Karras",  #
        "steps": 24,  #
        "cfg_scale": 7,  #
        "batch_size": 1,
        "n_iter": 1,
        "restore_faces": False,
        "tiling": False,
    }

    print(f"[SD] Richiesta generazione: {width}x{height}...")

    try:
        response = requests.post(SD_TXT2IMG_ENDPOINT, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()

        r = response.json()

        # Estrazione immagine base64
        if "images" not in r or not r["images"]:
            print("[SD] Errore: Nessuna immagine ricevuta dall'API.")
            return None

        image_data = r['images'][0]

        # Pulizia header base64 se presente
        if "," in image_data:
            image_data = image_data.split(",", 1)[-1]

        image_bytes = base64.b64decode(image_data)

        # Generazione nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"scene_{timestamp}.png"
        filepath = OUTPUT_DIR / filename

        # Salvataggio su disco
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        print(f"[SD] Immagine salvata correttamente: {filepath}")
        return str(filepath)

    except requests.exceptions.ConnectionError:
        print(f"[SD] ERRORE: Impossibile connettersi a {SD_URL}.")
        print("     Assicurati che Stable Diffusion sia aperto con l'argomento '--api'.")
        return None
    except Exception as e:
        print(f"[SD] Errore generico durante la generazione: {e}")
        return None