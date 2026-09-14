import tempfile
import unittest
from pathlib import Path

from chirp.config_manager import ChirpConfig, ConfigManager


class TestConfigValidation(unittest.TestCase):
    def test_validate_threads_negative(self):
        """Negative threads should fail validation."""
        conf = ChirpConfig(threads=-1)
        with self.assertRaisesRegex(ValueError, "threads must be non-negative"):
            conf.validate()

    def test_validate_clipboard_delay_negative(self):
        """Non-positive clipboard_clear_delay should fail validation."""
        conf = ChirpConfig(clipboard_clear_delay=-1.0)
        with self.assertRaisesRegex(ValueError, "clipboard_clear_delay must be positive"):
            conf.validate()

    def test_validate_clipboard_delay_zero(self):
        """Zero clipboard_clear_delay should fail validation."""
        conf = ChirpConfig(clipboard_clear_delay=0)
        with self.assertRaisesRegex(ValueError, "clipboard_clear_delay must be positive"):
            conf.validate()

    def test_validate_paste_mode_invalid(self):
        """Invalid paste_mode should fail validation."""
        conf = ChirpConfig(paste_mode="hacking")
        with self.assertRaisesRegex(ValueError, r"paste_mode must be 'ctrl' or 'ctrl\+shift'"):
            conf.validate()

    def test_validate_injection_mode_invalid(self):
        """Invalid injection_mode should fail validation."""
        conf = ChirpConfig(injection_mode="magic")
        with self.assertRaisesRegex(ValueError, r"injection_mode must be 'type' or 'paste'"):
            conf.validate()

    def test_validate_model_timeout_negative(self):
        """Negative model_timeout should fail validation."""
        conf = ChirpConfig(model_timeout=-1.0)
        with self.assertRaisesRegex(ValueError, "model_timeout must be non-negative"):
            conf.validate()

    def test_validate_audio_capture_mode_invalid(self):
        """Invalid audio_capture_mode should fail validation."""
        conf = ChirpConfig(audio_capture_mode="magic")
        with self.assertRaisesRegex(ValueError, "audio_capture_mode must be 'on_demand' or 'always_open'"):
            conf.validate()

    def test_from_dict_normalizes_audio_capture_mode(self):
        """Hyphenated audio_capture_mode values should be normalized."""
        conf = ChirpConfig.from_dict({"audio_capture_mode": "Always-Open"})
        self.assertEqual(conf.audio_capture_mode, "always_open")
        conf.validate()

    def test_validate_max_recording_duration_negative(self):
        """Negative max_recording_duration should fail validation."""
        conf = ChirpConfig(max_recording_duration=-1.0)
        with self.assertRaisesRegex(ValueError, "max_recording_duration must be non-negative"):
            conf.validate()

    def test_validate_max_recording_duration_excessive(self):
        """Excessive max_recording_duration should fail validation (DoS prevention)."""
        conf = ChirpConfig(max_recording_duration=7201.0)
        with self.assertRaisesRegex(ValueError, "max_recording_duration must be <="):
            conf.validate()

    def test_validate_sound_path_missing(self):
        """Non-existent sound paths should fail validation."""
        conf = ChirpConfig(start_sound_path="/this/path/absolutely/should/not/exist.wav")
        with self.assertRaisesRegex(ValueError, "start_sound_path does not exist"):
            conf.validate()

        conf = ChirpConfig(stop_sound_path="/this/path/absolutely/should/not/exist.wav")
        with self.assertRaisesRegex(ValueError, "stop_sound_path does not exist"):
            conf.validate()

    def test_validate_audio_feedback_volume_below_zero(self):
        """Negative audio_feedback_volume should fail validation."""
        conf = ChirpConfig(audio_feedback_volume=-0.1)
        with self.assertRaisesRegex(ValueError, "audio_feedback_volume must be between 0.0 and 1.0"):
            conf.validate()

    def test_validate_audio_feedback_volume_above_one(self):
        """audio_feedback_volume above 1.0 should fail validation."""
        conf = ChirpConfig(audio_feedback_volume=1.5)
        with self.assertRaisesRegex(ValueError, "audio_feedback_volume must be between 0.0 and 1.0"):
            conf.validate()

    def test_validate_audio_feedback_volume_valid_range(self):
        """audio_feedback_volume within 0.0-1.0 should pass validation."""
        for vol in [0.0, 0.5, 1.0]:
            conf = ChirpConfig(audio_feedback_volume=vol)
            conf.validate()  # Should not raise

    def test_valid_default_config(self):
        """Default config should pass validation."""
        conf = ChirpConfig()
        conf.validate()  # Should not raise

    def test_valid_config_with_zero_timeouts(self):
        """Zero timeouts (disable) should pass validation."""
        conf = ChirpConfig(model_timeout=0, max_recording_duration=0)
        conf.validate()  # Should not raise

    def test_from_dict_then_validate(self):
        """Verify the flow used by ConfigManager (from_dict -> validate)."""
        data = {"threads": -5, "paste_mode": "Hack", "injection_mode": "Paste"}
        conf = ChirpConfig.from_dict(data)
        # from_dict converts "Hack" to "hack"
        self.assertEqual(conf.paste_mode, "hack")
        self.assertEqual(conf.injection_mode, "paste")

        with self.assertRaisesRegex(ValueError, "threads must be non-negative"):
            conf.validate()

        conf.threads = 1  # fix threads
        with self.assertRaisesRegex(ValueError, r"paste_mode must be 'ctrl' or 'ctrl\+shift'"):
            conf.validate()


class TestLocalConfig(unittest.TestCase):
    def test_local_config_overrides_machine_settings_and_merges_words(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "config.toml"
            local = root / "config.local.toml"
            base.write_text(
                'preferred_mic = ""\n[word_overrides]\nbase = "base value"\n',
                encoding="utf-8",
            )
            local.write_text(
                'preferred_mic = "Desk microphone"\n[word_overrides]\nlocal = "local value"\n',
                encoding="utf-8",
            )
            manager = ConfigManager()
            manager._config_path = base
            manager._local_config_path = local

            config = manager.load()

            self.assertEqual(config.preferred_mic, "Desk microphone")
            self.assertEqual(
                config.word_overrides,
                {"base": "base value", "local": "local value"},
            )


if __name__ == "__main__":
    unittest.main()
