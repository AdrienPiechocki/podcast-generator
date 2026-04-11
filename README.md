# 🎙️ Podcast Generator

Automatic technical podcast generator in French and English. The script picks a topic, writes a full script via a local LLM, then synthesizes it to audio with Piper TTS.

---

## How it works

1. **Topic generation** — a topic, editorial angle, and context are picked randomly (or provided manually)
2. **Outline** — the LLM generates a plan with 4 to 6 distinct sections
3. **Writing** — intro, sections, and conclusion are written sequentially; each section is aware of what was already covered to avoid repetition
4. **Text-to-speech** — the script is converted to `.wav` by Piper TTS using the best available voice for the selected language
5. **Output** — the raw text is always saved to `podcast_text.txt`, audio to `podcast.wav`

---

## Requirements

| Tool | Role | Install |
|---|---|---|
| Python 3.9+ | Run the script | [python.org](https://www.python.org/downloads/) |
| [Ollama](https://ollama.com) | Local LLM | `curl -fsSL https://ollama.com/install.sh \| sh` |
| `gemma3n` model | Text generation | `ollama pull gemma3n` |
| [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) | Voice synthesis | see below |
| `curl` or `wget` | Voice model download | included on most systems |

### Installing Piper TTS

On Arch Linux, install from the AUR:

```bash
yay -S piper-tts
```

Otherwise, download the latest release for your architecture from [github.com/OHF-Voice/piper/releases](https://github.com/OHF-Voice/piper1-gpl/releases).

> **Note:** all voice models are downloaded automatically by `run.sh` on first run and stored in the `models/` folder.

---

## Installation

```bash
git clone https://github.com/AdrienPiechocki/podcast-generator.git
cd podcast-generator
chmod +x run.sh
```

Python dependencies are installed automatically in a `.venv/` virtualenv on first run.

---

## Usage

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

### Output files

| File | Content |
|---|---|
| `podcast_text.txt` | Full podcast script (always generated) |
| `podcast.wav` | Synthesized audio (if Piper TTS is available) |

---

## Project structure

```
.
├── main.py               # Main pipeline
├── run.sh                # Launch script
├── requirements.txt      # Python dependencies
├── models/               # Piper voice models (auto-downloaded)
│   ├── fr_FR-siwis-medium.onnx
│   ├── fr_FR-siwis-medium.onnx.json
│   ├── en_US-lessac-medium.onnx
│   ├── en_US-lessac-medium.onnx.json
├── .venv/                # Virtualenv (auto-created)
├── podcast_text.txt      # Text output (created at runtime)
└── podcast.wav           # Audio output (created at runtime)
```

---

## Configuration

Editorial parameters are defined at the top of `main.py`:

- **`TOPICS`** — list of available technical domains (Linux, Blockchain, Game Dev…), for both `fr` and `en`
- **`ANGLES`** — editorial angle applied (historical, critical, comparative…)
- **`TWISTS`** — additional context (industrial, ecological, post-GAFAM…)
- **`TARGET_STYLE`** — tone and style instructions passed to the LLM
- **`MODEL`** — Ollama model used (default: `gemma3n`)
- **`PIPER_VOICES`** — ordered list of voice models tried per language, pointing to `./models/`

---

## Troubleshooting

**Ollama not responding**
Check that the service is running: `ollama serve`. If the model is not yet downloaded: `ollama pull gemma3n`.

**No audio generated**
Check that `piper-tts` is in your PATH: `which piper-tts`. The text is always available in `podcast_text.txt`.

**Voice model download fails**
Check your connection, then download manually from [Hugging Face](https://huggingface.co/rhasspy/piper-voices) and place the `.onnx` and `.onnx.json` files in the `models/` folder.

**LLM response truncated**
The script automatically detects truncations and retries with a doubled token budget. If the issue persists, increase `max_tokens` in the `call_llm()` calls in `main.py`.