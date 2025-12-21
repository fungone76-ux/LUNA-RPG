# file: dice_widget.py
import os
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap


class DiceRollDialog(QDialog):
    rolled = Signal(int)

    def __init__(self, target_value: int, parent=None):
        super().__init__(parent)
        self._target_value = target_value

        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 500)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.anim_label = QLabel()
        self.anim_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.anim_label)

        # CARICAMENTO
        filename = f"r{target_value:02d}"
        self.image_path = Path(f"assets/ui/{filename}.png")
        if not self.image_path.exists():
            self.image_path = Path(f"assets/ui/{filename}.jpg")

        if self.image_path.exists():
            full_strip = QPixmap(str(self.image_path))

            # Configurazioni
            self.total_frames = 12
            frame_width = full_strip.width() // self.total_frames
            frame_height = full_strip.height()

            self.frames = []
            for i in range(self.total_frames):
                x = i * frame_width
                frame = full_strip.copy(x, 0, frame_width, frame_height)
                scaled_frame = frame.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.frames.append(scaled_frame)

            # ANIMAZIONE
            self.current_frame = 0
            self.loops = 0

            # Un solo giro
            self.max_loops = 1

            self.timer = QTimer()
            self.timer.timeout.connect(self._play_next_frame)

            # --- MODIFICA VELOCITÀ ---
            # 150ms = Molto lento e "pesante" (prima era 100ms)
            self.timer.start(150)

        else:
            self.anim_label.setText(f"MANCA FILE:\n{filename}")
            self.anim_label.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
            QTimer.singleShot(2000, self.finish)

    def _play_next_frame(self):
        if self.current_frame < len(self.frames):
            pix = self.frames[self.current_frame]
            self.anim_label.setPixmap(pix)
            self.current_frame += 1
        else:
            self.loops += 1
            if self.loops < self.max_loops:
                self.current_frame = 0
            else:
                self.timer.stop()
                self._bounce_effect()
                QTimer.singleShot(1200, self.finish)

    def _bounce_effect(self):
        original_pix = self.anim_label.pixmap()
        if not original_pix: return

        zoomed = original_pix.scaled(
            original_pix.width() * 1.1,
            original_pix.height() * 1.1,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.anim_label.setPixmap(zoomed)
        QTimer.singleShot(100, lambda: self.anim_label.setPixmap(original_pix))

    def finish(self):
        self.rolled.emit(self._target_value)
        self.accept()