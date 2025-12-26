import json
import uuid
import urllib.request
import urllib.parse
import requests
import websocket
import os
import random
import shutil
import time
import glob
from dotenv import load_dotenv
from google import genai

# --- CONFIGURAZIONE ---
load_dotenv()

COMFY_SERVER = os.getenv("COMFY_SERVER", "127.0.0.1:8188")
COMFY_OUTPUT_PATH = os.getenv("COMFY_OUTPUT_PATH")

CLIENT_ID = str(uuid.uuid4())
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("⚠️ ATTENZIONE: Chiave GEMINI_API_KEY mancante nel file .env")
    client = None
else:
    client = genai.Client(api_key=API_KEY)


def get_gemini_prompt(context_description):
    """Ottimizza il prompt per Wan 2.2."""
    if not client:
        return "high quality, cinematic, slow motion, 4k"

    print(f"🧠 [Gemini] Creo prompt Wan 2.2 per: '{context_description}'...")

    sys_instruction = """
    You are an AI Video Prompt Engineer for Wan 2.2.
    OUTPUT MUST BE 100% ENGLISH.
    Format: "Subject description. Action. Camera. Atmosphere."
    Include: "Cinematic, Wan 2.2 style, 4k, natural motion".
    NO Markdown.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Scene Context: {context_description}",
            config={"system_instruction": sys_instruction}
        )
        clean_prompt = response.text.strip()
        print(f"✨ [Gemini] Prompt: {clean_prompt}")
        return clean_prompt
    except Exception as e:
        print(f"⚠️ Errore Gemini: {e}. Uso fallback.")
        return "high quality, cinematic, slow motion, 4k"


def upload_image(image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Immagine non trovata: {image_path}")

    with open(image_path, "rb") as file:
        files = {"image": file}
        data = {"overwrite": "true"}
        print(f"📤 [ComfyUI] Upload immagine: {os.path.basename(image_path)}...")
        response = requests.post(f"http://{COMFY_SERVER}/upload/image", files=files, data=data)

    if response.status_code == 200:
        return response.json().get("name")
    else:
        raise Exception(f"Errore Upload: {response.text}")


def queue_workflow(workflow_json):
    p = {"prompt": workflow_json, "client_id": CLIENT_ID}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{COMFY_SERVER}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_latest_video_file(root_folder):
    """
    Cerca il file video più recente modificato negli ultimi 2 minuti.
    """
    print(f"🔎 Cerco l'ultimo video creato in: {root_folder}...")

    # Cerca mp4, mkv, gif in tutte le sottocartelle
    search_patterns = [
        os.path.join(root_folder, "**", "*.mp4"),
        os.path.join(root_folder, "**", "*.gif"),
        os.path.join(root_folder, "**", "*.mkv")
    ]

    all_files = []
    for pattern in search_patterns:
        # recursive=True richiede python 3.10+, altrimenti usa glob semplice
        all_files.extend(glob.glob(pattern, recursive=True))

    if not all_files:
        return None

    # Ordina per data di modifica (il più recente per ultimo)
    latest_file = max(all_files, key=os.path.getmtime)

    # Controllo di sicurezza: è stato creato negli ultimi 3 minuti?
    # Altrimenti rischiamo di prendere un video vecchio
    last_mod_time = os.path.getmtime(latest_file)
    if time.time() - last_mod_time > 180:  # 3 minuti tolleranza
        print(f"⚠️ Trovato video '{os.path.basename(latest_file)}' ma è troppo vecchio (>3 min).")
        return None

    print(f"✅ TROVATO ULTIMO FILE: {latest_file}")
    return latest_file


def track_and_download(ws, prompt_id, output_filename):
    print("⏳ [ComfyUI] Rendering Wan 2.2 in corso... (Attendi)")

    # 1. ATTESA ESECUZIONE
    while True:
        try:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['node'] is None and data['prompt_id'] == prompt_id:
                        print("✅ [ComfyUI] Esecuzione finita!")
                        break
        except Exception as e:
            print(f"⚠️ Errore WebSocket: {e}")
            break

    # 2. STRATEGIA "PRENDI L'ULTIMO" (Molto più affidabile)
    time.sleep(2)  # Diamo tempo al file system di chiudere il file

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


def generate_video_from_image(image_path, text_context, output_path="storage/videos/output.mp4"):
    """Funzione Principale"""
    # 1. Carica Workflow
    try:
        with open("workflow_api.json", "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        print("❌ ERRORE: Manca 'workflow_api.json'.")
        return None

    # 2. Prompt & Upload
    ai_prompt = get_gemini_prompt(text_context)
    try:
        comfy_image_name = upload_image(image_path)
    except Exception as e:
        print(f"❌ Errore upload: {e}")
        return None

    # 3. Injection
    prompt_injected = False
    image_injected = False
    seed_randomized = False

    for node_id, node in workflow.items():
        if node["class_type"] == "LoadImage":
            node["inputs"]["image"] = comfy_image_name
            image_injected = True

        if node["class_type"] == "CLIPTextEncode":
            text_val = node["inputs"].get("text", "")
            if "__PROMPT_GEMINI__" in text_val:
                node["inputs"]["text"] = ai_prompt
                prompt_injected = True

        # Randomizza Seed
        if node["class_type"] in ["KSampler", "KSamplerAdvanced", "Wan22Sampler"]:
            if "noise_seed" in node["inputs"]:
                node["inputs"]["noise_seed"] = random.randint(1, 10 ** 14)
                seed_randomized = True
            elif "seed" in node["inputs"]:
                node["inputs"]["seed"] = random.randint(1, 10 ** 14)
                seed_randomized = True

    if not image_injected: print("⚠️ Warning: Nodo LoadImage non trovato.")

    # 4. Esecuzione
    ws = websocket.WebSocket()
    try:
        ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={CLIENT_ID}")
        response = queue_workflow(workflow)
        final_file = track_and_download(ws, response['prompt_id'], output_path)
        return final_file
    except Exception as e:
        print(f"❌ Errore connessione WebSocket: {e}")
        return None
    finally:
        if ws.connected: ws.close()