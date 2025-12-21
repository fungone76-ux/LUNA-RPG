import json
import uuid
import urllib.request
import requests
import websocket
import os
import random
import shutil
import time
import glob
import hashlib
from typing import Any, Dict, Optional, List, Tuple

from dotenv import load_dotenv
from google import genai

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

load_dotenv()

COMFY_SERVER = os.getenv("COMFY_SERVER", "127.0.0.1:8188")
COMFY_OUTPUT_PATH = os.getenv("COMFY_OUTPUT_PATH")
WORKFLOW_API_JSON = os.getenv("WORKFLOW_API_JSON", "workflow_api.json")

CLIENT_ID = str(uuid.uuid4())

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("⚠️ ATTENZIONE: Chiave GEMINI_API_KEY mancante nel file .env")
    client = None
else:
    client = genai.Client(api_key=API_KEY)

# Gemini (video prompt) settings
GEMINI_VIDEO_MODEL = os.getenv("GEMINI_VIDEO_MODEL", "gemini-2.5-pro").strip()
WAN_GEMINI_DEBUG = os.getenv("WAN_GEMINI_DEBUG", "0").strip().lower() in ("1", "true", "yes", "on")

# Preset di default (ottimizzati per RTX 3060 Ti 8GB)
DEFAULT_I2V_SECONDS = float(os.getenv("WAN_I2V_SECONDS", "8"))
DEFAULT_I2V_WIDTH = int(os.getenv("WAN_I2V_WIDTH", "960"))
DEFAULT_I2V_HEIGHT = int(os.getenv("WAN_I2V_HEIGHT", "540"))
DEFAULT_I2V_OUTPUT_FPS = int(os.getenv("WAN_I2V_OUTPUT_FPS", "12"))
DEFAULT_I2V_STEPS = int(os.getenv("WAN_I2V_STEPS", "24"))
DEFAULT_I2V_CFG = float(os.getenv("WAN_I2V_CFG", "5"))
DEFAULT_I2V_SEED_MODE = os.getenv("WAN_I2V_SEED_MODE", "deterministic").strip().lower()  # deterministic|random

# RIFE: settaggi "3060 Ti friendly"
DEFAULT_RIFE_SCALE = float(os.getenv("WAN_I2V_RIFE_SCALE", "1"))
DEFAULT_RIFE_CLEAR_CACHE = int(os.getenv("WAN_I2V_RIFE_CLEAR_CACHE", "12"))
DEFAULT_RIFE_ENSEMBLE = os.getenv("WAN_I2V_RIFE_ENSEMBLE", "0").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# PROMPT ENGINE (Gemini)
# ---------------------------------------------------------------------------

def _extract_text_from_gemini_response(response: Any) -> str:
    """Estrae testo in modo robusto anche quando response.text è None."""
    if response is None:
        return ""
    # 1) Prova response.text
    try:
        t = getattr(response, "text", None)
        if isinstance(t, str) and t.strip():
            return t.strip()
    except Exception:
        pass

    # 2) Prova candidates[0].content.parts[].text
    try:
        candidates = getattr(response, "candidates", None)
        if candidates:
            cand0 = candidates[0]
            content = getattr(cand0, "content", None)
            parts = getattr(content, "parts", None) if content is not None else None
            if parts:
                pieces = []
                for p in parts:
                    pt = getattr(p, "text", None)
                    if isinstance(pt, str) and pt.strip():
                        pieces.append(pt.strip())
                if pieces:
                    return " ".join(pieces).strip()
    except Exception:
        pass

    # 3) Altri fallback "best effort"
    try:
        # Alcune versioni espongono output_text o simili
        for attr in ("output_text", "content", "result"):
            t = getattr(response, attr, None)
            if isinstance(t, str) and t.strip():
                return t.strip()
    except Exception:
        pass

    return ""


def get_gemini_prompt(context_description: str) -> str:
    """Ottimizza il prompt per Wan 2.2 I2V.

    Nota: prompt semplici e continui (movimenti piccoli) producono video più coerenti.
    Se Gemini non ritorna testo (response.text=None), usiamo un fallback SENZA sporcare la console.
    """
    fallback = "subject. subtle continuous motion. locked camera. cinematic, natural motion."

    if not client:
        return fallback

    print(f"🧠 [Gemini] Creo prompt Wan 2.2 per: '{context_description}'...")

    sys_instruction = """
    You are an AI Video Prompt Engineer for Wan 2.2 I2V.
    OUTPUT MUST BE 100% ENGLISH.
    Format: "Subject. Action (continuous). Camera (stable). Atmosphere."
    Rules:
    - Prefer subtle, continuous motion (breathing, small head turn, gentle hand movement).  <-- IL COLPEVOLE
    - Avoid scene cuts, outfit changes, lighting changes, and fast camera shake.
    - Keep identity consistent.
    NO Markdown.
    """

    try:
        response = client.models.generate_content(
            model=GEMINI_VIDEO_MODEL or "gemini-2.5-pro",
            contents=context_description,
            config=genai.types.GenerateContentConfig(
                system_instruction=sys_instruction,
                temperature=0.4,
                max_output_tokens=80,
            ),
        )

        clean_prompt = _extract_text_from_gemini_response(response)
        clean_prompt = clean_prompt.replace("\n", " ").strip()
        clean_prompt = " ".join(clean_prompt.split())

        if clean_prompt:
            print(f"✨ [Gemini] Prompt: {clean_prompt}")
            return clean_prompt

        # Se è vuoto, non è un "errore" bloccante: andiamo di fallback.
        if WAN_GEMINI_DEBUG:
            print("⚠️ [Gemini] Risposta senza testo (response.text=None). Uso fallback.")
        return fallback

    except Exception as e:
        # Non sporcare la console se non richiesto
        if WAN_GEMINI_DEBUG:
            print(f"⚠️ [Gemini] Errore: {e}. Uso fallback.")
        return fallback


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _round_to_multiple(x: int, m: int) -> int:
    if m <= 1:
        return int(x)
    return int(max(m, round(x / m) * m))


def _deterministic_seed(image_path: str, prompt: str) -> int:
    """Seed deterministico: stesso input -> stesso video (utile per coerenza)."""
    h = hashlib.sha256()
    try:
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except Exception:
        # fallback: path + mtime
        h.update(image_path.encode("utf-8", "ignore"))
        try:
            h.update(str(os.path.getmtime(image_path)).encode("utf-8"))
        except Exception:
            pass
    h.update(prompt.encode("utf-8", "ignore"))
    # ComfyUI seed: grande intero positivo
    return int(h.hexdigest()[:14], 16)  # ~56 bit


def _get_node_ids_by_class(workflow: Dict[str, Any], class_type: str) -> List[str]:
    return [nid for nid, node in workflow.items() if isinstance(node, dict) and node.get("class_type") == class_type]


def _apply_i2v_overrides(
    workflow: Dict[str, Any],
    uploaded_image_name: str,
    ai_prompt: str,
    *,
    seed: int,
    width: int,
    height: int,
    seconds: float,
    steps: int,
    cfg: float,
    output_fps: int,
    rife_scale_factor: float,
    rife_clear_cache_after_n_frames: int,
    rife_ensemble: bool,
) -> Tuple[bool, bool]:
    """Inietta immagine/prompt e applica override runtime ai nodi chiave."""
    image_injected = False
    prompt_injected = False

    # Scopri multiplier RIFE, se presente (serve per calcolare i frame "base")
    rife_multiplier = 1
    rife_ids = _get_node_ids_by_class(workflow, "RIFE VFI")
    if rife_ids:
        rife_node = workflow.get(rife_ids[0], {})
        inputs = rife_node.setdefault("inputs", {})
        try:
            rife_multiplier = int(inputs.get("multiplier", 1)) or 1
        except Exception:
            rife_multiplier = 1

    # Calcola frame base per la durata richiesta.
    # Esempio: output_fps=24, multiplier=2 -> frame base = seconds * 12
    base_fps = max(1, int(round(output_fps / max(1, rife_multiplier))))
    length_frames = max(16, int(round(seconds * base_fps)))

    for _node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue

        ctype = node.get("class_type")
        inputs = node.setdefault("inputs", {})

        # Immagine di partenza
        if ctype == "LoadImage":
            # ComfyUI vuole il nome file caricato
            if "image" in inputs:
                inputs["image"] = uploaded_image_name
                image_injected = True

        # Prompt (placeholder)
        if ctype == "CLIPTextEncode":
            text_val = str(inputs.get("text", ""))
            if "__PROMPT_GEMINI__" in text_val:
                inputs["text"] = ai_prompt
                prompt_injected = True

        # Resize immagine (prima del latent)
        if ctype == "ImageResize+":
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height

        # Wan I2V latent
        if ctype == "Wan22ImageToVideoLatent":
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height
            if "length" in inputs:
                # Lunghezza in frame "base" (prima di RIFE)
                inputs["length"] = length_frames

        # Sampler (seed + steps/cfg)
        if ctype in ("KSampler", "KSamplerAdvanced", "Wan22Sampler"):
            if "noise_seed" in inputs:
                inputs["noise_seed"] = int(seed)
            elif "seed" in inputs:
                inputs["seed"] = int(seed)

            if "steps" in inputs:
                inputs["steps"] = int(steps)
            if "cfg" in inputs:
                inputs["cfg"] = float(cfg)

        # RIFE (fluidità) - scala ridotta per VRAM + ensemble disattivabile
        if ctype == "RIFE VFI":
            if "scale_factor" in inputs:
                inputs["scale_factor"] = float(rife_scale_factor)
            if "clear_cache_after_n_frames" in inputs:
                inputs["clear_cache_after_n_frames"] = int(rife_clear_cache_after_n_frames)

            # Alcuni nodi chiamano questo flag "ensemble"
            if "ensemble" in inputs:
                inputs["ensemble"] = bool(rife_ensemble)
            # Altri lo chiamano "use_ensemble"
            if "use_ensemble" in inputs:
                inputs["use_ensemble"] = bool(rife_ensemble)

        # Export FPS (coerente con la durata desiderata)
        if ctype == "CreateVideo":
            if "fps" in inputs:
                inputs["fps"] = int(output_fps)

    return image_injected, prompt_injected


# ---------------------------------------------------------------------------
# COMFYUI I/O
# ---------------------------------------------------------------------------

def upload_image(image_path: str) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Immagine non trovata: {image_path}")

    with open(image_path, "rb") as file:
        files = {"image": file}
        data = {"overwrite": "true"}

        print(f"📤 [ComfyUI] Upload immagine: {os.path.basename(image_path)}...")
        response = requests.post(f"http://{COMFY_SERVER}/upload/image", files=files, data=data, timeout=60)

    if response.status_code == 200:
        return response.json().get("name")
    raise Exception(f"Errore Upload: {response.text}")


def queue_workflow(workflow_json: Dict[str, Any]) -> Dict[str, Any]:
    p = {"prompt": workflow_json, "client_id": CLIENT_ID}
    data = json.dumps(p).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_SERVER}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def _comfy_history(prompt_id: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(f"http://{COMFY_SERVER}/history/{prompt_id}", timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _download_from_view(filename: str, subfolder: str, file_type: str, dst_path: str) -> bool:
    try:
        url = f"http://{COMFY_SERVER}/view"
        params = {"filename": filename, "subfolder": subfolder, "type": file_type}
        r = requests.get(url, params=params, stream=True, timeout=120)
        if r.status_code != 200:
            return False

        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        return True
    except Exception:
        return False


def _download_first_media_from_history(history: Dict[str, Any], output_filename: str) -> Optional[str]:
    """Scarica il primo media utile dalla history (preferendo mp4/mkv/gif)."""
    try:
        # history: {prompt_id: {outputs: {...}}}
        if not history or not isinstance(history, dict):
            return None

        # Prendi la prima entry (di solito unica)
        entry = next(iter(history.values()))
        outputs = entry.get("outputs") if isinstance(entry, dict) else None
        if not isinstance(outputs, dict):
            return None

        candidates: List[Dict[str, str]] = []

        for _node_id, out in outputs.items():
            if not isinstance(out, dict):
                continue
            for key in ("videos", "gifs", "images"):
                items = out.get(key)
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict) and it.get("filename"):
                            candidates.append({
                                "filename": str(it.get("filename")),
                                "subfolder": str(it.get("subfolder") or ""),
                                "type": str(it.get("type") or "output"),
                            })

        if not candidates:
            return None

        def score(c: Dict[str, str]) -> int:
            fn = (c.get("filename") or "").lower()
            if fn.endswith(".mp4"):
                return 300
            if fn.endswith(".mkv"):
                return 250
            if fn.endswith(".gif"):
                return 200
            return 100

        candidates.sort(key=score, reverse=True)
        best = candidates[0]

        ok = _download_from_view(
            filename=best["filename"],
            subfolder=best["subfolder"],
            file_type=best["type"],
            dst_path=output_filename,
        )
        if ok:
            print(f"💾 [ComfyUI] Media scaricato via /view: {output_filename}")
            return output_filename

        return None
    except Exception:
        return None


def get_latest_video_file(root_folder: str) -> Optional[str]:
    """Fallback: prende l'ultimo file recente (entro 3 minuti) dalla cartella output."""
    search_patterns = [
        os.path.join(root_folder, "**", "*.mp4"),
        os.path.join(root_folder, "**", "*.gif"),
        os.path.join(root_folder, "**", "*.mkv"),
    ]

    all_files: List[str] = []
    for pattern in search_patterns:
        all_files.extend(glob.glob(pattern, recursive=True))

    if not all_files:
        return None

    latest_file = max(all_files, key=os.path.getmtime)

    last_mod_time = os.path.getmtime(latest_file)
    if time.time() - last_mod_time > 180:
        print(f"⚠️ Trovato '{os.path.basename(latest_file)}' ma è troppo vecchio (>3 min).")
        return None

    print(f"✅ TROVATO ULTIMO FILE: {latest_file}")
    return latest_file


def track_and_download(ws: websocket.WebSocket, prompt_id: str, output_filename: str) -> Optional[str]:
    print("⏳ [ComfyUI] Rendering Wan 2.2 in corso... (Attendi)")

    # 1) ATTESA ESECUZIONE
    while True:
        msg = ws.recv()
        if isinstance(msg, (bytes, bytearray)):
            continue
        data = json.loads(msg)
        if data.get("type") == "executing":
            exec_data = data.get("data", {})
            if exec_data.get("node") is None and exec_data.get("prompt_id") == prompt_id:
                print("✅ [ComfyUI] Rendering completato!")
                break

    # 2) Scarica da /history + /view (robusto)
    history = _comfy_history(prompt_id)
    if history:
        downloaded = _download_first_media_from_history(history, output_filename)
        if downloaded:
            return downloaded
        print("⚠️ [ComfyUI] History disponibile ma non ho trovato un media scaricabile. Uso fallback.")

    # 3) FALLBACK: PRENDI L'ULTIMO FILE DA OUTPUT FOLDER
    time.sleep(1.0)

    if COMFY_OUTPUT_PATH and os.path.exists(COMFY_OUTPUT_PATH):
        source_path = get_latest_video_file(COMFY_OUTPUT_PATH)

        if source_path and os.path.exists(source_path):
            try:
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                shutil.copy2(source_path, output_filename)
                print(f"💾 Video copiato con successo in: {output_filename}")
                return output_filename
            except Exception as e:
                print(f"❌ Errore copia file: {e}")
        else:
            print(f"❌ ERRORE: Non ho trovato nessun video recente in {COMFY_OUTPUT_PATH}")
            return None
    else:
        print(f"❌ ERRORE: Percorso output non valido nel file .env: {COMFY_OUTPUT_PATH}")
        return None


# ---------------------------------------------------------------------------
# API PRINCIPALE
# ---------------------------------------------------------------------------

def generate_video_from_image(
    image_path: str,
    text_context: str,
    output_path: str = "storage/videos/output.mp4",
    *,
    seconds: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    output_fps: Optional[int] = None,
    seed: Optional[int] = None,
    seed_mode: Optional[str] = None,
    rife_scale_factor: Optional[float] = None,
    rife_clear_cache_after_n_frames: Optional[int] = None,
    rife_ensemble: Optional[bool] = None,
) -> Optional[str]:
    """Genera un video Wan 2.2 I2V da un'immagine.

    Default ottimizzati per RTX 3060 Ti (8GB) via variabili .env:
    - WAN_I2V_SECONDS (default 8)
    - WAN_I2V_WIDTH/WAN_I2V_HEIGHT (default 960x540)
    - WAN_I2V_STEPS/WAN_I2V_CFG (default 20 / 5)
    - WAN_I2V_OUTPUT_FPS (default 24)
    - WAN_I2V_SEED_MODE (deterministic|random)
    - WAN_I2V_RIFE_SCALE (default 0.5)
    - WAN_I2V_RIFE_CLEAR_CACHE (default 12)
    - WAN_I2V_RIFE_ENSEMBLE (default 0; 1 per riattivarlo)
    """
    # 1) Carica Workflow
    try:
        with open(WORKFLOW_API_JSON, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        print(f"❌ ERRORE: Manca '{WORKFLOW_API_JSON}'.")
        return None
    except Exception as e:
        print(f"❌ ERRORE lettura workflow: {e}")
        return None

    # 2) Upload immagine e prompt
    try:
        uploaded_image = upload_image(image_path)
    except Exception as e:
        print(f"❌ Errore upload immagine: {e}")
        return None

    ai_prompt = get_gemini_prompt(text_context)

    # 3) Risoluzione parametri (env -> default)
    eff_seconds = float(seconds) if seconds is not None else DEFAULT_I2V_SECONDS

    eff_width = int(width) if width is not None else DEFAULT_I2V_WIDTH
    eff_height = int(height) if height is not None else DEFAULT_I2V_HEIGHT

    # Wan spesso preferisce multipli di 64 (o almeno 8/16). Qui arrotondiamo a 64 per stabilità.
    eff_width = _round_to_multiple(eff_width, 64)
    eff_height = _round_to_multiple(eff_height, 64)

    eff_steps = int(steps) if steps is not None else DEFAULT_I2V_STEPS
    eff_cfg = float(cfg) if cfg is not None else DEFAULT_I2V_CFG
    eff_output_fps = int(output_fps) if output_fps is not None else DEFAULT_I2V_OUTPUT_FPS

    eff_rife_scale = float(rife_scale_factor) if rife_scale_factor is not None else DEFAULT_RIFE_SCALE
    eff_rife_clear = int(rife_clear_cache_after_n_frames) if rife_clear_cache_after_n_frames is not None else DEFAULT_RIFE_CLEAR_CACHE
    eff_rife_ensemble = bool(rife_ensemble) if rife_ensemble is not None else DEFAULT_RIFE_ENSEMBLE

    eff_seed_mode = (seed_mode or DEFAULT_I2V_SEED_MODE).strip().lower()

    if seed is not None:
        eff_seed = int(seed)
    else:
        if eff_seed_mode == "random":
            eff_seed = random.randint(1, 10**14)
        else:
            eff_seed = _deterministic_seed(image_path, ai_prompt)

    print(
        f"🎛️ [Wan I2V] {eff_width}x{eff_height}, {eff_seconds:.2f}s, fps={eff_output_fps}, "
        f"steps={eff_steps}, cfg={eff_cfg}, seed_mode={eff_seed_mode}, seed={eff_seed}, "
        f"rife_scale={eff_rife_scale}, rife_ensemble={eff_rife_ensemble}"
    )

    # 4) Iniezione e override nodi
    image_injected, prompt_injected = _apply_i2v_overrides(
        workflow,
        uploaded_image,
        ai_prompt,
        seed=eff_seed,
        width=eff_width,
        height=eff_height,
        seconds=eff_seconds,
        steps=eff_steps,
        cfg=eff_cfg,
        output_fps=eff_output_fps,
        rife_scale_factor=eff_rife_scale,
        rife_clear_cache_after_n_frames=eff_rife_clear,
        rife_ensemble=eff_rife_ensemble,
    )

    if not image_injected:
        print("⚠️ Warning: Nodo LoadImage non trovato (immagine non iniettata).")
    if not prompt_injected:
        print("⚠️ Warning: Placeholder '__PROMPT_GEMINI__' non trovato nei CLIPTextEncode (prompt non iniettato).")

    # 5) Esecuzione
    ws = websocket.WebSocket()
    try:
        ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={CLIENT_ID}")
        response = queue_workflow(workflow)
        prompt_id = response.get("prompt_id", "")
        if not prompt_id:
            print(f"❌ ERRORE: risposta /prompt senza prompt_id: {response}")
            return None
        final_file = track_and_download(ws, prompt_id, output_path)
        return final_file
    except Exception as e:
        print(f"❌ Errore connessione WebSocket o esecuzione: {e}")
        return None
    finally:
        try:
            if ws.connected:
                ws.close()
        except Exception:
            pass
