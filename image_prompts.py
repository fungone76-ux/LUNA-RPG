# file: image_prompts.py
from __future__ import annotations

import os
from typing import Dict, List, Tuple

# Import del sistema di regole keyword -> LoRA/Embedding/Testo
# (Se manca il file, non blocchiamo la generazione immagini.)
try:
    from sd_prompt_rules import apply_sd_prompt_rules
except Exception:  # pragma: no cover
    apply_sd_prompt_rules = None


# --- CONFIGURAZIONI LORA E PROMPT SPECIFICI (INVARIATI) ---
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

BASE_ENV_PROMPT = (
    "score_9, score_8_up, masterpiece, photorealistic, dark fantasy, medieval setting, "
    "detailed, atmospheric, <lora:FantasyWorldPonyV2:0.40>"
)

# Prompt NPC generico (usato solo se non è Maria/Stella/Luna).
# NOTA: niente '1girl' fisso: l'NPC può essere maschio/creatura.
BASE_NPC_PROMPT_NEUTRAL = (
    "score_9, score_8_up, masterpiece, photorealistic, dark fantasy, medieval setting, "
    "npc, detailed, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

BASE_NPC_PROMPT_FEMALE = (
    "score_9, score_8_up, masterpiece, photorealistic, dark fantasy, medieval setting, "
    "1girl, female npc, medieval fantasy outfit, detailed, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

BASE_NPC_PROMPT_MALE = (
    "score_9, score_8_up, masterpiece, photorealistic, dark fantasy, medieval setting, "
    "1boy, male npc, medieval fantasy outfit, detailed, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
)

NEGATIVE_PROMPT = (
    "score_5, score_4, low quality, anime, monochrome, deformed, bad anatomy, "
    "worst face, bad eyes, extra fingers, mutated hands, cartoon, 3d render, "
    "sketch, drawing, illustration"
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
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


# Pony/SDXL di default (visto che nei prompt c'è FantasyWorldPonyV2)
SDXL_MODE_DEFAULT = _env_bool("SDXL_MODE", True)
SD_RULES_DEBUG = _env_bool("SD_RULES_DEBUG", False)
SD_RULES_MAX_LORAS = int(os.getenv("SD_RULES_MAX_LORAS", "2"))


def _apply_sd_rules(
    positive_prompt: str,
    negative_prompt: str,
    *,
    clean_tags: List[str],
    visual_text: str,
    full_text_search: str,
    game_state: Dict,
) -> Tuple[str, str]:
    """Applica le regole keyword->addon, senza rompere nulla se il file manca."""
    if apply_sd_prompt_rules is None:
        return positive_prompt, negative_prompt

    # Aggiungi un minimo di contesto extra (senza inventare niente)
    context_extra = " ".join(
        str(x) for x in [
            game_state.get("location", ""),
            game_state.get("last_action", ""),
            game_state.get("current_outfit", ""),
            game_state.get("companion_name", ""),
        ] if x
    )

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

    male_hints = [
        "1boy", "male", "man", "bearded", "bartender", "guard", "knight",
        "bandit", "soldier", "priest", "king", "orc", "goblin", "troll",
        "muscular man",
        "uomo", "barbuto", "oste", "guardia", "cavaliere", "bandito", "soldato",
        "prete", "re", "orco", "goblin", "troll",
    ]
    female_hints = [
        "1girl", "female", "woman", "barmaid", "maid", "nun", "queen",
        "donna", "cameriera", "serva", "suora", "regina",
    ]

    if any(h in t for h in male_hints) and not any(h in t for h in female_hints):
        return BASE_NPC_PROMPT_MALE
    if any(h in t for h in female_hints) and not any(h in t for h in male_hints):
        return BASE_NPC_PROMPT_FEMALE
    return BASE_NPC_PROMPT_NEUTRAL


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_image_prompts(
    image_subject: str,
    tags_en: List[str],
    visual_en: str,
    game_state: Dict,
) -> Tuple[str, str]:
    subj = (image_subject or "").strip().lower()
    companion_name = game_state.get("companion_name", "Luna")

    # --- LOGICA SMART OUTFIT ---
    current_outfit = game_state.get("current_outfit", "medieval fantasy clothes")
    current_outfit = str(current_outfit).replace("wearing", "").strip()

    nude_keywords = ["naked", "nude", "wearing nothing", "undressed", "completely naked"]

    if any(k in current_outfit.lower() for k in nude_keywords):
        outfit_prompt = f"(nude:1.3), (wearing nothing:1.2), (nipples:1.1), {current_outfit}"
    else:
        outfit_prompt = f"(wearing {current_outfit}:1.3)"
    # ---------------------------

    clean_tags = [t.strip() for t in (tags_en or []) if isinstance(t, str) and t.strip()]
    visual_text = (visual_en or "").strip()
    full_text_search = (visual_text + " " + " ".join(clean_tags)).lower()

    # 1) AMBIENTE (L'outfit non serve)
    if subj == "environment":
        full_prompt = f"{BASE_ENV_PROMPT}, {visual_text}, {', '.join(clean_tags)}"
        pos, neg = _apply_sd_rules(
            full_prompt, NEGATIVE_PROMPT,
            clean_tags=clean_tags, visual_text=visual_text,
            full_text_search=full_text_search, game_state=game_state,
        )
        return pos, neg

    # 2) NPC:
    # - Regola: NON iniettare il prompt della compagna SOLO perché viene nominata.
    # - ECCEZIONE richiesta: se nel testo c'è "Stella" o "Maria", allora usa il prompt personaggio.
    if subj == "npc":
        special = []
        if "stella" in full_text_search:
            special.append("Stella")
        if "maria" in full_text_search:
            special.append("Maria")

        if special:
            # Se compaiono entrambe, crea un gruppo (2girls) invece di un NPC generico.
            if len(special) >= 2:
                prompt_parts: List[str] = []
                prompt_parts.append("score_9, score_8_up, masterpiece, NSFW, photorealistic")
                prompt_parts.append(f"{len(special)}girls")

                for name in special:
                    char_prompt = CHARACTER_PROMPTS.get(name, "")
                    clean_char = char_prompt.replace("1girl,", "").replace("1girl", "").strip()
                    prompt_parts.append(clean_char)

                prompt_parts.append(visual_text)
                prompt_parts.append(", ".join(clean_tags))
                full_prompt = ", ".join(prompt_parts)
            else:
                target = special[0]
                char_prompt = CHARACTER_PROMPTS.get(target, LUNA_PROMPT)
                # outfit solo se è la companion attiva (di solito Luna)
                if target == companion_name:
                    full_prompt = f"{char_prompt}, {outfit_prompt}, {visual_text}, {', '.join(clean_tags)}"
                else:
                    full_prompt = f"{char_prompt}, {visual_text}, {', '.join(clean_tags)}"

            pos, neg = _apply_sd_rules(
                full_prompt, NEGATIVE_PROMPT,
                clean_tags=clean_tags, visual_text=visual_text,
                full_text_search=full_text_search, game_state=game_state,
            )
            return pos, neg

        # altrimenti: npc generico (non usare Luna solo perché nominata)
        npc_base = _choose_npc_base(full_text_search)
        full_prompt = f"{npc_base}, {visual_text}, {', '.join(clean_tags)}"
        pos, neg = _apply_sd_rules(
            full_prompt, NEGATIVE_PROMPT,
            clean_tags=clean_tags, visual_text=visual_text,
            full_text_search=full_text_search, game_state=game_state,
        )
        return pos, neg

    # 3) COMPANION / MULTI (qui ha senso usare LoRA personaggi)
    found_chars: List[str] = []
    for name in CHARACTER_PROMPTS.keys():
        if name.lower() in full_text_search:
            found_chars.append(name)

    if not found_chars and subj == "companion":
        found_chars.append(str(companion_name))

    # --- CASO GRUPPO ---
    if len(found_chars) >= 2:
        prompt_parts: List[str] = []
        prompt_parts.append("score_9, score_8_up, masterpiece, NSFW, photorealistic")
        prompt_parts.append(f"{len(found_chars)}girls")

        for name in found_chars:
            char_prompt = CHARACTER_PROMPTS.get(name, LUNA_PROMPT)
            clean_char = char_prompt.replace("1girl,", "").replace("1girl", "").strip()
            prompt_parts.append(clean_char)

            # Outfit SOLO per la companion principale (evita confusione)
            if name == companion_name:
                prompt_parts.append(outfit_prompt)

        prompt_parts.append(visual_text)
        prompt_parts.append(", ".join(clean_tags))

        full_prompt = ", ".join(prompt_parts)
        pos, neg = _apply_sd_rules(
            full_prompt, NEGATIVE_PROMPT,
            clean_tags=clean_tags, visual_text=visual_text,
            full_text_search=full_text_search, game_state=game_state,
        )
        return pos, neg

    # --- CASO SINGOLO ---
    if len(found_chars) == 1:
        target_char = found_chars[0]
        char_prompt = CHARACTER_PROMPTS.get(target_char, LUNA_PROMPT)

        # outfit SOLO se è la companion attiva (Luna di default)
        if target_char == companion_name:
            full_prompt = f"{char_prompt}, {outfit_prompt}, {visual_text}, {', '.join(clean_tags)}"
        else:
            full_prompt = f"{char_prompt}, {visual_text}, {', '.join(clean_tags)}"

        pos, neg = _apply_sd_rules(
            full_prompt, NEGATIVE_PROMPT,
            clean_tags=clean_tags, visual_text=visual_text,
            full_text_search=full_text_search, game_state=game_state,
        )
        return pos, neg

    # Fallback (companion attiva)
    char_prompt = CHARACTER_PROMPTS.get(str(companion_name), LUNA_PROMPT)
    full_prompt = f"{char_prompt}, {outfit_prompt}, {visual_text}, {', '.join(clean_tags)}"
    pos, neg = _apply_sd_rules(
        full_prompt, NEGATIVE_PROMPT,
        clean_tags=clean_tags, visual_text=visual_text,
        full_text_search=full_text_search, game_state=game_state,
    )
    return pos, neg
