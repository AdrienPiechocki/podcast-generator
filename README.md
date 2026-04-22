# 🎙️ Podcast Generator

Automatic technical podcast generator in French and English. The script picks a topic, writes a full script via a local LLM, then synthesizes it to audio with EdgeTTS.

---

## How it works

1. **Topic generation** — a topic is picked randomly from a pool of topics, then AI generates a unique title to be used.
2. **Outline** — the LLM generates a plan with 4 to 6 distinct sections
3. **Writing** — intro, sections, and conclusion are written sequentially; each section is aware of what was already covered to avoid repetition
4. **Text-to-speech** — the script is converted to `.wav` by `edge-tts` using one of the available voices for the selected language
5. **Output** — the raw text is always saved to `podcast_text.txt`, audio to `podcast.wav`

---

## Requirements

| Tool | Role | Install |
|------|------|---------|
| Python 3.9+ | Run the script | [python.org](https://www.python.org/downloads/) |
| [Ollama](https://ollama.com) | Local LLM | See platform instructions below |
| `gemma3n` model | Text generation | `ollama pull gemma3n` |

---

## Installation

### Linux

```bash
git clone https://github.com/AdrienPiechocki/podcast-generator.git
cd podcast-generator
chmod +x run.sh
```

Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3n
```

Python dependencies are installed automatically in a `.venv/` virtualenv on first run.

### Windows

> Requires Windows 10 or later. Run commands in **PowerShell** or **Command Prompt**.

```bat
git clone https://github.com/AdrienPiechocki/podcast-generator.git
cd podcast-generator
```

Install Ollama: download the installer from [ollama.com](https://ollama.com), then in a terminal:

```bat
ollama pull gemma3n
```

Python dependencies are installed automatically in a `.venv\` virtualenv on first run.

---

## Usage

### Linux

```bash
# Random topic, interactive language selection
./run.sh

# Pass language directly
./run.sh --lang fr
./run.sh --lang en

# Custom topic
./run.sh --lang fr "La conteneurisation dans les environnements critiques"
./run.sh --lang en "Containerization in critical environments"
```

### Windows

```bat
:: Random topic, interactive language selection
run.bat

:: Pass language directly
run.bat --lang fr
run.bat --lang en

:: Custom topic
run.bat --lang fr "La conteneurisation dans les environnements critiques"
run.bat --lang en "Containerization in critical environments"
```

### CLI arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--lang` | Language code (e.g. `fr`, `en`) | Interactive menu |

### Output files

| File | Content |
|------|---------|
| `podcast_text.txt` | Full podcast script |
| `podcast.wav` | Synthesized audio |

---

## Project structure

```
.
├── main.py               # Main pipeline
├── run.sh                # Launch script (Linux)
├── run.bat               # Launch script (Windows)
├── requirements.txt      # Python dependencies
├── lang/                 # Language files (JSON)
│   ├── en.json           # English
│   ├── fr.json           # French
│   └── *.json            # Any custom language you add
├── .venv/                # Virtualenv (auto-created)
├── podcast_text.txt      # Text output (created at runtime)
└── podcast.wav           # Audio output (created at runtime)
```

---

## Configuration

The following parameters can be adjusted in `main.py`:

- **`MODEL`** — Ollama model used (default: `gemma3n`)
- **`MAX_RETRIES`** — number of retries on LLM failure (default: `3`)

Everything else — topics, prompts, style, voice model — lives in the language files under `lang/`.

---

## Adding or customizing a language

Languages are defined as JSON files in the `lang/` folder. Any `.json` file placed there is automatically detected at startup and added to the language selection menu — no changes to `main.py` needed.

### Adding a new language

1. Copy an existing file as a starting point:

   ```bash
   cp lang/en.json lang/de.json
   ```

2. Open the new file and update every field for your language. The required top-level keys are:

   | Key | Description |
   |-----|-------------|
   | `name` | Display name shown in the language menu (e.g. `"Deutsch"`) |
   | `topics` | List of technical domains the LLM can pick from |
   | `target_style` | Tone and style instructions passed to the LLM for every section |
   | `voice_model` | voice model for this language |
   | `fallback` | Default values used when the LLM returns nothing (see below) |
   | `prompts` | All LLM prompt templates (see below) |
   | `log_messages` | Console messages displayed during generation |

3. Run the script — your language will appear in the menu automatically:

   ```
   🌐 Langue / Language:
     [1] Deutsch (de)
     [2] English (en)
     [3] Français (fr)
   ```

   Or pass it directly:

   ```bash
   ./run.sh --lang de
   ```

> **Validation:** if a JSON file is missing required keys or contains a syntax error, it is skipped with a warning and does not appear in the menu. The script will always run as long as at least one valid language file exists.

---

## Troubleshooting

### Ollama not responding

Make sure the service is running:

- **Linux:** `ollama serve`
- **Windows:** Ollama runs as a background service after installation. If it is not responding, relaunch it from the Start menu or run `ollama serve` in a terminal.

If the model is not yet downloaded: `ollama pull gemma3n`.

### LLM response truncated

The script automatically detects truncations and retries with a doubled token budget. If the issue persists, increase `max_tokens` in the `call_llm()` calls in `main.py`.

### Python not found on Windows

Make sure Python is installed from [python.org](https://www.python.org/downloads/) and that **"Add Python to PATH"** was checked during installation. You can verify with:

```bat
python --version
```

### My language file is not showing up in the menu

Check that your JSON file:
- is saved in the `lang/` folder with a `.json` extension
- contains valid JSON (no trailing commas, no missing brackets)
- includes all required keys: `topics`, `target_style`, `prompts`, `fallback`

Run the script to see any warning messages about skipped files.