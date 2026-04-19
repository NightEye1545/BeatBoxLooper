"""Main application window for BeatBoxLooper."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSpinBox,
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
        self.resize(1320, 620)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.master_label = QLabel("Master Loop: Not set")
        self.audio_label = QLabel("Audio: Starting...")
        self.master_label.setObjectName("TopLabel")
        self.audio_label.setObjectName("TopLabel")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.master_label)
        top_layout.addStretch(1)
        top_layout.addWidget(self.audio_label)
        root_layout.addLayout(top_layout)

        controls = QHBoxLayout()
        controls.setSpacing(12)

        controls.addWidget(QLabel("BPM"))
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(30, 260)
        self.bpm_spin.setValue(self.engine.bpm)
        self.bpm_spin.valueChanged.connect(self._on_bpm_changed)
        controls.addWidget(self.bpm_spin)

        controls.addWidget(QLabel("Time Signature"))
        self.signature_combo = QComboBox()
        self.signature_combo.addItems(["4/4", "3/4", "6/8", "5/4"])  # Default 4/4.
        self.signature_combo.setCurrentText("4/4")
        self.signature_combo.currentTextChanged.connect(self._on_signature_changed)
        controls.addWidget(self.signature_combo)

        self.metronome_check = QCheckBox("Metronome")
        self.metronome_check.setChecked(True)
        self.metronome_check.toggled.connect(self._on_metronome_toggled)
        controls.addWidget(self.metronome_check)

        controls.addWidget(QLabel("Input Threshold"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.005)
        self.threshold_spin.setRange(0.001, 0.500)
        self.threshold_spin.setValue(self.engine.input_threshold)
        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)
        controls.addWidget(self.threshold_spin)

        controls.addWidget(QLabel("Mic Level"))
        self.level_meter = QProgressBar()
        self.level_meter.setRange(0, 100)
        self.level_meter.setValue(0)
        self.level_meter.setTextVisible(False)
        self.level_meter.setMinimumWidth(180)
        controls.addWidget(self.level_meter)

        controls.addStretch(1)
        root_layout.addLayout(controls)

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
        self.refresh_timer.start(80)

    def _on_bpm_changed(self, bpm: int) -> None:
        self.statusBar().showMessage(self.engine.set_bpm(bpm))

    def _on_signature_changed(self, value: str) -> None:
        beats, unit = value.split("/")
        self.statusBar().showMessage(self.engine.set_time_signature(int(beats), int(unit)))

    def _on_metronome_toggled(self, enabled: bool) -> None:
        self.statusBar().showMessage(self.engine.set_metronome_enabled(enabled))

    def _on_threshold_changed(self, value: float) -> None:
        self.statusBar().showMessage(self.engine.set_input_threshold(value))

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

        self.audio_label.setText(
            f"{snapshot['device_status']} | Metro: {snapshot['bpm']} BPM {snapshot['time_signature']}"
        )
        self.level_meter.setValue(int(min(100, snapshot["input_level"] * 100)))

        for i, track_data in enumerate(snapshot["tracks"]):
            self.track_widgets[i].update_state(track_data["state"])

        if snapshot["last_error"]:
            self.statusBar().showMessage(f"Audio warning: {snapshot['last_error']}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.engine.stop()
        super().closeEvent(event)
