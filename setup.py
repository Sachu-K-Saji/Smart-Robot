"""
Campus Robot Bootstrap Script
Sets up the project: creates database, checks dependencies,
downloads models (with user confirmation).
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def check_python_version():
    """Ensure Python 3.9+."""
    if sys.version_info < (3, 9):
        print(f"ERROR: Python 3.9+ required, found {sys.version}")
        sys.exit(1)
    print(f"Python version: {sys.version}")


def install_requirements():
    """Install pip dependencies from requirements.txt."""
    req_file = BASE_DIR / "requirements.txt"
    print(f"\nInstalling dependencies from {req_file}...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r", str(req_file)
    ])
    print("Dependencies installed successfully.")


def create_database():
    """Initialize the SQLite database with schema and sample data."""
    print("\nCreating campus database...")
    sys.path.insert(0, str(BASE_DIR))
    from data.init_db import create_database as init_db
    init_db()
    print("Database created successfully.")


def check_models():
    """Check if required model files exist and provide download instructions."""
    vosk_dir = BASE_DIR / "data" / "vosk-model-small-en-us-0.15"
    piper_model = BASE_DIR / "models" / "en_US-amy-medium.onnx"
    piper_config = BASE_DIR / "models" / "en_US-amy-medium.onnx.json"

    print("\nChecking model files...")

    if not vosk_dir.exists():
        print(f"  MISSING: Vosk model at {vosk_dir}")
        print("  Download from: https://alphacephei.com/vosk/models")
        print("  File: vosk-model-small-en-us-0.15.zip (~40MB)")
        print(f"  Extract to: {vosk_dir}")
    else:
        print(f"  OK: Vosk model found at {vosk_dir}")

    if not piper_model.exists():
        print(f"  MISSING: Piper model at {piper_model}")
        print("  Download .onnx from:")
        print("  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
              "en/en_US/amy/medium/en_US-amy-medium.onnx")
    else:
        print(f"  OK: Piper model found at {piper_model}")

    if not piper_config.exists():
        print(f"  MISSING: Piper config at {piper_config}")
        print("  Download .onnx.json from:")
        print("  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
              "en/en_US/amy/medium/en_US-amy-medium.onnx.json")
    else:
        print(f"  OK: Piper config found at {piper_config}")


def create_directories():
    """Ensure all required directories exist."""
    dirs = [
        BASE_DIR / "data",
        BASE_DIR / "models",
        BASE_DIR / "videos",
        BASE_DIR / "modules",
        BASE_DIR / "tests",
    ]
    for d in dirs:
        d.mkdir(exist_ok=True)
    print("Directory structure verified.")


def run_tests():
    """Run the test suite."""
    print("\nRunning tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(BASE_DIR / "tests"), "-v"],
        cwd=str(BASE_DIR),
    )
    if result.returncode == 0:
        print("\nAll tests passed!")
    else:
        print(f"\nSome tests failed (exit code {result.returncode}).")


def main():
    print("=" * 60)
    print("  Campus Guide Robot - Setup Script")
    print("=" * 60)

    check_python_version()
    create_directories()
    install_requirements()
    create_database()
    check_models()

    run_tests_input = input("\nRun tests now? [y/N]: ").strip().lower()
    if run_tests_input == "y":
        run_tests()

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("  To start the robot: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
