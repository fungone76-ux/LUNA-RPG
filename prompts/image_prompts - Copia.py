# file: image_prompts.py
from typing import Dict, List, Tuple

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

# Prompt NPC generico (usato solo se non è Maria/Stella/Luna)
BASE_NPC_PROMPT = (
    "score_9, score_8_up, masterpiece, photorealistic, 1girl, medieval fantasy outfit, "
    "detailed face, cinematic lighting, <lora:FantasyWorldPonyV2:0.40>"
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


def build_image_prompts(
        image_subject: str,
        tags_en: List[str],
        visual_en: str,
        game_state: Dict,
) -> Tuple[str, str]:
    """
    Costruisce il prompt per Stable Diffusion gestendo SCENE DI GRUPPO.
    """
    subj = (image_subject or "").strip().lower()
    companion_name = game_state.get("companion_name", "Luna")

    # Pulizia tag e testi
    clean_tags = [t.strip() for t in tags_en if t.strip()]
    visual_text = (visual_en or "").strip()
    full_text_search = (visual_text + " " + " ".join(clean_tags)).lower()

    # 1. AMBIENTE (Priorità se esplicito)
    if subj == "environment":
        full_prompt = f"{BASE_ENV_PROMPT}, {visual_text}, {', '.join(clean_tags)}"
        return full_prompt, NEGATIVE_PROMPT

    # 2. RILEVAMENTO NOMI (Cerca TUTTI i personaggi, non solo il primo)
    found_chars = []
    for name in CHARACTER_PROMPTS.keys():
        if name.lower() in full_text_search:
            found_chars.append(name)

    # Se non trova nessuno ma il soggetto è 'companion', usa la compagna attiva
    if not found_chars and subj == "companion":
        found_chars.append(companion_name)

    # --- LOGICA MULTI-CAST vs SINGOLO ---

    # CASO A: PIÙ PERSONAGGI (Maria + Stella, o Luna + Maria, ecc.)
    if len(found_chars) >= 2:
        # Costruiamo un prompt ibrido
        prompt_parts = []

        # Header qualità (preso dal primo, pulito)
        header = "score_9, score_8_up, masterpiece, NSFW, photorealistic"
        prompt_parts.append(header)

        # Tag di gruppo FONDAMENTALE
        prompt_parts.append(f"{len(found_chars)}girls")

        # Aggiungiamo le descrizioni di ogni personaggio TROVATO
        for name in found_chars:
            char_prompt = CHARACTER_PROMPTS[name]
            # Rimuoviamo "1girl" dai prompt specifici per non confondere l'AI
            clean_char_prompt = char_prompt.replace("1girl,", "").replace("1girl", "").strip()
            prompt_parts.append(clean_char_prompt)

        # Aggiungiamo la descrizione della scena
        prompt_parts.append(visual_text)
        prompt_parts.append(", ".join(clean_tags))

        full_prompt = ", ".join(prompt_parts)

        # Negative prompt rinforzato per evitare gemelli/fusioni
        multi_negative = NEGATIVE_PROMPT + ", identical twins, fused bodies, missing limbs, more than 2 legs per person"
        return full_prompt, multi_negative

    # CASO B: PERSONAGGIO SINGOLO
    elif len(found_chars) == 1:
        target_char = found_chars[0]
        char_prompt = CHARACTER_PROMPTS.get(target_char)
        full_prompt = f"{char_prompt}, {visual_text}, {', '.join(clean_tags)}"
        return full_prompt, NEGATIVE_PROMPT

    # CASO C: NPC GENERICO (Nessun nome trovato)
    if subj == "npc":
        full_prompt = f"{BASE_NPC_PROMPT}, {visual_text}, {', '.join(clean_tags)}"
        return full_prompt, NEGATIVE_PROMPT

    # Fallback finale
    char_prompt = CHARACTER_PROMPTS.get(companion_name, LUNA_PROMPT)
    full_prompt = f"{char_prompt}, {visual_text}, {', '.join(clean_tags)}"
    return full_prompt, NEGATIVE_PROMPT