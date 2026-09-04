"""启动门户后端 uvicorn (端口 8003)。

注意：必须使用 yunxi conda 环境，base / 系统 Python 可能缺少 PyJWT，
会导致登录接口 500（Unexpected token 'l', "Internal S"... is not valid JSON）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def resolve_yunxi_python() -> str:
    """定位 yunxi conda 环境的 python.exe。

    优先级：环境变量 YUNXI_PYTHON > 当前用户 .conda > 常见 Anaconda 安装位置。
    """
    override = os.getenv("YUNXI_PYTHON")
    if override and Path(override).exists():
        return override

    candidates = [
        Path.home() / ".conda" / "envs" / "yunxi" / "python.exe",
        Path(r"C:\Users\DKE\.conda\envs\yunxi\python.exe"),
        Path(r"E:\Anaconda\envs\yunxi\python.exe"),
        Path(r"D:\develop\Anaconda\envs\yunxi\python.exe"),
        Path(r"C:\ProgramData\Anaconda3\envs\yunxi\python.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "未找到 yunxi 环境的 python.exe。\n"
        "请确认 conda 环境 `yunxi` 已创建，或设置环境变量 YUNXI_PYTHON 指向对应的 python.exe。"
    )


def main() -> int:
    project_root = Path(__file__).resolve().parent
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
    python_executable = resolve_yunxi_python()

    print(f"[Yunxi Portal] python: {python_executable}", flush=True)
    print("[Yunxi Portal] starting uvicorn on http://0.0.0.0:8003", flush=True)

    return subprocess.run(
        [
            python_executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8003",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())