import json
import os
import shutil
import time
import uuid
from urllib.parse import urlparse

import requests
import websocket
from dotenv import load_dotenv
from google import genai

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_RAW_COMFY = (os.getenv("COMFY_SERVER", "http://127.0.0.1:8188") or "").strip().rstrip("/")
COMFY_URL = _RAW_COMFY if _RAW_COMFY.startswith(("http://", "https://")) else f"http://{_RAW_COMFY}"
COMFY_WS_URL = COMFY_URL.replace("https://", "wss://").replace("http://", "ws://")

CLIENT_ID = str(uuid.uuid4())

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None

# Se stai girando *sul PC* e Comfy è *nel pod*, questa path non esiste.
# La teniamo comunque: se un domani monti la cartella output del pod sul PC, tornerà utile.
COMFY_OUTPUT_PATH = (os.getenv("COMFY_OUTPUT_PATH", "") or "").strip()


# ---------------------------------------------------------------------------
# Gemini (IT -> EN + prompt engineer)
# ---------------------------------------------------------------------------

def get_gemini_prompt(prompt_it: str) -> str:
    """IT -> EN + prompt engineering per I2V (LongCat/Wan)."""
    prompt_it = (prompt_it or "").strip()
    if not prompt_it:
        return "cinematic realism, subtle natural motion, stable identity, smooth camera movement"

    if not client:
        return prompt_it

    print(f"🧠 [Gemini] Prompt engineer I2V (da IT): '{prompt_it}'")

    sys_instruction = """
You are an elite AI video prompt engineer specialized in image-to-video (I2V) models (Wan/LongCat style).
Task:
1) Translate the user prompt from Italian to English.
2) Upgrade it into a production-grade I2V prompt that preserves the original intent and is optimized for temporal coherence.

Rules (must follow):
- Preserve the scene content and meaning; you may add cinematic details ONLY if consistent (camera, lighting, mood, motion).
- Assume I2V: the input image is the reference. Preserve identity, face, clothing, composition. Avoid drift.
- Add clear, natural motion cues (what moves, how fast, how the camera moves). Prefer subtle realistic motion.
- Avoid contradictions (no sudden outfit changes, no teleporting, no time jumps).
- Do NOT include technical parameters (no fps, steps, resolution, sampler, seed, model names).
- Output ONLY the final English positive prompt (single paragraph). No quotes, no markdown, no extra text.

Quality hints to include naturally:
- cinematic realism, stable details, sharp focus where needed
- smooth camera movement, consistent lighting, minimal flicker
- realistic physics for fabric/hair, subtle micro-movements (breathing/blinking) when appropriate
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Italian prompt:\n{prompt_it}",
            config={"system_instruction": sys_instruction, "temperature": 0.35},
        )
        out = (response.text or "").strip()
        out = " ".join(out.split())
        print(f"✨ [Gemini] Prompt EN (engineered): {out}")
        return out if out else prompt_it
    except Exception as e:
        print(f"⚠️ Errore Gemini: {e}. Uso prompt originale.")
        return prompt_it


# ---------------------------------------------------------------------------
# ComfyUI API helpers
# ---------------------------------------------------------------------------

def _url(path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"{COMFY_URL}{path}"


def upload_image(image_path: str, overwrite: bool = True) -> str:
    """
    Upload immagine in ComfyUI (/upload/image) e ritorna il nome file da usare nel nodo LoadImage.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)

    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f)}
        data = {"overwrite": "true" if overwrite else "false"}
        r = requests.post(_url("/upload/image"), files=files, data=data, timeout=120)
        r.raise_for_status()
        j = r.json()

    # Risposte viste in giro: {"name": "...", "subfolder": "", "type":"input"} oppure {"filename": "..."}
    name = j.get("name") or j.get("filename") or j.get("file") or j.get("data", {}).get("name")
    sub = j.get("subfolder") or ""
    if not name:
        raise RuntimeError(f"Upload riuscito ma risposta non contiene nome file: {j}")

    return f"{sub}/{name}" if sub else name


def queue_workflow(workflow: dict) -> dict:
    """
    Enqueue workflow su ComfyUI (/prompt).
    Ritorna dict con prompt_id.
    """
    payload = {"prompt": workflow, "client_id": CLIENT_ID}
    r = requests.post(_url("/prompt"), json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def _get_history_item(prompt_id: str) -> dict:
    r = requests.get(_url(f"/history/{prompt_id}"), timeout=60)
    r.raise_for_status()
    data = r.json()
    # spesso è {prompt_id: {...}}
    if isinstance(data, dict) and prompt_id in data:
        return data[prompt_id]
    return data


def _download_comfy_file(filename: str, subfolder: str, file_type: str, dest_path: str) -> str:
    """
    Scarica un file da ComfyUI (/view) e lo salva localmente.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # preserva l'estensione reale
    base, _ = os.path.splitext(dest_path)
    ext = os.path.splitext(filename)[1]
    if ext:
        dest_path = base + ext

    params = {"filename": filename, "type": file_type}
    if subfolder:
        params["subfolder"] = subfolder

    with requests.get(_url("/view"), params=params, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    return dest_path


def get_latest_video_file(folder: str, max_age_seconds: int = 300) -> str | None:
    """
    Cerca il file video più recente in una cartella locale (utile solo se COMFY_OUTPUT_PATH è montata sul PC).
    """
    if not folder or not os.path.exists(folder):
        return None

    now = time.time()
    video_ext = (".mp4", ".webm", ".mov", ".mkv", ".gif")

    candidates = []
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith(video_ext):
                p = os.path.join(root, fn)
                try:
                    m = os.path.getmtime(p)
                except OSError:
                    continue
                if (now - m) <= max_age_seconds:
                    candidates.append((m, p))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def track_and_download(ws: websocket.WebSocket, prompt_id: str, output_filename: str) -> str | None:
    """
    Attende fine job su WS e poi:
    - se COMFY_OUTPUT_PATH esiste localmente: copia il file più recente
    - altrimenti (PC -> Pod remoto): scarica l'output del prompt_id via /history + /view
    """
    print("⏳ [ComfyUI] Rendering in corso...")

    # 1) Attesa completamento (evento 'executing' con node=None)
    while True:
        try:
            raw = ws.recv()
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            message = json.loads(raw)

            if message.get("type") == "executing":
                data = message.get("data", {})
                if data.get("prompt_id") == prompt_id and data.get("node") is None:
                    print("✅ [ComfyUI] Esecuzione finita!")
                    break
        except Exception:
            # se cade il WS, proviamo comunque a recuperare via history
            break

    time.sleep(2)

    # 2) Modalità "più recente" da filesystem (SOLO se la cartella è visibile dal PC)
    if COMFY_OUTPUT_PATH and os.path.exists(COMFY_OUTPUT_PATH):
        source_path = get_latest_video_file(COMFY_OUTPUT_PATH)
        if source_path and os.path.exists(source_path):
            try:
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                # Manteniamo estensione dell'output locale così com'è (output_filename)
                shutil.copy2(source_path, output_filename)
                print(f"💾 Video copiato con successo in: {output_filename}")
                return output_filename
            except Exception as e:
                print(f"❌ Errore copia file: {e}")
                return None

        print(f"❌ Nessun video recente trovato in {COMFY_OUTPUT_PATH}")
        return None

    # 3) PC -> Pod remoto: scarica il file prodotto da quel prompt_id (affidabile)
    try:
        hist = _get_history_item(prompt_id)
        outputs = (hist or {}).get("outputs", {})

        # raccogli candidati video/gif
        candidates = []
        for _node_id, out in outputs.items():
            for key in ("videos", "gifs"):
                items = out.get(key)
                if isinstance(items, list):
                    for it in items:
                        fn = it.get("filename")
                        if fn:
                            candidates.append((fn, it.get("subfolder", ""), it.get("type", "output")))

        if not candidates:
            print("❌ Nessun output video trovato in /history per questo prompt_id.")
            return None

        # scegli il migliore: preferisci mp4 > webm > gif > altro
        def score(fn: str) -> int:
            fn = fn.lower()
            if fn.endswith(".mp4"):
                return 0
            if fn.endswith(".webm"):
                return 1
            if fn.endswith(".mov"):
                return 2
            if fn.endswith(".mkv"):
                return 3
            if fn.endswith(".gif"):
                return 4
            return 9

        candidates.sort(key=lambda t: score(t[0]))
        fn, sub, typ = candidates[0]
        saved = _download_comfy_file(fn, sub, typ, output_filename)
        print(f"💾 Video scaricato con successo in: {saved}")
        return saved

    except Exception as e:
        print(f"❌ Errore download via API: {e}")
        return None


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def generate_video_from_image(image_path: str, text_context: str, output_path: str = "storage/videos/output.mp4") -> str | None:
    """
    Genera un video da un'immagine usando il workflow LongCat i2v.
    Non cambia parametri del workflow: sostituisce SOLO immagine input + positive_prompt del nodo collegato al sampler.
    """
    # 1) Carica workflow
    workflow_file = os.getenv("COMFY_WORKFLOW_FILE", "workflow_longcat_i2v.json")
    try:
        with open(workflow_file, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        print(f"❌ ERRORE: Manca '{workflow_file}'.")
        return None

    # 2) Prompt (IT->EN + engineered)
    prompt_text = get_gemini_prompt(text_context)
    if not prompt_text:
        prompt_text = "cinematic realism, subtle natural motion, stable identity, smooth camera movement"

    # 3) Upload immagine
    try:
        comfy_image_name = upload_image(image_path)
    except Exception as e:
        print(f"❌ Errore upload: {e}")
        return None

    # 4) Trova nodo testo collegato al WanVideoSampler (così non tocchi nodi residui)
    text_node_id = None
    for nid, node in workflow.items():
        if node.get("class_type") == "WanVideoSampler":
            ref = node.get("inputs", {}).get("text_embeds")
            # ref tipico: ["107", 0]
            if isinstance(ref, list) and len(ref) >= 1:
                text_node_id = str(ref[0])
            else:
                text_node_id = None
            break

    # 5) Injection
    image_injected = False
    prompt_injected = False

    for nid, node in workflow.items():
        ctype = node.get("class_type")
        inputs = node.get("inputs", {})

        if ctype == "LoadImage":
            inputs["image"] = comfy_image_name
            image_injected = True

        if text_node_id and nid == text_node_id and ctype == "WanVideoTextEncodeCached":
            inputs["positive_prompt"] = prompt_text
            prompt_injected = True

    if not image_injected:
        print("⚠️ Warning: Nodo LoadImage non trovato nel workflow.")
    if not prompt_injected:
        print("⚠️ Warning: Nodo WanVideoTextEncodeCached collegato al sampler non trovato.")

    # 6) Esecuzione
    ws = websocket.WebSocket()
    try:
        ws.connect(f"{COMFY_WS_URL}/ws?clientId={CLIENT_ID}")
        response = queue_workflow(workflow)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            print(f"❌ Risposta /prompt senza prompt_id: {response}")
            return None

        return track_and_download(ws, prompt_id, output_path)

    except Exception as e:
        print(f"❌ Errore connessione/exec: {e}")
        return None
    finally:
        try:
            if ws.connected:
                ws.close()
        except Exception:
            pass
