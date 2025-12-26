# file: dm_engine.py
from typing import Any, Dict, List, Optional, Tuple
import copy
from dm_client import get_dm_response
from image_prompts import build_image_prompts

# Import morbido di SD
try:
    import sd_client
except ImportError:
    sd_client = None


def choose_image_size(image_subject: str, visual_en: str, tags_en: List[str]) -> Tuple[int, int]:
    """Wrapper per mantenere la tua logica originale."""
    if sd_client:
        return sd_client.choose_image_size(image_subject, visual_en, tags_en)
    return 1032, 864  # Fallback


def process_turn(
        main_quest: str,
        story_summary: str,
        game_state: Dict[str, Any],
        recent_dialogue: List[Dict[str, str]],
        player_input: str,
        generate_image: bool = True,
) -> Dict[str, Any]:
    """Ciclo completo del turno."""

    # 1. Chiamata LLM
    dm_output = get_dm_response(
        main_quest, story_summary, game_state, recent_dialogue, player_input
    )

    reply_it = dm_output.get("reply_it", "")
    new_state = dm_output.get("new_state", {})
    image_subject = dm_output.get("image_subject")  # Può essere None se errore
    visual_en = dm_output.get("visual_en", "")
    tags_en = dm_output.get("tags_en", [])

    # Propaghiamo il flag di errore se presente
    is_error = dm_output.get("is_error", False)

    # 2. Update Stato
    updated_state = copy.deepcopy(game_state)
    updated_state.update(new_state)

    # 3. Generazione Immagine
    image_path = None
    image_info = None

    # Generiamo SOLO se c'è un subject valido (quindi non in caso di errore)
    if generate_image and sd_client and image_subject:
        # Costruisce i prompt usando la logica dei LoRA (image_prompts.py)
        pos, neg = build_image_prompts(image_subject, tags_en, visual_en, updated_state)

        # Sceglie la dimensione (sd_client.py)
        w, h = choose_image_size(image_subject, visual_en, tags_en)

        # Genera
        print(f"[ENGINE] Generazione immagine: {image_subject} ({w}x{h})")
        image_path = sd_client.generate_image_from_prompts(
            positive_prompt=pos,
            negative_prompt=neg,
            width=w,
            height=h
        )

        image_info = {
            "image_path": image_path,
            "visual_en": visual_en
        }
    else:
        if not image_subject:
            print("[ENGINE] Nessun subject immagine ricevuto (o errore LLM), salto generazione.")

    return {
        "reply_it": reply_it,
        "game_state": updated_state,
        "image_info": image_info,
        "is_error": is_error  # Passiamo il flag alla GUI
    }