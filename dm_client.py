# file: dm_client.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from llm_client import call_llm

# ---------------------------------------------------------------------------
# Prompt paths
# ---------------------------------------------------------------------------

# ✅ Use Canovaccio C as the BASE DM prompt (already includes tone + tables + JSON contract)
DM_PROMPT_PATH = Path("prompts/dm_system_prompt_canovaccio_C.txt")

# Optional extra campaign data (secrets/plot beats). Kept for backward compatibility.
STORY_PATH = Path("prompts/campaign_story.txt")

# ---------------------------------------------------------------------------
# Long-term memory/state instruction (aligned with engine)
# ---------------------------------------------------------------------------

# IMPORTANT:
# - Your engine merges `new_state` into `game_state` via `updated_state.update(new_state)` (dm_engine.py),
#   so it is SAFE to update these fields via new_state.
# - recent_dialogue must NEVER be put inside new_state (GUI manages it).
MEMORY_INSTRUCTION = (
    "\n\n[CRITICAL MEMORY & STATE INSTRUCTION]"
    "\nIn the response JSON, inside 'new_state', you MAY update these fields when needed:"
    "\n"
    "\n1) 'story_summary': Updated conceptual summary (max 200 words)."
    "\n   - Keep it compact and persistent."
    "\n"
    "\n2) 'current_outfit': The companion's CURRENT outfit description."
    "\n   - PERSISTENCE RULE: COPY the previous value unless the scene clearly changes clothing/damage."
    "\n"
    "\n3) 'current_act': Current story phase (e.g., 'ATTO 1: ...')."
    "\n   - Update only on major plot progression."
    "\n"
    "\n4) 'quest_log': List of short current objectives."
    "\n   - Add/remove as progress changes."
    "\n"
    "\nNEVER include 'recent_dialogue' inside 'new_state'."
)

# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

def load_dm_system_prompt() -> str:
    # Build the DM brain:
    # 1) Base DM prompt (Canovaccio C + JSON contract)
    # 2) Optional campaign story (plot & secrets)
    # 3) Memory/state instruction
    try:
        base_prompt = DM_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        base_prompt = "You are a Dungeon Master. Respond only in valid JSON."

    try:
        campaign_story = STORY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        campaign_story = "[NO SPECIFIC CAMPAIGN STORY LOADED. IMPROVISE.]"

    full_prompt = (
        f"{base_prompt}\n\n"
        f"--- CAMPAIGN DATA (PLOT & SECRETS) ---\n"
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
    return {
        "main_quest": main_quest,
        "story_summary": story_summary,
        "game_state": game_state,  # includes current_outfit/current_act/quest_log
        "recent_dialogue": recent_dialogue,
        "player_input": player_input,
    }


def _repair_json(content: str) -> Dict[str, Any]:
    # Try to recover JSON if the model wraps it in code fences or adds stray text.
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
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start : end + 1])
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

    # --- DEBUG: what we send ---
    print("\n" + "─" * 60)
    print("📤 [IO] STO INVIANDO QUESTO AL MASTER:")
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

    # --- DEBUG: what we receive ---
    print("\n" + "─" * 60)
    print("📥 [MASTER] IL CERVELLO HA RISPOSTO:")
    print(json.dumps(final_json, ensure_ascii=False, indent=2))
    print("─" * 60 + "\n")

    return final_json
