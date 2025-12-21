# file: llm_client.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# -------------------- CONFIGURAZIONE --------------------

load_dotenv()

# Modello: lascia come nel tuo progetto (puoi cambiarlo a piacere)
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3-pro-preview")

client: Optional[genai.Client] = None
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("La variabile d'ambiente GEMINI_API_KEY non è impostata.")
    client = genai.Client(api_key=api_key)
    print(f"[LLM] Client inizializzato con modello: {MODEL_NAME}")
except Exception as e:
    print(f"[LLM] ERRORE CRITICO: Impossibile inizializzare il client. {e}")
    client = None


def call_llm(system_prompt: str, user_input_json: str, **kwargs: Any) -> Dict[str, Any]:
    if not client:
        return {"content": None, "error": "Client API non disponibile."}

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[user_input_json],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=system_prompt,
                temperature=float(kwargs.get("temperature", 0.9)),
                top_p=float(kwargs.get("top_p", 0.95)),
                top_k=int(kwargs.get("top_k", 40)),
                # Note: leaving your permissive safety settings as-is.
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            ),
        )

        text = getattr(response, "text", None)
        if not text:
            return {"content": None, "error": "Risposta vuota dal modello."}

        return {"content": text, "error": None}

    except Exception as e:
        error_msg = f"Errore durante la generazione: {e}"
        print(f"[LLM] {error_msg}")
        return {"content": None, "error": error_msg}
