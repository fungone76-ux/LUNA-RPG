# file: game_state.py
import random
from typing import Dict, Any


def create_initial_game_state(companion_name: str) -> Dict[str, Any]:
    return {
        "turn": 1,
        "companion_name": companion_name,
        "location": "Taverna Iniziale",
        "affinity": 50.0,
        "gold": 10,
        "inventory": [],

        # --- TRACKER OUTFIT ---
        # Questo campo persiste finché l'IA non decide di cambiarlo (es. "naked", "bikini")
        "current_outfit": "medieval fantasy adventurer clothes",

        # --- TRACKER TRAMA (CANOVACCIO) ---
        "story_summary": "L'avventura ha inizio.",
        "current_act": "ATTO 1: L'Inizio",
        "quest_log": ["Esplora i dintorni", "Parla con la tua compagna"],
        "main_quest": "Sopravvivi e scopri il tuo destino",

        # --- DADI ---
        "last_roll": None,
    }


def roll_d20() -> int:
    """
    Tiro di dado d20 TRUCCATO (Metodo 'Vantaggio Nascosto').
    """
    roll_base = random.randint(1, 20)
    roll_cheat = random.randint(8, 20)
    return max(roll_base, roll_cheat)


def update_game_state_after_roll(game_state: Dict, action: str, roll: int):
    """
    Registra solo il tiro. Le conseguenze sono gestite interamente dall'LLM.
    """
    game_state["last_roll"] = roll


def build_state_summary_text(game_state: Dict) -> str:
    """
    Mostra un riassunto dello stato nella colonna sinistra della GUI.
    Ora include anche l'Atto corrente e l'Outfit.
    """
    quest_text = "\n- ".join(game_state.get("quest_log", []))
    if not quest_text: quest_text = "Nessuna quest attiva"

    return (
        f"--- {game_state.get('current_act', 'Atto ?')} ---\n\n"
        f"Compagna: {game_state.get('companion_name')}\n"
        f"Outfit: {game_state.get('current_outfit')}\n"
        f"Luogo: {game_state.get('location')}\n"
        f"Affinità: {game_state.get('affinity')}\n"
        f"Oro: {game_state.get('gold')}\n"
        f"Ultimo dado: {game_state.get('last_roll') or '-'}\n\n"
        f"QUEST:\n- {quest_text}"
    )


def update_story_summary(game_state: Dict, new_text: str, max_words=300):
    """
    Funzione di backup. Normalmente l'IA aggiorna il summary via JSON,
    ma se fallisce, usiamo questa per accodare il testo.
    """
    current = game_state.get("story_summary", "")
    updated = f"{current} {new_text}".strip()
    words = updated.split()
    if len(words) > max_words:
        updated = " ".join(words[-max_words:])
    game_state["story_summary"] = updated