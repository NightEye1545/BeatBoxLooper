"""Per-track GUI widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class TrackWidget(QFrame):
    """Visual control surface for one loop track."""

    record_clicked = Signal(int)
    stop_clicked = Signal(int)
    clear_clicked = Signal(int)

    def __init__(self, track_index: int, parent=None) -> None:
        super().__init__(parent)
        self.track_index = track_index

        self.setObjectName("TrackPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(180)

        self.title_label = QLabel(f"TRACK {track_index + 1}")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setObjectName("TrackTitle")

        self.state_label = QLabel("Empty")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setObjectName("TrackState")

        self.record_button = QPushButton("REC / OVERDUB")
        self.record_button.setObjectName("RecordButton")
        self.record_button.setMinimumHeight(72)

        self.stop_button = QPushButton("STOP")
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setMinimumHeight(54)

        self.clear_button = QPushButton("CLEAR")
        self.clear_button.setObjectName("ClearButton")
        self.clear_button.setMinimumHeight(54)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.record_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.clear_button)
        layout.addStretch(1)
        self.setLayout(layout)

        self.record_button.clicked.connect(lambda: self.record_clicked.emit(self.track_index))
        self.stop_button.clicked.connect(lambda: self.stop_clicked.emit(self.track_index))
        self.clear_button.clicked.connect(lambda: self.clear_clicked.emit(self.track_index))

    def update_state(self, state: str) -> None:
        """Update visible state text from engine snapshot."""
        self.state_label.setText(state)
