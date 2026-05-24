from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def venv_python() -> str:
    for venv_dir in (".venv", "venv"):
        if os.name == "nt":
            candidate = PROJECT_ROOT / venv_dir / "Scripts" / "python.exe"
        else:
            candidate = PROJECT_ROOT / venv_dir / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    if os.name == "nt":
        return str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
    return str(PROJECT_ROOT / ".venv" / "bin" / "python")


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    python = venv_python()
    if not Path(python).exists():
        print("Could not find the virtual-environment Python. Create .venv first.", file=sys.stderr)
        return 1

    backend_cmd = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "backend",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    frontend_cmd = [npm_command(), "run", "dev", "--", "-p", "6001"]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    print("Starting Jubidate AI — Multi-Agent Strategic Intelligence Platform...")
    print("Backend:  http://127.0.0.1:8000")
    print("Frontend: http://127.0.0.1:6001")
    print("Press Ctrl+C once to stop both processes.\n")

    backend = subprocess.Popen(backend_cmd, cwd=PROJECT_ROOT, env=env)
    frontend = subprocess.Popen(frontend_cmd, cwd=PROJECT_ROOT / "frontend", env=env)

    try:
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            if backend_code is not None:
                print(f"Backend exited with code {backend_code}. Stopping frontend...")
                stop_process(frontend)
                return backend_code
            if frontend_code is not None:
                print(f"Frontend exited with code {frontend_code}. Stopping backend...")
                stop_process(backend)
                return frontend_code
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping both processes...")
        stop_process(frontend)
        stop_process(backend)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
