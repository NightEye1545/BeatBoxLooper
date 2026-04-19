"""Real-time audio engine for microphone capture and synchronized loop playback."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
import sounddevice as sd

from models.loop_track import LoopTrack, TrackState


class AudioEngine:
    """Simple 5-track looper engine.

    Design notes:
    - Uses one full-duplex sounddevice stream callback for low-latency IO.
    - First completed recording defines the master loop length.
    - Other tracks are constrained to the same length for reliable sync.
    - GUI should call control methods from the UI thread; callback runs in audio thread.
    """

    def __init__(
        self,
        track_count: int = 5,
        sample_rate: int = 44100,
        blocksize: int = 512,
        bpm: float = 120.0,
        beats_per_bar: int = 4,
    ) -> None:
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.channels = 1
        self.track_count = track_count
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar

        self.lock = threading.RLock()
        self.tracks = [LoopTrack(index=i) for i in range(track_count)]

        self.master_length_samples: int | None = None
        self.playhead = 0
        self.pre_master_playhead = 0
        self.transport_running = False

        self.stream: sd.Stream | None = None
        self.last_error_message = ""
        self.device_status = "Audio: not started"
        self.metronome_enabled = True
        self.metronome_gain = 0.20

    @property
    def samples_per_beat(self) -> int:
        """Number of samples in one beat at the configured BPM."""
        return max(1, int(self.sample_rate * 60.0 / self.bpm))

    def _beat_aligned_length(self, sample_length: int) -> int:
        """Snap a loop length to the nearest beat boundary."""
        beat = self.samples_per_beat
        return max(beat, int(round(sample_length / beat)) * beat)

    def _metronome_click(self, playhead_sample: int) -> float:
        """Return a short synthesized click on beat boundaries."""
        if not self.metronome_enabled:
            return 0.0

        beat = self.samples_per_beat
        in_beat = playhead_sample % beat
        click_len = max(4, int(0.01 * self.sample_rate))  # 10 ms
        if in_beat >= click_len:
            return 0.0

        beat_index = (playhead_sample // beat) % self.beats_per_bar
        amp = 1.0 if beat_index == 0 else 0.55
        env = 1.0 - (in_beat / click_len)
        return self.metronome_gain * amp * env

    def start(self) -> tuple[bool, str]:
        """Start audio stream and validate IO devices."""
        with self.lock:
            try:
                devices = sd.query_devices()
                if not devices:
                    return False, "No audio devices available."

                default_in, default_out = sd.default.device
                if default_in is None or default_in < 0:
                    return False, "No default input microphone detected."
                if default_out is None or default_out < 0:
                    return False, "No default output device detected."

                in_name = devices[default_in]["name"]
                out_name = devices[default_out]["name"]

                self.stream = sd.Stream(
                    samplerate=self.sample_rate,
                    blocksize=self.blocksize,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self.stream.start()
                self.device_status = f"Audio OK | In: {in_name} | Out: {out_name}"
                self.last_error_message = ""
                return True, "Audio engine started"
            except Exception as exc:  # noqa: BLE001 - user-friendly recovery path
                self.last_error_message = str(exc)
                self.device_status = f"Audio error: {exc}"
                return False, f"Failed to start audio stream: {exc}"

    def stop(self) -> None:
        """Stop and close audio stream."""
        with self.lock:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None

    def _audio_callback(self, indata: np.ndarray, outdata: np.ndarray, frames: int, _time: Any, status: sd.CallbackFlags) -> None:
        """Main real-time audio callback (runs on audio thread)."""
        outdata.fill(0)

        with self.lock:
            if status:
                self.last_error_message = str(status)

            if self.master_length_samples is None:
                self._process_without_master(indata, outdata, frames)
                return

            for i in range(frames):
                mic_sample = float(indata[i, 0])
                mixed = 0.0

                idx = self.playhead % self.master_length_samples

                for track in self.tracks:
                    if track.state in (TrackState.PLAYING, TrackState.OVERDUBBING) and track.has_loop:
                        mixed += float(track.loop_buffer[idx])

                    if track.state == TrackState.OVERDUBBING and track.has_loop:
                        track.loop_buffer[idx] += mic_sample

                    elif track.state == TrackState.RECORDING:
                        if self.master_length_samples is not None:
                            # Recording a non-master track: write into fixed-length loop buffer.
                            if not track.has_loop:
                                track.loop_buffer = np.zeros(self.master_length_samples, dtype=np.float32)
                            if track.record_pos < self.master_length_samples:
                                track.loop_buffer[track.record_pos] = mic_sample
                                track.record_pos += 1
                            # Auto-close recording at end to avoid drifting lengths.
                            if track.record_pos >= self.master_length_samples:
                                track.state = TrackState.PLAYING

                mixed += self._metronome_click(self.playhead)
                outdata[i, 0] = np.clip(mixed, -1.0, 1.0)
                self.playhead = (self.playhead + 1) % self.master_length_samples

    def _process_without_master(self, indata: np.ndarray, outdata: np.ndarray, frames: int) -> None:
        """Process audio before master loop exists.

        Only first-pass recording can happen in this state. Playback is silent.
        """
        for i in range(frames):
            mic_sample = float(indata[i, 0])
            for track in self.tracks:
                if track.state == TrackState.RECORDING:
                    track.record_buffer.append(mic_sample)
            outdata[i, 0] = self._metronome_click(self.pre_master_playhead)
            self.pre_master_playhead += 1

    def toggle_record_overdub(self, track_index: int) -> str:
        """Handle Record/Overdub button behavior for a track."""
        with self.lock:
            track = self.tracks[track_index]

            if track.state == TrackState.EMPTY:
                track.record_buffer.clear()
                track.record_pos = 0
                track.state = TrackState.RECORDING
                return f"Track {track_index + 1}: recording started"

            if track.state == TrackState.RECORDING:
                # Close first-pass recording.
                if self.master_length_samples is None:
                    if len(track.record_buffer) < self.blocksize:
                        track.state = TrackState.EMPTY
                        track.record_buffer.clear()
                        return f"Track {track_index + 1}: recording too short, discarded"

                    raw_loop = np.array(track.record_buffer, dtype=np.float32)
                    aligned_len = self._beat_aligned_length(int(raw_loop.size))
                    track.loop_buffer = np.zeros(aligned_len, dtype=np.float32)
                    write_len = min(aligned_len, int(raw_loop.size))
                    track.loop_buffer[:write_len] = raw_loop[:write_len]
                    track.record_buffer.clear()
                    self.master_length_samples = int(track.loop_buffer.size)
                    self.playhead = 0
                    self.pre_master_playhead = 0
                    self.transport_running = True

                    for other in self.tracks:
                        if other is not track and other.state == TrackState.RECORDING:
                            other.state = TrackState.EMPTY
                            other.record_buffer.clear()

                    track.state = TrackState.PLAYING
                    return f"Track {track_index + 1}: loop closed ({self.master_length_samples} samples)"

                # Non-master manual close: zero-pad if shorter than master.
                if track.record_pos < self.master_length_samples:
                    if not track.has_loop:
                        track.loop_buffer = np.zeros(self.master_length_samples, dtype=np.float32)
                    # Remaining area already zero.
                track.state = TrackState.PLAYING
                return f"Track {track_index + 1}: recording closed"

            if track.state in (TrackState.PLAYING, TrackState.STOPPED):
                if not track.has_loop:
                    return f"Track {track_index + 1}: no loop to overdub"
                track.state = TrackState.OVERDUBBING
                return f"Track {track_index + 1}: overdub started"

            if track.state == TrackState.OVERDUBBING:
                track.state = TrackState.PLAYING
                return f"Track {track_index + 1}: overdub ended"

            return f"Track {track_index + 1}: no action"

    def stop_track(self, track_index: int) -> str:
        """Stop playback/recording for a specific track without clearing loop data."""
        with self.lock:
            track = self.tracks[track_index]

            if track.state == TrackState.EMPTY:
                return f"Track {track_index + 1}: already empty"

            if track.state == TrackState.RECORDING:
                track.state = TrackState.STOPPED
                track.record_buffer.clear()
                track.record_pos = 0
                return f"Track {track_index + 1}: recording stopped"

            track.state = TrackState.STOPPED
            return f"Track {track_index + 1}: stopped"

    def clear_track(self, track_index: int) -> str:
        """Erase a track's loop and reset it to empty."""
        with self.lock:
            track = self.tracks[track_index]
            track.reset()

            # If no loops remain, reset master timing.
            if all(not t.has_loop for t in self.tracks):
                self.master_length_samples = None
                self.playhead = 0
                self.pre_master_playhead = 0
                self.transport_running = False

            return f"Track {track_index + 1}: cleared"

    def get_snapshot(self) -> dict[str, Any]:
        """Return a UI-safe read-only status snapshot."""
        with self.lock:
            return {
                "master_length_samples": self.master_length_samples,
                "playhead": self.playhead,
                "device_status": self.device_status,
                "last_error": self.last_error_message,
                "bpm": self.bpm,
                "metronome_enabled": self.metronome_enabled,
                "tracks": [
                    {
                        "index": t.index,
                        "state": t.state.value,
                        "has_loop": t.has_loop,
                        "loop_samples": int(t.loop_buffer.size),
                    }
                    for t in self.tracks
                ],
            }
