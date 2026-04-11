# 🎙️ Podcast Generator

Générateur automatique de podcasts techniques en français. Le script choisit un sujet, rédige un script complet via un LLM local, puis le synthétise en audio avec Piper TTS.

---

## Fonctionnement

1. **Génération du sujet** — un sujet, un angle éditorial et un contexte sont tirés aléatoirement (ou fournis manuellement)
2. **Plan** — le LLM génère un plan en 4 à 6 parties distinctes
3. **Rédaction** — intro, parties et conclusion sont rédigées séquentiellement, chaque partie ignorant les thèmes déjà couverts
4. **Synthèse vocale** — le texte est converti en `.wav` par Piper TTS avec la voix `fr_FR-siwis-medium`
5. **Sauvegarde** — le texte brut est toujours écrit dans `podcast_texte.txt`, l'audio dans `podcast.wav`

---

## Prérequis

| Outil | Rôle | Installation |
|---|---|---|
| Python 3.9+ | Exécution du script | [python.org](https://www.python.org/downloads/) |
| [Ollama](https://ollama.com) | LLM local | `curl -fsSL https://ollama.com/install.sh \| sh` |
| modèle `gemma3n` | Génération du texte | `ollama pull gemma3n` |
| [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) | Synthèse vocale | voir ci-dessous |
| `curl` ou `wget` | Téléchargement du modèle voix | inclus sur la plupart des systèmes |

### Installer Piper TTS

Si comme moi, vous etes sur ArchLinux, vous pouvez passer par l'AUR :

```bash
yay -S piper-tts
```

Sinon, téléchargez la dernière release pour votre architecture depuis [github.com/OHF-Voice/piper/releases](https://github.com/OHF-Voice/piper1-gpl/releases)

> **Note :** le modèle de voix (`fr_FR-siwis-medium.onnx`) est téléchargé automatiquement par `run.sh` au premier lancement.

---

## Installation

```bash
git clone https://github.com/AdrienPiechocki/podcast-generator.git
cd podcast-generator
chmod +x run.sh
```

Les dépendances Python sont installées automatiquement dans un virtualenv `.venv/` au premier lancement.

---

## Utilisation

```bash
# Sujet aléatoire
./run.sh

# Sujet personnalisé
./run.sh "La conteneurisation dans les environnements critiques"
```

### Fichiers générés

| Fichier | Contenu |
|---|---|
| `podcast_texte.txt` | Script complet du podcast (toujours généré) |
| `podcast.wav` | Audio synthétisé (si Piper TTS est disponible) |

---

## Structure du projet

```
.
├── main.py                         # Pipeline principal
├── run.sh                          # Script de lancement
├── requirements.txt                # Dépendances Python
├── fr_FR-siwis-medium.onnx         # Modèle voix Piper (téléchargé auto)
├── fr_FR-siwis-medium.onnx.json    # Config du modèle (téléchargé auto)
├── .venv/                          # Virtualenv (créé auto)
├── podcast_texte.txt               # Sortie texte (créé à l'exécution)
└── podcast.wav                     # Sortie audio (créé à l'exécution)
```

---

## Configuration

Les paramètres éditoriaux sont définis en tête de `main.py` :

- **`SUJETS`** — liste des domaines techniques disponibles (Linux, Blockchain, Jeux vidéo…)
- **`ANGLES`** — angle éditorial appliqué (historique, critique, comparatif…)
- **`TWISTS`** — contexte supplémentaire (industriel, écologique, post-GAFAM…)
- **`MODEL`** — modèle Ollama utilisé (défaut : `gemma3n`)
- **`VOIX_PIPER`** — liste ordonnée des modèles de voix tentés

---

## Dépannage

**Ollama ne répond pas**
Vérifiez que le service tourne : `ollama serve`. Si le modèle n'est pas encore téléchargé : `ollama pull gemma3n`.

**Pas d'audio généré**
Vérifiez que `piper-tts` est bien dans le PATH : `which piper-tts`. Le texte reste disponible dans `podcast_texte.txt`.

**Téléchargement du modèle voix échoue**
Vérifiez votre connexion, puis téléchargez manuellement depuis [Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium) et placez les deux fichiers à la racine du projet.

**Réponse tronquée du LLM**
Le script détecte automatiquement les troncatures et relance avec un budget de tokens doublé. Si le problème persiste, augmentez `max_tokens` dans les appels à `appeler_llm()`.
