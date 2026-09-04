from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def resolve_yunxi_python() -> str:
    """定位 yunxi conda 环境的 python.exe。

    优先级：环境变量 YUNXI_PYTHON > 当前用户 .conda > 常见 Anaconda 安装位置。
    注意：必须使用 yunxi 环境，base 环境的 sklearn 版本会导致模型加载失败。
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


def main() -> None:
    project_root = Path(__file__).resolve().parent
    backend_root = project_root / "backend"
    # 仓库根（platforms/data -> Yunxi_Project），用于 import shared.auth_client（SSO 验签）
    repo_root = project_root.parent.parent
    env = os.environ.copy()
    python_path = str(backend_root) + os.pathsep + str(repo_root)
    env["PYTHONPATH"] = python_path if not env.get("PYTHONPATH") else python_path + os.pathsep + env["PYTHONPATH"]
    env.setdefault("PYTHONUTF8", "1")
    python_executable = resolve_yunxi_python()

    print(f"[Yunxi] backend root: {backend_root}", flush=True)
    print(f"[Yunxi] python: {python_executable}", flush=True)
    print("[Yunxi] starting uvicorn on http://127.0.0.1:8000", flush=True)

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
        cwd=str(backend_root),
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
