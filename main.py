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
from ddgs import DDGS
from datetime import datetime
from babel.dates import format_date
from contextlib import contextmanager

# ---------------------------
# 🪵 Logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
for name, lgr in logging.Logger.manager.loggerDict.items():
    if isinstance(lgr, logging.Logger) and name != "__main__":
        lgr.setLevel(logging.WARNING)
        lgr.propagate = False
log = logging.getLogger(__name__)

@contextmanager  
def suppress_all_output():
    with open(os.devnull, 'w') as devnull:
        old_out_fd = os.dup(1)
        old_err_fd = os.dup(2)
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
        try:
            yield
        finally:
            os.dup2(old_out_fd, 1)
            os.dup2(old_err_fd, 2)
            os.close(old_out_fd)
            os.close(old_err_fd)

# ---------------------------
# ⚙️ Config
# ---------------------------
MODEL = "gemma3n"
MAX_RETRIES = 3
LANG_DIR = os.path.join(os.path.dirname(__file__), "lang")
HISTORY_SIZE = 10
HISTORY_FILE = os.path.join(os.path.dirname(__file__), ".podcast_history.json")
TITLES_PER_GENERATION = 5  # number of candidate titles generated, each with its own random topic seed
MAX_TOPIC_RETRIES = 10
now = datetime.now()

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
            required = {"topics", "target_style", "prompts", "fallback"}
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
# 📋 History persistence
# ---------------------------
def load_history() -> list[str]:
    """Load the sliding window of recently generated topics from disk."""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(history: list[str]) -> None:
    """Persist the last HISTORY_SIZE topics to disk."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-HISTORY_SIZE:], f, ensure_ascii=False, indent=2)

# ---------------------------
# 🔧 LLM utilities
# ---------------------------
TRUNCATION_PATTERN = re.compile(
    r'(,\s*$'                          # virgule finale
    r'|\b(parce|lorsque|because|when)\s*$'   # conjonctions de subordination incomplètes
    r'|\b(et|ou|and|or|but)\s*$'      # coordonnants en toute fin (sans ponctuation)
    r')',
    re.IGNORECASE
)

def get_web_context(query: str, current_date: str = "") -> str:
    context_parts = []
    seen = set()
    search_query = f"{query} {current_date}".strip()
    try:
        with suppress_all_output():
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=10))
                for r in results:
                    body = r.get('body', '').strip()
                    if body and body not in seen:
                        seen.add(body)
                        context_parts.append(
                            f"Titre: {r['title']}\nSource: {r.get('href', '')}\n{body}\n"
                        )
        return "\n".join(context_parts)
    except Exception as e:
        log.warning(f"Recherche web échouée : {e}")
        return "Pas de données web récentes disponibles."

def call_llm(prompt: str, system_prompt: Optional[str] = None, temperature: float = 1.0, max_tokens: int = 1024) -> Optional[str]:
    current_max_tokens = max_tokens

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if system_prompt:
                response = ollama.chat(
                    model=MODEL,
                    messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": prompt}],
                    options={
                        "temperature": temperature,
                        "top_p": 0.95,
                        "repeat_penalty": 1.2,
                        "num_predict": current_max_tokens,
                    }
                )
            else:
                response = ollama.chat(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": temperature,
                        "top_p": 0.95,
                        "repeat_penalty": 1.2,
                        "num_predict": current_max_tokens,
                    }
                )
            content = response["message"]["content"].strip()
            if not content:
                raise ValueError("Empty response from model")

            last_line = content.split("\n")[-1].strip()

            # Only flag truncation on unambiguous dangling conjunctions/commas
            dangling = TRUNCATION_PATTERN.search(last_line)

            # Only flag missing closing tag if the response contains opening tags
            has_opening_tag = bool(re.search(r'\[P\]', content))
            last_open = content.rfind('[P]')
            closing_tag_missing = has_opening_tag and '[/P]' not in content[last_open:]

            if dangling or closing_tag_missing:
                log.warning(
                    f"Response likely truncated (attempt {attempt}, "
                    f"max_tokens={current_max_tokens}) | "
                    f"dangling={bool(dangling)} closing_missing={closing_tag_missing} | "
                    f"last_line={last_line!r}"
                )
                current_max_tokens *= 2
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

def _pick_fresh_topic(L: dict, history: list[str]) -> str:
    topics = L["topics"]
    # Extraire les seeds déjà utilisés de l'historique
    used_seeds = {h for h in history}

    for _ in range(MAX_TOPIC_RETRIES):
        candidate = random.choice(topics)
        if candidate not in used_seeds:
            return candidate

    log.warning("Could not find a fresh topic seed, picking randomly.")
    return random.choice(topics)


def generate_topic(L: dict, history: Optional[list[str]] = None) -> str:
    history = history or []

    seed_topic = _pick_fresh_topic(L, history)
    log.info(f"🎲 Topic seed: {seed_topic}")

    # Sauvegarder uniquement le seed
    updated_history = (history + [f"{seed_topic}"])[-HISTORY_SIZE:]
    save_history(updated_history)

    seed = random.randint(0, 100000)
    locale = L.get("locale", "en_US")
    date = format_date(now, format='yyyy', locale=locale)
    system_prompt = L["prompts"]["system_date"].format(date=date)
    prompt = L["prompts"]["topic_generation"].format(seed=seed, topic=seed_topic)

    raw = call_llm(prompt, system_prompt, temperature=1.2)
    if not raw:
        return []

    title = extract_tag(raw, "T")

    cleaned = clean_title(title)
    return cleaned


# ---------------------------
# 📋 Outline generation
# ---------------------------
def generate_outline(topic: str, L: dict, system_prompt: str) -> list[str]:
    prompt = L["prompts"]["outline_generation"].format(topic=topic)

    raw = call_llm(prompt, system_prompt, temperature=1.0, max_tokens=512)
    if not raw:
        log.warning("LLM returned nothing for outline, using default.")
        return L["fallback"]["outline"]

    sections = extract_tag_list(raw, "P")
    if not sections:
        log.warning("Outline tag extraction failed (fallback active)")
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
# ---------------------------
# 🔍 Keyword filtering
# ---------------------------
MIN_KW_LEN = 6
GENERIC_WORDS = {
    # French
    "avancées", "applications", "efficacité", "optimisation", "durabilité",
    "prédiction", "résistance", "température", "pression", "déformation",
    "propriétés", "composition", "matériaux", "transformation", "scénarios",
    "géométries", "résultats", "processus", "méthodes", "systèmes",
    "modèles", "analyse", "données", "contexte", "approche", "impact",
    # English
    "advances", "applications", "efficiency", "optimization", "durability",
    "prediction", "resistance", "temperature", "pressure", "deformation",
    "properties", "composition", "materials", "transformation", "scenarios",
    "geometries", "results", "processes", "methods", "systems",
    "models", "analysis", "context", "approach", "impact", "data",
}

def filter_keywords(raw_keywords: str) -> str:
    """Remove generic/short keywords from the blocklist before sending to verifier."""
    lines = [l.strip().lstrip("- ") for l in raw_keywords.splitlines() if l.strip()]
    filtered = [
        l for l in lines
        if len(l) >= MIN_KW_LEN and l.lower() not in GENERIC_WORDS
    ]
    return "\n".join(f"- {l}" for l in filtered)


def verify_section(text: str, forbidden_keywords: str, L: dict) -> Optional[list[str]]:
    """Check if text uses any forbidden keywords. Returns list of violations or None if OK."""
    filtered = filter_keywords(forbidden_keywords)
    if not filtered.strip():
        return None

    prompt = L["prompts"]["section_verify"].format(
        forbidden=filtered,
        text=text
    )
    raw = call_llm(prompt, temperature=0.0, max_tokens=128)
    if not raw:
        return None

    if "[OK]" in raw.upper():
        return None

    match = re.search(r'\[FAIL\](.*?)\[/FAIL\]', raw, re.DOTALL | re.IGNORECASE)
    if match:
        violations = [v.strip() for v in match.group(1).split(",") if v.strip()]
        return violations if violations else None

    return None


def generate_section(topic: str, section: str, previous_sections: list[dict], other_sections: list[str], L: dict, system_prompt: str) -> str:
    already_covered = ""
    all_keywords = ""
    if previous_sections:
        all_ideas = "\n".join(f"- {s['ideas']}" for s in previous_sections if s.get('ideas'))
        all_keywords = "\n".join(f"- {kw}" for s in previous_sections for kw in s.get('keywords', '').splitlines() if kw.strip())
        already_covered = L["prompts"]["already_covered_label"].format(
            ideas=all_ideas,
            keywords=all_keywords
        )

    base_prompt_kwargs = dict(
        topic=topic,
        section=section,
        already_covered=already_covered,
        other_sections=", ".join(other_sections),
        style=L["target_style"]
    )

    prompt = L["prompts"]["section_generation"].format(**base_prompt_kwargs)
    raw = call_llm(prompt, system_prompt, temperature=0.8)
    if not raw:
        return L["fallback"]["section_unavailable"].format(section=section)

    content = extract_tag(raw, "P") or clean_text(raw)

    # Post-generation verification loop
    for attempt in range(1, MAX_RETRIES + 1):
        violations = verify_section(content, all_keywords, L)
        if violations is None:
            log.info(L["log_messages"]["log_verify_ok"].format(section=section))
            break

        violations_str = ", ".join(violations)
        log.warning(L["log_messages"]["log_verify_fail"].format(
            section=section, violations=violations_str
        ))

        regen_prompt = L["prompts"]["section_regenerate"].format(
            **base_prompt_kwargs,
            violations=violations_str
        )
        raw = call_llm(regen_prompt, system_prompt, temperature=1.0)
        if not raw:
            break
        content = extract_tag(raw, "P") or clean_text(raw)

    return content


def generate_intro(topic: str, outline: list[str], L: dict, system_prompt: str) -> str:
    outline_str = ", ".join(outline)
    prompt = L["prompts"]["intro_generation"].format(
        topic=topic,
        outline_str=outline_str,
        style=L["target_style"]
    )

    raw = call_llm(prompt, system_prompt, temperature=0.8)
    if not raw:
        log.warning("LLM returned nothing for intro, using fallback.")
        return L["fallback"]["intro"].format(topic=topic)

    content = extract_tag(raw, "I")
    return content if content else clean_text(raw)

def generate_conclusion(topic: str, processed_sections: list[dict], L: dict, system_prompt: str) -> str:
    all_ideas = "\n".join(f"- {s['ideas']}" for s in processed_sections if s.get('ideas'))
    all_keywords = "\n".join(f"- {kw}" for s in processed_sections for kw in s.get('keywords', '').splitlines() if kw.strip())
    key_points = f"Idées couvertes :\n{all_ideas}\n\nTermes déjà utilisés (ne pas répéter) :\n{all_keywords}"

    prompt = L["prompts"]["conclusion_generation"].format(
        topic=topic,
        key_points=key_points,
        style=L["target_style"]
    )

    raw = call_llm(prompt, system_prompt, temperature=0.8)
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

    locale = L.get("locale", "en_US")
    date = format_date(now, format='MMMM yyyy', locale=locale).capitalize()
    web_data = get_web_context(topic, current_date=date)
    system_date=L["prompts"]["system_date"].format(date=date)
    system_data=L["prompts"]["system_data"].format(context=web_data)
    system_prompt = system_date + system_data

    log.info(msgs["generating_outline"])
    outline = generate_outline(topic, L, system_prompt)
    log.info(f"Outline: {outline}")

    sections = []
    processed_sections = []

    log.info(msgs["generating_intro"])
    intro = generate_intro(topic, outline, L, system_prompt)
    sections.append(intro)

    for i, section in enumerate(outline):
        other_sections = outline.copy()
        other_sections.remove(section)
        log.info(msgs["generating_section"].format(i=i + 1, total=len(outline), section=section))
        text = generate_section(topic, section, processed_sections, other_sections, L, system_prompt)
        sections.append(text)
        points = resume_section(text, L)
        processed_sections.append(points)

    log.info(msgs["generating_conclusion"])
    conclusion = generate_conclusion(topic, processed_sections, L, system_prompt)
    sections.append(conclusion)

    return "\n\n".join(sections)

# ---------------------------
# 🧹 Cleaning
# ---------------------------
def clean_text(text: str) -> str:
    # 1. Suppression des enrichissements Markdown (gras, italique, titres)
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'\_{1,2}(.*?)\_{1,2}', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # 2. Nettoyage des balises de structure et métadonnées LLM
    text = re.sub(r'\[/?[A-Z]+\]', '', text) # Supprime [P], [/P], [I], etc.
    text = re.sub(r'\033\[[0-9;]*m', '', text) # Codes couleur ANSI
    
    # 3. Suppression des indications sonores (musique, bruits)
    pattern_noise = r'[\(\[][^\]\)]*?(musique|bruit|son|ambiance|jingle|music|noise|sound|ambient)[^\]\)]*?[\)\]]'
    text = re.sub(pattern_noise, '', text, flags=re.IGNORECASE)
    
    # 4. GESTION DES ESPACES ET SAUTS DE LIGNE (Optimisée)
    # Remplace les tabulations et espaces multiples par un seul espace
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Supprime les espaces en début et fin de chaque ligne
    text = "\n".join(line.strip() for line in text.splitlines())
    
    # Remplace 3 sauts de ligne ou plus par exactement deux (un seul saut vide)
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

def resume_section(text: str, L: dict) -> dict:
    """Extract ideas and concrete keywords/titles from a section, returned as a dict."""
    ideas_prompt = L["prompts"]["resume_section_ideas"].format(text=text)
    keywords_prompt = L["prompts"]["resume_section_keywords"].format(text=text)

    ideas = clean_text(call_llm(ideas_prompt, temperature=0.2) or "")
    keywords = clean_text(call_llm(keywords_prompt, temperature=0.2) or "")

    return {"ideas": ideas, "keywords": keywords}

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
            elif chunk["type"] in ["WordBoundary", "SentenceBoundary"]:
                submaker.feed(chunk)

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
):
    available = scan_languages()

    if lang is None:
        if sys.stdin.isatty():
            lang = pick_language(available)
        else:
            lang = next(iter(available))
            log.warning(f"No interactive terminal, defaulting to '{lang}'.")

    if lang not in available:
        fallback = next(iter(available))
        log.warning(f"Unknown language '{lang}', falling back to '{fallback}'.")
        lang = fallback

    L = load_lang(lang)
    msgs = L["log_messages"]
    log.info(msgs["language_selected"])

    history = load_history()
    if history:
        log.debug(f"📋 Recent topics to avoid: {history}")

    if not topic:
        topic = generate_topic(L, history=history)

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
        return None, args[:idx] + args[idx + 1:]
    return None, args


if __name__ == "__main__":
    args = sys.argv[1:]

    lang_arg,  args = _pop_arg(args, "--lang")

    if lang_arg:
        lang_arg = lang_arg.lower()

    if args:
        leftover = " ".join(args)

    create_podcast(topic=(leftover if args else None), lang=lang_arg)