# Intégrations de l'installation Windows

Ces fichiers conservent les scripts écrits pour l'installation existante. Les services OpenCode, Telegram, Speech et OpenChamber utilisent encore leurs copies déployées sous `%LOCALAPPDATA%`. Modifier un fichier dans ce dossier ne redéploie pas le service : comparer, tester puis copier explicitement les changements vers sa destination avant un redémarrage contrôlé.

| Source | Destination / dépendance de référence |
| --- | --- |
| `opencode/run-server.ps1` | `%LOCALAPPDATA%/OpenCodeWeb/run-server.ps1` ; OpenCode 1.18.35 sous `Programs/OpenCode` |
| `opencode/opencode.example.json` | Modèle pour `%USERPROFILE%/.config/opencode/opencode.json` ; ne pas écraser une configuration existante |
| `telegram/run-bot.ps1` | `%LOCALAPPDATA%/Programs/OpenCodeTelegram/run-bot.ps1` ; `@grinev/opencode-telegram-bot` 0.26.3 |
| `speech/` | `%LOCALAPPDATA%/Programs/OpenCodeTelegramSpeech` ; Python et venv propres au service |
| `openchamber/run-openchamber.ps1` | `%LOCALAPPDATA%/OpenChamberWeb/run-openchamber.ps1` ; installation OpenChamber existante |

Les lanceurs reflètent les chemins et versions de l'installation de référence. Ils supposent les répertoires d'état, environnements Python, binaires, identifiants et tâches Windows déjà préparés. Ils ne sont pas des installateurs autonomes. Le lanceur Telegram utilise le Node embarqué d'OpenChamber ; adapter ce chemin lors d'une nouvelle installation.

## OpenCode et MCP

L'exemple conserve le fournisseur LiteLLM, les capacités déclarées des modèles et la politique d'autorisations des agents. Adapter `VOTRE_UTILISATEUR` et les paramètres propres à la machine. Les secrets des MCP sont remplacés par des références `{env:NOM}` : ces variables doivent être fournies au processus OpenCode depuis un stockage local protégé. Les autorisations OAuth Google restent à établir sur la machine et ne sont pas incluses.

La référence `agent.key` vise une clé LiteLLM de service à provisionner séparément : endpoints d'inférence/liste des modèles, liste de modèles autorisés, budget, limites de débit et concurrence. La clé administrateur `gateway.key` reste indépendante. Les limites affichées par Asia ne configurent pas la clé serveur.

Les contrôles d'autorisation OpenCode demandent un accord par défaut, avec des exceptions pour certaines lectures et opérations de travail ; ils ne constituent pas une isolation du système d'exploitation.

## Telegram et audio

Le paquet tiers du bot, ses dépendances et son archive d'installation ne sont pas inclus dans ce dépôt. `telegram/distribution.json` identifie la version et l'empreinte SHA-256 de l'archive d'origine. `telegram/local-changes.patch` conserve le changement local détecté dans les fichiers de cette distribution : le contrôle d'accès exige une conversation privée. Vérifier l'archive puis appliquer ce patch à la racine du paquet installé avant de reconstruire le bot. Le dépôt conserve le correctif, sans copier l'ensemble de `node_modules`.

Le service vocal contient le code de transcription, le lanceur et les versions Python relevées dans l'environnement existant. `download-model.py` télécharge `Systran/faster-whisper-base` et enregistre la révision téléchargée ; il requiert Internet et n'est jamais exécuté par la CI. Le modèle et les enregistrements vocaux ne sont pas suivis par Git. Le lanceur charge ensuite le modèle local en mode hors connexion.

Le bot lit ses identifiants et le secret vocal depuis `%LOCALAPPDATA%/OpenCodeTelegramSetup`. Il utilise l'API OpenCode locale et la transcription sur `127.0.0.1:4123`. Les fonctionnalités audio Telegram sont distinctes des pièces jointes de l'interface web Asia.
