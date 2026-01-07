# file: game_state.py
from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict, List, Optional


# =============================================================================
# LUNA RPG — GAME STATE (coerente con campaign_story + canovaccio DM)
# =============================================================================
# Obiettivo di questo file:
# - definire uno stato iniziale coerente con "Il Sigillo della Carne"
# - offrire helper semplici per GUI e DM engine (affinità, outfit, memoria NPC)
#
# Nota contenuti:
# - ambientazione dark medieval-fantasy, ADULT (18+)
# - qui NON descriviamo atti sessuali espliciti: è solo stato/setting.
# =============================================================================


# ---------------------------------------------------------------------------
# CONFIGURAZIONE INIZIALE NPC (sempre adulti 18+)
# ---------------------------------------------------------------------------

NPC_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "Luna": {
        "age_note": "Adult (30s), 18+",
        "outfit": (
            "bare legs,  pubic hair coming out, small crumpled shorts, barefoot, "
            "black pantyhose, subtle scars, medieval fantasy"
        ),
        "memory": (
            "Luna è la tua complice di lunga data: ironica, tagliente, lucida quando serve. "
            "Tra te e lei c'è confidenza alta e prese in giro affettuose: non siete estranei. "
            "Si è appena risvegliata con te nelle celle del Bastione dei Sospiri. "
            "Sulla sua pelle pulsa un marchio viola: il Sigillo della Chiave. "
            "Lo nasconde dietro battute, ma la cosa la preoccupa."
        ),
        "initial_affinity": 8,
    },
    "Stella": {
        "age_note": "Adult (18+)",
        "outfit": (
            "torn noble silk dress, loosened corset, pale skin, "
            "iron shackles marks on wrists, medieval fantasy"
        ),
        "memory": (
            "Stella è una nobildonna adulta rapita: ingenua, fragile, bisognosa di protezione. "
            "All'inizio è solo un obiettivo e una presenza indiretta (voci, tracce, indizi). "
            "Non deve comparire fisicamente prima del momento giusto."
        ),
        "initial_affinity": 0,
    },
    "Maria": {
        "age_note": "Adult (18+)",
        "outfit": (
            "black inquisitor leather armor, high boots, iron sigils, "
            "veil, cold gaze, whip at belt, medieval dark fantasy"
        ),
        "memory": (
            "Maria è la Grande Inquisitrice: dominante, perfida, usa seduzione e tortura "
            "come strumenti di potere. Nel Bastione è una presenza costante: messaggi, rituali, "
            "tracce e minacce. È l'antagonista centrale della campagna."
        ),
        "initial_affinity": -3,
    },
}


# ---------------------------------------------------------------------------
# Creazione stato iniziale (coerente con ATTO 1 / celle)
# ---------------------------------------------------------------------------

def create_initial_game_state(companion_name: str = "Luna") -> Dict[str, Any]:
    """Crea uno stato iniziale coerente con la campagna.

    Chiavi principali (attese dal resto dell'app):
    - turn, companion_name, location
    - affinity_scores (dict per personaggio)
    - gold, inventory
    - current_outfit, npc_memory_text
    - npc_storage (DB degli NPC)
    - story_summary, main_quest
    - last_roll
    """

    # Normalizza companion
    if not companion_name or companion_name not in NPC_DEFAULTS:
        companion_name = "Luna"

    start_data = NPC_DEFAULTS[companion_name]

    state: Dict[str, Any] = {
        # --- TURN / POSIZIONE ---
        "turn": 1,
        "companion_name": companion_name,
        "location": "Bastione dei Sospiri - Sotterranei dell'Oblio - Celle",

        # --- TRACKING AFFINITÀ (SEPARATO) ---
        "affinity_scores": {
            "Luna": int(NPC_DEFAULTS["Luna"]["initial_affinity"]),
            "Stella": int(NPC_DEFAULTS["Stella"]["initial_affinity"]),
            "Maria": int(NPC_DEFAULTS["Maria"]["initial_affinity"]),
        },

        # --- RISORSE ---
        "gold": 0,
        "inventory": [],  # vi siete svegliati disarmati

        # --- STATO ATTIVO (NPC corrente) ---
        "current_outfit": str(start_data["outfit"]),
        "npc_memory_text": str(start_data["memory"]),

        # --- DATABASE NPC (quando non sono attivi) ---
        "npc_storage": {
            "Luna": deepcopy(NPC_DEFAULTS["Luna"]),
            "Stella": deepcopy(NPC_DEFAULTS["Stella"]),
            "Maria": deepcopy(NPC_DEFAULTS["Maria"]),
        },

        # --- PROGRESSIONE STORIA ---
        "current_act": "ATTO 1: I Sotterranei dell'Oblio (INIZIO)",
        "main_quest": (
            "Fuggire dal Bastione dei Sospiri, spezzare il Sigillo della Chiave, "
            "salvare Stella e fermare Maria."
        ),
        "quest_log": [
            "Uscire dalle celle e raggiungere i depositi del Bastione",
            "Recuperare l'equipaggiamento base",
            "Scoprire cosa significa il Sigillo della Chiave sulla pelle di Luna",
        ],
        "story_summary": (
            "Ti risvegli nelle celle umide del Bastione dei Sospiri insieme a Luna, tua complice. "
            "Un marchio viola — il Sigillo della Chiave — pulsa sulla sua pelle. "
            "L'aria è densa di incenso e feromoni magici: la Brama Nera rende tutto più aggressivo e tentatore. "
            "Prima cosa: uscire vivi dai sotterranei e recuperare l'equipaggiamento."
        ),

        # --- FLAG (aiuto per LLM/DM) ---
        "flags": {
            "chapter": 1,
            "stella_introduced": False,
            "maria_presence_level": 1,  # 1=tracce/messaggi, 2=apparizioni, 3=scontro
            "sigil_key_active": True,
        },

        # --- DADI / AZIONI ---
        "last_roll": None,
        "last_action": "",
        "last_roll_effect": None,
    }

    return state


# ---------------------------------------------------------------------------
# Cambio compagna attiva (Luna/Stella/Maria)
# ---------------------------------------------------------------------------

def switch_companion(game_state: Dict[str, Any], new_name: str) -> None:
    """Cambia la compagna attiva salvando outfit/memoria dell'attuale nel DB."""
    if not isinstance(game_state, dict):
        return

    current_name = str(game_state.get("companion_name") or "Luna")
    new_name = str(new_name or "").strip()

    # salva attuale
    storage: Dict[str, Dict[str, Any]] = game_state.get("npc_storage") or {}
    if isinstance(storage, dict) and current_name in storage:
        storage[current_name]["outfit"] = str(game_state.get("current_outfit", ""))
        storage[current_name]["memory"] = str(game_state.get("npc_memory_text", ""))

    # carica nuovo
    if isinstance(storage, dict) and new_name in storage:
        data = storage[new_name]
        game_state["companion_name"] = new_name
        game_state["current_outfit"] = str(data.get("outfit", ""))
        game_state["npc_memory_text"] = str(data.get("memory", ""))
    else:
        # fallback sicuro: non inventiamo un personaggio moderno/strano
        game_state["companion_name"] = "Luna"
        data = storage.get("Luna", NPC_DEFAULTS["Luna"])
        game_state["current_outfit"] = str(data.get("outfit", NPC_DEFAULTS["Luna"]["outfit"]))
        game_state["npc_memory_text"] = str(data.get("memory", NPC_DEFAULTS["Luna"]["memory"]))


# ---------------------------------------------------------------------------
# Dadi
# ---------------------------------------------------------------------------

def roll_d20() -> int:
    """Tiro D20 con piccolo vantaggio nascosto (anti-frustrazione).

    Regola: l'app può applicare un lieve vantaggio. Il DM deve trattare last_roll come finale.
    """
    roll_base = random.randint(1, 20)
    roll_cheat = random.randint(8, 20)  # min 8: aiuta a far avanzare la storia
    return max(roll_base, roll_cheat)


def update_game_state_after_roll(game_state: Dict[str, Any], action: str, roll: int) -> None:
    """Registra l'ultimo tiro e l'azione tentata."""
    if not isinstance(game_state, dict):
        return
    game_state["last_roll"] = int(roll)
    game_state["last_action"] = str(action or "").strip()


# ---------------------------------------------------------------------------
# UI helper: testo riassuntivo per pannello laterale
# ---------------------------------------------------------------------------

def build_state_summary_text(game_state: Dict[str, Any]) -> str:
    """Crea il testo per il pannello laterale della GUI."""
    if not isinstance(game_state, dict):
        return ""

    aff: Dict[str, Any] = game_state.get("affinity_scores") or {}
    def _aff(name: str) -> str:
        v = aff.get(name, "?")
        return str(v)

    inv = game_state.get("inventory") or []
    inv_text = ", ".join(map(str, inv)) if inv else "—"

    qlog = game_state.get("quest_log") or []
    if isinstance(qlog, list) and qlog:
        quest_text = "\n- " + "\n- ".join(str(x) for x in qlog if str(x).strip())
    else:
        quest_text = "\n- —"

    last_roll = game_state.get("last_roll")
    roll_text = f"{last_roll}" if last_roll is not None else "—"

    act = str(game_state.get("current_act") or "—")

    return (
        f"Turno: {game_state.get('turn')}\n"
        f"Luogo: {game_state.get('location')}\n"
        f"Atto: {act}\n\n"
        f"Compagna attiva: {game_state.get('companion_name')}\n"
        f"Affinità → Luna: {_aff('Luna')} | Stella: {_aff('Stella')} | Maria: {_aff('Maria')}\n\n"
        f"Oro: {game_state.get('gold')}\n"
        f"Inventario: {inv_text}\n"
        f"Ultimo tiro: {roll_text}\n\n"
        f"[MEMORIA {game_state.get('companion_name')}]:\n"
        f"“{game_state.get('npc_memory_text', '')}”\n\n"
        f"OBIETTIVI:{quest_text}"
    )


# ---------------------------------------------------------------------------
# Memoria globale: riassunto storia (cap a N parole)
# ---------------------------------------------------------------------------

def update_story_summary(game_state: Dict[str, Any], new_text: str, max_words: int = 300) -> None:
    """Aggiorna il riassunto della storia mantenendolo conciso."""
    if not isinstance(game_state, dict):
        return

    current = str(game_state.get("story_summary", "") or "")
    incoming = str(new_text or "").strip()
    if not incoming:
        return

    updated = f"{current} {incoming}".strip()
    words = updated.split()
    if len(words) > max_words:
        updated = " ".join(words[-max_words:])
    game_state["story_summary"] = updated
