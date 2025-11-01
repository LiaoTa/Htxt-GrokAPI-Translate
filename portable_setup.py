"""
通用工具：提供專案根目錄定位與 .env 載入功能，方便腳本以便攜方式執行。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent


def project_path(*parts: str) -> Path:
    """
    取得相對於專案根目錄的路徑。
    """
    return BASE_DIR.joinpath(*parts)


def load_env(env_filename: str = ".env", override: bool = False) -> None:
    """
    將專案根目錄下的 .env 檔案載入成環境變數。
    """
    env_path = project_path(env_filename)
    if not env_path.exists():
        return

    for line in _read_env_lines(env_path):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        if not override and key in os.environ:
            continue
        os.environ[key] = value


def _read_env_lines(env_path: Path) -> Iterator[str]:
    """
    讀取 .env，忽略空行與註解。
    """
    with env_path.open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            yield line


__all__ = ["BASE_DIR", "project_path", "load_env"]
