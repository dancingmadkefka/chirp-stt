import io
import importlib
import logging
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# Pre-populate mock modules before Chirp imports its audio stack.
_mock_sd = types.ModuleType("sounddevice")
_mock_sd.InputStream = MagicMock()

_mock_winsound = types.ModuleType("winsound")


class TestLoggingSecurity(unittest.TestCase):
    def test_sensitive_transcription_not_logged_at_info(self):
        """Verify that sensitive transcription text is NOT logged at INFO level."""
        with patch.dict(sys.modules, {"sounddevice": _mock_sd, "winsound": _mock_winsound}):
            chirp_main = importlib.import_module("chirp.main")
            with (
                patch.object(chirp_main, "ConfigManager") as mock_config,
                patch.object(chirp_main, "KeyboardShortcutManager"),
                patch.object(chirp_main, "AudioFeedback"),
                patch.object(chirp_main, "AudioCapture"),
                patch.object(chirp_main, "ParakeetManager"),
                patch.object(chirp_main, "TextInjector"),
            ):
                # Setup mocks
                mock_config_instance = mock_config.return_value
                mock_config_instance.load.return_value.parakeet_model = "test-model"
                mock_config_instance.load.return_value.parakeet_quantization = None
                mock_config_instance.load.return_value.onnx_providers = "cpu"
                mock_config_instance.load.return_value.threads = 1
                mock_config_instance.load.return_value.paste_mode = "ctrl"
                mock_config_instance.load.return_value.word_overrides = {}
                mock_config_instance.load.return_value.post_processing = ""
                mock_config_instance.load.return_value.clipboard_behavior = False
                mock_config_instance.load.return_value.clipboard_clear_delay = 1.0
                mock_config_instance.load.return_value.max_recording_duration = 45.0
                mock_config_instance.load.return_value.audio_feedback = True
                mock_config_instance.load.return_value.audio_feedback_volume = 1.0
                mock_config_instance.load.return_value.start_sound_path = None
                mock_config_instance.load.return_value.stop_sound_path = None
                mock_config_instance.load.return_value.error_sound_path = None
                mock_config_instance.load.return_value.model_timeout = 0.0
                mock_config_instance.load.return_value.recording_overlay = False
                mock_config_instance.load.return_value.preferred_mic = ""
                mock_config_instance.load.return_value.audio_capture_mode = "on_demand"
                mock_config_instance.model_dir.return_value = "models/test-model"

                # Capture logs
                log_capture = io.StringIO()
                handler = logging.StreamHandler(log_capture)
                handler.setLevel(logging.INFO)

                # Configure the chirp logger
                logger = logging.getLogger("chirp")
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
                try:
                    # Initialize app
                    app = chirp_main.ChirpApp()

                    # Simulate transcription
                    sensitive_text = "TEST_TRANSCRIPTION_DO_NOT_LOG_12345"
                    app.parakeet.transcribe.return_value = sensitive_text

                    # Simulate stop recording which triggers transcribe
                    waveform = np.zeros(16000)
                    app._transcribe_and_inject(waveform)

                    # Check logs
                    log_contents = log_capture.getvalue()

                    # Assert that sensitive text is NOT in the logs
                    self.assertNotIn(
                        sensitive_text, log_contents, "Sensitive transcription text leaked into INFO logs!"
                    )
                finally:
                    logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
