"""
应用日志配置

在 uvicorn 启动前调用 setup_logging()，使 app.* 模块的日志输出到终端。
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    root = logging.getLogger()
    if root.handlers:
        # 避免 reload 时重复添加 handler
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root.setLevel(level)
    root.addHandler(handler)

    # 压低第三方库噪音
    for name in ("httpx", "httpcore", "openai", "chromadb", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
