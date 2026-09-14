from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import ctypes
import logging
import os
import platform
import sys
import threading
import time
from ctypes import wintypes
from typing import Generator, Optional, Sequence

import numpy as np

from rich.console import Console
from rich.logging import RichHandler

from .audio_capture import AudioCapture, find_input_devices
from .audio_feedback import AudioFeedback
from .config_manager import ConfigManager
from .keyboard_shortcuts import KeyboardShortcutManager
from .logger import get_logger
from .parakeet_manager import ModelNotPreparedError, ParakeetManager
from .recording_overlay import RecordingOverlay, enable_dpi_awareness
from .text_injector import TextInjector
from .tray_icon import TrayIcon


class ChirpApp:
    def __init__(self, *, verbose: bool = False) -> None:
        level = logging.DEBUG if verbose else logging.INFO
        self.logger = get_logger(level=level)
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        model_dir = self.config_manager.model_dir(self.config.parakeet_model, self.config.parakeet_quantization)
        self.logger.debug(
            "Environment: platform=%s python=%s config=%s models=%s",
            platform.platform(),
            platform.python_version(),
            self.config_manager.config_path,
            self.config_manager.models_root,
        )
        self.logger.debug(
            "Config summary: model=%s quantization=%s provider=%s threads=%s paste_mode=%s",
            self.config.parakeet_model,
            self.config.parakeet_quantization or "none",
            self.config.onnx_providers,
            self.config.threads,
            self.config.paste_mode,
        )

        self.keyboard = KeyboardShortcutManager(logger=self.logger)
        input_host_apis = (
            ("WASAPI", "MME", "DirectSound")
            if self.config.audio_capture_mode == "on_demand"
            else ("WASAPI", "DirectSound", "MME")
        )
        input_devices = find_input_devices(
            self.config.preferred_mic,
            preferred_host_apis=input_host_apis,
        )
        input_device = input_devices[0] if input_devices else None
        self.audio_capture = AudioCapture(
            status_callback=self._log_capture_status,
            device=input_device,
            fallback_devices=input_devices,
            keep_stream_open=self.config.audio_capture_mode == "always_open",
        )
        self.audio_feedback = AudioFeedback(
            logger=self.logger,
            enabled=self.config.audio_feedback,
            volume=self.config.audio_feedback_volume,
        )
        self.recording_overlay = RecordingOverlay(
            logger=self.logger,
            enabled=self.config.recording_overlay,
        )

        console = None
        for handler in self.logger.handlers:
            if isinstance(handler, RichHandler):
                console = handler.console
                break
        if not console:
            console = Console(stderr=True)

        def _has_real_console() -> bool:
            try:
                return sys.stdout is not None and sys.stdout.isatty()
            except Exception:
                return False

        try:
            self.recording_overlay.show("loading")
            if _has_real_console():
                with console.status("[bold green]Initializing Parakeet model...[/bold green]", spinner="dots"):
                    self.parakeet = ParakeetManager(
                        model_name=self.config.parakeet_model,
                        quantization=self.config.parakeet_quantization,
                        provider_key=self.config.onnx_providers,
                        threads=self.config.threads,
                        logger=self.logger,
                        model_dir=model_dir,
                        timeout=self.config.model_timeout,
                        loading_state_callback=self._handle_model_loading_state,
                    )
            else:
                self.logger.info("Initializing Parakeet model...")
                self.parakeet = ParakeetManager(
                    model_name=self.config.parakeet_model,
                    quantization=self.config.parakeet_quantization,
                    provider_key=self.config.onnx_providers,
                    threads=self.config.threads,
                    logger=self.logger,
                    model_dir=model_dir,
                    timeout=self.config.model_timeout,
                    loading_state_callback=self._handle_model_loading_state,
                )
        except ModelNotPreparedError as exc:
            self.logger.error(str(exc))
            raise SystemExit(1) from exc
        finally:
            self.recording_overlay.hide()
        self.text_injector = TextInjector(
            keyboard_manager=self.keyboard,
            logger=self.logger,
            injection_mode=self.config.injection_mode,
            paste_mode=self.config.paste_mode,
            word_overrides=self.config.word_overrides,
            post_processing=self.config.post_processing,
            clipboard_behavior=self.config.clipboard_behavior,
            clipboard_clear_delay=self.config.clipboard_clear_delay,
        )

        self._recording = False
        self._lock = threading.Lock()
        self._stop_timer: Optional[threading.Timer] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="Transcriber")
        self._exit_event = threading.Event()
        self._tray_thread: Optional[threading.Thread] = None
        self._tray = TrayIcon(
            logger=self.logger,
            on_toggle=self.toggle_recording,
            on_exit=self._request_exit,
        )

    def run(self) -> None:
        try:
            self.audio_capture.open()
            self._register_hotkey()
            self.logger.info("Chirp ready. Toggle recording with %s", self.config.primary_shortcut)
            if self._tray.enabled:
                self._tray_thread = threading.Thread(
                    target=self._tray.run,
                    daemon=False,
                    name="TrayIcon",
                )
                self._tray_thread.start()
            # Block until exit is requested; keyboard.wait() doesn't work under pythonw.exe
            self._exit_event.wait()
        except KeyboardInterrupt:
            self.logger.info("Interrupted, exiting.")
        except Exception as exc:
            self.logger.exception("Unhandled error in main loop: %s", exc)
            self._write_crash_log(exc)
        finally:
            self._shutdown()

    @staticmethod
    def _write_crash_log(exc: Exception) -> None:
        import traceback as _tb
        from pathlib import Path as _Path
        try:
            crash_path = _Path.home() / ".chirp" / "crash.log"
            crash_path.parent.mkdir(exist_ok=True)
            with open(crash_path, "a", encoding="utf-8") as f:
                f.write(f"--- CRASH at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                f.write(_tb.format_exc())
                f.write("\n")
        except Exception:
            pass

    def _register_hotkey(self) -> None:
        self.logger.debug("Registering hotkey: %s", self.config.primary_shortcut)
        try:
            self.keyboard.register(self.config.primary_shortcut, self._handle_hotkey)
        except Exception:
            self.logger.error("Unable to register primary shortcut. Run as Administrator on Windows.")
            raise

    def _handle_hotkey(self) -> None:
        try:
            self.toggle_recording()
        except Exception as exc:  # pragma: no cover - hotkey thread safety
            self.logger.exception("Hotkey handler failed: %s", exc)
            self._recover_from_hotkey_failure()

    def _recover_from_hotkey_failure(self) -> None:
        with self._lock:
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            self._recording = False
        try:
            self.audio_capture.stop()
        except Exception:
            pass
        try:
            self.recording_overlay.hide()
        except Exception:
            pass
        try:
            self.audio_feedback.play_error(self.config.error_sound_path)
        except Exception:
            pass

    def toggle_recording(self) -> None:
        with self._lock:
            if not self._recording:
                self._start_recording()
            else:
                self._stop_recording()

    def _start_recording(self) -> None:
        self.logger.debug("Starting audio capture")
        try:
            self.audio_capture.start()
        except Exception as exc:
            self.logger.error("Audio capture start failed: %s", exc)
            self._tray.notify_error(
                "Could not open the microphone. Chirp is still running; try again or check the log."
            )
            self.audio_feedback.play_error(self.config.error_sound_path)
            return
        self._recording = True
        self._tray.set_recording(True)
        self.recording_overlay.show("transcribing")
        self.audio_feedback.play_start(self.config.start_sound_path)
        self.logger.info("Recording started")

        if self.config.max_recording_duration > 0:
            self._stop_timer = threading.Timer(
                self.config.max_recording_duration, self._handle_timeout
            )
            self._stop_timer.start()

    def _handle_timeout(self) -> None:
        self.logger.info("Maximum recording duration reached.")
        self.toggle_recording()

    def _stop_recording(self) -> None:
        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None

        self.logger.debug("Stopping audio capture")
        waveform = self.audio_capture.stop()
        sample_rate = self.audio_capture.sample_rate
        self._recording = False
        self._tray.set_recording(False)
        self.recording_overlay.hide()
        self.audio_feedback.play_stop(self.config.stop_sound_path)
        self.logger.info("Recording stopped (%s samples)", waveform.size)
        self._executor.submit(self._transcribe_and_inject, waveform, sample_rate)

    def _transcribe_and_inject(
        self,
        waveform: np.ndarray,
        sample_rate: int = 16_000,
    ) -> None:
        start_time = time.perf_counter()
        if waveform.size == 0:
            self.logger.warning("No audio samples captured")
            return
        try:
            text = self.parakeet.transcribe(
                waveform,
                sample_rate=sample_rate,
                language=self.config.language,
            )
        except Exception as exc:
            self.logger.exception("Transcription failed: %s", exc)
            self.audio_feedback.play_error(self.config.error_sound_path)
            return
        duration = time.perf_counter() - start_time
        self.logger.debug("Transcription finished in %.2fs (chars=%s)", duration, len(text))
        if not text.strip():
            self.logger.info("Transcription empty; skipping paste")
            return
        self.logger.debug("Transcription: %s", text)
        self.text_injector.inject(text)

    def _log_capture_status(self, message: str) -> None:
        self.logger.debug("Audio status: %s", message)

    def _handle_model_loading_state(self, is_loading: bool) -> None:
        if is_loading:
            self.recording_overlay.show("loading")
        else:
            self.recording_overlay.hide()

    def _request_exit(self) -> None:
        self.logger.info("Exit requested from tray.")
        self._exit_event.set()
        self._tray.stop()

    def _shutdown(self) -> None:
        self.logger.info("Shutting down...")
        with self._lock:
            if self._recording:
                try:
                    self.audio_capture.stop()
                except Exception:
                    pass
                self._recording = False
            try:
                self.audio_capture.close()
            except Exception:
                pass
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
        try:
            self.recording_overlay.close()
        except Exception:
            pass
        try:
            self.keyboard.stop()
        except Exception:
            pass
        self._tray.stop()
        if self._tray_thread and self._tray_thread.is_alive():
            self._tray_thread.join(timeout=2.0)
        self._executor.shutdown(wait=True, cancel_futures=True)
        try:
            self.parakeet.close()
        except Exception:
            pass
        self.logger.info("Goodbye.")


def _run_single_instance() -> contextlib.AbstractContextManager[None]:
    """Ensure only one Chirp process is active.

    Windows-specific mutex prevents duplicate startup from Task Scheduler/startup
    triggers while still allowing deterministic process shutdown on exit.
    """
    if os.name != "nt":
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def _manager() -> Generator[None, None, None]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        mutex = kernel32.CreateMutexW(None, False, "Local\\ChirpSingleInstance")
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            kernel32.CloseHandle(mutex)
            raise SystemExit("Chirp is already running")

        try:
            yield
        finally:
            kernel32.CloseHandle(mutex)

    return _manager()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chirp",
        description="Chirp – Windows dictation app using local Parakeet STT (CPU-only).",
        epilog=(
            "Usage:\n"
            "  uv run python -m chirp.setup   # one-time: download the Parakeet model files\n"
            "  uv run python -m chirp.main    # daily: start Chirp and use the configured hotkey\n\n"
            "While Chirp is running, press your configured shortcut (default: ctrl+shift)\n"
            "to toggle recording on and off."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Smoke-test the pipeline without registering hotkeys or capturing audio",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    enable_dpi_awareness()
    args = _build_parser().parse_args(argv)
    if args.check:
        _run_smoke_check(verbose=args.verbose)
        return
    with _run_single_instance():
        app = ChirpApp(verbose=args.verbose)
        app.run()


def _run_smoke_check(*, verbose: bool = False) -> None:
    logger = get_logger(level=logging.DEBUG if verbose else logging.INFO)
    logger.info("Running Chirp smoke check")
    config_manager = ConfigManager()
    config = config_manager.load()
    try:
        model_dir = config_manager.model_dir(config.parakeet_model, config.parakeet_quantization)
        parakeet = ParakeetManager(
            model_name=config.parakeet_model,
            quantization=config.parakeet_quantization,
            provider_key=config.onnx_providers,
            threads=config.threads,
            logger=logger,
            model_dir=model_dir,
            timeout=config.model_timeout,
        )
    except ModelNotPreparedError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    text_injector = TextInjector(
        keyboard_manager=KeyboardShortcutManager(logger=logger),
        logger=logger,
        injection_mode=config.injection_mode,
        paste_mode=config.paste_mode,
        word_overrides=config.word_overrides,
        post_processing=config.post_processing,
        clipboard_behavior=False,
        clipboard_clear_delay=config.clipboard_clear_delay,
    )

    dummy_audio = np.zeros(16_000, dtype=np.float32)
    transcription = parakeet.transcribe(dummy_audio, sample_rate=16_000, language=config.language)
    processed = text_injector.process(transcription or "test")
    logger.info("Smoke check passed. Processed sample: %s", processed)


if __name__ == "__main__":
    main()
