import subprocess
import re
import ollama
import os
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
# 📋 Topics / Angles / Twists (FR + EN)
# ---------------------------

TOPICS = {
    "fr": [
        "Linux",
        "Wayland",
        "Open Source",
        "Jeux Vidéos Indépendants",
        "Jeux Vidéos Triple A",
        "Langages de Programmation",
        "Développement Logiciel",
        "Développement de jeux vidéo",
        "Studios de jeux vidéo",
        "Systèmes Unix et BSD",
        "Administration système",
        "Virtualisation",
        "Conteneurisation et orchestration",
        "Architecture des systèmes d'exploitation",
        "Réseaux informatiques",
        "Architecture des ordinateurs",
        "Systèmes embarqués",
        "Souveraineté Numérique",
        "Sobriété énergétique",
        "Blockchain",
    ],
    "en": [
        "Linux",
        "Wayland",
        "Open Source",
        "Indie Video Games",
        "AAA Video Games",
        "Programming Languages",
        "Software Development",
        "Game Development",
        "Video Game Studios",
        "Unix and BSD Systems",
        "System Administration",
        "Virtualization",
        "Containerization and Orchestration",
        "Operating System Architecture",
        "Computer Networks",
        "Computer Architecture",
        "Embedded Systems",
        "Digital Sovereignty",
        "Energy Efficiency in Tech",
        "Blockchain",
    ],
}

ANGLES = {
    "fr": [
        "angle historique",
        "angle critique",
        "angle futuriste",
        "angle technique avancé",
        "angle débutant",
        "angle controversé",
        "angle comparatif",
        "angle business",
        "angle sécurité",
        "angle performance",
        "angle philosophie du logiciel",
    ],
    "en": [
        "historical angle",
        "critical angle",
        "futuristic angle",
        "advanced technical angle",
        "beginner angle",
        "controversial angle",
        "comparative angle",
        "business angle",
        "security angle",
        "performance angle",
        "software philosophy angle",
    ],
}

TWISTS = {
    "fr": [
        "cette année",
        "dans un contexte industriel",
        "pour les développeurs",
        "dans les environnements critiques",
        "face aux géants du cloud",
        "dans un monde post-GAFAM",
        "avec des contraintes écologiques",
    ],
    "en": [
        "this year",
        "in an industrial context",
        "for developers",
        "in critical environments",
        "facing cloud giants",
        "in a post-GAFAM world",
        "with ecological constraints",
    ],
}

TARGET_STYLE = {
    "fr": """Style attendu :
- Ton journalistique neutre et posé, ni trop familier ni trop académique
- Phrases courtes, rythme oral mais sans exclamations ou interpellations du type "Écoutez bien !"
- Pas de "on" de connivence excessive ; préférer "nous" ou la forme impersonnelle
- Terminer sur une phrase complète, jamais en milieu de pensée""",
    "en": """Expected style:
- Neutral, measured journalistic tone, neither too casual nor too academic
- Short sentences, oral rhythm but without exclamations or prompts like "Listen up!"
- Avoid excessive use of "you guys"; prefer "we" or impersonal forms
- Always end on a complete sentence, never mid-thought""",
}

MODEL = "gemma3n"
MAX_RETRIES = 3
SUPPORTED_LANGS = {"fr", "en"}

# ---------------------------
# 📦 Global state
# ---------------------------

@dataclass
class PodcastState:
    generated_titles: set = field(default_factory=set)

state = PodcastState()

# ---------------------------
# 🌐 Language selection
# ---------------------------

def pick_language() -> str:
    """Prompt the user to pick a language in interactive mode."""
    print("\n🌐 Langue / Language:")
    print("  [1] English (en)")
    print("  [2] Français (fr)")
    choice = input("Votre choix / Your choice [1/2] : ").strip()
    return "fr" if choice == "2" else "en"

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

def generate_topic(lang: str) -> str:
    topic = random.choice(TOPICS[lang])
    angle = random.choice(ANGLES[lang])
    twist = random.choice(TWISTS[lang])
    seed = random.randint(0, 100000)

    if lang == "fr":
        prompt = f"""Seed: {seed}

Tu dois générer 5 titres d'articles de podcast technique en français.

Sujet : {topic}
Contexte : {twist}
Angle éditorial : {angle}

Règles ABSOLUES :
- Chaque titre doit être FACTUEL et ancré dans le sujet donné
- Aucune invention, aucun hors-sujet
- Un titre par ligne, uniquement entre balises
- Pas de numérotation, pas de markdown, pas de parenthèses

Format OBLIGATOIRE (exactement comme ceci) :
[TITRE]Titre ici[/TITRE]
[TITRE]Titre ici[/TITRE]
[TITRE]Titre ici[/TITRE]
[TITRE]Titre ici[/TITRE]
[TITRE]Titre ici[/TITRE]"""
    else:
        prompt = f"""Seed: {seed}

Generate 5 titles for a technical podcast episode in English.

Topic: {topic}
Context: {twist}
Editorial angle: {angle}

ABSOLUTE RULES:
- Each title must be FACTUAL and grounded in the given topic
- No invention, no off-topic content
- One title per line, only between tags
- No numbering, no markdown, no parentheses

MANDATORY FORMAT (exactly like this):
[TITRE]Title here[/TITRE]
[TITRE]Title here[/TITRE]
[TITRE]Title here[/TITRE]
[TITRE]Title here[/TITRE]
[TITRE]Title here[/TITRE]"""

    raw = call_llm(prompt, temperature=1.2)
    if not raw:
        return f"{topic}: {angle}"

    titles = extract_tag_list(raw, "TITRE")

    if not titles:
        log.debug(f"Tag extraction failed (fallback active), raw output:\n{raw[:500]}")
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        titles = []
        for line in lines:
            m = re.match(r'^\[(.+?)\[/TITRE\]$', line, re.IGNORECASE)
            if m:
                titles.append(m.group(1).strip())
                continue
            m = re.match(r'^\[TITRE\](.+?)\[/TITRE\]$', line, re.IGNORECASE)
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

    chosen = random.choice(fresh_titles if fresh_titles else titles) if titles else f"{topic} – {angle}"
    state.generated_titles.add(chosen)
    return chosen

# ---------------------------
# 📋 Outline generation
# ---------------------------

def generate_outline(topic: str, lang: str) -> list[str]:
    if lang == "fr":
        prompt = f"""Tu dois créer un plan de podcast technique en français.

Sujet précis : {topic}

Règles ABSOLUES :
- 4 à 6 parties DISTINCTES, sans chevauchement
- Chaque partie doit couvrir un aspect DIFFÉRENT du sujet
- Titres courts (5 mots max)
- Aucun markdown, aucune explication

Format OBLIGATOIRE :
[PARTIE]Titre[/PARTIE]
[PARTIE]Titre[/PARTIE]"""
    else:
        prompt = f"""Create a plan for a technical podcast episode in English.

Precise topic: {topic}

ABSOLUTE RULES:
- 4 to 6 DISTINCT sections, no overlap
- Each section must cover a DIFFERENT aspect of the topic
- Short titles (5 words max)
- No markdown, no explanations

MANDATORY FORMAT:
[PARTIE]Title[/PARTIE]
[PARTIE]Title[/PARTIE]"""

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for outline, using default.")
        return (
            ["Introduction", "Contexte historique", "Enjeux techniques", "Perspectives"]
            if lang == "fr"
            else ["Introduction", "Historical Context", "Technical Challenges", "Perspectives"]
        )

    sections = extract_tag_list(raw, "PARTIE")

    if not sections:
        log.debug("Outline tag extraction failed (fallback active)")
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        sections = []
        for line in lines:
            m = re.match(r'\[PARTIE\](.+?)(?:\[/?|</)PARTIE\]?', line, re.IGNORECASE)
            if m:
                sections.append(m.group(1).strip())
                continue
            m = re.match(r'^(.+?)(?:\[/?|</)PARTIE\]?\s*$', line, re.IGNORECASE)
            if m and len(m.group(1)) > 3:
                sections.append(m.group(1).strip())
                continue

    sections = [re.sub(r'</?\w+>|\[/?\w+\]?', '', s).strip() for s in sections]
    sections = [s.split("\n")[0][:60] for s in sections if s.strip()]

    if len(sections) < 2:
        log.warning("Outline too short, using default.")
        sections = (
            ["Contexte et origines", "État de l'art", "Enjeux techniques", "Cas d'usage", "Perspectives"]
            if lang == "fr"
            else ["Context and Origins", "State of the Art", "Technical Challenges", "Use Cases", "Perspectives"]
        )

    return sections[:6]

# ---------------------------
# ✍️ Section generation
# ---------------------------

def generate_section(topic: str, section: str, previous_sections: list[str], lang: str) -> str:
    already_covered = ""
    if previous_sections:
        label = "Thèmes déjà couverts (NE PAS RÉPÉTER) :" if lang == "fr" else "Topics already covered (DO NOT REPEAT):"
        already_covered = label + "\n" + "\n".join(f"- {s}" for s in previous_sections[-3:])

    style = TARGET_STYLE[lang]

    if lang == "fr":
        prompt = f"""Tu es un journaliste radio expert en technologie.

Sujet global du podcast : {topic}
Partie à rédiger : {section}

{already_covered}

{style}

Règles ABSOLUES :
- 400 à 500 mots UNIQUEMENT sur "{section}"
- Contenu FACTUEL, pas d'invention
- Pas d'introduction du type "Dans cette partie..."
- Pas de conclusion globale
- Pas de répétition des parties précédentes
- Pas de mise en scène (musique, bruitages, etc.)
- Terminer obligatoirement par une phrase complète avant [/PARTIE]

Format :
[PARTIE]
Texte ici
[/PARTIE]"""
    else:
        prompt = f"""You are a radio journalist and technology expert.

Overall podcast topic: {topic}
Section to write: {section}

{already_covered}

{style}

ABSOLUTE RULES:
- 400 to 500 words ONLY about "{section}"
- FACTUAL content, no invention
- No introduction like "In this section..."
- No global conclusion
- No repetition of previous sections
- No staging (music, sound effects, etc.)
- Always end with a complete sentence before [/PARTIE]

Format:
[PARTIE]
Text here
[/PARTIE]"""

    raw = call_llm(prompt, temperature=1.1, max_tokens=900)
    if not raw:
        return (
            f"[Contenu indisponible pour la partie : {section}]"
            if lang == "fr"
            else f"[Content unavailable for section: {section}]"
        )

    content = extract_tag(raw, "PARTIE")
    return content if content else clean_text(raw)


def generate_intro(topic: str, outline: list[str], lang: str) -> str:
    outline_str = ", ".join(outline)
    style = TARGET_STYLE[lang]

    if lang == "fr":
        prompt = f"""Tu es un journaliste radio.

Rédige l'introduction d'un podcast sur : {topic}

Le podcast abordera : {outline_str}

{style}

Règles :
- 150 à 200 mots
- Accroche forte dès la première phrase
- Annonce claire du plan sans le détailler
- Pas de mise en scène (musique, etc.)
- Terminer par une phrase complète avant [/INTRO]

Format :
[INTRO]
Texte
[/INTRO]"""
    else:
        prompt = f"""You are a radio journalist.

Write the introduction for a podcast about: {topic}

The podcast will cover: {outline_str}

{style}

Rules:
- 150 to 200 words
- Strong hook from the very first sentence
- Clear outline of the plan without detailing it
- No staging (music, etc.)
- End with a complete sentence before [/INTRO]

Format:
[INTRO]
Text
[/INTRO]"""

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for intro, using fallback.")
        return (
            f"Bienvenue dans ce podcast consacré à {topic}."
            if lang == "fr"
            else f"Welcome to this podcast about {topic}."
        )

    content = extract_tag(raw, "INTRO")
    return content if content else clean_text(raw)


def generate_conclusion(topic: str, outline: list[str], lang: str) -> str:
    key_points = ", ".join(outline)
    style = TARGET_STYLE[lang]

    if lang == "fr":
        prompt = f"""Tu es un journaliste radio.

Rédige la conclusion d'un podcast sur : {topic}

Points abordés : {key_points}

{style}

Règles :
- 150 à 200 mots
- Synthèse rapide + ouverture sur l'avenir
- Pas de répétition mot pour mot des parties
- Terminer par une phrase complète avant [/CONCLUSION]

Format :
[CONCLUSION]
Texte
[/CONCLUSION]"""
    else:
        prompt = f"""You are a radio journalist.

Write the conclusion for a podcast about: {topic}

Points covered: {key_points}

{style}

Rules:
- 150 to 200 words
- Quick summary + opening toward the future
- No word-for-word repetition of sections
- End with a complete sentence before [/CONCLUSION]

Format:
[CONCLUSION]
Text
[/CONCLUSION]"""

    raw = call_llm(prompt, temperature=1.0)
    if not raw:
        log.warning("LLM returned nothing for conclusion, using fallback.")
        return (
            f"Voilà qui conclut notre podcast sur {topic}. Merci de nous avoir écoutés."
            if lang == "fr"
            else f"That concludes our podcast about {topic}. Thank you for listening."
        )

    content = extract_tag(raw, "CONCLUSION")
    return content if content else clean_text(raw)

# ---------------------------
# 🧠 Main pipeline
# ---------------------------

def generate_full_content(topic: str, lang: str) -> str:
    log.info("📋 Generating outline...")
    outline = generate_outline(topic, lang)
    log.info(f"Outline: {outline}")

    sections = []
    processed_sections = []

    log.info("🎙️ Generating intro...")
    intro = generate_intro(topic, outline, lang)
    sections.append(intro)

    for i, section in enumerate(outline):
        log.info(f"✍️  Section {i+1}/{len(outline)}: {section}")
        text = generate_section(topic, section, processed_sections, lang)
        sections.append(text)
        processed_sections.append(section)

    log.info("🔚 Generating conclusion...")
    conclusion = generate_conclusion(topic, outline, lang)
    sections.append(conclusion)

    return "\n\n".join(sections)

# ---------------------------
# 🧹 Cleaning
# ---------------------------

def clean_text(text: str) -> str:
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
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
# 🔊 Piper TTS
# ---------------------------

PIPER_VOICES = {
    "fr": [
        "./models/fr_FR-siwis-medium.onnx"
    ],
    "en": [
        "./models/en_US-lessac-medium.onnx"
    ],
}


def find_piper_model(lang: str) -> Optional[str]:
    for voice in PIPER_VOICES.get(lang, []):
        if os.path.exists(voice):
            log.info(f"Piper model found: {voice}")
            return voice
    all_voices = PIPER_VOICES["fr"] + PIPER_VOICES["en"]
    for voice in all_voices:
        if os.path.exists(voice):
            log.warning(f"No model for lang '{lang}', falling back to: {voice}")
            return voice
    log.error("No Piper model found. Searched: " + ", ".join(all_voices))
    return None


def generate_audio(text: str, lang: str, output_file: str = "podcast.wav") -> Optional[str]:
    model = find_piper_model(lang)
    if not model:
        return None

    tmp = "temp_podcast.txt"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)

        cmd = ["sh", "-c", f"cat {tmp} | piper-tts -m {model} -f {output_file}"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log.error(f"Piper error: {result.stderr}")
            return None

        log.info(f"Audio generated: {output_file}")
        return output_file

    except Exception as e:
        log.error(f"Audio generation failed: {e}")
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

# ---------------------------
# 🎧 Full pipeline
# ---------------------------

def create_podcast(topic: Optional[str] = None, lang: Optional[str] = None) -> Optional[str]:
    if lang is None:
        if sys.stdin.isatty():
            lang = pick_language()
        else:
            log.warning("No interactive terminal detected, defaulting to English.")
            lang = "en"

    if lang not in SUPPORTED_LANGS:
        log.warning(f"Unsupported language '{lang}', falling back to English.")
        lang = "en"

    log.info(f"🌐 Language selected: {lang.upper()}")

    if not topic:
        topic = generate_topic(lang)

    log.info(f"\n🎯 Topic: {topic}\n")

    log.info("🧠 Generating content...")
    raw_content = generate_full_content(topic, lang)
    content = clean_text(raw_content)

    output_dir = "/app/output" if os.path.isdir("/app/output") else "."
    text_file = os.path.join(output_dir, "podcast_text.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(f"LANG: {lang.upper()}\nTOPIC: {topic}\n\n{content}")
    log.info(f"📄 Text saved: {text_file}")

    log.info("🎙️ Generating audio...")
    audio_path = os.path.join(output_dir, "podcast.wav")
    audio_file = generate_audio(content, lang, output_file=audio_path)

    if audio_file:
        log.info(f"\n✅ Podcast generated: {audio_file}")
        return audio_file
    else:
        log.warning("⚠️  Audio not generated (Piper missing?). Text available at podcast_text.txt")
        return text_file

# ---------------------------
# 🚀 Entry point
# ---------------------------

if __name__ == "__main__":
    # Usage: python script.py [--lang fr|en] [optional topic...]
    args = sys.argv[1:]
    lang_arg = None
    topic_arg = None

    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang_arg = args[idx + 1].lower()
            args = args[:idx] + args[idx + 2:]

    topic_arg = " ".join(args) if args else None

    create_podcast(topic=topic_arg, lang=lang_arg)