from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

try:
    import keyboard
except ImportError:  # pragma: no cover - exercised only in incomplete envs
    keyboard = None

_MODIFIER_VKS: dict[str, tuple[int, ...]] = {
    "ctrl": (0x11, 0xA2, 0xA3),
    "shift": (0x10, 0xA0, 0xA1),
    "alt": (0x12, 0xA4, 0xA5),
    "win": (0x5B, 0x5C),
}


def modifier_vk_groups(shortcut: str) -> list[tuple[int, ...]]:
    keys = [key.strip().lower() for key in shortcut.split("+") if key.strip()]
    if not keys:
        raise ValueError("shortcut must not be empty")
    groups: list[tuple[int, ...]] = []
    for key in keys:
        group = _MODIFIER_VKS.get(key)
        if group is None:
            return []
        groups.append(group)
    return groups


class WindowsModifierHotkeyPoller:
    def __init__(
        self,
        shortcut: str,
        callback: Callable[[], None],
        *,
        logger: logging.Logger,
        interval: float = 0.01,
    ) -> None:
        self._shortcut = shortcut
        self._callback = callback
        self._logger = logger
        self._interval = interval
        self._vk_groups = modifier_vk_groups(shortcut)
        if not self._vk_groups:
            raise ValueError(f"shortcut is not modifier-only: {shortcut!r}")
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="WindowsModifierHotkeyPoller",
            daemon=True,
        )
        self._user32 = None

    def start(self) -> None:
        import ctypes

        self._user32 = ctypes.windll.user32
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _is_vk_down(self, vk: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def _is_group_down(self, group: tuple[int, ...]) -> bool:
        return any(self._is_vk_down(vk) for vk in group)

    def _is_chord_down(self) -> bool:
        return all(self._is_group_down(group) for group in self._vk_groups)

    def _all_chord_keys_up(self) -> bool:
        return not any(self._is_group_down(group) for group in self._vk_groups)

    def _run(self) -> None:
        armed = True
        while not self._stop_event.wait(self._interval):
            if armed and self._is_chord_down():
                armed = False
                try:
                    self._callback()
                except Exception as exc:
                    self._logger.exception("Hotkey callback failed for %s: %s", self._shortcut, exc)
            elif not armed and self._all_chord_keys_up():
                armed = True


class KeyboardShortcutManager:
    def __init__(self, *, logger: logging.Logger) -> None:
        self._logger = logger
        self._listeners: list[object] = []
        self._hotkeys: list[object] = []

    def register(self, shortcut: str, callback: Callable[[], None]) -> None:
        if sys.platform.startswith("win") and modifier_vk_groups(shortcut):
            listener = WindowsModifierHotkeyPoller(shortcut, callback, logger=self._logger)
            try:
                listener.start()
            except Exception as exc:  # pragma: no cover - runtime safety
                self._logger.error("Failed to register modifier hotkey %s: %s", shortcut, exc)
                raise
            self._listeners.append(listener)
            return

        keys = [k.strip() for k in shortcut.split("+") if k.strip()]
        if keyboard is None:
            raise RuntimeError("keyboard package is required for non modifier-only shortcuts")

        def _wrapped() -> None:
            callback()

        # Only single-key hotkeys can use trigger_on_release=True. For combinations,
        # ``keyboard`` resolves nonblocking hotkeys against ``_pressed_events`` in
        # ``pre_process_event`` *after* the releasing key is removed, so the chord
        # no longer matches on KEY_UP and the callback never runs (e.g. ctrl+shift).
        try:
            hotkey = keyboard.add_hotkey(
                shortcut,
                _wrapped,
                trigger_on_release=len(keys) == 1,
            )
        except Exception as exc:  # pragma: no cover - runtime safety
            self._logger.error("Failed to register hotkey %s: %s", shortcut, exc)
            raise
        self._hotkeys.append(hotkey)

    def send(self, combination: str) -> None:
        if keyboard is None:
            raise RuntimeError("keyboard package is required for keyboard send")
        keyboard.send(combination)

    def write(self, text: str) -> None:
        if keyboard is None:
            raise RuntimeError("keyboard package is required for keyboard write")
        keyboard.write(text)

    def wait(self) -> None:
        if keyboard is None:
            raise RuntimeError("keyboard package is required for keyboard wait")
        keyboard.wait()

    def stop(self) -> None:
        while self._listeners:
            listener = self._listeners.pop()
            try:
                listener.stop()
            except Exception:
                pass
        if keyboard is not None:
            while self._hotkeys:
                hotkey = self._hotkeys.pop()
                try:
                    keyboard.remove_hotkey(hotkey)
                except Exception:
                    pass
