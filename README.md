# Smart Campus Guide Robot

An interactive campus guide robot that helps students, visitors, and staff navigate the campus, look up faculty and student information, and find department details — all through voice interaction.

Built for **Raspberry Pi** with offline speech recognition and text-to-speech, an animated eye display, and video-based navigation guides.

## Features

- **Voice Interaction** — Offline speech recognition (Vosk) and neural text-to-speech (Piper)
- **Campus Navigation** — Graph-based pathfinding with step-by-step spoken directions
- **Faculty Lookup** — Search for professors by name, get office locations and contact info
- **Student Lookup** — Find students by name or roll number
- **Department Info** — Building locations, HOD details, and contact numbers
- **Animated Eye Display** — Pygame-based expressions (idle, listening, thinking, speaking, error)
- **Video Playback** — Pre-recorded route videos for visual navigation guidance
- **Battery Monitoring** — UPS HAT integration with low/critical battery warnings
- **State Machine Architecture** — Clean state transitions: idle → listening → processing → responding

## Hardware

| Component | Purpose |
|---|---|
| Raspberry Pi 4/5 | Main compute |
| ReSpeaker 2-Mic HAT | Microphone input |
| Small display (320x240) | Eye animation |
| Speaker | Audio output |
| Waveshare UPS HAT | Battery monitoring |

> The software gracefully degrades on non-Pi platforms for development and testing.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Sachu-K-Saji/Smart-Robot.git
cd Smart-Robot
```

### 2. Run setup

```bash
python setup.py
```

This will:
- Verify Python 3.9+
- Install pip dependencies
- Initialize the SQLite database with sample data
- Check for required model files

### 3. Download models

**Vosk** (speech recognition, ~40MB):
- Download `vosk-model-small-en-us-0.15` from [Vosk Models](https://alphacephei.com/vosk/models)
- Extract to `data/vosk-model-small-en-us-0.15/`

**Piper** (text-to-speech):
- Download [`en_US-amy-medium.onnx`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx)
- Download [`en_US-amy-medium.onnx.json`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json)
- Place both in `models/`

### 4. Start the robot

```bash
python main.py
```

Say **"hey robot"** followed by your question to interact.

## Project Structure

```
├── main.py                 # Entry point and state machine controller
├── config.py               # All configuration constants
├── setup.py                # Bootstrap script
├── requirements.txt        # Python dependencies
├── data/
│   ├── campus_map.json     # Navigation graph (nodes + edges)
│   └── init_db.py          # Database schema and sample data
├── models/                 # Vosk and Piper model files
├── modules/
│   ├── speech_recognition.py   # Vosk-based offline STT
│   ├── text_to_speech.py       # Piper-based offline TTS
│   ├── intent_parser.py        # Fuzzy intent + entity extraction
│   ├── navigator.py            # Graph pathfinding with NetworkX
│   ├── database.py             # SQLite campus database
│   ├── eye_display.py          # Pygame animated eyes
│   ├── video_player.py         # VLC-based video playback
│   └── power_monitor.py        # UPS HAT battery monitoring
├── tests/                  # Pytest test suite
└── videos/                 # Pre-recorded navigation videos
```

## Usage Examples

| Say this | The robot will |
|---|---|
| "Hey robot, where is the library?" | Give spoken directions from the main gate to the library |
| "Hey robot, tell me about Professor Smith" | Share their department, office, and email |
| "Hey robot, look up roll number 101" | Return the student's name, department, and section |
| "Hey robot, what departments do you have?" | List all departments on campus |

## Dependencies

- Python 3.9+
- [Vosk](https://alphacephei.com/vosk/) — offline speech recognition
- [Piper](https://github.com/rhasspy/piper) — offline neural TTS
- [Pygame](https://www.pygame.org/) — eye display animation
- [NetworkX](https://networkx.org/) — graph-based navigation
- [python-vlc](https://pypi.org/project/python-vlc/) — video playback
- [python-statemachine](https://pypi.org/project/python-statemachine/) — state machine framework
- [fuzzywuzzy](https://pypi.org/project/fuzzywuzzy/) — fuzzy string matching for intent parsing

## Running Tests

```bash
pytest tests/ -v
```

## License

This project is developed for educational purposes.
