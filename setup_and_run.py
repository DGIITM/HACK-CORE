#!/usr/bin/env python3
"""One-command setup + run for KrishiSathi — for anyone this repo gets
shared with. Pure standard library, no dependencies of its own, so it
can bootstrap the venv that everything else needs.

Usage:
    python setup_and_run.py

What it does:
  1. Picks a working Python (avoids 3.14+ — pydantic-core has no
     prebuilt wheel there yet and fails to compile from source; this
     project is validated on 3.10-3.13, with 3.13 the one actually
     used throughout development).
  2. Creates .venv/ if it doesn't exist yet (reuses it otherwise).
  3. Installs requirements.txt into it.
  4. Copies .env.example -> .env if .env doesn't exist yet (never
     overwrites an existing one).
  5. Starts the server and opens the chat UI in your browser.

The app works immediately even with an empty .env: every module has a
real, honestly-labeled fallback for when GEMINI_API_KEY / GOOGLE_CLOUD_
PROJECT aren't set (see CLAUDE.md). Add a free Gemini Developer API key
to .env any time to switch on real Gemini calls — see .env.example.
"""
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
SERVER_URL = "http://localhost:8000/"

# pydantic-core has no prebuilt wheel for 3.14+ yet and fails to compile
# there (PyO3 doesn't support it) — learned the hard way during
# development. 3.10 is a reasonably conservative floor for the rest of
# the dependency set (FastAPI, pydantic v2, etc.).
MIN_PYTHON = (3, 10)
MAX_PYTHON_EXCLUSIVE = (3, 14)


def _log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def _venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _candidate_interpreters():
    """Yields interpreter command lists to try, most-preferred first.
    3.13 is listed first because that's what this project is actually
    developed and tested against."""
    if platform.system() == "Windows":
        for minor in (13, 12, 11, 10):
            yield ["py", f"-3.{minor}"]
        yield ["py", "-3"]
    else:
        for minor in (13, 12, 11, 10):
            yield [f"python3.{minor}"]
        yield ["python3"]
    yield [sys.executable]


def _version_of(cmd: list) -> tuple:
    try:
        result = subprocess.run(
            cmd + ["-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        major, minor = map(int, result.stdout.split())
        return (major, minor)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def find_python() -> list:
    """Returns the command list for the best available Python."""
    seen = set()
    for cmd in _candidate_interpreters():
        key = tuple(cmd)
        if key in seen:
            continue
        seen.add(key)
        version = _version_of(cmd)
        if version is None:
            continue
        if MIN_PYTHON <= version < MAX_PYTHON_EXCLUSIVE:
            _log(f"Using Python {version[0]}.{version[1]} ({' '.join(cmd)})")
            return cmd

    _log(
        f"WARNING: couldn't find a Python between {'.'.join(map(str, MIN_PYTHON))} "
        f"and {'.'.join(map(str, MAX_PYTHON_EXCLUSIVE))} (exclusive) on PATH. Falling "
        "back to the interpreter running this script — if it's 3.14+, installing "
        "dependencies will likely fail building pydantic-core. Install Python 3.13 "
        "from python.org and re-run this script if that happens."
    )
    return [sys.executable]


def ensure_venv() -> None:
    if _venv_python().exists():
        _log(".venv already exists, reusing it.")
        return
    python_cmd = find_python()
    _log("Creating .venv ...")
    subprocess.run(python_cmd + ["-m", "venv", str(VENV_DIR)], check=True, cwd=REPO_ROOT)


def install_requirements() -> None:
    _log("Installing dependencies (first run can take a few minutes) ...")
    try:
        subprocess.run(
            [str(_venv_python()), "-m", "pip", "install", "--upgrade", "pip", "-q"],
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run(
            [str(_venv_python()), "-m", "pip", "install", "-r", "requirements.txt", "-q"],
            check=True,
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError:
        _log(
            "Dependency install failed — if the error above mentions pydantic-core, "
            "Rust, or PyO3, .venv was probably created with an unsupported Python "
            "version (3.14+). Delete the .venv folder and re-run this script with "
            "Python 3.10-3.13 available on PATH."
        )
        raise


def ensure_env_file() -> None:
    env_path = REPO_ROOT / ".env"
    example_path = REPO_ROOT / ".env.example"
    if env_path.exists():
        return
    if not example_path.exists():
        _log("WARNING: .env.example is missing, skipping .env setup.")
        return
    shutil.copyfile(example_path, env_path)
    _log("Created .env from .env.example — runs fully in offline/fallback mode by default.")
    _log(
        "Add a free Gemini Developer API key to .env any time for real Gemini calls: "
        "https://aistudio.google.com/apikey"
    )


def _wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(SERVER_URL, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_server() -> None:
    _log("Starting KrishiSathi ...")
    proc = subprocess.Popen([str(_venv_python()), "run.py"], cwd=REPO_ROOT)
    try:
        if _wait_for_server():
            _log(f"Ready! Opening {SERVER_URL} in your browser ...")
            try:
                webbrowser.open(SERVER_URL)
            except Exception:
                pass
        else:
            _log("Server didn't respond within 30s — check the output above for errors.")

        _log("Press Ctrl+C to stop the server.")
        proc.wait()
    except KeyboardInterrupt:
        _log("Stopping ...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    _log(f"KrishiSathi setup — repo root: {REPO_ROOT}")
    ensure_venv()
    install_requirements()
    ensure_env_file()
    run_server()


if __name__ == "__main__":
    main()
