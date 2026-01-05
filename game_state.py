# file: game_state.py
import random
from typing import Dict, Any

# --- CONFIGURAZIONE INIZIALE DEI PERSONAGGI ---
# Qui definiamo lo stato di default per ogni ragazza.
# Se il gioco viene resettato, si parte da qui.
NPC_DEFAULTS = {
    "Luna": {
        "outfit": "Strict grey blazer, black pencil skirt, sheer black pantyhose, glasses",
        "memory": "Professor Luna. Stern and authoritative, she does not tolerate distractions. She is watching you closely.",
        "initial_affinity": 5
    },
    "Stella": {
        "outfit": "Short plaid pleated skirt, white button-up shirt, knee-high socks, loose tie",
        "memory": "Your classmate Stella. Mischievous, arrogant and amused by your bold behavior. She thinks she is better than you.",
        "initial_affinity": 10
    },
    "Maria": {
        "outfit": "Blue industrial custodian jumpsuit, messy bun, heavy work boots, smudged makeup",
        "memory": "The school janitor Maria. Reclusive, blunt and focused on her heavy labor. She avoids eye contact.",
        "initial_affinity": 2
    }
}


def create_initial_game_state(companion_name: str = "Luna") -> Dict[str, Any]:
    """
    Inizializza lo stato del gioco da zero.
    Crea la struttura dati necessaria per gestire 3 personaggi separati.
    """
    # Se il nome non è valido, usa Luna come fallback
    start_data = NPC_DEFAULTS.get(companion_name, NPC_DEFAULTS["Luna"])

    return {
        "turn": 1,
        "companion_name": companion_name,
        "location": "St. Jude's Academy - Classroom",  # Location iniziale default

        # --- TRACKING AFFINITÀ SEPARATO (CRUCIALE) ---
        # L'LLM leggerà e aggiornerà questo dizionario invece di un singolo numero.
        "affinity_scores": {
            "Luna": NPC_DEFAULTS["Luna"]["initial_affinity"],
            "Stella": NPC_DEFAULTS["Stella"]["initial_affinity"],
            "Maria": NPC_DEFAULTS["Maria"]["initial_affinity"]
        },

        "gold": 50,
        "inventory": ["Smartphone", "Backpack", "Student ID"],

        # --- STATO ATTIVO CORRENTE ---
        "current_outfit": start_data["outfit"],
        "npc_memory_text": start_data["memory"],

        # --- DATABASE NASCOSTO (MEMORY STORAGE) ---
        # Qui salviamo lo stato delle ragazze quando NON sono attive.
        "npc_storage": {
            "Luna": NPC_DEFAULTS["Luna"].copy(),
            "Stella": NPC_DEFAULTS["Stella"].copy(),
            "Maria": NPC_DEFAULTS["Maria"].copy(),
        },

        # --- MEMORIA GLOBALE DELLA STORIA ---
        "story_summary": "Hai appena iniziato il semestre alla St. Jude's Academy.",
        "current_act": "ATTO 1: Primo Giorno",
        "quest_log": ["Segui la lezione di Letteratura", "Trova Stella durante la pausa"],
        "main_quest": "Sopravvivi alla vita scolastica e seduci Luna, Stella e Maria",

        # --- DADI ---
        "last_roll": None,
    }


def switch_companion_memory(game_state: Dict, new_name: str):
    """
    Funzione helper per scambiare i dati quando cambia la ragazza attiva.
    Salva l'outfit/memoria della ragazza attuale nel 'npc_storage'
    e carica quelli della nuova ragazza.
    """
    old_name = game_state.get("companion_name", "Luna")

    # 1. SALVA lo stato della ragazza attuale (se esiste nel DB)
    if old_name in game_state["npc_storage"]:
        game_state["npc_storage"][old_name]["outfit"] = game_state.get("current_outfit", "")
        game_state["npc_storage"][old_name]["memory"] = game_state.get("npc_memory_text", "")
        # Nota: l'affinità è già in 'affinity_scores', non serve salvarla qui.

    # 2. CARICA lo stato della nuova ragazza
    if new_name in game_state["npc_storage"]:
        data = game_state["npc_storage"][new_name]
        game_state["current_outfit"] = data["outfit"]
        game_state["npc_memory_text"] = data["memory"]
        game_state["companion_name"] = new_name
    else:
        # Fallback se il nome è nuovo/sconosciuto
        game_state["companion_name"] = new_name
        game_state["current_outfit"] = "standard school uniform"
        game_state["npc_memory_text"] = f"Hai appena incontrato {new_name}."


def roll_d20() -> int:
    """Tiro di dado con vantaggio nascosto per evitare frustrazione."""
    roll_base = random.randint(1, 20)
    roll_cheat = random.randint(8, 20)  # Minimo 8 per aiutare la narrazione
    return max(roll_base, roll_cheat)


def update_game_state_after_roll(game_state: Dict, action: str, roll: int):
    """Registra l'ultimo tiro nel game_state per l'LLM."""
    game_state["last_roll"] = roll


def build_state_summary_text(game_state: Dict) -> str:
    """
    Crea il testo per il pannello laterale della GUI.
    Ora gestisce correttamente la visualizzazione di TUTTE le affinità.
    """
    quest_text = "\n- ".join(game_state.get("quest_log", []))
    if not quest_text: quest_text = "Nessun obiettivo attivo."

    # --- GESTIONE VISUALIZZAZIONE AFFINITÀ ---
    aff = game_state.get("affinity_scores", {})
    if isinstance(aff, dict):
        # Formatta come: L=10 | S=15 | M=2
        aff_str = " | ".join([f"{k[0]}={v}" for k, v in aff.items()])
    else:
        aff_str = str(aff)

    return (
        f"--- {game_state.get('current_act', 'Atto ?')} ---\n\n"
        f"Compagna: {game_state.get('companion_name')}\n"
        f"Outfit: {game_state.get('current_outfit')}\n"
        f"Affinità: [{aff_str}]\n"
        f"Luogo: {game_state.get('location')}\n\n"
        f"[MEMORIA {game_state.get('companion_name')}]:\n"
        f"\"{game_state.get('npc_memory_text', '')}\"\n\n"
        f"OBIETTIVI:\n- {quest_text}"
    )


def update_story_summary(game_state: Dict, new_text: str, max_words=300):
    """Aggiorna il riassunto della storia mantenendolo conciso."""
    current = game_state.get("story_summary", "")
    updated = f"{current} {new_text}".strip()
    words = updated.split()
    if len(words) > max_words:
        updated = " ".join(words[-max_words:])
    game_state["story_summary"] = updated