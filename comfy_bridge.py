import json
import uuid
import requests
import websocket
import os
import random
import shutil
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
from google import genai

load_dotenv()

# CONFIGURAZIONE
COMFY_URL = os.getenv("COMFY_SERVER", "http://127.0.0.1:8188")
CLIENT_ID = str(uuid.uuid4())
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None


def get_gemini_prompt(text):
    """Migliora il prompt con Gemini specificamente per LongCat/WanVideo."""
    if not client: return text
    try:
        # Istruzione aggiornata per LongCat
        instruction = (
            "TASK: Convert this input into a high-quality, detailed English visual description "
            "for LongCat (WanVideo) generation. Focus on cinematic movement, lighting, and "
            "consistency. RULE: Output ONLY the raw text. Input: "
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{instruction}{text}"
        )
        return response.text.strip() if response.text else text
    except:
        return text


def generate_video_from_image(image_path, text_context, output_path):
    print(f"🚀 Inizio generazione su: {COMFY_URL}")

    if not os.path.exists("workflow_api.json"):
        print("❌ ERRORE: Manca il file workflow_api.json!")
        return None

    with open("workflow_api.json", "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 1. Upload Immagine
    print(f"📤 Carico immagine: {os.path.basename(image_path)}...")
    try:
        with open(image_path, "rb") as f:
            base_url = COMFY_URL.rstrip("/")
            resp = requests.post(f"{base_url}/upload/image", files={"image": f}, data={"overwrite": "true"})
            if resp.status_code != 200:
                print(f"❌ Errore Server Upload: {resp.text}")
                return None
            uploaded_filename = resp.json().get("name")
    except Exception as e:
        print(f"❌ Errore Connessione: {e}")
        return None

    # 2. Inserimento Dati nel Workflow
    prompt_inglese = get_gemini_prompt(text_context)
    print(f"📝 Prompt IA: {prompt_inglese}")

    for node in workflow.values():
        if "inputs" in node and "image" in node["inputs"]:
            node["inputs"]["image"] = uploaded_filename
        if "inputs" in node:
            if "text" in node["inputs"] and isinstance(node["inputs"]["text"], str):
                if "__" in node["inputs"]["text"] or len(node["inputs"]["text"]) < 50:
                    node["inputs"]["text"] = prompt_inglese
            if "positive_prompt" in node["inputs"] and isinstance(node["inputs"]["positive_prompt"], str):
                node["inputs"]["positive_prompt"] = prompt_inglese
        if "inputs" in node and "seed" in node["inputs"]:
            node["inputs"]["seed"] = random.randint(1, 1000000000)

    # 3. Esecuzione
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + f"/ws?clientId={CLIENT_ID}"
    ws = websocket.WebSocket()

    try:
        ws.connect(ws_url)
        resp = requests.post(f"{base_url}/prompt", json={"prompt": workflow, "client_id": CLIENT_ID})

        # --- DIAGNOSTICA ERRORI ---
        if resp.status_code != 200:
            print(f"❌ Errore HTTP {resp.status_code}: {resp.text}")
            return None

        resp_json = resp.json()
        if 'prompt_id' not in resp_json:
            print(f"\n❌ ERRORE DA COMFYUI:\n{json.dumps(resp_json, indent=2)}")
            print("💡 SUGGERIMENTO: Probabilmente manca un modello o il nome nel JSON è sbagliato.")
            return None
        # ---------------------------

        prompt_id = resp_json['prompt_id']
        print("⏳ Video in lavorazione... (Attendi 1-2 minuti)")

        while True:
            out = ws.recv()
            if isinstance(out, str) and prompt_id in out:
                msg = json.loads(out)
                if msg['type'] == 'executing' and msg['data']['node'] is None:
                    break

        history = requests.get(f"{base_url}/history/{prompt_id}").json()[prompt_id]
        for out in history['outputs'].values():
            media_files = out.get('videos', []) + out.get('gifs', [])
            if media_files:
                fname = media_files[0]['filename']
                print(f"📥 Scarico video: {fname}...")
                data = requests.get(f"{base_url}/view?filename={fname}", stream=True)
                with open(output_path, "wb") as f:
                    shutil.copyfileobj(data.raw, f)
                print(f"✅ Video salvato in: {output_path}")
                return output_path

    except Exception as e:
        print(f"❌ Errore Generico: {e}")
        return None
    finally:
        if ws.connected:
            ws.close()
    return None