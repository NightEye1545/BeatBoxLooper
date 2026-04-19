"""Main application window for BeatBoxLooper."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from audio.engine import AudioEngine
from gui.track_widget import TrackWidget


class MainWindow(QMainWindow):
    """Main looper control window."""

    def __init__(self, engine: AudioEngine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine

        self.setWindowTitle("BeatBoxLooper v1")
        self.resize(1200, 520)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.master_label = QLabel("Master Loop: Not set")
        self.metro_label = QLabel("Metronome: --")
        self.audio_label = QLabel("Audio: Starting...")
        self.master_label.setObjectName("TopLabel")
        self.metro_label.setObjectName("TopLabel")
        self.audio_label.setObjectName("TopLabel")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.master_label)
        top_layout.addWidget(self.metro_label)
        top_layout.addStretch(1)
        top_layout.addWidget(self.audio_label)

        root_layout.addLayout(top_layout)

        tracks_layout = QHBoxLayout()
        tracks_layout.setSpacing(10)

        self.track_widgets: list[TrackWidget] = []
        for i in range(self.engine.track_count):
            track_widget = TrackWidget(i)
            track_widget.record_clicked.connect(self._on_record)
            track_widget.stop_clicked.connect(self._on_stop)
            track_widget.clear_clicked.connect(self._on_clear)
            self.track_widgets.append(track_widget)
            tracks_layout.addWidget(track_widget)

        root_layout.addLayout(tracks_layout)

        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        self.statusBar().showMessage("Ready")

        ok, msg = self.engine.start()
        if not ok:
            QMessageBox.critical(self, "Audio Error", msg)
            self.statusBar().showMessage(msg)
        else:
            self.statusBar().showMessage("Audio engine started")

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_ui)
        self.refresh_timer.start(100)

    def _on_record(self, track_index: int) -> None:
        msg = self.engine.toggle_record_overdub(track_index)
        self.statusBar().showMessage(msg)

    def _on_stop(self, track_index: int) -> None:
        msg = self.engine.stop_track(track_index)
        self.statusBar().showMessage(msg)

    def _on_clear(self, track_index: int) -> None:
        msg = self.engine.clear_track(track_index)
        self.statusBar().showMessage(msg)

    def _refresh_ui(self) -> None:
        snapshot = self.engine.get_snapshot()

        master = snapshot["master_length_samples"]
        if master is None:
            self.master_label.setText("Master Loop: Not set")
        else:
            secs = master / self.engine.sample_rate
            self.master_label.setText(f"Master Loop: {master} samples ({secs:.2f} s)")

        self.audio_label.setText(snapshot["device_status"])
        metro_state = "On" if snapshot["metronome_enabled"] else "Off"
        self.metro_label.setText(f"Metronome: {metro_state} @ {snapshot['bpm']:.1f} BPM")

        for i, track_data in enumerate(snapshot["tracks"]):
            self.track_widgets[i].update_state(track_data["state"])

        if snapshot["last_error"]:
            self.statusBar().showMessage(f"Audio warning: {snapshot['last_error']}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API naming
        """Ensure audio stream is closed when app exits."""
        self.engine.stop()
        super().closeEvent(event)
