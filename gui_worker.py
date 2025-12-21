# file: gui_worker.py
import copy
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal

from dm_engine import process_turn

class SceneWorker(QObject):
    """
    Worker eseguito in un QThread:
    - Chiama il DM (LLM) tramite process_turn
    - Genera l'immagine (Stable Diffusion)
    """
    finished = Signal(str, dict, str, object)  # reply_it, updated_state, visual_en, img_path
    error = Signal(str)

    def __init__(self, game_state: dict, last_action: Optional[str], recent_dialogue: List[Dict[str, str]]) -> None:
        super().__init__()
        self._game_state = copy.deepcopy(game_state)
        self._last_action = last_action
        self._recent_dialogue = list(recent_dialogue)

    def run(self) -> None:
        try:
            main_quest = str(self._game_state.get("main_quest") or "")
            story_summary = str(self._game_state.get("story_summary") or "")

            # Normalizzazione dialogo
            recent_dialogue: List[Dict[str, str]] = []
            for item in self._recent_dialogue:
                if isinstance(item, dict) and "speaker" in item and "text" in item:
                    recent_dialogue.append({
                        "speaker": str(item["speaker"]),
                        "text": str(item["text"]),
                    })

            # Chiamata al motore centrale
            result = process_turn(
                main_quest=main_quest,
                story_summary=story_summary,
                game_state=self._game_state,
                recent_dialogue=recent_dialogue,
                player_input=self._last_action or "",
                generate_image=True,
            )

            reply_it: str = result.get("reply_it", "") or ""
            updated_state: dict = result.get("game_state", self._game_state)
            image_info = result.get("image_info")

            if isinstance(image_info, dict):
                visual_en: str = image_info.get("visual_en", "") or ""
                img_path = image_info.get("image_path")
            else:
                visual_en = ""
                img_path = None

            self.finished.emit(reply_it, updated_state, visual_en, result)

        except Exception as e:
            self.error.emit(str(e))