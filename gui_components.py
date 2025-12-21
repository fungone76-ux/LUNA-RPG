# file: gui_components.py
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QRadioButton, QPushButton,
    QDialogButtonBox, QFileDialog, QGraphicsView, QGraphicsScene, QWidget
)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import Qt, Signal

# --- LABEL CLICCABILE ---
class ClickableLabel(QLabel):
    """Label cliccabile usata per l'anteprima immagine."""
    clicked = Signal()

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# --- VIEWER IMMAGINI (ZOOM/PAN) ---
class ImageViewer(QGraphicsView):
    """
    Viewer con zoom (rotellina) e pan (drag) per visualizzare l'immagine.
    """
    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        scene = QGraphicsScene(self)
        scene.addPixmap(pixmap)
        self.setScene(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._zoom = 0

    def wheelEvent(self, event):  # type: ignore[override]
        if event.angleDelta().y() > 0:
            factor = 1.25
            self._zoom += 1
        else:
            factor = 0.8
            self._zoom -= 1
        self.scale(factor, factor)


class ImagePreviewDialog(QDialog):
    """Dialog che mostra l'immagine a dimensioni maggiori con zoom e pan."""
    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Anteprima scena")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        layout = QVBoxLayout(self)
        viewer = ImageViewer(pixmap, self)
        layout.addWidget(viewer)


# --- DIALOGO SELEZIONE INIZIALE ---
class CompanionSelectionDialog(QDialog):
    """
    Finestra iniziale: Nuova partita o Caricamento.
    """
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Luna D&D – Nuova partita o caricamento")
        self._loaded_session_path: Optional[str] = None

        layout = QVBoxLayout(self)

        label = QLabel("Vuoi iniziare una nuova avventura o caricare una partita salvata?")
        label.setWordWrap(True)
        layout.addWidget(label)

        # Scelta compagna
        self.radio_luna = QRadioButton("Luna – incantatrice empatica")
        self.radio_stella = QRadioButton("Stella – ladra astuta")
        self.radio_maria = QRadioButton("Maria – guerriera devota")
        self.radio_luna.setChecked(True)

        layout.addWidget(self.radio_luna)
        layout.addWidget(self.radio_stella)
        layout.addWidget(self.radio_maria)

        # Pulsante Carica
        self.load_button = QPushButton("Carica partita salvata…")
        self.load_button.clicked.connect(self._on_load_clicked)
        layout.addWidget(self.load_button)

        # Pulsanti OK/Annulla
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_load_clicked(self) -> None:
        saves_dir = Path("storage/saves")
        saves_dir.mkdir(parents=True, exist_ok=True)
        filename, _ = QFileDialog.getOpenFileName(
            self, "Carica sessione di gioco", str(saves_dir), "Sessioni di gioco (*.json);;Tutti i file (*.*)"
        )
        if filename:
            self._loaded_session_path = filename
            self.accept()

    def get_result(self) -> Dict[str, Optional[str]]:
        result = self.exec()
        if result != QDialog.Accepted:
            return {"mode": "cancel", "companion": None, "session_path": None}

        if self._loaded_session_path:
            return {"mode": "load", "companion": None, "session_path": self._loaded_session_path}

        comp = "Luna"
        if self.radio_stella.isChecked(): comp = "Stella"
        elif self.radio_maria.isChecked(): comp = "Maria"

        return {"mode": "new", "companion": comp, "session_path": None}