import unittest
from unittest.mock import Mock, patch

import numpy as np

from chirp.audio_capture import AudioCapture


class TestAudioCaptureModes(unittest.TestCase):
    @patch("chirp.audio_capture.sd.InputStream")
    def test_on_demand_opens_only_while_recording(self, mock_stream_cls):
        stream = Mock()
        mock_stream_cls.return_value = stream
        capture = AudioCapture(keep_stream_open=False)

        capture.open()
        mock_stream_cls.assert_not_called()

        capture.start()
        mock_stream_cls.assert_called_once()
        callback = mock_stream_cls.call_args.kwargs["callback"]
        callback(np.ones((2, 1), dtype=np.float32), 2, None, None)

        audio = capture.stop()

        stream.start.assert_called_once()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        np.testing.assert_array_equal(audio, np.ones(2, dtype=np.float32))

    @patch("chirp.audio_capture.sd.InputStream")
    def test_always_open_keeps_stream_open_between_recordings(self, mock_stream_cls):
        stream = Mock()
        mock_stream_cls.return_value = stream
        capture = AudioCapture(keep_stream_open=True)

        capture.open()
        mock_stream_cls.assert_called_once()

        capture.start()
        capture.stop()
        stream.stop.assert_not_called()
        stream.close.assert_not_called()

        capture.close()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()

    @patch("chirp.audio_capture.sd.query_devices")
    @patch("chirp.audio_capture.sd.InputStream")
    def test_uses_native_rate_when_requested_rate_is_rejected(
        self,
        mock_stream_cls,
        mock_query_devices,
    ):
        failed_stream = Mock()
        failed_stream.start.side_effect = RuntimeError("invalid sample rate")
        working_stream = Mock()
        mock_stream_cls.side_effect = [failed_stream, working_stream]
        mock_query_devices.return_value = {
            "name": "Microphone (Logi C270 HD WebCam)",
            "default_samplerate": 48_000,
        }
        capture = AudioCapture(device=27, fallback_devices=[27])

        capture.start()

        self.assertEqual(mock_stream_cls.call_args_list[0].kwargs["samplerate"], 16_000)
        self.assertEqual(mock_stream_cls.call_args_list[1].kwargs["samplerate"], 48_000)
        self.assertEqual(capture.sample_rate, 48_000)
        failed_stream.close.assert_called_once()
        capture.close()


if __name__ == "__main__":
    unittest.main()
