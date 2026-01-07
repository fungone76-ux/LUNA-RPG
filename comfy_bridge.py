# comfy_bridge.py
from __future__ import annotations

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

# Importazione corretta dei comandi SD per la VRAM
try:
    from sd_client import unload_checkpoint, reload_checkpoint

    SD_VRAM_GUARD = True
except ImportError:
    SD_VRAM_GUARD = False

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

COMFY_OUTPUT_PATH = (os.getenv("COMFY_OUTPUT_PATH", "") or "").strip()


def _is_local_comfy() -> bool:
    try:
        host = urlparse(COMFY_URL).hostname or ""
    except Exception:
        host = ""
    return host.lower().strip() in ("127.0.0.1", "localhost")


COMFY_POLL_INTERVAL_SEC = float(os.getenv("COMFY_POLL_INTERVAL_SEC", "2") or "2")
COMFY_MAX_WAIT_SEC = int(os.getenv("COMFY_MAX_WAIT_SEC", "1800") or "1800")
COMFY_WS_RECV_TIMEOUT_SEC = float(os.getenv("COMFY_WS_RECV_TIMEOUT_SEC", "10") or "10")


def free_comfy_vram() -> bool:
    """Invia il comando a ComfyUI per liberare memoria. Fix: invia JSON vuoto."""
    try:
        # Il server ComfyUI richiede un corpo JSON valido per l'endpoint /free
        r = requests.post(f"{COMFY_URL}/free", json={}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gemini (IT -> EN + prompt engineer) - TUA LOGICA ORIGINALE
# ---------------------------------------------------------------------------

def get_gemini_prompt(prompt_it: str) -> str:
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
    - Preserve the scene content and meaning; you may add cinematic details ONLY if consistent (lighting, mood, subtle motion).
    - Assume I2V: the input image is the reference. Preserve identity, face, clothing, and composition. Avoid drift.
    - Default camera behavior MUST be: locked-off tripod, static shot, no zoom, no push-in, no dolly, no reframing.
      Only include camera movement if the user explicitly asks for it in the Italian prompt.
    - Add clear, natural motion cues for the subject (subtle realistic motion). Avoid big motions.
    - Output ONLY the final English positive prompt (single paragraph). No quotes, no markdown, no extra text.
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

def upload_image(image_path: str, overwrite: bool = True) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)

    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f)}
        data = {"overwrite": "true" if overwrite else "false"}
        r = requests.post(f"{COMFY_URL}/upload/image", files=files, data=data, timeout=120)
        r.raise_for_status()
        j = r.json()

    name = j.get("name") or j.get("filename") or j.get("file") or j.get("data", {}).get("name")
    sub = j.get("subfolder") or ""
    if not name:
        raise RuntimeError(f"Upload riuscito ma risposta non contiene nome file: {j}")

    return f"{sub}/{name}" if sub else name


def queue_workflow(workflow: dict) -> dict:
    payload = {"prompt": workflow, "client_id": CLIENT_ID}
    r = requests.post(f"{COMFY_URL}/prompt", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def _get_history_item(prompt_id: str) -> dict:
    r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and prompt_id in data:
        return data[prompt_id]
    return data


def _download_comfy_file(filename: str, subfolder: str, file_type: str, dest_path: str) -> str:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    params = {"filename": filename, "type": file_type}
    if subfolder:
        params["subfolder"] = subfolder

    with requests.get(f"{COMFY_URL}/view", params=params, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return dest_path


def _collect_candidate_files(obj) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def walk(x):
        if isinstance(x, dict):
            fn = x.get("filename")
            if isinstance(fn, str) and fn.strip():
                out.append((fn.strip(), (x.get("subfolder") or ""), (x.get("type") or "output")))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)

    walk(obj)
    return out


def _pick_best_video(candidates: list[tuple[str, str, str]]) -> tuple[str, str, str] | None:
    if not candidates:
        return None

    def score(fn: str) -> int:
        fn = fn.lower()
        if fn.endswith(".mp4"): return 0
        if fn.endswith(".webm"): return 1
        if fn.endswith(".mov"): return 2
        if fn.endswith(".gif"): return 4
        return 9

    seen = set()
    uniq = []
    for fn, sub, typ in candidates:
        key = (fn, sub, typ)
        if key not in seen:
            uniq.append((fn, sub, typ))
            seen.add(key)

    uniq.sort(key=lambda t: score(t[0]))
    best = uniq[0]
    return best if score(best[0]) < 9 else None


def get_latest_video_file(folder: str, max_age_seconds: int = 300) -> str | None:
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
                    if (now - m) <= max_age_seconds:
                        candidates.append((m, p))
                except OSError:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def track_and_download(ws: websocket.WebSocket, prompt_id: str, output_filename: str) -> str | None:
    print("⏳ [ComfyUI] Rendering in corso...")
    ws_candidates: list[tuple[str, str, str]] = []
    try:
        ws.settimeout(COMFY_WS_RECV_TIMEOUT_SEC)
    except Exception:
        pass

    deadline = time.time() + COMFY_MAX_WAIT_SEC
    ws_finished = False
    last_poll = 0.0

    while time.time() < deadline:
        try:
            raw = ws.recv()
            if raw:
                message = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8", errors="ignore"))
                mtype = message.get("type")
                data = message.get("data", {}) if isinstance(message, dict) else {}

                if mtype == "executed" and data.get("prompt_id") == prompt_id:
                    ws_candidates.extend(_collect_candidate_files(data.get("output", {})))

                if mtype == "executing" and data.get("prompt_id") == prompt_id and data.get("node") is None:
                    ws_finished = True
        except websocket._exceptions.WebSocketTimeoutException:
            pass
        except Exception:
            pass

        now = time.time()
        if (now - last_poll) >= COMFY_POLL_INTERVAL_SEC or ws_finished:
            last_poll = now
            hist = None
            try:
                hist = _get_history_item(prompt_id)
            except Exception:
                hist = None

            candidates = []
            candidates.extend(ws_candidates)
            if isinstance(hist, dict):
                candidates.extend(_collect_candidate_files(hist.get("outputs", {})))
                candidates.extend(_collect_candidate_files(hist.get("output", {})))
                candidates.extend(_collect_candidate_files(hist))

            best = _pick_best_video(candidates)
            if best:
                chosen = best
                break
            if ws_finished:
                print("⌛ [ComfyUI] Finito, ma output non ancora disponibile in /history...")
        time.sleep(0.2)
    else:
        chosen = None

    if COMFY_OUTPUT_PATH and os.path.exists(COMFY_OUTPUT_PATH) and _is_local_comfy():
        source_path = get_latest_video_file(COMFY_OUTPUT_PATH)
        if source_path:
            try:
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                shutil.copy2(source_path, output_filename)
                print(f"💾 Video copiato con successo in: {output_filename}")
                return output_filename
            except Exception:
                pass

    if chosen:
        fn, sub, typ = chosen
        try:
            saved = _download_comfy_file(fn, sub, typ, output_filename)
            print(f"💾 Video scaricato con successo in: {saved}")
            return saved
        except Exception as e:
            print(f"❌ Errore download via API: {e}")
    return None


# ---------------------------------------------------------------------------
# Main entry (CON STAFFETTA VRAM)
# ---------------------------------------------------------------------------

def generate_video_from_image(image_path: str, text_context: str,
                              output_path: str = "storage/videos/output.mp4") -> str | None:
    """
    Genera un video usando il workflow LongCat gestendo la VRAM di Stable Diffusion.
    """
    # 1) STAFFETTA: SPEGNIMENTO SD
    if SD_VRAM_GUARD:
        print("🚀 [VRAM] Spegnimento Stable Diffusion per liberare memoria...")
        unload_checkpoint()

    try:
        workflow_file = os.getenv("COMFY_WORKFLOW_FILE", "workflow_longcat_i2v.json")
        try:
            with open(workflow_file, "r", encoding="utf-8") as f:
                workflow = json.load(f)
        except FileNotFoundError:
            print(f"❌ ERRORE: Manca '{workflow_file}'.")
            return None

        prompt_text = get_gemini_prompt(text_context)
        comfy_image_name = upload_image(image_path)

        text_node_id = None
        for nid, node in workflow.items():
            if node.get("class_type") == "WanVideoSampler":
                ref = node.get("inputs", {}).get("text_embeds")
                if isinstance(ref, list) and len(ref) >= 1:
                    text_node_id = str(ref[0])
                break

        for nid, node in workflow.items():
            ctype = node.get("class_type")
            inputs = node.get("inputs", {})
            if ctype == "LoadImage":
                inputs["image"] = comfy_image_name
            if text_node_id and nid == text_node_id and ctype == "WanVideoTextEncodeCached":
                inputs["positive_prompt"] = prompt_text

        ws = websocket.WebSocket()
        try:
            ws.connect(f"{COMFY_WS_URL}/ws?clientId={CLIENT_ID}")
            response = queue_workflow(workflow)
            prompt_id = response.get("prompt_id")
            if not prompt_id: return None
            return track_and_download(ws, prompt_id, output_path)
        finally:
            if ws.connected:
                try:
                    ws.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"❌ Errore connessione/exec: {e}")
        return None
    finally:
        # 2) PULIZIA E RIPRISTINO STAFFETTA
        print("🧹 [VRAM] Liberazione memoria ComfyUI...")
        free_comfy_vram()
        if SD_VRAM_GUARD:
            print("🔄 [VRAM] Riaccensione Stable Diffusion...")
            reload_checkpoint()