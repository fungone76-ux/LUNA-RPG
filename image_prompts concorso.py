# file: image_prompts.py
from __future__ import annotations

import os
from typing import Dict, List, Tuple

# Import del sistema di regole keyword -> LoRA/Embedding/Testo
try:
    from sd_prompt_rules import apply_sd_prompt_rules
except Exception:
    apply_sd_prompt_rules = None

# --- CONFIGURAZIONE PULITA ---
# RIMOSSO: STYLE_BOOST = "(perfect view)"
STYLE_BOOST = ""

# --- DEFINIZIONE DEGLI AMBIENTI (LOCATION MAPPING) ---
LOCATION_BACKGROUNDS = {
    # Default / Generici
    "default": "school hallway, interior, lockers, daylight",

    # Aule & Uffici
    "St. Jude's Academy - Classroom": "school classroom background, desks, chalkboard, daylight from windows, anime style school",
    "Empty Classroom": "empty school classroom, sunset light, dust particles, desks, nostalgic atmosphere",
    "Luna's Office": "private office, professor desk, bookshelves, leather chair, dim lighting, strict atmosphere",
    "Faculty Room": "teacher lounge, coffee machine, sofas, meeting table",

    # Zone Comuni
    "Corridor": "school hallway, lockers, polished floor, depth of field",
    "Library": "school library, rows of books, quiet atmosphere, wooden tables, reading lamps",
    "Cafeteria": "school cafeteria, lunch tables, crowd in background, bright window",
    "Rooftop": "school rooftop, chain link fence, blue sky, clouds, wind",

    # Zone Sportive/Private
    "Gym": "school gymnasium, basketball court, wooden floor, high ceiling, gym mats",
    "Locker Room": "school locker room, metal lockers, benches, changing room, steamy atmosphere",
    "Pool": "indoor swimming pool, water reflections, tiled floor, large windows, blue water",

    # Zone Servizio/Nascoste
    "School Bathroom": "school bathroom, white tiled walls, mirrors, sinks, clean, ceramic floor",
    "Boiler Room": "boiler room, industrial pipes, steam, dark lighting, metallic textures, rusty",
    "Janitor Closet": "cramped janitor closet, cleaning supplies, buckets, mops, dim light, claustrophobic",

    # Esterni
    "School Entrance": "school gate, cherry blossom trees, exterior, grand entrance",
    "Courtyard": "school courtyard, grass, benches, trees, lunch break",
}

# LUNA: Capo Hostess / Uniforme stretta o Bikini
# Nota: "photorealistic, masterpiece" sono già qui, quindi non servono in fondo.
LUNA_PROMPT = (
    "score_9, score_8_up, score_7_up, masterpiece, NSFW, photorealistic, photo winning award, "
    "stsdebbie, dynamic pose, (thick thighs:0.45), big breasts, full body, 1girl, mature woman, "
    "brown hair, long hair, shiny body, shiny skin, head tilt, massive breasts, cleavage, "
    "athletic body, Cold Lighting, <lora:stsDebbie-10e:0.7> <lora:Expressive_H-000001:0.20>"
)

# STELLA: Maid / Cameriera / Bikini carino
STELLA_PROMPT = (
    "score_9, score_8_up, masterpiece, NSFW, photorealistic, photo winning award, 1girl, "
    "alice_milf_catchers, massive breasts, cleavage, blonde hair, beautiful blue eyes, "
    "shapely legs, hourglass figure, skinny body, narrow waist, wide hips, large breasts, "
    "expressive_h, lean body, tied hair, <lora:alice_milf_catchers_lora:0.7> <lora:Expressive_H:0.2>"
)

# MARIA: Manager SPA / Dominante
MARIA_PROMPT = (
    "score_9, score_8_up, stsSmith, ultra-detailed, realistic lighting, 1girl, mature female, "
    "(middle eastern woman:1.5), old woman, veiny breasts, black hair, short hair, brown eyes, "
    "<lora:stsSmith-10e:0.65> <lora:Expressive_H:0.2>"
)

# AMBIENTE BASE (Fallback)
BASE_ENV_PROMPT = (
    "score_9, score_8_up, masterpiece, photorealistic, 8k, highly detailed, cinematic lighting"
)

# NPC GENERICI
BASE_NPC_PROMPT_NEUTRAL = "score_9, score_8_up, masterpiece, photorealistic, modern setting, npc, school staff"
BASE_NPC_PROMPT_FEMALE = "score_9, score_8_up, masterpiece, photorealistic, modern setting, 1girl, female student, school uniform"
BASE_NPC_PROMPT_MALE = "score_9, score_8_up, masterpiece, photorealistic, modern setting, 1boy, male student, school uniform"

NEGATIVE_PROMPT = (
    "Negative prompt: score_5, score_4, low quality, anime, monochrome, deformed, bad anatomy, "
    "worst face, bad eyes, extra fingers, mutated hands, cartoon, 3d render, sketch, drawing, illustration"
)

CHARACTER_PROMPTS = {
    "Luna": LUNA_PROMPT,
    "Stella": STELLA_PROMPT,
    "Maria": MARIA_PROMPT,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None: return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


SDXL_MODE_DEFAULT = _env_bool("SDXL_MODE", True)
SD_RULES_DEBUG = _env_bool("SD_RULES_DEBUG", False)
SD_RULES_MAX_LORAS = int(os.getenv("SD_RULES_MAX_LORAS", "2"))


def _get_location_prompt(game_state: Dict) -> str:
    """Recupera i tag visivi basati sulla location attuale."""
    loc_name = game_state.get("location", "Corridor")
    if loc_name in LOCATION_BACKGROUNDS:
        return LOCATION_BACKGROUNDS[loc_name]
    for key, val in LOCATION_BACKGROUNDS.items():
        if key in loc_name:
            return val
    return LOCATION_BACKGROUNDS["default"]


def _apply_sd_rules(positive_prompt: str, negative_prompt: str, *, clean_tags: List[str], visual_text: str,
                    full_text_search: str, game_state: Dict) -> Tuple[str, str]:
    if apply_sd_prompt_rules is None: return positive_prompt, negative_prompt

    context_extra = " ".join(str(x) for x in [
        game_state.get("location", ""),
        game_state.get("last_action", ""),
        game_state.get("current_outfit", ""),
        game_state.get("companion_name", ""),
    ] if x)

    try:
        pos2, neg2, dbg = apply_sd_prompt_rules(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            tags=clean_tags,
            visual=visual_text,
            context=(full_text_search + " " + context_extra).strip(),
            sdxl=SDXL_MODE_DEFAULT,
            max_additional_loras=SD_RULES_MAX_LORAS,
        )
        if SD_RULES_DEBUG and (dbg.get("loras") or dbg.get("embeddings") or dbg.get("text")):
            print("[SD RULES]", dbg)
        return pos2, neg2
    except Exception as e:
        print(f"[SD RULES] Warning: errore apply_sd_prompt_rules: {e}")
        return positive_prompt, negative_prompt


def _choose_npc_base(full_text_search: str) -> str:
    t = (full_text_search or "").lower()
    male_hints = ["1boy", "male", "man", "bearded", "teacher", "guard"]
    female_hints = ["1girl", "female", "woman", "student", "maid"]

    if any(h in t for h in male_hints) and not any(h in t for h in female_hints):
        return BASE_NPC_PROMPT_MALE
    if any(h in t for h in female_hints) and not any(h in t for h in male_hints):
        return BASE_NPC_PROMPT_FEMALE
    return BASE_NPC_PROMPT_NEUTRAL


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_image_prompts(image_subject: str, tags_en: List[str], visual_en: str, game_state: Dict) -> Tuple[str, str]:
    subj = (image_subject or "").strip().lower()
    companion_name = game_state.get("companion_name", "Luna")

    # 1. Recupera Sfondo Automatico
    background_prompt = _get_location_prompt(game_state)

    # 2. Outfit (Calcolato ma NON usato automaticamente)
    current_outfit = game_state.get("current_outfit", "hostess uniform")
    # Nota: L'outfit non viene più appeso automaticamente per evitare il blocco "(wearing ...)"
    # Ci affidiamo al fatto che l'LLM lo descriva in 'visual_en' o che sia implicito.

    # 3. Pulizia Tag (Calcolati per le regole SD, ma NON appesi alla fine)
    if isinstance(tags_en, str): tags_en = tags_en.split(",")
    clean_tags = [t.strip() for t in (tags_en or []) if isinstance(t, str) and t.strip() and len(t) > 1]

    visual_text = (visual_en or "").strip()
    full_text_search = (visual_text + " " + " ".join(clean_tags)).lower()

    # --- COSTRUZIONE PROMPT (SEMPLIFICATA) ---

    # A. AMBIENTE SOLO
    if subj == "environment":
        full_prompt = f"{BASE_ENV_PROMPT}, {visual_text}, {background_prompt}"
        return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                               full_text_search=full_text_search, game_state=game_state)

    # B. PERSONAGGI
    target_prompt = ""

    found_chars = [name for name in CHARACTER_PROMPTS.keys() if name.lower() in full_text_search]
    if not found_chars and subj == "companion":
        found_chars.append(str(companion_name))

    if len(found_chars) >= 2:
        # Gruppo
        parts = ["score_9, score_8_up, masterpiece, NSFW, photorealistic", f"{len(found_chars)}girls"]
        for name in found_chars:
            p = CHARACTER_PROMPTS.get(name, LUNA_PROMPT).replace("1girl,", "").replace("1girl", "").strip()
            parts.append(p)
            # RIMOSSO: if name == companion_name: parts.append(outfit_prompt)
        target_prompt = ", ".join(parts)

    elif len(found_chars) == 1:
        # Singolo Companion
        name = found_chars[0]
        base = CHARACTER_PROMPTS.get(name, LUNA_PROMPT)
        target_prompt = base  # RIMOSSO: outfit_prompt

    elif subj == "npc":
        target_prompt = _choose_npc_base(full_text_search)

    else:
        target_prompt = LUNA_PROMPT

    # C. ASSEMBLAGGIO FINALE PULITO
    # Formato: [BASE PERSONAGGIO] + [DESCRIZIONE LLM] + [SFONDO AUTOMATICO]
    # Rimosso: {', '.join(clean_tags)} alla fine per evitare duplicati come "photorealistic, 8k"
    full_prompt = f"{target_prompt}, {visual_text}, {background_prompt}"

    return _apply_sd_rules(full_prompt, NEGATIVE_PROMPT, clean_tags=clean_tags, visual_text=visual_text,
                           full_text_search=full_text_search, game_state=game_state)