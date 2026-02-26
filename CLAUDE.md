# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Smart Campus Guide Robot — a voice-interactive campus guide running on Raspberry Pi with offline speech recognition (Vosk), neural TTS (Piper), animated eye display (Pygame), and graph-based navigation (NetworkX). All processing is offline; no cloud dependencies.

## Commands

```bash
# Setup (installs deps, creates DB, checks models)
python setup.py

# Run the robot
python main.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_intent_parser.py -v

# Run a single test
pytest tests/test_navigator.py::test_shortest_path -v

# Reinitialize the database with sample data
python data/init_db.py
```

## Architecture

**State machine controller** (`main.py`) orchestrates modular subsystems:

```
idle → listening → processing → responding → idle
       (wake word    (intent       (TTS
        "hey robot")  parse +       speaks
                      DB query)     response)
```

`CampusRobot` in `main.py` owns all subsystem instances and the main loop. `RobotStateMachine` (python-statemachine) enforces valid state transitions. Error from any state returns to idle.

### Subsystem Modules (in `modules/`)

| Module | Role | Key Detail |
|---|---|---|
| `intent_parser.py` | Classifies user intent + extracts entities | Two-stage: regex patterns → fuzzywuzzy entity extraction (threshold: 70%) |
| `database.py` | SQLite campus data | Uses FTS5 for faculty search with fuzzy fallback; `row_factory = sqlite3.Row` |
| `navigator.py` | Pathfinding on campus graph | NetworkX + Dijkstra; graph loaded from `data/campus_map.json` |
| `speech_recognition.py` | Offline STT | Vosk streaming in background thread; queues results |
| `text_to_speech.py` | Offline neural TTS | Piper generates WAV → PyAudio playback; thread-safe with lock |
| `eye_display.py` | Animated eye expressions | Pygame at 320x240/30fps; expression enum (IDLE, LISTENING, THINKING, SPEAKING, ERROR, SLEEPING) |
| `video_player.py` | Route video playback | python-vlc wrapper |
| `power_monitor.py` | Battery monitoring | I2C reads from INA219 on Waveshare UPS HAT |

### Intent Types

`navigation`, `faculty_info`, `student_lookup`, `department_info`, `greeting`, `farewell`, `help`, `unknown` — defined via regex patterns in `intent_parser.py`.

### Database Schema (defined in `data/init_db.py`)

Six tables: `departments`, `faculty`, `faculty_fts` (FTS5 virtual), `students`, `locations`, `routes`. Pre-populated with sample campus data.

## Configuration

All constants live in `config.py` — paths, thresholds, display geometry, hardware addresses, GPIO pins, LED colors. No config is scattered across modules.

## Platform Graceful Degradation

Every hardware-dependent module falls back on non-Pi platforms:
- Speech recognition → console text input
- TTS → print to stdout
- Eye display → regular Pygame window (instead of framebuffer)
- Video player → mock mode (log only)
- Power monitor → always reports 100%

Detection via `config.is_raspberry_pi()` checking `platform.machine()` and `/proc/device-tree/model`.

## Models (git-ignored, must download manually)

- **Vosk**: `data/vosk-model-small-en-us-0.15/` — from https://alphacephei.com/vosk/models
- **Piper**: `models/en_US-amy-medium.onnx` + `.onnx.json` — from HuggingFace rhasspy/piper-voices

## Key Conventions

- Python 3.9+ required
- All paths use `pathlib.Path` rooted at `config.BASE_DIR`
- Subsystem threads are started in `CampusRobot.start()` and cleaned up in `shutdown()` via signal handler (SIGINT/SIGTERM)
- `is_speaking` threading event prevents speech recognizer from hearing TTS echo
- Tests use pytest fixtures; database tests create temporary in-memory SQLite instances
