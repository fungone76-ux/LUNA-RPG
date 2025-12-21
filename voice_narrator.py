"""
voice_narrator.py
Versione Anti-Blocco: Usa nomi di file univoci per evitare errori [Errno 13].
"""

import threading
import time
import os
import re
import tempfile
import uuid  # Importante per nomi file univoci
from typing import Optional

# Import Google Cloud TTS
try:
    from google.cloud import texttospeech
except ImportError:
    raise ImportError("Installa la libreria con: pip install google-cloud-texttospeech")

# Import Pygame
try:
    import pygame
except Exception as e:
    raise ImportError("pygame is required. Install with: pip install pygame") from e

# --- CONFIGURAZIONE ---
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_credentials.json"

# Puoi cambiare qui la voce (es. "it-IT-Neural2-C" per maschile)
GOOGLE_VOICE_NAME = "it-IT-Neural2-C"

# Stato interno
_audio_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_is_initialized = False
_init_lock = threading.Lock()

def _sanitize_text_for_tts(text: str) -> str:
    if not text: return ""
    s = str(text).strip()
    s = s.replace("*", "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[\[\(][^\]\)]+[\]\)]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _generate_file_google(text: str, out_path: str):
    """Genera audio e lo salva in un percorso specifico."""
    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="it-IT",
            name=GOOGLE_VOICE_NAME
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        with open(out_path, "wb") as out:
            out.write(response.audio_content)

    except Exception as e:
        print(f"[GOOGLE TTS] ❌ Errore API: {e}")
        raise e

def _playback_worker(text: str):
    """Genera un file UNIVOCO, lo suona e poi lo cancella."""
    temp_path = None
    try:
        clean_text = _sanitize_text_for_tts(text)
        if not clean_text:
            return

        # 1. Crea un percorso file UNIVOCO (mai usato prima)
        unique_name = f"voice_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(tempfile.gettempdir(), unique_name)

        # 2. Generazione
        try:
            _generate_file_google(clean_text, temp_path)
        except Exception:
            return

        # 3. Riproduzione
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            try:
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()

                # Attesa
                while pygame.mixer.music.get_busy() and not _stop_event.is_set():
                    pygame.time.Clock().tick(20)

                if _stop_event.is_set():
                    pygame.mixer.music.stop()

                # Importante: scarica il file da pygame per poterlo cancellare
                try:
                    pygame.mixer.music.unload()
                except AttributeError:
                    # Versioni vecchie di pygame non hanno unload, fa nulla
                    pass

            except Exception as e:
                print(f"[AUDIO] Errore riproduzione: {e}")

    except Exception as e:
        print(f"[AUDIO] Errore worker: {e}")

    finally:
        # 4. PULIZIA: Cancella il file temporaneo alla fine
        if temp_path and os.path.exists(temp_path):
            try:
                # Attendiamo un attimo che Windows rilasci il file
                time.sleep(0.1)
                os.remove(temp_path)
            except Exception:
                # Se non riesce a cancellarlo ora, pazienza, è nella cartella temp
                pass

def init_narrator():
    global _is_initialized
    with _init_lock:
        if _is_initialized: return
        try:
            pygame.mixer.init()
            _is_initialized = True
            print("[AUDIO] Narrator Google inizializzato.")
        except Exception as e:
            print(f"[AUDIO] Errore init pygame: {e}")

def speak(text: str):
    global _audio_thread
    if not text: return

    if not _is_initialized:
        init_narrator()

    stop()
    _stop_event.clear()

    _audio_thread = threading.Thread(target=_playback_worker, args=(text,), daemon=True)
    _audio_thread.start()

def speak_script(script_list):
    full_text = " ".join([item.get("text", "") for item in script_list])
    speak(full_text)

def stop():
    _stop_event.set()
    try:
        time.sleep(0.05)
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
    except Exception:
        pass

def shutdown_narrator():
    stop()
    try:
        pygame.mixer.quit()
    except Exception:
        pass