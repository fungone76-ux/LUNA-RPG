# file: dm_client.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from llm_client import call_llm

# ---------------------------------------------------------------------------
# Prompt paths
# ---------------------------------------------------------------------------

DM_PROMPT_PATH = Path("prompts/dm_system_prompt_canovaccio_C.txt")
STORY_PATH = Path("prompts/campaign_story.txt")

# ---------------------------------------------------------------------------
# Long-term memory/state instruction
# ---------------------------------------------------------------------------

# ISTRUZIONI AGGIORNATE PER LA MEMORIA SEPARATA
MEMORY_INSTRUCTION = (
    "\n\n[CRITICAL MEMORY & STATE INSTRUCTION]"
    "\nIn the response JSON, inside 'new_state', you MUST update these fields:"
    "\n"
    "\n1) 'npc_memory_text': Summarize interactions with the CURRENT active girl only."
    "\n   - E.g. 'Luna promised a massage', 'Stella is wearing the red bikini you gifted'."
    "\n   - This string is SAVED permanently for this specific girl."
    "\n"
    "\n2) 'current_outfit': The companion's outfit description in ENGLISH."
    "\n   - MUST reflect the current visual state (e.g. 'red bikini')."
    "\n"
    "\n3) 'companion_name': Change ONLY if the user explicitly calls or interacts with another girl."
    "\n"
    "\n4) 'story_summary': Global plot summary (max 200 words)."
    "\n"
    "\n5) 'quest_log': List of current objectives."
)


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

def load_dm_system_prompt() -> str:
    try:
        base_prompt = DM_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        base_prompt = "You are a Dungeon Master. Respond only in valid JSON."

    try:
        campaign_story = STORY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        campaign_story = "[NO SPECIFIC CAMPAIGN STORY LOADED.]"

    full_prompt = (
        f"{base_prompt}\n\n"
        f"--- CAMPAIGN DATA ---\n"
        f"{campaign_story}\n"
        f"--- END CAMPAIGN DATA ---\n"
        f"{MEMORY_INSTRUCTION}"
    )
    return full_prompt


def build_dm_input(
        main_quest: str,
        story_summary: str,
        game_state: Dict[str, Any],
        recent_dialogue: List[Dict[str, str]],
        player_input: str,
) -> Dict[str, Any]:
    # --- MODIFICA FONDAMENTALE ---
    # Estraiamo la memoria specifica del personaggio attivo per passarla all'IA
    # in modo che sappia cosa è successo con LEI in passato.
    active_char_mem = game_state.get("npc_memory_text", "Nessuna memoria precedente con questo personaggio.")

    return {
        "main_quest": main_quest,
        "story_summary": story_summary,  # Storia globale del Resort
        "active_character_memory": active_char_mem,  # <--- MEMORIA PERSONALE SPECIFICA
        "game_state": {
            "companion_name": game_state.get("companion_name"),
            "current_outfit": game_state.get("current_outfit"),
            "location": game_state.get("location"),
            "affinity": game_state.get("affinity"),
            "quest_log": game_state.get("quest_log"),
            "current_act": game_state.get("current_act"),
        },
        "recent_dialogue": recent_dialogue,
        "player_input": player_input,
    }


def _repair_json(content: str) -> Dict[str, Any]:
    clean = (content or "").strip()
    if clean.startswith("```json"):
        clean = clean.replace("```json", "", 1)
    if clean.startswith("```"):
        clean = clean.replace("```", "", 1)
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Tentativo disperato di recuperare JSON parziale
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start: end + 1])
            except Exception:
                pass
        raise ValueError(f"JSON irrecuperabile: {clean[:80]}...")


def get_dm_response(
        main_quest: str,
        story_summary: str,
        game_state: Dict[str, Any],
        recent_dialogue: List[Dict[str, str]],
        player_input: str,
) -> Dict[str, Any]:
    system_prompt = load_dm_system_prompt()
    dm_input = build_dm_input(main_quest, story_summary, game_state, recent_dialogue, player_input)

    # --- DEBUG ---
    print("\n" + "─" * 60)
    print("📤 [IO] SENDING TO MASTER:")
    print(json.dumps(dm_input, ensure_ascii=False, indent=2))
    print("─" * 60)

    input_str = json.dumps(dm_input, ensure_ascii=False)
    raw_response = call_llm(system_prompt, input_str)

    final_json: Dict[str, Any] = {}

    if isinstance(raw_response, dict):
        if "reply_it" in raw_response:
            final_json = raw_response
        else:
            content = raw_response.get("content")
            if isinstance(content, str) and content.strip():
                try:
                    final_json = _repair_json(content)
                except Exception:
                    final_json = {}

    if not final_json:
        final_json = {
            "reply_it": "Il narratore ha avuto un momento di confusione (Errore comunicazione LLM).",
            "new_state": {},
            "image_subject": None,
            "visual_en": None,
            "tags_en": [],
            "animation_instructions_en": "",
            "is_error": True,
        }

    # --- DEBUG ---
    print("\n" + "─" * 60)
    print("📥 [MASTER] RESPONSE:")
    print(json.dumps(final_json, ensure_ascii=False, indent=2))
    print("─" * 60 + "\n")

    return final_json