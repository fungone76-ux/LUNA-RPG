# file: game_state.py
import random
from typing import Dict, Any

# --- CONFIGURAZIONE INIZIALE DEI PERSONAGGI ---
# Ora coerente con l'ambientazione scolastica
NPC_DEFAULTS = {
    "Luna": {
        "outfit": "Strict grey blazer, black pencil skirt, sheer black pantyhose",
        "memory": "Professor Luna. Stern and authoritative, she does not tolerate distractions."
    },
    "Stella": {
        "outfit": "Short plaid pleated skirt, white button-up shirt, knee-high socks",
        "memory": "Your classmate. Mischievous and amused by your bold behavior."
    },
    "Maria": {
        "outfit": "Blue industrial custodian jumpsuit, messy bun",
        "memory": "The school janitor. Reclusive and focused on her heavy labor."
    }
}


def create_initial_game_state(companion_name: str = "Luna") -> Dict[str, Any]:
    # Carica i dati della compagna iniziale
    start_data = NPC_DEFAULTS.get(companion_name, NPC_DEFAULTS["Luna"])

    return {
        "turn": 1,
        "companion_name": companion_name,
        "location": "St. Jude's Academy - Classroom", # Aggiornato
        "affinity": 5.0, # Partiamo bassi come richiesto
        "gold": 50, # Budget da studente
        "inventory": ["Smartphone", "Backpack", "Student ID"],

        # --- STATI ATTIVI ---
        "current_outfit": start_data["outfit"],
        "npc_memory_text": start_data["memory"],

        # --- DATABASE NASCOSTO (La memoria di tutte le ragazze) ---
        "npc_storage": {
            "Luna": NPC_DEFAULTS["Luna"].copy(),
            "Stella": NPC_DEFAULTS["Stella"].copy(),
            "Maria": NPC_DEFAULTS["Maria"].copy(),
        },

        # --- MEMORIA GLOBALE (Trama principale scolastica) ---
        "story_summary": "Hai appena iniziato il semestre alla St. Jude's Academy.", # Aggiornato
        "current_act": "ATTO 1: Primo Giorno",
        "quest_log": ["Segui la lezione di Letteratura", "Trova Stella durante la pausa"], # Aggiornato
        "main_quest": "Sopravvivi alla vita scolastica e seduci Luna, Stella e Maria", # Aggiornato
        "last_roll": None,
    }


def switch_companion_memory(game_state: Dict, new_name: str):
    """
    Funzione MAGICA: Salva i dati della ragazza vecchia e carica quella nuova.
    """
    old_name = game_state.get("companion_name", "Luna")

    # 1. SALVA lo stato attuale nella scheda della ragazza che se ne va
    if old_name in game_state["npc_storage"]:
        game_state["npc_storage"][old_name]["outfit"] = game_state.get("current_outfit", "")
        game_state["npc_storage"][old_name]["memory"] = game_state.get("npc_memory_text", "")
        print(f"[MEMORY] Dati salvati per {old_name}: {game_state['npc_storage'][old_name]}")

    # 2. CARICA lo stato della nuova ragazza
    if new_name in game_state["npc_storage"]:
        data = game_state["npc_storage"][new_name]
        game_state["current_outfit"] = data["outfit"]
        game_state["npc_memory_text"] = data["memory"]
        game_state["companion_name"] = new_name
        print(f"[MEMORY] Dati caricati per {new_name}: {data}")
    else:
        game_state["companion_name"] = new_name
        game_state["current_outfit"] = "standard school uniform"
        game_state["npc_memory_text"] = f"Hai appena incontrato {new_name}."


def roll_d20() -> int:
    roll_base = random.randint(1, 20)
    roll_cheat = random.randint(10, 20)
    return max(roll_base, roll_cheat)


def update_game_state_after_roll(game_state: Dict, action: str, roll: int):
    game_state["last_roll"] = roll


def build_state_summary_text(game_state: Dict) -> str:
    quest_text = "\n- ".join(game_state.get("quest_log", []))
    if not quest_text: quest_text = "Nessun obiettivo attivo."

    return (
        f"--- {game_state.get('current_act', 'Atto ?')} ---\n\n"
        f"Compagna: {game_state.get('companion_name')}\n"
        f"Outfit Lei: {game_state.get('current_outfit')}\n"
        f"Affinità: {game_state.get('affinity')}\n"
        f"Luogo: {game_state.get('location')}\n\n"
        f"[MEMORIA {game_state.get('companion_name')}]:\n"
        f"\"{game_state.get('npc_memory_text', '')}\"\n\n"
        f"OBIETTIVI:\n- {quest_text}"
    )


def update_story_summary(game_state: Dict, new_text: str, max_words=300):
    current = game_state.get("story_summary", "")
    updated = f"{current} {new_text}".strip()
    words = updated.split()
    if len(words) > max_words:
        updated = " ".join(words[-max_words:])
    game_state["story_summary"] = updated