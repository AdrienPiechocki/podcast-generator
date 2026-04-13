# 🎙️ Podcast Generator

Automatic technical podcast generator in French and English. The script picks a topic, writes a full script via a local LLM, then synthesizes it to audio with EdgeTTS.

---

## How it works

1. **Topic generation** — a topic, editorial angle, and context are picked randomly (or provided manually via `--angle` and `--twist`)
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
./run.sh --lang fr --topic "La conteneurisation dans les environnements critiques"
./run.sh --lang en --topic "Containerization in critical environments"

# Custom angle and/or twist (combined with a random or explicit topic)
./run.sh --lang fr --angle "angle critique" --twist "dans un contexte industriel"
./run.sh --lang en --topic "Rust programming language" --angle "security angle" --twist "from a beginner perspective"
```

### Windows

```bat
:: Random topic, interactive language selection
run.bat

:: Pass language directly
run.bat --lang fr
run.bat --lang en

:: Custom topic
run.bat --lang fr --topic "La conteneurisation dans les environnements critiques"
run.bat --lang en --topic "Containerization in critical environments"

:: Custom angle and/or twist
run.bat --lang fr --angle "angle critique" --twist "dans un contexte industriel"
run.bat --lang en --topic "Rust programming language" --angle "security angle" --twist "from a beginner perspective"
```

### CLI arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--lang` | Language code (e.g. `fr`, `en`) | Interactive menu |
| `--topic` | Topic for the episode | Random from `lang/*.json` |
| `--angle` | Editorial angle (e.g. `"historical angle"`) | Random from `lang/*.json` |
| `--twist` | Contextual modifier (e.g. `"in an industrial context"`) | Random from `lang/*.json` |

All arguments are optional and can be combined freely. Any argument not provided falls back to a random value from the active language file.

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

Everything else — topics, angles, twists, prompts, style, voice model — lives in the language files under `lang/`.

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
   | `angles` | List of editorial angles (e.g. historical, critical, comparative) |
   | `twists` | List of contextual modifiers (e.g. "in an industrial context") |
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

### Customizing topics, angles, and twists

Open any language file and edit the relevant arrays directly.

**`topics`** — the pool of technical domains the LLM randomly picks from:

```json
"topics": [
  "Linux",
  "Rust programming language",
  "Self-hosted infrastructure",
  "Retro computing"
]
```

**`angles`** — the editorial lens applied to the chosen topic. Can also be set at runtime with `--angle`:

```json
"angles": [
  "historical angle",
  "beginner-friendly angle",
  "security angle",
  "philosophical angle"
]
```

**`twists`** — a contextual modifier combined with the topic and angle to make each episode more specific. Can also be set at runtime with `--twist`:

```json
"twists": [
  "in a small business context",
  "from an open-source perspective",
  "with a focus on privacy"
]
```

The LLM picks one value from each list at random and combines them into a generation prompt — unless overridden via `--angle` or `--twist` on the command line. Adding more values increases variety; removing values narrows the output to your preferred themes.

---

### Customizing prompts and style

**`target_style`** controls the tone the LLM writes in. It is injected into every section, intro, and conclusion prompt. Write it as instructions addressed to the model:

```json
"target_style": "Write in a calm, neutral journalistic tone. Use short sentences. Never use exclamation marks. Always end on a complete sentence."
```

**`prompts`** contains the full LLM prompt templates for each generation step. Available placeholders:

| Prompt | Available placeholders |
|--------|------------------------|
| `topic_generation` | `{seed}`, `{topic}`, `{angle}`, `{twist}` |
| `outline_generation` | `{topic}` |
| `section_generation` | `{topic}`, `{section}`, `{already_covered}`, `{style}` |
| `intro_generation` | `{topic}`, `{outline_str}`, `{style}` |
| `conclusion_generation` | `{topic}`, `{key_points}`, `{style}` |
| `already_covered_label` | *(no placeholders — plain label string)* |

You can rewrite any prompt entirely as long as you keep the `[TAG]...[/TAG]` format that the parser expects in the LLM response (`[T]`, `[P]`, `[I]`, `[C]`).

**`fallback`** defines the default values used when the LLM returns an empty or unparseable response. Supports `{topic}` and `{section}` where relevant:

```json
"fallback": {
  "topic": "Linux: historical angle",
  "outline": ["Origins", "Current state", "Key challenges", "Future outlook"],
  "intro": "Welcome to this podcast about {topic}.",
  "conclusion": "That concludes our episode on {topic}. Thanks for listening.",
  "section_unavailable": "[Content unavailable for section: {section}]"
}
```

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
- includes all required keys: `topics`, `angles`, `twists`, `target_style`, `prompts`, `fallback`

Run the script to see any warning messages about skipped files.