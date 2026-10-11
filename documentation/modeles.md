# Catalogue des modèles

Inventaire généré depuis `gateway/config.yaml` par `python scripts/document-models.py`. Les capacités ci-dessous sont déclarées dans la configuration ; elles ne constituent pas un nouveau test réel de chaque endpoint.

Le catalogue contient 34 routes, dont 16 conversationnelles. Les modèles spécialisés restent dans LiteLLM mais ne deviennent pas automatiquement des outils OpenClaw. Leur présence au catalogue ne garantit ni le quota fournisseur disponible, ni leur exposition dans Telegram.

| Route | Mode | Entrées | Sorties | Outils | JSON Schema |
| --- | --- | --- | --- | --- | --- |
| `asia-rapide` | chat | text, image | text | oui | non |
| `asia-pro` | chat | text | text | oui | non |
| `gemini-2.5-flash-image` | image_generation | text, image | text, image | non | non |
| `gemini-3-pro-image` | image_generation | text, image | text, image | non | non |
| `gemini-3-pro-image-preview` | image_generation | text, image | text, image | non | non |
| `gemini-3.1-flash-image` | image_generation | text, image, video, pdf | text, image | non | non |
| `gemini-3.1-flash-image-preview` | image_generation | text, image, video, pdf | text, image | non | non |
| `gemini-3.1-flash-lite-image` | image_generation | text, image, video, pdf | text, image | non | non |
| `gemini-nano-banana-2.1` | image_generation | text, image, video, pdf | text, image | non | non |
| `gemini-omni-1.1-flash` | interactions | text, image, audio, video | text, video | non | non |
| `gemini-omni-flash-preview` | interactions | text, image, audio, video | text, video | non | non |
| `gemini-embedding-001` | embedding | text | embedding | non | non |
| `gemini-embedding-2` | embedding | text, image, audio, video, pdf | embedding | non | non |
| `gemini-embedding-2-preview` | embedding | text, image, audio, video, pdf | embedding | non | non |
| `gemini-2.5-flash-preview-tts` | audio_speech | text | audio | non | non |
| `gemini-2.5-pro-preview-tts` | audio_speech | text | audio | non | non |
| `gemini-3.1-flash-tts-preview` | audio_speech | text | audio | non | non |
| `gemini-3.8-flash-lite-tts` | audio_speech | text | audio | non | non |
| `gemini-3.8-flash-tts` | audio_speech | text | audio | non | non |
| `gemini-3-flash-preview` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.1-flash-lite` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.1-flash-lite-preview` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.1-pro-preview` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.1-pro-preview-customtools` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.5-flash` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.5-flash-lite` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.6-flash` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.7-flash` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.8-flash` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-flash-latest` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-flash-lite-latest` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-pro-latest` | chat | text, image, audio, video, pdf | text | oui | oui |
| `gemini-3.5-transcribe` | audio_transcription | audio | text | non | non |
| `asia-auto` | chat | text, image, audio, video, pdf | text | oui | oui |

## Utilisation dans les agents

Le défaut OpenClaw est `litellm/asia-auto`. La limite déclarée au moteur est de 128 000 tokens de contexte au maximum et 4 096 tokens de sortie, plus restrictive que certaines limites fournisseur. LiteLLM limite les appels Auto à 8 192 tokens ; la borne demandée par le moteur reste applicable.

Les notes vocales passent d’abord par Speaches et deviennent du texte. Le test image a traversé OpenClaw puis LiteLLM. Les capacités PDF/audio/vidéo annoncées dans LiteLLM ne prouvent pas leur prise en charge comme pièces jointes natives par chaque client.

Les essais réels antérieurs des 34 routes sont décrits dans [l’état de référence](../docs/operations.md). Les tests propres à la migration sont distingués dans [le bilan](revue-et-tests.md). Aucun test de contexte maximal ni nouvel essai de génération vidéo n’est revendiqué.

## Réévaluation

Les alias « latest », quotas, capacités et prix évoluent. Revalider une modification contre les API et documentations des fournisseurs, mettre à jour `model_info`, tester les replis, puis régénérer ce tableau. Sources utilisées par le catalogue : [DeepSeek](https://api-docs.deepseek.com/api/list-models/), [Gemini](https://ai.google.dev/gemini-api/docs/models).
