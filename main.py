"""BeatBoxLooper application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from audio.engine import AudioEngine
from gui.main_window import MainWindow


def _build_stylesheet() -> str:
    """Return a dark performance-oriented stylesheet."""
    return """
    QWidget {
        background-color: #1b1d22;
        color: #eceff4;
        font-size: 13px;
    }
    QLabel#TopLabel {
        font-size: 14px;
        font-weight: 600;
        color: #d8dee9;
    }
    QFrame#TrackPanel {
        background-color: #252932;
        border: 2px solid #3b4252;
        border-radius: 8px;
        padding: 8px;
    }
    QLabel#TrackTitle {
        font-size: 15px;
        font-weight: 700;
        color: #88c0d0;
    }
    QLabel#TrackState {
        background: #2e3440;
        border: 1px solid #4c566a;
        border-radius: 6px;
        padding: 8px;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton {
        border: 1px solid #4c566a;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 700;
        padding: 8px;
    }
    QPushButton#RecordButton {
        background-color: #bf616a;
        color: #ffffff;
    }
    QPushButton#StopButton {
        background-color: #d08770;
        color: #ffffff;
    }
    QPushButton#ClearButton {
        background-color: #5e81ac;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #4c566a;
    }
    QStatusBar {
        background-color: #2e3440;
    }
    """


def main() -> int:
    """App bootstrap."""
    app = QApplication(sys.argv)
    app.setStyleSheet(_build_stylesheet())

    engine = AudioEngine(track_count=5, sample_rate=44100, blocksize=512)
    window = MainWindow(engine)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
