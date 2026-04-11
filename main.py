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
# 📋 Sujets / Angles / Twists
# ---------------------------

SUJETS = [
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
]

ANGLES = [
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
]

TWISTS = [
    "cette année",
    "dans un contexte industriel",
    "pour les développeurs",
    "dans les environnements critiques",
    "face aux géants du cloud",
    "dans un monde post-GAFAM",
    "avec des contraintes écologiques",
]

MODEL = "gemma3n"
MAX_RETRIES = 3

# ---------------------------
# 📦 État global
# ---------------------------

@dataclass
class PodcastState:
    titres_generes: set = field(default_factory=set)

state = PodcastState()

# ---------------------------
# 🔧 Utilitaires LLM
# ---------------------------

TRONCATURE_SIGNES = re.compile(
    r'(,\s*$|\b(et|ou|mais|car|donc|ainsi|notamment|comme|parce|lorsque|que)\s*$'
    r'|[a-zéèêàùîïôâ]\s*$)',  # phrase interrompue en plein mot
    re.IGNORECASE
)

def appeler_llm(prompt: str, temperature: float = 1.0, max_tokens: int = 1024) -> Optional[str]:
    """Appelle Ollama avec retry et gestion d'erreur.
    Si la réponse semble tronquée, relance avec plus de tokens (1 fois).
    """
    for tentative in range(1, MAX_RETRIES + 1):
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
            contenu = response["message"]["content"].strip()
            if not contenu:
                raise ValueError("Réponse vide du modèle")

            # Détection troncature : dernière ligne incomplète + pas de balise fermante
            derniere_ligne = contenu.split("\n")[-1].strip()
            balise_fermante_absente = "[/" not in contenu[-100:]
            if TRONCATURE_SIGNES.search(derniere_ligne) and balise_fermante_absente:
                log.warning(f"Réponse potentiellement tronquée (max_tokens={max_tokens}), relance avec {max_tokens * 2}")
                max_tokens = max_tokens * 2
                continue  # retente avec plus de tokens

            return contenu
        except Exception as e:
            log.warning(f"Tentative {tentative}/{MAX_RETRIES} échouée : {e}")
    log.error("Toutes les tentatives ont échoué.")
    return None


def extraire_balise(texte: str, balise: str) -> Optional[str]:
    """Extrait le contenu entre [BALISE]...[/BALISE], insensible aux fautes de frappe dans la balise fermante."""
    # Balise ouvrante stricte, balise fermante tolérante (ex: [/CONCLUISION])
    pattern = rf'\[{balise}\](.*?)\[/{balise[:4]}\w*\]'
    match = re.search(pattern, texte, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extraire_liste_balises(texte: str, balise: str) -> list[str]:
    """Extrait tous les contenus d'une balise répétée."""
    pattern = rf'\[{balise}\](.*?)\[/{balise}\]'
    resultats = re.findall(pattern, texte, re.DOTALL | re.IGNORECASE)
    return [r.strip() for r in resultats if r.strip()]

# ---------------------------
# 🧠 Génération sujet
# ---------------------------

def generer_sujet() -> str:
    sujet = random.choice(SUJETS)
    angle = random.choice(ANGLES)
    twist = random.choice(TWISTS)
    seed = random.randint(0, 100000)

    prompt = f"""Seed: {seed}

Tu dois générer 5 titres d'articles de podcast technique en français.

Sujet : {sujet}
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

    brut = appeler_llm(prompt, temperature=1.2)
    if not brut:
        return f"{sujet} : {angle}"

    titres = extraire_liste_balises(brut, "TITRE")

    # Fallback : lignes courtes qui ressemblent à des titres
    if not titres:
        log.debug(f"Extraction balises échouée (fallback actif), brut reçu:\n{brut[:500]}")
        lignes = [l.strip() for l in brut.split("\n") if l.strip()]
        titres = []
        for l in lignes:
            # Cas : [Titre[/TITRE] — balise ouvrante manquante (gemma3n)
            m = re.match(r'^\[(.+?)\[/TITRE\]$', l, re.IGNORECASE)
            if m:
                titres.append(m.group(1).strip())
                continue
            # Cas : [TITRE]Titre[/TITRE] déjà géré par extraire_liste_balises mais raté
            m = re.match(r'^\[TITRE\](.+?)\[/TITRE\]$', l, re.IGNORECASE)
            if m:
                titres.append(m.group(1).strip())
                continue
            # Cas : [Titre complet] — crochets simples sans balise fermante XML
            m = re.match(r'^\[([^\[\]/]{10,120})\]\s*$', l)
            if m:
                titres.append(m.group(1).strip())
                continue
            # Cas : ligne brute sans balisage
            if 10 < len(l) < 120 and not l.startswith("["):
                titres.append(nettoyer_titre(l))

    titres = [nettoyer_titre(t).split("\n")[0][:120] for t in titres if t]
    titres_uniques = [t for t in titres if t not in state.titres_generes]

    titre = random.choice(titres_uniques if titres_uniques else titres) if titres else f"{sujet} – {angle}"
    state.titres_generes.add(titre)
    return titre

# ---------------------------
# 📋 Génération plan
# ---------------------------

def generer_plan(sujet: str) -> list[str]:
    prompt = f"""Tu dois créer un plan de podcast technique en français.

Sujet précis : {sujet}

Règles ABSOLUES :
- 4 à 6 parties DISTINCTES, sans chevauchement
- Chaque partie doit couvrir un aspect DIFFÉRENT du sujet
- Titres courts (5 mots max)
- Aucun markdown, aucune explication

Format OBLIGATOIRE :
[PARTIE]Titre[/PARTIE]
[PARTIE]Titre[/PARTIE]"""

    brut = appeler_llm(prompt, temperature=1.0)
    if not brut:
        return ["Introduction", "Contexte historique", "Enjeux techniques", "Perspectives"]

    parties = extraire_liste_balises(brut, "PARTIE")

    if not parties:
        log.debug("Extraction plan échouée (fallback actif)")
        lignes = [l.strip() for l in brut.split("\n") if l.strip()]
        parties = []
        for l in lignes:
            # [PARTIE]Titre</PARTIE] ou [PARTIE]Titre[/PARTIE]
            m = re.match(r'\[PARTIE\](.+?)(?:\[/?|</)PARTIE\]?', l, re.IGNORECASE)
            if m:
                parties.append(m.group(1).strip())
                continue
            # Titre</PARTIE] — balise ouvrante manquante
            m = re.match(r'^(.+?)(?:\[/?|</)PARTIE\]?\s*$', l, re.IGNORECASE)
            if m and len(m.group(1)) > 3:
                parties.append(m.group(1).strip())
                continue

    # Nettoyage résidus de balises dans tous les cas
    parties = [re.sub(r'</?\w+>|\[/?\w+\]?', '', p).strip() for p in parties]
    parties = [p.split("\n")[0][:60] for p in parties if p.strip()]

    if len(parties) < 2:
        log.warning("Plan trop court, utilisation du plan par défaut")
        parties = ["Contexte et origines", "État de l'art", "Enjeux techniques", "Cas d'usage", "Perspectives"]

    return parties[:6]

# ---------------------------
# ✍️ Génération parties
# ---------------------------

def resumer_contexte(contexte: str, max_chars: int = 1500) -> str:
    """Tronque le contexte en gardant les derniers échanges, pas les premiers."""
    if len(contexte) <= max_chars:
        return contexte
    # Garde la fin (plus récente) plutôt que le début
    return "...\n" + contexte[-max_chars:]


TON_CIBLE = """Style attendu :
- Ton journalistique neutre et posé, ni trop familier ni trop académique
- Phrases courtes, rythme oral mais sans exclamations ou interpellations du type "Écoutez bien !"
- Pas de "on" de connivence excessive ; préférer "nous" ou la forme impersonnelle
- Terminer sur une phrase complète, jamais en milieu de pensée"""


def generer_partie(sujet: str, partie: str, parties_precedentes: list[str]) -> str:
    # Résumé des thèmes déjà traités pour éviter les répétitions
    resume_precedent = ""
    if parties_precedentes:
        resume_precedent = "Thèmes déjà couverts (NE PAS RÉPÉTER) :\n" + \
            "\n".join(f"- {p}" for p in parties_precedentes[-3:])

    prompt = f"""Tu es un journaliste radio expert en technologie.

Sujet global du podcast : {sujet}
Partie à rédiger : {partie}

{resume_precedent}

{TON_CIBLE}

Règles ABSOLUES :
- 400 à 500 mots UNIQUEMENT sur "{partie}"
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

    brut = appeler_llm(prompt, temperature=1.1, max_tokens=900)
    if not brut:
        return f"[Contenu indisponible pour la partie : {partie}]"

    contenu = extraire_balise(brut, "PARTIE")
    return contenu if contenu else nettoyer_texte(brut)


def generer_intro(sujet: str, plan: list[str]) -> str:
    plan_str = ", ".join(plan)
    prompt = f"""Tu es un journaliste radio.

Rédige l'introduction d'un podcast sur : {sujet}

Le podcast abordera : {plan_str}

{TON_CIBLE}

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

    brut = appeler_llm(prompt, temperature=1.0)
    if not brut:
        return f"Bienvenue dans ce podcast consacré à {sujet}."

    contenu = extraire_balise(brut, "INTRO")
    return contenu if contenu else nettoyer_texte(brut)


def generer_conclusion(sujet: str, parties: list[str]) -> str:
    points_cles = ", ".join(parties)
    prompt = f"""Tu es un journaliste radio.

Rédige la conclusion d'un podcast sur : {sujet}

Points abordés : {points_cles}

{TON_CIBLE}

Règles :
- 150 à 200 mots
- Synthèse rapide + ouverture sur l'avenir
- Pas de répétition mot pour mot des parties
- Terminer par une phrase complète avant [/CONCLUSION]

Format :
[CONCLUSION]
Texte
[/CONCLUSION]"""

    brut = appeler_llm(prompt, temperature=1.0)
    if not brut:
        return f"Voilà qui conclut notre podcast sur {sujet}. Merci de nous avoir écoutés."

    contenu = extraire_balise(brut, "CONCLUSION")
    return contenu if contenu else nettoyer_texte(brut)

# ---------------------------
# 🧠 Pipeline principal
# ---------------------------

def generer_contenu_long(sujet: str) -> str:
    log.info("📋 Génération du plan...")
    plan = generer_plan(sujet)
    log.info(f"Plan : {plan}")

    sections = []
    titres_traites = []

    log.info("🎙️ Génération de l'intro...")
    intro = generer_intro(sujet, plan)
    sections.append(intro)

    for i, partie in enumerate(plan):
        log.info(f"✍️  Partie {i+1}/{len(plan)} : {partie}")
        texte = generer_partie(sujet, partie, titres_traites)
        sections.append(texte)
        titres_traites.append(partie)

    log.info("🔚 Génération de la conclusion...")
    conclusion = generer_conclusion(sujet, plan)
    sections.append(conclusion)

    return "\n\n".join(sections)

# ---------------------------
# 🧹 Nettoyage
# ---------------------------

def nettoyer_texte(text: str) -> str:
    # Markdown
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Codes ANSI
    text = re.sub(r'\033\[[0-9;]*m', '', text)
    # Didascalies / mise en scène
    text = re.sub(r'\(.*?(musique|bruit|son|ambiance|silence|jingle).*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(musique|bruit|son|ambiance).*?\]', '', text, flags=re.IGNORECASE)
    # Balises résiduelles
    text = re.sub(r'\[/?[A-Z]+\]', '', text)
    # Lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def nettoyer_titre(titre: str) -> str:
    titre = re.sub(r'\[.*?\]', '', titre)
    titre = re.sub(r'^\d+[\).\s]+', '', titre)
    titre = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', titre)
    titre = re.sub(r'\(.*?\)', '', titre)
    titre = titre.replace('"', '').replace("'", "'")
    titre = re.sub(r'\s+', ' ', titre)
    return titre.strip()

# ---------------------------
# 🔊 Piper TTS
# ---------------------------

# Cherche les modèles dans /app/models (Docker) puis dans le répertoire courant
_MODELS_DIR = "/app/models" if os.path.isdir("/app/models") else "."
VOIX_PIPER = [
    os.path.join(_MODELS_DIR, "fr_FR-siwis-medium.onnx"),
    os.path.join(_MODELS_DIR, "fr_FR-mls-medium.onnx"),
    os.path.join(_MODELS_DIR, "fr_FR-gilles-low.onnx"),
]

def trouver_modele_piper() -> Optional[str]:
    for voix in VOIX_PIPER:
        if os.path.exists(voix):
            log.info(f"Modèle Piper trouvé : {voix}")
            return voix
    log.error("Aucun modèle Piper trouvé. Voix disponibles cherchées : " + ", ".join(VOIX_PIPER))
    return None


def generer_audio(texte: str, output_file: str = "podcast.wav") -> Optional[str]:
    model = trouver_modele_piper()
    if not model:
        return None

    tmp = "temp_podcast.txt"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texte)

        cmd = ["sh", "-c", f"cat {tmp} | piper-tts -m {model} -f {output_file}"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log.error(f"Erreur Piper : {result.stderr}")
            return None

        log.info(f"Audio généré : {output_file}")
        return output_file

    except Exception as e:
        log.error(f"Erreur lors de la génération audio : {e}")
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

# ---------------------------
# 🎧 Pipeline complet
# ---------------------------

def creer_podcast(sujet: Optional[str] = None) -> Optional[str]:
    if not sujet:
        sujet = generer_sujet()

    log.info(f"\n🎯 Sujet : {sujet}\n")

    log.info("🧠 Génération du contenu...")
    contenu_brut = generer_contenu_long(sujet)
    contenu = nettoyer_texte(contenu_brut)

    # Sauvegarde du texte (utile pour debug)
    _output_dir = "/app/output" if os.path.isdir("/app/output") else "."
    texte_file = os.path.join(_output_dir, "podcast_texte.txt")
    with open(texte_file, "w", encoding="utf-8") as f:
        f.write(f"SUJET : {sujet}\n\n{contenu}")
    log.info(f"📄 Texte sauvegardé : {texte_file}")

    log.info("🎙️ Génération audio...")
    audio_path = os.path.join(_output_dir, "podcast.wav")
    fichier_audio = generer_audio(contenu, output_file=audio_path)

    if fichier_audio:
        log.info(f"\n✅ Podcast généré : {fichier_audio}")
        return fichier_audio
    else:
        log.warning("⚠️  Audio non généré (Piper manquant ?). Le texte est disponible dans podcast_texte.txt")
        return texte_file

# ---------------------------
# 🚀 Entrée
# ---------------------------

if __name__ == "__main__":
    # Optionnel : passer un sujet en argument
    sujet_custom = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    creer_podcast(sujet=sujet_custom)
