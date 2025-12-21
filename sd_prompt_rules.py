# file: sd_prompt_rules.py
"""
Regole "keyword -> addon" per Stable Diffusion (AUTOMATIC1111 / --api).

Obiettivo:
- Se nel contesto (chat / tags_en / visual_en) compaiono certe parole, aggiungi automaticamente:
  - LoRA / LyCORIS (in A1111 1.5+ LyCORIS usa la stessa sintassi LoRA: <lora:NAME:W>)
  - Embeddings (Textual Inversion) nel prompt positivo o negativo
  - (Opzionale) trigger testuali extra

Come si usa (minimo indispensabile):
- Nel tuo builder (es. image_prompts.build_image_prompts) chiama:

    from sd_prompt_rules import apply_sd_prompt_rules
    pos, neg, _dbg = apply_sd_prompt_rules(
        positive_prompt=pos,
        negative_prompt=neg,
        tags=tags_en,
        visual=visual_en,
        context=full_text_search,  # oppure recent_dialogue / reply_it / ecc.
        sdxl=False,                # SD 1.5 -> False
    )

Questo file è INTENZIONALMENTE semplice da editare: aggiungi nuove regole nella lista RULES.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import re


# ---------------------------------------------------------------------------
# DATI
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoraAddon:
    """Addon LoRA/LyCORIS (A1111 1.5+)."""
    name: str
    weight: float = 0.7
    category: str = "style"                # per limitare quante ne metti insieme
    keywords: Tuple[str, ...] = ()
    triggers: Tuple[str, ...] = ()         # testo extra (oltre al token <lora:...>)
    sd15_ok: bool = True                  # compatibile con SD 1.5
    sdxl_ok: bool = True                  # compatibile con SDXL 1.0


@dataclass(frozen=True)
class EmbeddingAddon:
    """Textual Inversion: in A1111 è semplicemente una parola/token nel prompt."""
    name: str
    weight: float = 1.0                    # 1.0 = nudo, altrimenti (name:weight)
    where: str = "positive"                # "positive" | "negative"
    keywords: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TextAddon:
    """Aggiunta di testo generico nel prompt."""
    text: str
    where: str = "positive"                # "positive" | "negative"
    keywords: Tuple[str, ...] = ()


# Limiti: quante LoRA aggiungere al massimo come "extra" (oltre a quelle già nel prompt base)
MAX_ADDITIONAL_LORAS = 0

# Limiti per categoria (evita di mettere 3 style lora insieme e far deragliare l'identità)
CATEGORY_LIMITS: Dict[str, int] = {
    "adapter": 1,
    "utility": 1,
    "realism": 1,
    "style": 1,
    "slider": 1,
    "morph": 1,
    "nsfw": 1,
}

# ---------------------------------------------------------------------------
# REGOLE DI DEFAULT (ESEMPI) — PERSONALIZZA QUI
# ---------------------------------------------------------------------------

# NOTE:
# - Keywords: match "contains" (substring), case-insensitive.
# - Aggiungi sinonimi IT/EN: es. ("mani","hands","fingers")
# - LyCORIS: trattalo come LoRA (name = file .safetensors dentro models/Lora)

LORAS: List[LoraAddon] = [
    # Utility: mani
    LoraAddon(
        name="Hand v2",
        weight=0.70,
        category="utility",
        keywords=("hands", "hand", "fingers", "mani", "dita", "palm", "palms"),
        triggers=("hands detail",),
        sdxl_ok=True,
    ),
    # Style: gotico
    LoraAddon(
        name="g0th1c2XLP",
        weight=0.60,
        category="style",
        keywords=("goth", "gothic", "dark", "moody", "gotico", "dark fantasy", "punk", "alt"),
        triggers=("gothic style",),
        sdxl_ok=True,
    ),
    # Realism helper (se hai questa LoRA nel tuo setup)
    LoraAddon(
        name="epiRealismHelper",
        weight=0.40,
        category="realism",
        keywords=("realistic", "photorealistic", "realism", "skin pores", "pores", "realistico", "pelle", "pori"),
        triggers=("realism helper",),
        sdxl_ok=True,
    ),

    # NSFW / creatures (SDXL) — HDAMonsterSexXL (CivitAI 476224)
    # NOTE: il "name" deve combaciare col nome file della LoRA (senza estensione) dentro models/Lora.
    LoraAddon(
        name="HDAMonsterSexXL",
        weight=0.75,
        category="nsfw",
        keywords=(
            "monster", "creature", "nonhuman", "tentacle", "tentacles", "eldritch", "demon", "orc", "beast",
            "mostro", "creatura", "non umano", "tentacoli", "tentacolo", "abominio", "demone", "orco", "bestia",
            "monster girl", "ragazza mostro",
        ),
        triggers=("monster scene",),
        sd15_ok=False,
        sdxl_ok=True,
    ),

    # NSFW / fetish (SDXL) — CivitAI modelVersionId 1148500 (nome file da impostare)
    # Se hai scaricato il modello, rinominalo (o aggiorna 'name' qui) per matchare il file.
    LoraAddon(
        name="CivitAI_1148500",
        weight=0.70,
        category="nsfw",
        keywords=(
            "fetish", "kink", "bdsm", "bondage", "leather", "latex",
            "feticismo", "kink", "bdsm", "bondage", "pelle", "latex",
            "collar", "choker", "harness", "straps", "cuffs",
            "collare", "imbracatura", "cinturini", "manette",
        ),
        triggers=("bondage gear",),
        sd15_ok=False,
        sdxl_ok=True,
    ),

]

EMBEDDINGS: List[EmbeddingAddon] = [
    # Negative embeddings comuni (se li hai in /embeddings)
    EmbeddingAddon(
        name="EasyNegative",
        weight=1.0,
        where="negative",
        keywords=("default", "base", "always", "quality", "qualità", "fix", "cleanup"),
    ),
]

TEXT_RULES: List[TextAddon] = [
    # Anti-flicker / qualità per SD (testo generico)
    TextAddon(
        text="sharp focus, high detail, texture",
        where="positive",
        keywords=("detail", "detailed", "texture", "sharp", "nitidezza", "dettaglio", "dettagli"),
    ),
    TextAddon(
        text="fused fingers, extra digits, bad hands, deformed hands",
        where="negative",
        keywords=("hands", "hand", "fingers", "mani", "dita"),
    ),
]


# ---------------------------------------------------------------------------
# IMPLEMENTAZIONE
# ---------------------------------------------------------------------------

_LORA_RE = re.compile(r"<lora:([^:>]+):([0-9]*\.?[0-9]+)>", re.IGNORECASE)

def _normalize_text(*parts: str) -> str:
    t = " ".join(p for p in parts if p)
    t = t.lower()
    # normalizza separatori comuni per facilitare match substring
    t = t.replace("-", " ").replace("_", " ").replace("/", " ")
    return t

def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    return any(k and k.lower() in text for k in keywords)

def _existing_loras(prompt: str) -> List[str]:
    return [m.group(1).strip() for m in _LORA_RE.finditer(prompt or "")]

def _has_token(prompt: str, token: str) -> bool:
    return token.lower() in (prompt or "").lower()

def _fmt_embedding(name: str, weight: float) -> str:
    if weight is None or abs(weight - 1.0) < 1e-6:
        return name
    return f"({name}:{weight:.2f})"

def _fmt_lora(name: str, weight: float) -> str:
    return f"<lora:{name}:{weight:.2f}>"

def _append_csv(prompt: str, extra: str) -> str:
    extra = (extra or "").strip()
    if not extra:
        return prompt
    if not prompt:
        return extra
    # evita doppie virgole/spazi
    if prompt.rstrip().endswith(","):
        return prompt.rstrip() + " " + extra
    return prompt.rstrip() + ", " + extra

def apply_sd_prompt_rules(
    positive_prompt: str,
    negative_prompt: str,
    *,
    tags: Optional[List[str]] = None,
    visual: str = "",
    context: str = "",
    sdxl: bool = False,
    max_additional_loras: int = MAX_ADDITIONAL_LORAS,
    include_lora_triggers: bool = True,
) -> Tuple[str, str, Dict[str, List[str]]]:

    # --- MODIFICA: BYPASS TOTALE ---
    # Restituisce i prompt esattamente come sono arrivati, senza toccare nulla.
    return positive_prompt, negative_prompt, {}
    # -------------------------------

    """
    Applica regole basate su keyword a prompt SD.

    Ritorna: (positive, negative, debug)
    debug = {"loras":[...], "embeddings":[...], "text":[...]}
    """
    tags = tags or []
    corpus = _normalize_text(context, visual, " ".join(tags))

    debug: Dict[str, List[str]] = {"loras": [], "embeddings": [], "text": []}

    # --- 1) Text rules ---
    for rule in TEXT_RULES:
        if not rule.keywords:
            continue
        if not _contains_any(corpus, rule.keywords):
            continue
        if rule.where == "negative":
            if not _has_token(negative_prompt, rule.text):
                negative_prompt = _append_csv(negative_prompt, rule.text)
                debug["text"].append(f"NEG:{rule.text}")
        else:
            if not _has_token(positive_prompt, rule.text):
                positive_prompt = _append_csv(positive_prompt, rule.text)
                debug["text"].append(f"POS:{rule.text}")

    # --- 2) Embeddings ---
    for emb in EMBEDDINGS:
        if not emb.keywords:
            continue
        if not _contains_any(corpus, emb.keywords):
            continue

        token = _fmt_embedding(emb.name, emb.weight)
        if emb.where == "negative":
            if not _has_token(negative_prompt, emb.name):
                negative_prompt = _append_csv(negative_prompt, token)
                debug["embeddings"].append(f"NEG:{token}")
        else:
            if not _has_token(positive_prompt, emb.name):
                positive_prompt = _append_csv(positive_prompt, token)
                debug["embeddings"].append(f"POS:{token}")

    # --- 3) LoRA / LyCORIS ---
    existing = set(n.lower() for n in _existing_loras(positive_prompt))
    picked: List[LoraAddon] = []

    used_per_cat: Dict[str, int] = {k: 0 for k in CATEGORY_LIMITS}
    added = 0

    # ordina per "quanto matcha" (più keyword trovate -> più su)
    def score(e: LoraAddon) -> int:
        return sum(1 for k in e.keywords if k and k.lower() in corpus)

    candidates = sorted(
        (e for e in LORAS if (e.sdxl_ok if sdxl else e.sd15_ok)),
        key=lambda e: (score(e), e.weight),
        reverse=True,
    )

    for e in candidates:
        if added >= max_additional_loras:
            break
        if score(e) <= 0:
            continue
        if e.name.lower() in existing:
            continue

        cap = CATEGORY_LIMITS.get(e.category, 1)
        if used_per_cat.get(e.category, 0) >= cap:
            continue

        picked.append(e)
        used_per_cat[e.category] = used_per_cat.get(e.category, 0) + 1
        existing.add(e.name.lower())
        added += 1

    for e in picked:
        token = _fmt_lora(e.name, e.weight)
        positive_prompt = _append_csv(positive_prompt, token)
        debug["loras"].append(token)

        if include_lora_triggers and e.triggers:
            # aggiunge SOLO il primo trigger per non appesantire troppo
            trig = e.triggers[0]
            if trig and not _has_token(positive_prompt, trig):
                positive_prompt = _append_csv(positive_prompt, trig)
                debug["loras"].append(f"TRIG:{trig}")

    return positive_prompt, negative_prompt, debug


# Alias più breve (se ti piace)
apply_rules = apply_sd_prompt_rules


if __name__ == "__main__":
    # Demo rapido
    tags_demo = ["dark fantasy", "hands visible", "high detail"]
    vis_demo = "close-up portrait, detailed skin pores"
    pos = "masterpiece, 1girl"
    neg = "low quality, bad anatomy"

    p2, n2, dbg = apply_sd_prompt_rules(pos, neg, tags=tags_demo, visual=vis_demo, context="gotico mani", sdxl=False)
    print("POS:", p2)
    print("NEG:", n2)
    print("DBG:", dbg)
