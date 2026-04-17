"""Loop track data model for the BeatBoxLooper prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class TrackState(str, Enum):
    """Public states shown in the UI."""

    EMPTY = "Empty"
    RECORDING = "Recording"
    PLAYING = "Playing"
    OVERDUBBING = "Overdubbing"
    STOPPED = "Stopped"


@dataclass
class LoopTrack:
    """A single track's loop and state container.

    The engine writes/reads this object from the real-time callback while
    state transitions are controlled by UI-triggered methods under a lock.
    """

    index: int
    state: TrackState = TrackState.EMPTY
    loop_buffer: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    # Temporary buffer used while recording the first pass.
    record_buffer: list[float] = field(default_factory=list)
    # Write position for fixed-length overdub/record-to-master-length operations.
    record_pos: int = 0
    # If True, playback waits for master loop boundary (playhead=0) before sounding.
    pending_start: bool = False

    @property
    def has_loop(self) -> bool:
        """Return True if the track contains any loop samples."""
        return self.loop_buffer.size > 0

    def reset(self) -> None:
        """Clear all audio/state data for this track."""
        self.state = TrackState.EMPTY
        self.loop_buffer = np.zeros(0, dtype=np.float32)
        self.record_buffer.clear()
        self.record_pos = 0
        self.pending_start = False
