from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont

    HAS_PYSTRAY = True
except Exception:  # pragma: no cover - optional dep
    HAS_PYSTRAY = False


class TrayIcon:
    """System-tray icon for Chirp that keeps the app alive in the background."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        on_toggle: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._logger = logger
        self._on_toggle = on_toggle
        self._on_exit = on_exit
        self._icon: Optional[pystray.Icon] = None
        self._recording = False
        self._enabled = HAS_PYSTRAY

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        if self._icon:
            self._icon.title = self._tooltip()
            self._icon.icon = self._create_image(recording=recording)

    def notify_error(self, message: str) -> None:
        if not self._icon:
            return
        try:
            self._icon.notify(message, "Chirp STT")
        except Exception as exc:  # pragma: no cover - shell integration varies
            self._logger.debug("Unable to show tray notification: %s", exc)

    def run(self) -> None:
        if not self._enabled:
            self._logger.warning("pystray not available; tray icon disabled")
            return

        try:
            self._logger.info("Creating tray icon...")
            image = self._create_image(recording=self._recording)
            menu = pystray.Menu(
                pystray.MenuItem("Toggle Recording", self._handle_toggle),
                pystray.MenuItem("Exit", self._handle_exit),
            )
            self._icon = pystray.Icon("chirp", image, self._tooltip(), menu=menu)
            self._logger.info("Tray icon created, starting run loop...")
            self._icon.run()
            self._logger.info("Tray icon run loop ended.")
        except Exception as exc:  # pragma: no cover - tray edge cases
            self._logger.error("Tray icon failed: %s", exc)

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def _tooltip(self) -> str:
        return "Chirp STT — Recording" if self._recording else "Chirp STT — Idle"

    def _handle_toggle(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=self._on_toggle, daemon=True).start()

    def _handle_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=self._on_exit, daemon=True).start()

    @staticmethod
    def _create_image(*, recording: bool = False) -> Image.Image:
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        # Background circle — blue when idle, red when recording
        color = (255, 59, 48) if recording else (0, 122, 255)
        dc.ellipse((0, 0, size - 1, size - 1), fill=color)

        # "C" letter in white, centered
        try:
            font = ImageFont.truetype("segoeui.ttf", 36)
        except Exception:
            font = ImageFont.load_default()

        dc.text((size // 2, size // 2), "C", font=font, fill=(255, 255, 255), anchor="mm")
        return image
