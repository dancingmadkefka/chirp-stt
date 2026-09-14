from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


def _has_console() -> bool:
    return sys.stdout is not None and sys.stderr is not None


def get_logger(name: str = "chirp", *, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        return logger

    if _has_console():
        console = Console(force_terminal=True)
        handler: logging.Handler = RichHandler(console=console, show_time=True, markup=False)
    else:
        # Running under pythonw.exe — no console available; log to file
        log_dir = Path.home() / ".chirp"
        log_dir.mkdir(exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "chirp.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )

    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def configure_root(level: int = logging.INFO) -> None:
    if _has_console():
        logging.basicConfig(level=level, handlers=[RichHandler(console=Console(force_terminal=True))])
    else:
        log_dir = Path.home() / ".chirp"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=level,
            handlers=[
                RotatingFileHandler(
                    log_dir / "chirp.log",
                    maxBytes=2 * 1024 * 1024,
                    backupCount=2,
                    encoding="utf-8",
                )
            ],
        )
