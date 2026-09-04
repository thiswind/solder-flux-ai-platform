from __future__ import annotations

import os
import subprocess
from pathlib import Path


def resolve_yunxi_python() -> str:
    candidates = [
        Path(r"C:\Users\DKE\.conda\envs\yunxi\python.exe"),
        Path(r"E:\Anaconda\envs\yunxi\python.exe"),
        Path.home() / ".conda" / "envs" / "yunxi" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "未找到 yunxi 环境的 python.exe，请确认 conda 环境 `yunxi` 已创建。"
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent
    # 仓库根（platforms/data/backend -> Yunxi_Project），用于 import shared.auth_client
    repo_root = project_root.parent.parent
    env = os.environ.copy()
    python_path = str(project_root) + os.pathsep + str(repo_root)
    env["PYTHONPATH"] = python_path if not env.get("PYTHONPATH") else python_path + os.pathsep + env["PYTHONPATH"]
    env.setdefault("PYTHONUTF8", "1")
    python_executable = resolve_yunxi_python()

    env["PYTHONHOME"] = str(Path(python_executable).resolve().parent)

    print(f"[Yunxi Data] project root: {project_root}", flush=True)
    print(f"[Yunxi Data] python: {python_executable}", flush=True)
    print("[Yunxi Data] starting uvicorn on http://127.0.0.1:8000", flush=True)

    subprocess.run(
        [
            python_executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--reload",
        ],
        cwd=str(project_root),
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
