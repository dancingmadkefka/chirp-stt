from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Sequence

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


def find_input_devices(
    preferred_name: str,
    preferred_host_apis: Optional[Sequence[str]] = None,
) -> list[int]:
    """Find all matching input device indices, ordered by host-API preference."""
    if not preferred_name:
        return []

    try:
        host_apis = sd.query_hostapis()
    except (AttributeError, OSError):
        return []

    host_api_names = [api["name"] for api in host_apis]
    if preferred_host_apis is None:
        preferred_host_apis = ("WASAPI",)
    preferred_patterns = [pattern.lower() for pattern in preferred_host_apis]

    def _host_api_priority(host_api_idx: int) -> int:
        name = host_api_names[host_api_idx].lower()
        for priority, pattern in enumerate(preferred_patterns):
            if pattern in name:
                return priority
        return len(preferred_patterns)

    try:
        n_devices = sd.query_devices().__len__()
    except (AttributeError, OSError):
        return []

    candidates: list[tuple[int, int, str]] = []  # (priority, device_idx, name)
    for i in range(n_devices):
        dev = sd.query_devices(i)
        if dev["max_input_channels"] <= 0:
            continue
        if preferred_name.lower() not in dev["name"].lower():
            continue
        host_api = dev["hostapi"]
        priority = _host_api_priority(host_api)
        candidates.append((priority, i, dev["name"]))

    if not candidates:
        return []

    candidates.sort()
    return [i for _, i, _ in candidates]


def find_input_device(
    preferred_name: str,
    preferred_host_apis: Optional[Sequence[str]] = None,
) -> Optional[int]:
    devices = find_input_devices(preferred_name, preferred_host_apis=preferred_host_apis)
    if not devices:
        return None
    logger.info(
        "Selected input device %d: %s (preferred_mic=%r)",
        devices[0],
        sd.query_devices(devices[0])["name"],
        preferred_name,
    )
    return devices[0]


class AudioCapture:
    """Captures audio using either on-demand or always-open streams.

    ``keep_stream_open=False`` (default) opens the input device only while
    recording.  This lets Bluetooth headsets leave their voice profile when
    Chirp is idle.

    ``keep_stream_open=True`` opens the stream once (``open()``) and keeps it
    running for the lifetime of the app.  ``start()`` / ``stop()`` only control
    whether incoming frames are collected.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        channels: int = 1,
        dtype: str = "float32",
        device: Optional[int] = None,
        fallback_devices: Optional[Sequence[Optional[int]]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        keep_stream_open: bool = False,
    ) -> None:
        self.sample_rate = sample_rate
        self._requested_sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self._device = device
        candidates = list(fallback_devices or [device])
        if None not in candidates:
            candidates.append(None)
        self._fallback_devices = tuple(candidates)
        self._status_callback = status_callback
        self.keep_stream_open = keep_stream_open
        self._stream: Optional[sd.InputStream] = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._collecting = False

    # -- lifecycle -------------------------------------------------------------

    def open(self) -> None:
        """Prepare capture; only opens the device in always-open mode."""
        if self.keep_stream_open:
            self._open_stream()
        else:
            logger.info("Audio stream will open on demand while recording")

    def close(self) -> None:
        """Stop and close the underlying stream (call at shutdown)."""
        with self._lock:
            self._collecting = False
        self._close_stream()

    def _open_stream(self) -> None:
        if self._stream is not None:
            return

        candidates = list(self._fallback_devices)
        def _callback(
            indata: np.ndarray,
            _frames: int,
            _time: object,
            status: object,
        ) -> None:  # type: ignore[name-defined]
            if status and self._status_callback:
                self._status_callback(str(status))
            with self._lock:
                if self._collecting:
                    self._frames.append(indata.copy())

        if not candidates:
            candidates = [self._device]

        last_error: Optional[Exception] = None
        for candidate in candidates:
            rates = [self._requested_sample_rate]
            try:
                device_info = sd.query_devices(candidate, "input")
                native_rate = int(device_info["default_samplerate"])
                if native_rate not in rates:
                    rates.append(native_rate)
            except Exception:
                pass

            for rate in rates:
                stream: Optional[sd.InputStream] = None
                try:
                    stream = sd.InputStream(
                        samplerate=rate,
                        channels=self.channels,
                        dtype=self.dtype,
                        device=candidate,
                        callback=_callback,
                    )
                    stream.start()
                    self._stream = stream
                    self._device = candidate
                    self.sample_rate = rate
                    self._fallback_devices = (candidate,) + tuple(
                        item for item in self._fallback_devices if item != candidate
                    )
                    break
                except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                    last_error = exc
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
                    logger.debug(
                        "Input stream attempt failed (device=%s, rate=%s): %s",
                        candidate,
                        rate,
                        exc,
                    )
            if self._stream is not None:
                break

        if self._stream is None:
            raise last_error or RuntimeError("Unable to open any configured input device")

        if self._device is not None:
            dev_name = sd.query_devices(self._device)["name"]
        else:
            dev_name = "system default"
        mode = "always-open" if self.keep_stream_open else "on-demand"
        logger.info(
            "Audio stream opened (device: %s, rate: %s Hz, mode: %s)",
            dev_name,
            self.sample_rate,
            mode,
        )

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()
        logger.debug("Audio stream closed")

    # -- recording toggle ------------------------------------------------------

    def start(self) -> None:
        """Begin collecting audio frames, opening the device if needed."""
        with self._lock:
            self._frames.clear()
            self._collecting = True
        try:
            self._open_stream()
        except Exception:
            with self._lock:
                self._collecting = False
            raise

    def stop(self) -> np.ndarray:
        """Stop collecting and return the recorded audio."""
        with self._lock:
            self._collecting = False
            if self._frames:
                audio = np.concatenate(self._frames, axis=0)
                self._frames.clear()
            else:
                audio = np.empty(0, dtype=self.dtype)
        if not self.keep_stream_open:
            self._close_stream()
        if self.channels == 1:
            audio = audio.reshape(-1)
        return audio.astype(np.float32, copy=False)
