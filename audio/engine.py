"""Real-time audio engine for microphone capture and synchronized loop playback."""

from __future__ import annotations

import math
import threading
from typing import Any

import numpy as np
import sounddevice as sd

from models.loop_track import LoopTrack, TrackState


class AudioEngine:
    """Simple 5-track looper engine with metronome and smart recording trim."""

    def __init__(self, track_count: int = 5, sample_rate: int = 44100, blocksize: int = 512) -> None:
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.channels = 1
        self.track_count = track_count

        self.lock = threading.RLock()
        self.tracks = [LoopTrack(index=i) for i in range(track_count)]

        self.master_length_samples: int | None = None
        self.playhead = 0
        self.transport_running = False

        self.stream: sd.Stream | None = None
        self.last_error_message = ""
        self.device_status = "Audio: not started"

        # Metronome + smart trim controls.
        self.metronome_enabled = True
        self.bpm = 100
        self.beats_per_bar = 4
        self.beat_unit = 4
        self.input_threshold = 0.03
        self.input_level = 0.0

        self._metronome_free_counter = 0
        self._click_remaining = 0
        self._click_phase = 0.0
        self._click_freq = 1200.0

    @property
    def samples_per_beat(self) -> int:
        """Return integer samples per beat for current BPM."""
        return max(1, int((60.0 / self.bpm) * self.sample_rate))

    @property
    def samples_per_bar(self) -> int:
        """Return integer samples per bar using current time signature numerator."""
        return self.samples_per_beat * self.beats_per_bar

    def set_bpm(self, bpm: int) -> str:
        with self.lock:
            self.bpm = max(30, min(260, int(bpm)))
            return f"BPM set to {self.bpm}"

    def set_time_signature(self, beats_per_bar: int, beat_unit: int) -> str:
        with self.lock:
            self.beats_per_bar = max(1, beats_per_bar)
            self.beat_unit = beat_unit
            return f"Time signature set to {self.beats_per_bar}/{self.beat_unit}"

    def set_metronome_enabled(self, enabled: bool) -> str:
        with self.lock:
            self.metronome_enabled = bool(enabled)
            return "Metronome ON" if self.metronome_enabled else "Metronome OFF"

    def set_input_threshold(self, threshold: float) -> str:
        with self.lock:
            self.input_threshold = max(0.001, min(0.5, float(threshold)))
            return f"Input threshold set to {self.input_threshold:.3f}"

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
            except Exception as exc:  # noqa: BLE001
                self.last_error_message = str(exc)
                self.device_status = f"Audio error: {exc}"
                return False, f"Failed to start audio stream: {exc}"

    def stop(self) -> None:
        with self.lock:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None

    def _audio_callback(self, indata: np.ndarray, outdata: np.ndarray, frames: int, _time: Any, status: sd.CallbackFlags) -> None:
        outdata.fill(0)

        with self.lock:
            if status:
                self.last_error_message = str(status)

            for i in range(frames):
                mic_sample = float(indata[i, 0])
                self.input_level = 0.9 * self.input_level + 0.1 * abs(mic_sample)

                mixed = 0.0
                timeline_pos = self.playhead if self.master_length_samples is not None else self._metronome_free_counter

                if self.master_length_samples is not None:
                    idx = self.playhead % self.master_length_samples
                    if idx == 0:
                        # Quantized track starts: closed tracks begin at master boundary.
                        for track in self.tracks:
                            if track.pending_start and track.has_loop and track.state == TrackState.PLAYING:
                                track.pending_start = False

                    for track in self.tracks:
                        if (
                            track.state in (TrackState.PLAYING, TrackState.OVERDUBBING)
                            and track.has_loop
                            and not track.pending_start
                        ):
                            mixed += float(track.loop_buffer[idx])

                        if track.state == TrackState.OVERDUBBING and track.has_loop:
                            track.loop_buffer[idx] += mic_sample

                # Record pass always captures raw mic; trim/quantize is done on close.
                for track in self.tracks:
                    if track.state == TrackState.RECORDING:
                        track.record_buffer.append(mic_sample)

                mixed += self._metronome_sample(timeline_pos)

                outdata[i, 0] = np.clip(mixed, -1.0, 1.0)

                if self.master_length_samples is not None:
                    self.playhead = (self.playhead + 1) % self.master_length_samples
                self._metronome_free_counter += 1

    def _metronome_sample(self, timeline_pos: int) -> float:
        """Generate one metronome sample aligned to timeline position."""
        if not self.metronome_enabled:
            return 0.0

        spb = self.samples_per_beat
        if timeline_pos % spb == 0:
            beat_index = (timeline_pos // spb) % self.beats_per_bar
            self._click_remaining = max(1, int(0.025 * self.sample_rate))
            self._click_phase = 0.0
            # Accent downbeat.
            self._click_freq = 1700.0 if beat_index == 0 else 1100.0

        if self._click_remaining > 0:
            env = self._click_remaining / max(1, int(0.025 * self.sample_rate))
            sample = 0.25 * env * math.sin(2.0 * math.pi * self._click_phase)
            self._click_phase += self._click_freq / self.sample_rate
            self._click_remaining -= 1
            return sample

        return 0.0

    def _trim_and_quantize(self, raw: np.ndarray, target_len: int | None = None) -> np.ndarray:
        """Trim leading silence and optionally fit to target/master length.

        - Leading silence is removed using `input_threshold`.
        - If target_len is None (master creation), pad to full bars.
        - If target_len is set (non-master), clamp to target and zero-pad.
        """
        if raw.size == 0:
            return raw

        active = np.flatnonzero(np.abs(raw) >= self.input_threshold)
        if active.size == 0:
            return np.zeros(0, dtype=np.float32)

        trimmed = raw[int(active[0]) :].astype(np.float32, copy=False)

        if target_len is None:
            # Master loop ends on the bar boundary.
            bar = self.samples_per_bar
            final_len = max(bar, int(math.ceil(trimmed.size / bar) * bar))
            out = np.zeros(final_len, dtype=np.float32)
            out[: min(final_len, trimmed.size)] = trimmed[:final_len]
            return out

        out = np.zeros(target_len, dtype=np.float32)
        copy_len = min(target_len, trimmed.size)
        out[:copy_len] = trimmed[:copy_len]
        return out

    def toggle_record_overdub(self, track_index: int) -> str:
        with self.lock:
            track = self.tracks[track_index]

            if track.state == TrackState.EMPTY:
                track.record_buffer.clear()
                track.pending_start = False
                track.state = TrackState.RECORDING
                return f"Track {track_index + 1}: recording started"

            if track.state == TrackState.RECORDING:
                raw = np.array(track.record_buffer, dtype=np.float32)
                track.record_buffer.clear()

                if self.master_length_samples is None:
                    processed = self._trim_and_quantize(raw, target_len=None)
                    if processed.size == 0:
                        track.state = TrackState.EMPTY
                        return f"Track {track_index + 1}: no audio above threshold"

                    track.loop_buffer = processed
                    self.master_length_samples = int(processed.size)
                    self.playhead = 0
                    self.transport_running = True

                    for other in self.tracks:
                        if other is not track and other.state == TrackState.RECORDING:
                            other.state = TrackState.EMPTY
                            other.record_buffer.clear()
                            other.pending_start = False

                    track.state = TrackState.PLAYING
                    track.pending_start = False
                    return f"Track {track_index + 1}: loop closed ({self.master_length_samples} samples)"

                processed = self._trim_and_quantize(raw, target_len=self.master_length_samples)
                if processed.size == 0 or not np.any(processed):
                    track.state = TrackState.EMPTY if not track.has_loop else TrackState.PLAYING
                    return f"Track {track_index + 1}: no audio above threshold"

                track.loop_buffer = processed
                track.state = TrackState.PLAYING
                track.pending_start = True
                return f"Track {track_index + 1}: recording closed (starts next master loop)"

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
        with self.lock:
            track = self.tracks[track_index]

            if track.state == TrackState.EMPTY:
                return f"Track {track_index + 1}: already empty"

            if track.state == TrackState.RECORDING:
                track.state = TrackState.STOPPED
                track.record_buffer.clear()
                return f"Track {track_index + 1}: recording stopped"

            track.state = TrackState.STOPPED
            return f"Track {track_index + 1}: stopped"

    def clear_track(self, track_index: int) -> str:
        with self.lock:
            track = self.tracks[track_index]
            track.reset()

            if all(not t.has_loop for t in self.tracks):
                self.master_length_samples = None
                self.playhead = 0
                self.transport_running = False

            return f"Track {track_index + 1}: cleared"

    def get_snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "master_length_samples": self.master_length_samples,
                "playhead": self.playhead,
                "device_status": self.device_status,
                "last_error": self.last_error_message,
                "metronome_enabled": self.metronome_enabled,
                "bpm": self.bpm,
                "time_signature": f"{self.beats_per_bar}/{self.beat_unit}",
                "input_threshold": self.input_threshold,
                "input_level": self.input_level,
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
