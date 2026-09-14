# Windows setup

Chirp runs from its Python environment and does not need a packaged executable.

## Install

Install [uv](https://docs.astral.sh/uv/), clone the repository, and prepare the
model:

```powershell
git clone https://github.com/dancingmadkefka/chirp-stt.git
cd chirp-stt
uv sync
uv run chirp-setup
```

Start Chirp in a terminal while testing the installation:

```powershell
uv run chirp --verbose
```

The default `Ctrl+Shift` shortcut starts and stops recording. Transcribed text
is inserted into the application that has focus.

## Personal configuration

Repository defaults live in `config.toml`. Put machine-specific settings in
`config.local.toml`; that file is ignored by Git and overrides the shared
defaults. Word overrides from both files are combined.

For example:

```toml
preferred_mic = "Desk microphone"
audio_capture_mode = "on_demand"

[word_overrides]
"project nickname" = "ProjectName"
```

`preferred_mic` is a case-insensitive substring. Chirp tries matching Windows
audio endpoints in a stable order, negotiates their native sample rate when
needed, and falls back to the system default.

Use `audio_capture_mode = "on_demand"` to release the microphone between
recordings. `"always_open"` can reduce toggle latency but keeps the selected
input active for the life of the app.

## Background startup

Use `pythonw.exe` directly so Windows does not create a console window:

1. Press `Win+R`, enter `shell:startup`, and select **OK**.
2. Create a shortcut with these values, replacing `<repo>` with the clone path:
   - Target: `<repo>\.venv\Scripts\pythonw.exe`
   - Arguments: `"<repo>\main.py"`
   - Start in: `<repo>`

Chirp's single-instance guard stops duplicate shortcuts or repeated launches
from loading another model.

## Command-line shortcuts

`chirp.bat` and `chirp-dev.bat` resolve the repository from their own location.
Add the repository directory to your user `Path` if you want to run `chirp` or
`chirp-dev` from any terminal.

Development mode restarts Chirp after Python or TOML changes:

```powershell
uv run chirp-dev -- --verbose
```

## Troubleshooting

- Check `%USERPROFILE%\.chirp\chirp.log` when background startup fails. The log
  is timestamped and rotates automatically.
- Run `uv run chirp-setup` if model loading reports missing files.
- Choose a different shortcut if another application reacts to `Ctrl+Shift`.
- Run `uv run chirp --verbose` to see microphone endpoint failures directly.
