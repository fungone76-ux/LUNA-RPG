# file: image_prompts.py
from __future__ import annotations
import os
from typing import Dict, List, Tuple

# Import opzionale regole
try:
    from sd_prompt_rules import apply_sd_prompt_rules
except Exception:
    apply_sd_prompt_rules = None

# --- PERSONAGGI BASE (MODIFICHE MINIME AI LORA/FISICO) ---
# Nota: I vestiti vengono sovrascritti/integrati dallo stato di gioco (game_state.py)
# ma qui rimuoviamo riferimenti troppo moderni se presenti.

LUNA_PROMPT = (
    "score_9, score_8_up, score_7_up, masterpiece, NSFW, photorealistic, "
    "stsdebbie, dynamic pose, (thick thighs:0.45), big breasts, full body, "
    "1girl, mature woman, brown hair, shiny skin, head tilt, massive breasts, cleavage, "
    "<lora:stsDebbie-10e:0.7> <lora:Expressive_H-000001:0.20> <lora:FantasyWorldPonyV2:0.40>"
)

STELLA_PROMPT = (
    "score_9, score_8_up, masterpiece, NSFW, photorealistic, 1girl, "
    "alice_milf_catchers, massive breasts, cleavage, blonde hair, beautiful blue eyes, "
    "shapely legs, hourglass figure, skinny body, narrow waist, wide hips, "
    "<lora:alice_milf_catchers_lora:0.7> <lora:Expressive_H:0.2> <lora:FantasyWorldPonyV2:0.40>"
)

MARIA_PROMPT = (
    "score_9, score_8_up, stsSmith, ultra-detailed, realistic lighting, 1girl, "
    "mature female, (middle eastern woman:1.5), veiny breasts, black hair, short hair, "
    "evil smile, glowing magic, "
    "<lora:stsSmith-10e:0.65> <lora:Expressive_H:0.2> <lora:FantasyWorldPonyV2:0.40>"
)

# --- NUOVO AMBIENTE: VICTORIAN GOTHIC NOIR ---
BASE_ENV_PROMPT = (
    "score_9, score_8_up, masterpiece, photorealistic, "
    "victorian era setting, 1890s london atmosphere, gothic manor interiors, "
    "gaslight, fog, velvet curtains, dark wood, mystery, cinematic lighting, "
    "<lora:FantasyWorldPonyV2:0.40>"
)

# NPC Generici (Adattati all'epoca)
BASE_NPC_PROMPT_NEUTRAL = (
    "score_9, score_8_up, masterpiece, photorealistic, victorian era, npc, "
    "gentleman or servant, 1890s clothing, detailed face, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

BASE_NPC_PROMPT_FEMALE = (
    "score_9, score_8_up, masterpiece, photorealistic, victorian era, 1girl, "
    "victorian lady or maid, long dress, corset, detailed, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

BASE_NPC_PROMPT_MALE = (
    "score_9, score_8_up, masterpiece, photorealistic, victorian era, 1boy, "
    "victorian gentleman, suit, top hat, detailed, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

NEGATIVE_PROMPT = (
    "score_5, score_4, low quality, anime, monochrome, deformed, bad anatomy, "
    "worst face, bad eyes, extra fingers, mutated hands, cartoon, 3d render, "
    "sketch, drawing, illustration, modern cars, modern clothes, skyscrapers"
)

CHARACTER_PROMPTS = {
    "Luna": LUNA_PROMPT,
    "Stella": STELLA_PROMPT,
    "Maria": MARIA_PROMPT,
}


# --- HELPERS (Invariati) ---
def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None: return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


SDXL_MODE_DEFAULT = _env_bool("SDXL_MODE", True)
SD_RULES_DEBUG = _env_bool("SD_RULES_DEBUG", False)
SD_RULES_MAX_LORAS = int(os.getenv("SD_RULES_MAX_LORAS", "2"))


def _apply_sd_rules(positive_prompt, negative_prompt, *, clean_tags, visual_text, full_text_search, game_state):
    if apply_sd_prompt_rules is None: return positive_prompt, negative_prompt
    context_extra = " ".join(str(x) for x in [
        game_state.get("location", ""),
        game_state.get("last_action", ""),
        game_state.get("current_outfit", ""),
        game_state.get("companion_name", ""),
    ] if x)
    try:
        pos2, neg2, dbg = apply_sd_prompt_rules(
            positive_prompt=positive_prompt, negative_prompt=negative_prompt,
            tags=clean_tags, visual=visual_text,
            context=(full_text_search + " " + context_extra).strip(),
            sdxl=SDXL_MODE_DEFAULT, max_additional_loras=SD_RULES_MAX_LORAS,
        )
        if SD_RULES_DEBUG and (dbg.get("loras") or dbg.get("embeddings") or dbg.get("text")):
            print("[SD RULES]", dbg)
        return pos2, neg2
    except Exception as e:
        print(f"[SD RULES] Warning: {e}")
        return positive_prompt, negative_prompt


def _choose_npc_base(full_text_search: str) -> str:
    t = (full_text_search or "").lower()
    male_hints = ["1boy", "male", "man", "gentleman", "butler", "lord", "doctor"]
    female_hints = ["1girl", "female", "woman", "lady", "maid", "nurse"]
    if any(h in t for h in male_hints) and not any(h in t for h in female_hints):
        return BASE_NPC_PROMPT_MALE
    if any(h in t for h in female_hints) and not any(h in t for h in male_hints):
        return BASE_NPC_PROMPT_FEMALE
    return BASE_NPC_PROMPT_NEUTRAL


# --- MAIN BUILDER ---
def build_image_prompts(image_subject: str, tags_en: List[str], visual_en: str, game_state: Dict) -> Tuple[str, str]:
    subj = (image_subject or "").strip().lower()
    companion_name = game_state.get("companion_name", "Luna")

    # Gestione Outfit dallo Stato (Priorità: Game State > Prompt Base)
    current_outfit = game_state.get("current_outfit", "Victorian clothes")
    current_outfit = str(current_outfit).replace("wearing", "").strip()

    if any(k in current_outfit.lower() for k in ["naked", "nude", "undressed"]):
        outfit_prompt = f"(nude:1.3), (wearing nothing:1.2), {current_outfit}"
    else:
        outfit_prompt = f"(wearing {current_outfit}:1.3)"

    clean_tags = [t.strip() for t in (tags_en or []) if isinstance(t, str) and t.strip()]
    visual_text = (visual_en or "").strip()
    full_text_search = (visual_text + " " + " ".join(clean_tags)).lower()

    # 1) AMBIENTE
    if subj == "environment":
        full_prompt = f"{BASE_ENV_PROMPT}, {visual_text}, {', '.join(clean_tags)}"
        return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                               full_text_search=full_text_search, game_state=game_state)

    # 2) NPC (con gestione Stella/Maria nel testo)
    if subj == "npc":
        special = []
        if "stella" in full_text_search: special.append("Stella")
        if "maria" in full_text_search: special.append("Maria")

        if special:
            if len(special) >= 2:  # Gruppo
                parts = ["score_9, score_8_up, masterpiece, NSFW, photorealistic", f"{len(special)}girls"]
                for name in special:
                    p = CHARACTER_PROMPTS.get(name, "").replace("1girl,", "").replace("1girl", "").strip()
                    parts.append(p)
                parts.append(visual_text)
                full_prompt = ", ".join(parts)
            else:  # Singolo NPC Speciale
                target = special[0]
                char_prompt = CHARACTER_PROMPTS.get(target, LUNA_PROMPT)
                # Applica outfit solo se è il companion attivo, altrimenti outfit generico o descritto
                if target == companion_name:
                    full_prompt = f"{char_prompt}, {outfit_prompt}, {visual_text}, {', '.join(clean_tags)}"
                else:
                    full_prompt = f"{char_prompt}, {visual_text}, {', '.join(clean_tags)}"
            return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                                   full_text_search=full_text_search, game_state=game_state)

        # NPC Generico
        npc_base = _choose_npc_base(full_text_search)
        full_prompt = f"{npc_base}, {visual_text}, {', '.join(clean_tags)}"
        return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                               full_text_search=full_text_search, game_state=game_state)

    # 3) COMPANION / MULTI
    found_chars = [name for name in CHARACTER_PROMPTS.keys() if name.lower() in full_text_search]
    if not found_chars and subj == "companion": found_chars.append(str(companion_name))

    if len(found_chars) >= 2:  # Gruppo
        parts = ["score_9, score_8_up, masterpiece, NSFW, photorealistic", f"{len(found_chars)}girls"]
        for name in found_chars:
            p = CHARACTER_PROMPTS.get(name, LUNA_PROMPT).replace("1girl,", "").replace("1girl", "").strip()
            parts.append(p)
            if name == companion_name: parts.append(outfit_prompt)
        parts.append(visual_text)
        parts.append(", ".join(clean_tags))
        full_prompt = ", ".join(parts)
        return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                               full_text_search=full_text_search, game_state=game_state)

    # Singolo Companion
    target_char = found_chars[0] if found_chars else str(companion_name)
    char_prompt = CHARACTER_PROMPTS.get(target_char, LUNA_PROMPT)
    # Qui applichiamo con forza l'outfit per "vestire" il personaggio in stile vittoriano
    full_prompt = f"{char_prompt}, {outfit_prompt}, {visual_text}, {', '.join(clean_tags)}"

    return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                           full_text_search=full_text_search, game_state=game_state)