# file: game_state.py
import random
from typing import Dict, Any

# --- CONFIGURAZIONE INIZIALE DEI PERSONAGGI (VICTORIAN NOIR) ---
# I prompt base restano, ma qui cambiamo l'outfit per coerenza storica.
NPC_DEFAULTS = {
    "Luna": {
        "outfit": "Elegant Victorian mourning dress, black lace corset, veil hat, leather gloves, dark lipstick",
        "memory": "La tua socia in affari e Medium spiritualista. Cinica, seducente e legata a te da un passato occulto. Usa il suo fascino per manipolare i vivi e i morti.",
        "initial_affinity": 15
    },
    "Stella": {
        "outfit": "White silk nightgown, translucent lace robe, bare feet, pale skin, look innocente ma corrotto",
        "memory": "La giovane ereditiera scomparsa. Sembra fragile e innocente, ma la permanenza nella villa ha risvegliato in lei desideri proibiti.",
        "initial_affinity": 10
    },
    "Maria": {
        "outfit": "Strict black housekeeper uniform, high collar, white apron, holding a heavy key ring, severe bun hairstyle",
        "memory": "La governante capo di Blackwood Manor. Una donna matura, severa e sadica che gestisce i 'piaceri' degli ospiti con disciplina ferrea.",
        "initial_affinity": 5
    }
}


def create_initial_game_state(companion_name: str = "Luna") -> Dict[str, Any]:
    start_data = NPC_DEFAULTS.get(companion_name, NPC_DEFAULTS["Luna"])

    return {
        "turn": 1,
        "companion_name": companion_name,
        "location": "Carrozza privata - Verso Blackwood Manor",

        "affinity_scores": {
            "Luna": NPC_DEFAULTS["Luna"]["initial_affinity"],
            "Stella": NPC_DEFAULTS["Stella"]["initial_affinity"],
            "Maria": NPC_DEFAULTS["Maria"]["initial_affinity"]
        },

        # Inventario investigativo
        "gold": 20, # Sterline
        "inventory": ["Revolver Webley", "Orologio da taschino", "Diario dell'Occulto", "Fiammiferi"],

        "current_outfit": start_data["outfit"],
        "npc_memory_text": start_data["memory"],

        "npc_storage": {
            "Luna": NPC_DEFAULTS["Luna"].copy(),
            "Stella": NPC_DEFAULTS["Stella"].copy(),
            "Maria": NPC_DEFAULTS["Maria"].copy(),
        },

        "story_summary": "Londra, 1892. Siete in viaggio verso Blackwood Manor per indagare sulla scomparsa di Stella.",
        "current_act": "ATTO 1: L'Arrivo nella Nebbia",
        "quest_log": ["Raggiungi la villa senza incidenti", "Non rivelare la tua vera identità"],
        "main_quest": "Scopri il segreto dell'Ordine della Falena e salva Stella prima dell'Eclissi.",

        "last_roll": None,
    }


def switch_companion_memory(game_state: Dict, new_name: str):
    old_name = game_state.get("companion_name", "Luna")
    if old_name in game_state["npc_storage"]:
        game_state["npc_storage"][old_name]["outfit"] = game_state.get("current_outfit", "")
        game_state["npc_storage"][old_name]["memory"] = game_state.get("npc_memory_text", "")

    if new_name in game_state["npc_storage"]:
        data = game_state["npc_storage"][new_name]
        game_state["current_outfit"] = data["outfit"]
        game_state["npc_memory_text"] = data["memory"]
        game_state["companion_name"] = new_name
    else:
        game_state["companion_name"] = new_name
        game_state["current_outfit"] = "Victorian dress"
        game_state["npc_memory_text"] = f"Hai appena incontrato {new_name}."


def roll_d20() -> int:
    roll_base = random.randint(1, 20)
    roll_cheat = random.randint(8, 20)
    return max(roll_base, roll_cheat)


def update_game_state_after_roll(game_state: Dict, action: str, roll: int):
    game_state["last_roll"] = roll


def build_state_summary_text(game_state: Dict) -> str:
    quest_text = "\n- ".join(game_state.get("quest_log", []))
    if not quest_text: quest_text = "Indaga..."

    aff = game_state.get("affinity_scores", {})
    if isinstance(aff, dict):
        aff_str = " | ".join([f"{k[0]}={v}" for k, v in aff.items()])
    else:
        aff_str = str(aff)

    return (
        f"--- {game_state.get('current_act', 'Atto ?')} ---\n\n"
        f"Partner: {game_state.get('companion_name')}\n"
        f"Vestito: {game_state.get('current_outfit')}\n"
        f"Affinità: [{aff_str}]\n"
        f"Luogo: {game_state.get('location')}\n\n"
        f"[DOSSIER {game_state.get('companion_name')}]:\n"
        f"\"{game_state.get('npc_memory_text', '')}\"\n\n"
        f"INDAGINE:\n- {quest_text}"
    )


def update_story_summary(game_state: Dict, new_text: str, max_words=300):
    current = game_state.get("story_summary", "")
    updated = f"{current} {new_text}".strip()
    words = updated.split()
    if len(words) > max_words:
        updated = " ".join(words[-max_words:])
    game_state["story_summary"] = updated