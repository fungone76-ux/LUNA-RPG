# file: dm_engine.py
from typing import Any, Dict, List, Optional, Tuple
import copy
from dm_client import get_dm_response
from image_prompts import build_image_prompts
from game_state import switch_companion_memory  # Importiamo la funzione switch

try:
    import sd_client
except ImportError:
    sd_client = None


def choose_image_size(image_subject: str, visual_en: str, tags_en: List[str]) -> Tuple[int, int]:
    if sd_client:
        return sd_client.choose_image_size(image_subject, visual_en, tags_en)
    return 1032, 864


def process_turn(
        main_quest: str,
        story_summary: str,
        game_state: Dict[str, Any],
        recent_dialogue: List[Dict[str, str]],
        player_input: str,
        generate_image: bool = True,
) -> Dict[str, Any]:
    # 1. Chiamata LLM
    dm_output = get_dm_response(
        main_quest, story_summary, game_state, recent_dialogue, player_input
    )

    reply_it = dm_output.get("reply_it", "")
    new_state = dm_output.get("new_state", {})
    image_subject = dm_output.get("image_subject")
    visual_en = dm_output.get("visual_en", "")
    tags_en = dm_output.get("tags_en", [])
    is_error = dm_output.get("is_error", False)

    # 2. Update Stato & GESTIONE MEMORIA PERSONAGGI
    updated_state = copy.deepcopy(game_state)

    # Controllo Cambio Personaggio
    new_companion = new_state.get("companion_name")
    current_companion = updated_state.get("companion_name")

    if new_companion and new_companion != current_companion:
        # Se l'LLM cambia ragazza, attiviamo lo scambio di memoria
        print(f"[ENGINE] Cambio personaggio rilevato: {current_companion} -> {new_companion}")
        switch_companion_memory(updated_state, new_companion)

        # IMPORTANTE: Rimuoviamo 'companion_name', 'current_outfit' e 'npc_memory_text'
        # da new_state per evitare che l'LLM sovrascriva i dati appena caricati
        # con valori "allucinati" o vuoti.
        if "companion_name" in new_state: del new_state["companion_name"]
        if "current_outfit" in new_state: del new_state["current_outfit"]
        if "npc_memory_text" in new_state: del new_state["npc_memory_text"]

    # Applichiamo il resto degli aggiornamenti (location, affinity, ecc.)
    updated_state.update(new_state)

    # 3. Generazione Immagine
    image_path = None
    image_info = None

    if generate_image and sd_client and image_subject:
        pos, neg = build_image_prompts(image_subject, tags_en, visual_en, updated_state)
        w, h = choose_image_size(image_subject, visual_en, tags_en)

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

    return {
        "reply_it": reply_it,
        "game_state": updated_state,
        "image_info": image_info,
        "is_error": is_error
    }