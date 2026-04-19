# BeatBoxLooper v1 Prototype

A minimal Windows desktop beatbox looper prototype built in Python.

This app is inspired by the *workflow* of hardware loop stations like the RC-505 MKII: five visible tracks, large performance buttons, and quick hands-on loop layering.

## What version 1 does

- Uses your default microphone input and default output device.
- Provides **5 loop tracks**.
- Per track:
  - **Record / Overdub**
  - **Stop**
  - **Clear**
  - State display: `Empty`, `Recording`, `Playing`, `Overdubbing`, `Stopped`
- First completed recording defines the **master loop length**.
- Built-in click-track **metronome** (default 120 BPM, 4/4) to guide timing.
- First completed recording is automatically **quantized to the nearest beat** and defines the master loop length.
- Additional tracks stay synchronized to that master loop clock.
- Supports simple overdubbing by mixing incoming mic audio into an existing loop.
- Uses a dark, performance-oriented UI.

## Version 1 limitations (intentional)

- No effects, BPM detection, MIDI, pitch shifting, time stretching.
- No save/export, no cloud, no account system.
- No waveform editor.
- Additional tracks are designed to follow the master loop length for stable sync.
- Device selection UI is not implemented yet (engine is structured so it can be added later).

## Requirements

- Windows 10/11
- Python 3.10+
- A working microphone/audio interface configured as default input

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Build a Windows `.exe` with PyInstaller

Install PyInstaller (already listed in `requirements.txt`) and run:

```bash
pyinstaller --noconfirm --windowed --name BeatBoxLooper --onefile main.py
```

Output executable will appear in:

- `dist/BeatBoxLooper.exe`

If audio backend DLLs are missing on your machine, run a non-onefile build first:

```bash
pyinstaller --noconfirm --windowed --name BeatBoxLooper main.py
```

## Project structure

```text
BeatBoxLooper/
├─ main.py
├─ requirements.txt
├─ audio/
│  └─ engine.py
├─ models/
│  └─ loop_track.py
└─ gui/
   ├─ main_window.py
   └─ track_widget.py
```

## Notes for future extension

The code is split into GUI, loop-track model, and audio engine so that features like device dropdowns, per-track volume/mute, metronome, keyboard controls, and project save/load can be added later without rewriting the whole prototype.
