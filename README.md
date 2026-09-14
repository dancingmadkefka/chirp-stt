# Chirp STT

Chirp is a local Windows dictation app powered by NVIDIA Parakeet TDT 0.6B v3.
Press a global shortcut, speak, and press it again to insert the transcription
into the application that has focus. Audio and transcription stay on the PC.

## Features

- CPU-only Parakeet inference with optional INT8 quantization
- Configurable global shortcut and microphone preference
- Direct typing or clipboard paste
- Audio cues and a small recording overlay
- Tray controls with visible recording and error states
- Native sample-rate negotiation and fallback across Windows audio endpoints
- Background startup through `pythonw.exe`, with duplicate-instance protection
- Optional model unloading after an idle timeout

## Install

Chirp requires Windows, Python 3.12 or newer, and
[uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/dancingmadkefka/chirp-stt.git
cd chirp-stt
uv sync
uv run chirp-setup
```

Start Chirp:

```powershell
uv run chirp
```

`Ctrl+Shift` starts and stops recording by default. Use `--verbose` during
setup or troubleshooting.

## Configuration

`config.toml` contains shared defaults. Put machine-specific settings in
`config.local.toml`; it is ignored by Git and overrides the shared file. Word
overrides from both files are combined.

```toml
preferred_mic = "Desk microphone"
audio_capture_mode = "on_demand"
primary_shortcut = "ctrl+shift"
parakeet_quantization = "int8"
threads = 0
language = "en"
injection_mode = "type"
audio_feedback = true
recording_overlay = true
max_recording_duration = 45.0
model_timeout = 0

[word_overrides]
"parra keet" = "Parakeet"
```

`preferred_mic` is a case-insensitive substring. Chirp tries matching endpoints
in a stable order and falls back to the system default. `on_demand` releases
the microphone between recordings; `always_open` keeps it active to reduce
toggle latency.

The post-processing rules supported by `post_processing` are documented in
[docs/post_processing_style_guide.md](docs/post_processing_style_guide.md).

## Background startup

Launch `.venv\Scripts\pythonw.exe` with `main.py` as its argument to run Chirp
without a console window. See [SETUP.md](SETUP.md) for the Windows Startup
shortcut and troubleshooting steps.

Background logs are written to `%USERPROFILE%\.chirp\chirp.log` and rotate
automatically. Raw transcriptions are logged only when verbose logging is
enabled.

## Development

```powershell
uv run pytest
uv run chirp-dev -- --verbose
```

`chirp-dev` restarts the app when Python or TOML files change.

## Credits

- [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [ONNX conversion by Ilya Stupakov](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx)

Chirp is licensed under the [MIT License](LICENSE).
