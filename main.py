import asyncio
import edge_tts
import re
import ollama
import os
import json
import random
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------
# 🪵 Logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ---------------------------
# ⚙️ Config
# ---------------------------
MODEL = "gemma3n"
MAX_RETRIES = 3
LANG_DIR = os.path.join(os.path.dirname(__file__), "lang")

# ---------------------------
# 🌐 Language loading
# ---------------------------
def scan_languages() -> dict[str, str]:
    """Scan the lang/ folder and return {code: name} for every valid JSON found."""
    langs = {}
    if not os.path.isdir(LANG_DIR):
        log.error(f"Lang directory not found: {LANG_DIR}")
        sys.exit(1)

    for filename in sorted(os.listdir(LANG_DIR)):
        if not filename.endswith(".json"):
            continue
        code = filename[:-5]  # strip .json
        path = os.path.join(LANG_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Require the minimum keys needed to run
            required = {"topics", "angles", "twists", "target_style", "prompts", "fallback"}
            if not required.issubset(data.keys()):
                missing = required - data.keys()
                log.warning(f"Skipping {filename}: missing keys {missing}")
                continue
            langs[code] = data.get("name", code.upper())
        except json.JSONDecodeError as e:
            log.warning(f"Skipping {filename}: invalid JSON ({e})")

    if not langs:
        log.error("No valid language files found in lang/")
        sys.exit(1)

    return langs

def load_lang(lang: str) -> dict:
    """Load the JSON language file for the given language code."""
    path = os.path.join(LANG_DIR, f"{lang}.json")
    if not os.path.exists(path):
        log.error(f"Language file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_language(available: dict[str, str]) -> str:
    """Display a dynamic menu built from the lang/ folder and return the chosen code."""
    print("\n🌐 Language:")
    codes = list(available.keys())
    for i, code in enumerate(codes, 1):
        print(f"  [{i}] {available[code]} ({code})")

    while True:
        raw = input(f"Your choice [1-{len(codes)}] : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(codes):
            return codes[int(raw) - 1]
        # Also accept direct code input (e.g. "fr", "en", "de")
        if raw.lower() in available:
            return raw.lower()
        print(f"  ⚠️  Please enter a number between 1 and {len(codes)}, or a language code.")

# ---------------------------
# 📦 Global state
# ---------------------------
@dataclass
class PodcastState:
    generated_titles: set = field(default_factory=set)

state = PodcastState()

# ---------------------------
# 🔧 LLM utilities
# ---------------------------
TRUNCATION_PATTERN = re.compile(
    r'(,\s*$|\b(et|ou|mais|car|donc|ainsi|notamment|comme|parce|lorsque|que'
    r'|and|or|but|because|so|thus|notably|as|when|that)\s*$'
    r'|[a-zéèêàùîïôâ]\s*$)',
    re.IGNORECASE
)

def call_llm(prompt: str, temperature: float = 1.0, max_tokens: int = 1024) -> Optional[str]:
    """Call Ollama with retry logic and truncation detection."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": temperature,
                    "top_p": 0.95,
                    "repeat_penalty": 1.2,
                    "num_predict": max_tokens,
                }
            )
            content = response["message"]["content"].strip()
            if not content:
                raise ValueError("Empty response from model")

            last_line = content.split("\n")[-1].strip()
            closing_tag_missing = "[/" not in content[-100:]
            if TRUNCATION_PATTERN.search(last_line) and closing_tag_missing:
                log.warning(f"Response likely truncated (max_tokens={max_tokens}), retrying with {max_tokens * 2}")
                max_tokens = max_tokens * 2
                continue

            return content
        except Exception as e:
            log.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")

    log.error("All attempts failed.")
    return None

def extract_tag(text: str, tag: str) -> Optional[str]:
    """Extract content between [TAG]...[/TAG], tolerant of typos in the closing tag."""
    pattern = rf'\[{tag}\](.*?)\[/{tag[:4]}\w*\]'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_tag_list(text: str, tag: str) -> list[str]:
    """Extract all occurrences of a repeated tag."""
    pattern = rf'\[{tag}\](.*?)\[/{tag}\]'
    results = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    return [r.strip() for r in results if r.strip()]

# ---------------------------
# 🧠 Topic generation
# ---------------------------
def generate_topic(L: dict, angle: Optional[str] = None, twist: Optional[str] = None) -> str:
    topic = random.choice(L["topics"])
    angle = angle if angle is not None else random.choice(L["angles"])
    twist = twist if twist is not None else random.choice(L["twists"])
    seed = random.randint(0, 100000)

    prompt = L["prompts"]["topic_generation"].format(
        seed=seed, topic=topic, twist=twist, angle=angle
    )

    raw = call_llm(prompt, temperature=1.2)
    if not raw:
        return L["fallback"]["topic"]

    titles = extract_tag_list(raw, "T")
    if not titles:
        log.debug(f"Tag extraction failed (fallback active), raw output:\n{raw[:500]}")
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        titles = []
        for line in lines:
            m = re.match(r'^\[(.+?)\[/T\]$', line, re.IGNORECASE)
            if m:
                titles.append(m.group(1).strip())
                continue
            m = re.match(r'^\[T\](.+?)\[/T\]$', line, re.IGNORECASE)
            if m:
                titles.append(m.group(1).strip())
                continue
            m = re.match(r'^\[([^\[\]/]{10,120})\]\s*$', line)
            if m:
                titles.append(m.group(1).strip())
                continue
            if 10 < len(line) < 120 and not line.startswith("["):
                titles.append(clean_title(line))

    titles = [clean_title(t).split("\n")[0][:120] for t in titles if t]
    fresh_titles = [t for t in titles if t not in state.generated_titles]
    chosen = random.choice(fresh_titles if fresh_titles else titles) if titles else L["fallback"]["topic"]
    state.generated_titles.add(chosen)
    return chosen

# ---------------------------
# 📋 Outline generation
# ---------------------------
def generate_outline(topic: str, L: dict) -> list[str]:
    prompt = L["prompts"]["outline_generation"].format(topic=topic)

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for outline, using default.")
        return L["fallback"]["outline"]

    sections = extract_tag_list(raw, "P")
    if not sections:
        log.debug("Outline tag extraction failed (fallback active)")
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        sections = []
        for line in lines:
            m = re.match(r'\[P\](.+?)(?:\[/?|</)P\]?', line, re.IGNORECASE)
            if m:
                sections.append(m.group(1).strip())
                continue
            m = re.match(r'^(.+?)(?:\[/?|</)P\]?\s*$', line, re.IGNORECASE)
            if m and len(m.group(1)) > 3:
                sections.append(m.group(1).strip())
                continue

    sections = [re.sub(r'</?\w+>|\[/?\w+\]?', '', s).strip() for s in sections]
    sections = [s.split("\n")[0][:60] for s in sections if s.strip()]

    if len(sections) < 2:
        log.warning("Outline too short, using default.")
        sections = L["fallback"]["outline"]

    return sections[:6]

# ---------------------------
# ✍️ Section generation
# ---------------------------
def generate_section(topic: str, section: str, previous_sections: list[str], L: dict) -> str:
    already_covered = ""
    if previous_sections:
        label = L["prompts"]["already_covered_label"]
        already_covered = label + "\n\n" + "\n".join(f"{s}" for s in previous_sections)

    prompt = L["prompts"]["section_generation"].format(
        topic=topic,
        section=section,
        already_covered=already_covered,
        style=L["target_style"]
    )

    raw = call_llm(prompt, temperature=1.1, max_tokens=900)
    if not raw:
        return L["fallback"]["section_unavailable"].format(section=section)

    content = extract_tag(raw, "P")
    return content if content else clean_text(raw)

def generate_intro(topic: str, outline: list[str], L: dict) -> str:
    outline_str = ", ".join(outline)
    prompt = L["prompts"]["intro_generation"].format(
        topic=topic,
        outline_str=outline_str,
        style=L["target_style"]
    )

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for intro, using fallback.")
        return L["fallback"]["intro"].format(topic=topic)

    content = extract_tag(raw, "I")
    return content if content else clean_text(raw)

def generate_conclusion(topic: str, outline: list[str], L: dict) -> str:
    key_points = ", ".join(outline)
    prompt = L["prompts"]["conclusion_generation"].format(
        topic=topic,
        key_points=key_points,
        style=L["target_style"]
    )

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for conclusion, using fallback.")
        return L["fallback"]["conclusion"].format(topic=topic)

    content = extract_tag(raw, "C")
    return content if content else clean_text(raw)

# ---------------------------
# 🧠 Main pipeline
# ---------------------------
def generate_full_content(topic: str, L: dict) -> str:
    msgs = L["log_messages"]

    log.info(msgs["generating_outline"])
    outline = generate_outline(topic, L)
    log.info(f"Outline: {outline}")

    sections = []
    processed_sections = []

    log.info(msgs["generating_intro"])
    intro = generate_intro(topic, outline, L)
    sections.append(intro)

    for i, section in enumerate(outline):
        log.info(msgs["generating_section"].format(i=i + 1, total=len(outline), section=section))
        text = generate_section(topic, section, processed_sections, L)
        sections.append(text)
        processed_sections.append(text)

    log.info(msgs["generating_conclusion"])
    conclusion = generate_conclusion(topic, outline, L)
    sections.append(conclusion)

    return "\n\n".join(sections)

# ---------------------------
# 🧹 Cleaning
# ---------------------------
def clean_text(text: str) -> str:
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'\_{1,2}(.*?)\_{1,2}', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\033\[[0-9;]*m', '', text)
    text = re.sub(r'\(.*?(musique|bruit|son|ambiance|silence|jingle|music|noise|sound|ambient).*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(musique|bruit|son|ambiance|music|noise|sound|ambient).*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/?[A-Z]+\]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def clean_title(title: str) -> str:
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'^\d+[\).\s]+', '', title)
    title = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', title)
    title = re.sub(r'\(.*?\)', '', title)
    title = title.replace('"', '').replace("'", "'")
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

# ---------------------------
# 🔊 Generate TTS
# ---------------------------
async def generate_audio_and_subs(text, voice, audio_path, srt_path):
    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            # MODIFICATION ICI : On accepte les phrases si les mots sont absents
            elif chunk["type"] in ["WordBoundary", "SentenceBoundary"]:
                submaker.feed(chunk)

    # On vérifie si on a récupéré quelque chose
    subtitles = submaker.get_srt()

    with open(srt_path, "w", encoding="utf-8") as f:
        if srt_path.endswith(".vtt"):
            f.write("WEBVTT\n\n")
            vtt_content = re.sub(r'(\d),(\d)', r'\1.\2', subtitles)
            f.write(vtt_content)
        else:
            f.write(subtitles)

# ---------------------------
# 🎧 Full pipeline
# ---------------------------
def create_podcast(
    topic: Optional[str] = None,
    lang: Optional[str] = None,
    angle: Optional[str] = None,
    twist: Optional[str] = None,
):
    available = scan_languages()

    if lang is None:
        if sys.stdin.isatty():
            lang = pick_language(available)
        else:
            # Non-interactive: default to first available language
            lang = next(iter(available))
            log.warning(f"No interactive terminal, defaulting to '{lang}'.")

    if lang not in available:
        fallback = next(iter(available))
        log.warning(f"Unknown language '{lang}', falling back to '{fallback}'.")
        lang = fallback

    # Load language data
    L = load_lang(lang)
    msgs = L["log_messages"]
    log.info(msgs["language_selected"])

    # Log overrides so the user knows what was injected
    if angle:
        log.info(f"🎯 Angle override : {angle}")
    if twist:
        log.info(f"🌀 Twist override  : {twist}")

    if not topic:
        # topic is generated; angle/twist may be injected or random
        topic = generate_topic(L, angle=angle, twist=twist)
    else:
        # topic is fixed; angle/twist are informational — append them to guide
        # the LLM implicitly by enriching the topic string passed downstream.
        if angle or twist:
            extras = " — ".join(filter(None, [angle, twist]))
            topic = f"{topic} ({extras})"
            log.info(f"📌 Enriched topic : {topic}")

    log.info(f"\n🎯 Topic: {topic}\n")
    log.info(msgs["generating_content"])
    raw_content = generate_full_content(topic, L)
    content = clean_text(raw_content)

    output_dir = "/app/output" if os.path.isdir("/app/output") else "."
    text_file = os.path.join(output_dir, "podcast_text.txt")

    with open(text_file, "w", encoding="utf-8") as f:
        f.write(f"LANG: {lang.upper()}\nTOPIC: {topic}\n\n{content}")

    log.info(msgs["text_saved"].format(path=text_file))
    log.info(msgs["generating_audio"])

    audio_path = os.path.join(output_dir, "podcast.wav")
    srt_path = os.path.join(output_dir, "podcast.vtt")
    asyncio.run(generate_audio_and_subs(content, L["voice_model"], audio_path, srt_path))
    log.info(msgs["podcast_done"].format(path=audio_path))
    
# ---------------------------
# 🚀 Entry point
# ---------------------------
def _pop_arg(args: list, flag: str) -> tuple[Optional[str], list]:
    """Extract --flag value from an args list. Returns (value_or_None, remaining_args)."""
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            value = args[idx + 1]
            return value, args[:idx] + args[idx + 2:]
        # Flag present but no value — just drop the flag
        return None, args[:idx] + args[idx + 1:]
    return None, args


if __name__ == "__main__":
    args = sys.argv[1:]

    lang_arg,  args = _pop_arg(args, "--lang")
    topic_arg, args = _pop_arg(args, "--topic")
    angle_arg, args = _pop_arg(args, "--angle")
    twist_arg, args = _pop_arg(args, "--twist")

    if lang_arg:
        lang_arg = lang_arg.lower()

    # Backward-compat: leftover positional args are treated as the topic
    if args:
        leftover = " ".join(args)
        topic_arg = f"{topic_arg} {leftover}".strip() if topic_arg else leftover

    create_podcast(topic=topic_arg, lang=lang_arg, angle=angle_arg, twist=twist_arg)