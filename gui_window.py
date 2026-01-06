# file: gui_window.py
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QFrame, QLineEdit, QCheckBox,
    QMessageBox, QInputDialog, QFileDialog
)
from PySide6.QtGui import QPixmap, QTextCursor, QDesktopServices
from PySide6.QtCore import Qt, QTimer, QThread, QUrl, Signal, QObject

# Moduli interni
from game_state import (
    create_initial_game_state, roll_d20, update_game_state_after_roll,
    build_state_summary_text, update_story_summary
)
import voice_narrator
from dice_widget import DiceRollDialog

# Moduli GUI rifattorizzati
from gui_components import ClickableLabel, ImagePreviewDialog, CompanionSelectionDialog
from gui_worker import SceneWorker

# Ponte ComfyUI
import comfy_bridge


# --- NUOVO WORKER PER IL VIDEO (Background Thread) ---
class VideoWorker(QThread):
    """
    Esegue la generazione del video in background per non bloccare la finestra.
    """
    finished = Signal(str)  # Emette il percorso del video finale
    error = Signal(str)  # Emette messaggio di errore

    def __init__(self, image_path: str, context_text: str, output_path: str):
        super().__init__()
        self.image_path = image_path
        self.context_text = context_text
        self.output_path = output_path

    def run(self):
        try:
            # Chiama la funzione pesante di comfy_bridge
            final_video = comfy_bridge.generate_video_from_image(
                image_path=self.image_path,
                text_context=self.context_text,
                output_path=self.output_path
            )

            if final_video and os.path.exists(final_video):
                self.finished.emit(final_video)
            else:
                self.error.emit("Il file video non è stato trovato alla fine del processo.")

        except Exception as e:
            self.error.emit(str(e))


class GameWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luna D&D – Master Libero")
        self.resize(1200, 750)

        # Scelta iniziale
        selection_dialog = CompanionSelectionDialog(self)
        choice = selection_dialog.get_result()

        if choice["mode"] == "cancel":
            QTimer.singleShot(0, QApplication.instance().quit)
            return

        self._startup_session_path: Optional[str] = None

        if choice["mode"] == "new":
            companion_name = choice["companion"] or "Luna"
            self.game_state: dict = create_initial_game_state(companion_name)
        elif choice["mode"] == "load":
            self.game_state: dict = create_initial_game_state("Luna")
            self._startup_session_path = choice["session_path"]
        else:
            self.game_state: dict = create_initial_game_state("Luna")

        # Variabili di stato UI
        self.last_action: Optional[str] = None
        self._last_image_path: Optional[str] = None
        self.recent_dialogue: List[Dict[str, str]] = []
        self._image_history: List[str] = []
        self._image_index: int = -1
        self._saves_dir = Path("storage/saves")
        self._saves_dir.mkdir(parents=True, exist_ok=True)

        Path("storage/videos").mkdir(parents=True, exist_ok=True)

        # Threading Scene
        self._scene_thread: Optional[QThread] = None
        self._scene_worker: Optional[SceneWorker] = None

        # Threading Video
        self._video_thread: Optional[VideoWorker] = None

        # Voce
        voice_narrator.init_narrator()

        # UI Setup
        self._setup_ui()
        self._update_state_panel()

        # Avvio partita
        if getattr(self, "_startup_session_path", None):
            self._load_session_from_path(self._startup_session_path)
        else:
            QTimer.singleShot(0, self._request_scene)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # === COLONNA SINISTRA ===
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        main_layout.addLayout(left_layout, 2)

        lbl_state_title = QLabel("Stato party")
        lbl_state_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        left_layout.addWidget(lbl_state_title)

        self.state_edit = QTextEdit()
        self.state_edit.setReadOnly(True)
        self.state_edit.setMinimumHeight(140)
        self.state_edit.setStyleSheet(
            "background-color: #f7f2e8; border: 1px solid #c8b49a; font-family: Consolas; font-size: 12pt;")
        left_layout.addWidget(self.state_edit)

        left_layout.addWidget(self._create_separator())

        lbl_img_title = QLabel("Scena attuale")
        lbl_img_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        left_layout.addWidget(lbl_img_title)

        self.image_label = ClickableLabel("Nessuna immagine generata.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(420, 260)
        self.image_label.setStyleSheet("background-color: #000; color: #eee; border: 1px solid #444;")
        self.image_label.clicked.connect(self._open_image_preview)
        left_layout.addWidget(self.image_label, stretch=1)

        # Navigazione immagini
        nav_layout = QHBoxLayout()
        self.prev_image_button = QPushButton("◀")
        self.prev_image_button.setFixedWidth(40)
        self.prev_image_button.clicked.connect(self._on_prev_image)
        nav_layout.addWidget(self.prev_image_button)
        nav_layout.addStretch(1)
        self.next_image_button = QPushButton("▶")
        self.next_image_button.setFixedWidth(40)
        self.next_image_button.clicked.connect(self._on_next_image)
        nav_layout.addWidget(self.next_image_button)
        left_layout.addLayout(nav_layout)

        self.voice_checkbox = QCheckBox("Voce narrante attiva")
        self.voice_checkbox.setChecked(True)
        self.voice_checkbox.toggled.connect(lambda c: voice_narrator.stop() if not c else None)
        left_layout.addWidget(self.voice_checkbox)

        self.roll_label = QLabel("Nessuna azione ancora.")
        self.roll_label.setStyleSheet("font-size: 12pt; color: #333;")
        left_layout.addWidget(self.roll_label)

        self.status_label = QLabel("L'avventura sta per cominciare...")
        self.status_label.setStyleSheet("color: #555; font-size: 12pt;")
        left_layout.addWidget(self.status_label)

        # Pulsanti gestione
        save_load_layout = QHBoxLayout()
        self.save_button = QPushButton("Salva")
        self.save_button.clicked.connect(self._on_save_game)
        save_load_layout.addWidget(self.save_button)
        self.load_button = QPushButton("Carica")
        self.load_button.clicked.connect(self._on_load_game)
        save_load_layout.addWidget(self.load_button)
        left_layout.addLayout(save_load_layout)

        # BOTTONE VIDEO
        self.video_button = QPushButton("Genera Video (ComfyUI)")
        self.video_button.clicked.connect(self._on_generate_video_clicked)
        left_layout.addWidget(self.video_button)

        # === COLONNA DESTRA ===
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        main_layout.addLayout(right_layout, 3)

        lbl_story = QLabel("Storia")
        lbl_story.setStyleSheet("font-size: 13pt; font-weight: bold; color: #3b2410;")
        right_layout.addWidget(lbl_story)

        # Area Storia
        self.story_edit = QTextEdit()
        self.story_edit.setReadOnly(True)
        self.story_edit.setPlaceholderText("La tua avventura inizierà qui...")
        self.story_edit.setStyleSheet(
            """
            QTextEdit {
                background-color: #fdf6e3;
                border: 2px solid #d6c4a0;
                border-radius: 6px;
                color: #2b2b2b;
                font-family: 'Georgia', 'Times New Roman', serif;
                font-size: 15pt;
                line-height: 1.6;
                padding: 15px;
            }
            """
        )
        right_layout.addWidget(self.story_edit, stretch=1)

        right_layout.addWidget(self._create_separator())

        # INPUT AREA
        input_layout = QHBoxLayout()
        right_layout.addLayout(input_layout)

        # CHECKBOX DADO
        self.dice_checkbox = QCheckBox("🎲 Tira")
        self.dice_checkbox.setToolTip("Spunta se l'azione è rischiosa e richiede un tiro di dado")
        self.dice_checkbox.setStyleSheet("font-weight: bold; font-size: 11pt; margin-right: 5px;")
        input_layout.addWidget(self.dice_checkbox)

        self.action_input = QLineEdit()
        self.action_input.setPlaceholderText("Scrivi cosa fai...")
        self.action_input.returnPressed.connect(self._on_send_action)
        self.action_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #ffffff;
                border: 2px solid #888;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13pt;
                color: #000;
            }
            QLineEdit:focus {
                border: 2px solid #d6c4a0;
            }
            """
        )
        input_layout.addWidget(self.action_input, stretch=1)

        self.send_button = QPushButton("Invia azione")
        self.send_button.clicked.connect(self._on_send_action)
        input_layout.addWidget(self.send_button)

        # Init stato bottoni
        self.prev_image_button.setEnabled(False)
        self.next_image_button.setEnabled(False)

    def _create_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    # --- LOGICA CORE ---
    def _update_state_panel(self) -> None:
        text = build_state_summary_text(self.game_state)
        self.state_edit.setPlainText(text)

    def _append_story(self, text: str) -> None:
        if not text: return
        self.story_edit.append(text)
        self.story_edit.moveCursor(QTextCursor.End)

    def _show_image(self, img_path: Optional[str]) -> None:
        self._last_image_path = img_path
        if not img_path or not Path(img_path).is_file():
            self.image_label.setText("Nessuna immagine." if not img_path else "File non trovato.")
            self.image_label.setPixmap(QPixmap())
            return

        pix = QPixmap(img_path)
        if pix.isNull(): return

        target_size = self.image_label.size()
        if target_size.width() <= 0: target_size = self.image_label.minimumSize()

        scaled = pix.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def _register_new_image(self, img_path: str) -> None:
        if not img_path: return
        if self._image_index < len(self._image_history) - 1:
            self._image_history = self._image_history[: self._image_index + 1]

        if not self._image_history or self._image_history[-1] != img_path:
            self._image_history.append(img_path)
            self._image_index = len(self._image_history) - 1

        self._show_image(img_path)
        self._update_image_buttons()

    def _update_image_buttons(self) -> None:
        has_history = len(self._image_history) > 0
        self.prev_image_button.setEnabled(has_history and self._image_index > 0)
        self.next_image_button.setEnabled(has_history and self._image_index < len(self._image_history) - 1)

    def _on_prev_image(self):
        if self._image_index > 0:
            self._image_index -= 1
            self._show_image(self._image_history[self._image_index])
            self._update_image_buttons()

    def _on_next_image(self):
        if self._image_index < len(self._image_history) - 1:
            self._image_index += 1
            self._show_image(self._image_history[self._image_index])
            self._update_image_buttons()

    def _open_image_preview(self):
        if self._last_image_path and Path(self._last_image_path).is_file():
            pix = QPixmap(self._last_image_path)
            if not pix.isNull():
                dlg = ImagePreviewDialog(pix, self)
                dlg.resize(960, 600)
                dlg.exec()

    # --- WORKER MANAGEMENT ---
    def _request_scene(self) -> None:
        if self._scene_thread is not None: return

        self.status_label.setText("Il narratore sta pensando...")
        self._toggle_controls(False)

        self._scene_thread = QThread(self)
        self._scene_worker = SceneWorker(self.game_state, self.last_action, self.recent_dialogue)
        self._scene_worker.moveToThread(self._scene_thread)

        self._scene_thread.started.connect(self._scene_worker.run)
        self._scene_worker.finished.connect(self._on_scene_ready)
        self._scene_worker.error.connect(self._on_scene_error)
        self._scene_worker.finished.connect(self._cleanup_scene_thread)
        self._scene_worker.error.connect(lambda e: self._cleanup_scene_thread())

        self._scene_thread.start()

    def _on_scene_ready(self, reply_it: str, updated_state: dict, visual_en: str, full_data: dict):
        # 1. CONTROLLO ERRORI
        is_error = full_data.get("is_error", False)

        if is_error:
            self.status_label.setText("Errore LLM: Storia non aggiornata.")
            self._append_story(f"\n[SISTEMA]: {reply_it}\n(Questa risposta non è stata salvata. Riprova.)\n")
            self._cleanup_scene_thread()
            return

        # 2. AGGIORNAMENTO DI STATO
        self.game_state = updated_state

        # Fallback se l'IA dimentica il riassunto
        if "story_summary" not in self.game_state or not self.game_state["story_summary"]:
            update_story_summary(self.game_state, reply_it, max_words=120)

        current_turn = int(self.game_state.get("turn", 1))
        header = "--- INIZIO AVVENTURA ---" if current_turn <= 1 else f"--- SCENA {current_turn} ---"

        # Aggiorna Storia a video
        self._append_story(f"\n{header}\n{reply_it}\n")

        self.recent_dialogue.append({"speaker": "DM", "text": reply_it})
        self.recent_dialogue = self.recent_dialogue[-3:]

        # AUDIO
        if self.voice_checkbox.isChecked():
            voice_narrator.stop()
            if isinstance(full_data, dict) and "speech_script" in full_data and full_data["speech_script"]:
                voice_narrator.speak_script(full_data["speech_script"])
            else:
                voice_narrator.speak(reply_it)

        # IMMAGINE
        img_path_str = None
        if isinstance(full_data, dict) and "image_info" in full_data:
            info = full_data["image_info"]
            if isinstance(info, dict):
                img_path_str = info.get("image_path")

        if not img_path_str and isinstance(full_data, str) and os.path.isfile(full_data):
            img_path_str = full_data

        if img_path_str and os.path.exists(img_path_str):
            self._register_new_image(img_path_str)
            self.status_label.setText("Immagine generata.")

        self.last_action = None
        self._update_state_panel()

    def _on_scene_error(self, message: str):
        self.status_label.setText(f"ERRORE: {message}")
        self._append_story(f"\n[ERRORE TECNICO] {message}\n")

    def _cleanup_scene_thread(self):
        if self._scene_thread:
            self._scene_thread.quit()
            self._scene_thread.wait()
        self._scene_thread = None
        self._scene_worker = None
        self._toggle_controls(True)

    def _toggle_controls(self, enabled: bool):
        self.send_button.setEnabled(enabled)
        self.action_input.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.load_button.setEnabled(enabled)
        # Il video button è gestito separatamente durante la sua esecuzione
        if not self._video_thread:
            self.video_button.setEnabled(enabled)
        self.dice_checkbox.setEnabled(enabled)

    # --- AZIONI UTENTE ---
    def _on_send_action(self):
        text = self.action_input.text().strip()
        if not text: return

        voice_narrator.stop()
        self._append_story(f"\n[Tu]: {text}\n")
        self.action_input.clear()

        self.recent_dialogue.append({"speaker": "Tu", "text": text})
        self.recent_dialogue = self.recent_dialogue[-4:]
        self.last_action = text

        if self.dice_checkbox.isChecked():
            roll_val = roll_d20()
            self.roll_label.setText(f"Lancio in corso...")
            self.dice_checkbox.setChecked(False)
            self._dice_dialog = DiceRollDialog(target_value=roll_val, parent=self)
            self._dice_dialog.rolled.connect(lambda res: self._on_dice_finished(res, roll_val))
            self._dice_dialog.exec()
        else:
            self.game_state["last_roll"] = None
            self.roll_label.setText("Azione narrativa (No Dado).")
            self._update_state_panel()
            self._request_scene()

    def _on_dice_finished(self, final: int, logical: int):
        self.game_state["last_roll"] = logical
        self.roll_label.setText(f"Risultato D20: {logical}")
        update_game_state_after_roll(self.game_state, self.last_action or "", logical)
        self._update_state_panel()
        self._request_scene()

    # --- SALVATAGGIO ---
    def _on_save_game(self):
        default_path = self._saves_dir / "luna_sessione.json"
        filename, _ = QFileDialog.getSaveFileName(self, "Salva", str(default_path), "JSON (*.json)")
        if not filename: return

        data = {
            "game_state": self.game_state,
            "recent_dialogue": self.recent_dialogue,
            "last_action": self.last_action,
            "story_text": self.story_edit.toPlainText(),
            "last_image_path": self._last_image_path,
            "image_history": self._image_history,
            "image_index": self._image_index
        }
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.status_label.setText("Sessione salvata.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _on_load_game(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Carica", str(self._saves_dir), "JSON (*.json)")
        if filename: self._load_session_from_path(filename)

    def _load_session_from_path(self, filename: str):
        self._cleanup_scene_thread()
        voice_narrator.stop()
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.game_state = data.get("game_state", {})
            self.recent_dialogue = data.get("recent_dialogue", [])
            self.last_action = data.get("last_action")
            self._last_image_path = data.get("last_image_path")
            self._image_history = data.get("image_history", [])
            self._image_index = data.get("image_index", -1)
            self.story_edit.setPlainText(data.get("story_text", ""))

            self._update_state_panel()
            if self._image_history and 0 <= self._image_index < len(self._image_history):
                self._show_image(self._image_history[self._image_index])
            else:
                self._show_image(self._last_image_path)
            self._update_image_buttons()
            self.status_label.setText("Sessione caricata.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    # --- VIDEO COMFYUI CON THREADING (ANTI-CRASH) ---
    def _on_generate_video_clicked(self):
        # 1. Controlli
        if not self._last_image_path or not os.path.exists(self._last_image_path):
            QMessageBox.warning(self, "Attenzione", "Nessuna immagine presente da animare.")
            return

        # 2. Input
        default_context = self.last_action if self.last_action else "Cinematic ambient movement"
        user_input, ok = QInputDialog.getMultiLineText(
            self,
            "Generazione Video (ComfyUI)",
            "Descrivi la scena:
(Gemini la trasformerà in prompt video tecnico)",
            default_context
        )
        if not ok:
            return
        context_text = user_input.strip()

        # 3. Setup Percorso (ASSOLUTO, così salva sempre sul PC nel progetto)
        base_dir = Path(__file__).resolve().parent
        videos_dir = base_dir / "storage" / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        image_stem = Path(self._last_image_path).stem
        expected_video_base = videos_dir / f"{image_stem}_comfy"
        expected_video_path = expected_video_base.with_suffix(".mp4")

        # Rimuove eventuali vecchi output (qualsiasi estensione comune)
        for ext in (".mp4", ".webm", ".mov", ".mkv", ".gif"):
            p = expected_video_base.with_suffix(ext)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        # 4. AVVIO THREAD
        self.status_label.setText("ComfyUI in background... La finestra rimane attiva.")
        self.video_button.setEnabled(False)
        self.video_button.setText("Video in lavorazione...")

        self._video_thread = VideoWorker(self._last_image_path, context_text, str(expected_video_path))
        self._video_thread.finished.connect(self._on_video_finished)
        self._video_thread.error.connect(self._on_video_error)
        self._video_thread.start()

    def _on_video_finished(self, path_str: str):
        """Chiamata quando il video è pronto e salvato sul PC."""
        self._video_thread = None
        self.video_button.setEnabled(True)
        self.video_button.setText("Genera Video (ComfyUI)")
        self.status_label.setText("Video Creato!")

        # Apri automaticamente il video nel player di sistema
        from pathlib import Path
        import os
        import sys
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox

        video_path = str(Path(path_str).resolve())
        if not os.path.exists(video_path):
            QMessageBox.warning(self, "Video non trovato", f"Il file video non esiste:\n{video_path}")
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(video_path))

        # Fallback Windows se QDesktopServices non apre
        if not opened and sys.platform.startswith("win"):
            try:
                os.startfile(video_path)  # type: ignore[attr-defined]
                opened = True
            except Exception:
                opened = False

        if not opened:
            QMessageBox.information(
                self,
                "Video pronto",
                f"Video salvato in:\n{video_path}\n\nNon sono riuscita ad aprirlo automaticamente: aprilo manualmente.",
            )

    def _on_video_error(self, err_msg: str):
        """Slot chiamato quando il thread fallisce."""
        self._video_thread = None
        self.video_button.setEnabled(True)
        self.video_button.setText("Genera Video (ComfyUI)")
        self.status_label.setText("Errore video.")
        QMessageBox.warning(self, "Errore", f"Errore generazione video:\n{err_msg}")

    def closeEvent(self, event):
        msg = QMessageBox(self)
        msg.setWindowTitle("Uscita")
        msg.setText('Luna ti guarda confusa:\n"Sei sicuro di volerci lasciare qui?"')
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        luna_path = Path("assets/ui/luna_exit.png")
        if luna_path.exists():
            pix = QPixmap(str(luna_path)).scaled(200, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            msg.setIconPixmap(pix)

        if msg.exec() == QMessageBox.Yes:
            voice_narrator.stop()
            self._cleanup_scene_thread()
            if self._video_thread and self._video_thread.isRunning():
                self._video_thread.quit()
                self._video_thread.wait()
            event.accept()
        else:
            event.ignore()