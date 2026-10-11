# Installation de référence — état au 11 octobre 2026

Ce document décrit les services déjà installés et les validations historiques. Cloner le dépôt ne provisionne pas ces services ni les tâches Windows. Les paramètres personnels sont remplacés par des exemples.

# Asia — interface personnelle OpenCode

Application privée inspirée de la référence Muse fournie, en français, pour téléphone et ordinateur. Les thèmes noir et blanc sont mémorisés sur chaque appareil.

## Fonctionnalités

- Conversations existantes OpenCode, création de sessions, envoi à DeepSeek et suivi en direct.
- Réponses Markdown, arrêt d'une tâche et affichage des erreurs.
- Activité des outils, plan de tâches, fichiers modifiés et comparaison avant/après.
- Approbation ou refus des demandes OpenCode et réponses aux questions de l'agent.
- Pièces jointes texte/code jusqu'à 150 Ko chacune, trois par message.
- Installation depuis le navigateur (PWA), avec un écran hors connexion. Aucun message n'est envoyé ou mis en file hors connexion.
- Lien vers le bot Telegram existant. L'application ne change pas le bot et ne transmet pas de messages Telegram.

## Lancement sur ce PC

Après installation des prérequis, pour reconstruire :

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd test
```

Pour lancer directement : `npm.cmd start`. Le serveur écoute uniquement sur `http://127.0.0.1:3210`.

`start-asia.ps1` surveille le serveur et le redémarre après un arrêt inattendu. Il utilise un verrou pour éviter plusieurs superviseurs. Les journaux se trouvent dans `%LOCALAPPDATA%\AsiaAgent`.

Un raccourci `Asia Agent.lnk` est installé dans le dossier Démarrage de l'utilisateur Windows. Il relance l'application à l'ouverture de session. Pour désactiver ce démarrage automatique, retirer ce raccourci via `shell:startup`.

## Accès privé sur téléphone / laptop

L'adresse prévue est `https://VOTRE-PC.VOTRE-TAILNET.ts.net:9443`.

Sur l'installation de référence, l'accès privé utilise :

```powershell
tailscale serve --bg --https=9443 http://127.0.0.1:3210
```

Ouvrir l'adresse avec Tailscale actif sur le téléphone ou le laptop. Le PC, OpenCode et Asia doivent être démarrés. L'accès HTTPS privé a été vérifié depuis ce PC ; un essai physique sur le téléphone reste à faire. Les autres adresses OpenCode et OpenChamber restent inchangées.

## Connexion et confidentialité

`config.local.json` contient les chemins locaux et les paramètres de connexion, sans clé API ni mot de passe. Le serveur relit les identifiants OpenCode existants dans `%LOCALAPPDATA%\OpenCodeWeb\server-secret.json`. Ils ne sont pas renvoyés au navigateur. OpenCode appelle DeepSeek ou Google via le proxy LiteLLM local.

## Routage LiteLLM — 11 octobre 2026

Trajet : téléphone/laptop → Tailscale → Asia → OpenCode → LiteLLM local (`127.0.0.1:4000`) → DeepSeek ou Google AI Studio.

**Auto économique** (`litellm/asia-auto`) est le défaut des nouvelles conversations. Le classificateur heuristique local de LiteLLM choisit sans appel API supplémentaire :

| Niveau | Modèle |
| --- | --- |
| Simple | DeepSeek Flash |
| Intermédiaire | Gemini 3.1 Flash-Lite |
| Complexe | Gemini 3.8 Flash |
| Raisonnement avancé | Gemini 3.1 Pro Preview |

Le classement dépend du texte et de règles françaises/anglaises. Il ne garantit pas le modèle optimal ni un pourcentage d'économie. La décision reste stable pendant les appels d'outils d'une demande, avec une identité de tâche hachée et une durée de conservation maximale d'une heure. Chaque nouvelle demande est classée à nouveau. Les anciens profils manuels restent mémorisés : choisir Auto pour les convertir.

Auto limite chaque réponse à 8 192 tokens et chaque appel à un repli, sans nouvelle tentative sur le même fournisseur. Flash et Flash-Lite se remplacent en cas d'erreur ; les niveaux Complexe/Raisonnement ont DeepSeek Pro en secours. Délai : 120 secondes par tentative. OpenCode peut lui-même reprendre une tâche : ces bornes ne sont pas un budget financier global.

Les 10 références Gemini conversationnelles validées restent sélectionnables manuellement, avec les deux DeepSeek. Trois alias Google « latest » sont aussi accessibles via LiteLLM/OpenCode. Les 18 modèles spécialisés validés (image, synthèse vocale, embeddings, transcription, Omni Interactions) sont activés sur leurs endpoints LiteLLM dédiés, pas dans le chat. Live et Robotics ne sont pas intégrés à Asia ; les modèles refusés ou indisponibles lors des tests sont exclus.

Les Réglages affichent appels, tokens et estimation de coût par modèle. La clé de service de l’agent possède un budget de 20 $ US sur 30 jours, 60 appels/minute et 4 appels simultanés. Les requêtes déjà en vol et les délais de comptabilisation peuvent dépasser le seuil ; les appels administrateur restent hors de ce budget. Tarifs vérifiés : [Google](https://ai.google.dev/gemini-api/docs/pricing), [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing). Le tarif promotionnel Gemini 3.8 Flash est temporaire : vérifier les prix avant de réévaluer cette politique. Configuration documentée dans `gateway/routing-policy.json` et `gateway/config.yaml` ; fonctionnement du [routeur LiteLLM](https://docs.litellm.ai/docs/proxy/auto_routing).

`gateway/run.py` lit les clés locales DeepSeek/OpenCode, `AsiaLiteLLM/gemini.key` et `AsiaLiteLLM/gateway.key` sous LOCALAPPDATA. Aucune clé n'est envoyée au navigateur. LiteLLM 1.104.1 et Prisma 0.15.0 sont installés dans `%LOCALAPPDATA%/Programs/AsiaLiteLLM/venv`, avec PostgreSQL local pour le tableau de bord. Le proxy exige sa clé et reste sur loopback.

Les superviseurs existants relancent Asia et LiteLLM après un arrêt ; les raccourcis Windows assurent le démarrage à l'ouverture de session. `usage.jsonl` conserve modèle, niveau, durée, statut, tokens et estimation, jamais les messages. Rotation à 10 Mo ; le compteur couvre le journal courant.

Telegram conserve son choix mémorisé : sélectionner **LiteLLM local → Auto économique / asia-auto** dans son menu de modèles. Un choix dans un autre client ne synchronise pas le sélecteur Asia.

## Consolidation — premier lot du 11 octobre 2026

OpenCode utilise une clé de service référencée par fichier (`AsiaLiteLLM/agent.key`), limitée aux 34 routes configurées et aux endpoints d’inférence/liste des modèles. La clé administrateur reste réservée à l’administration. Seul le fournisseur `litellm` est activé dans OpenCode ; les définitions historiques sont conservées mais désactivées. Modifier le budget de la clé `asia-agent` dans le dashboard LiteLLM et mettre à jour `config.local.json:limits` pour l’affichage.

La politique globale OpenCode demande un accord par défaut. Les agents autorisent les lectures usuelles et les opérations de travail courantes ; commandes shell non listées, écritures MCP et accès externes demandent un accord. Les fichiers de secrets connus sont refusés par les outils de lecture/édition. Limites : 30 étapes build, 20 plan, 15 general/explore. Ces règles ne constituent pas une sandbox du système d’exploitation : une commande explicitement autorisée peut avoir des effets plus larges. Un compte d’exécution isolé reste un chantier distinct.

Les envois de messages Asia utilisent un UUID persistant et un journal SQLite (`%LOCALAPPDATA%/AsiaAgent/requests.sqlite`) sans texte ni contenu de pièce jointe. Les doublons reprennent le résultat connu. Une confirmation perdue est vérifiée dans OpenCode grâce au messageID enregistré ; aucun renvoi automatique en cas d’incertitude. Le bouton « Abandonner cet envoi » clôt la vérification après confirmation explicite, sans rejouer le message. Le serveur bloque les soumissions simultanées d’une conversation. Le navigateur renouvelle le token CSRF expiré en conservant l’identité de la demande. Cette protection concerne les prompts de l’interface Asia ; la création de conversation et le transport Telegram ne passent pas encore par le même journal. Elle ne garantit pas l’exécution exactement une fois des effets externes des outils.

`npm test` exécute 10 tests : accès, CSRF, doublons, concurrence, redémarrage, réponse perdue, abandon explicite et stockage navigateur sans message. Les rapports des essais de production restent conservés localement ; ils ne font pas partie du dépôt.

## Sauvegardes chiffrées

La tâche Windows `Asia Encrypted Backup` s’exécute quotidiennement à 03:00 et à l’ouverture de session (si la dernière sauvegarde date de plus de 23 heures). Elle s’exécute avec les droits limités de l’utilisateur ; le PC et une session disponible sont nécessaires. Le Planificateur rattrape une exécution manquée et retente les échecs deux fois. `ops/run-backup.ps1 -Force` lance une sauvegarde immédiate.

Archives AES-256-GCM dans `D:/AsiaBackups`. Chaque sauvegarde comprend le code/configuration Asia, l’espace de travail, les configurations OpenCode/MCP, l’historique SQLite, le journal des envois, les secrets et paramètres des connecteurs trouvés, et un dump PostgreSQL. Les dépendances réinstallables, modèles vocaux téléchargés, caches navigateur/snapshots, binaires et logs sont exclus. Chaque archive est déchiffrée pour contrôler ses empreintes, l’intégrité SQLite et la lisibilité du dump. Aucun effacement automatique des anciennes archives dans cette première version.

La clé de récupération est `%LOCALAPPDATA%/AsiaBackup/recovery-key.txt`, protégée par les permissions Windows. Conserver une copie de cette clé dans un gestionnaire de mots de passe ou un emplacement sûr indépendant du PC ; ne pas la stocker en clair avec les archives. D: est un second disque interne : une copie des archives hors du PC reste à organiser. Les copies ne sont pas un instantané transactionnel commun aux différents services.

Test de restauration isolé (n’écrase pas la production) :

```powershell
& "$env:LOCALAPPDATA\Programs\AsiaLiteLLM\venv\Scripts\python.exe" .\ops\backup.py --verify 'D:\AsiaBackups\NOM_ARCHIVE.aes' --restore-check
```

Le test restaure PostgreSQL dans une base temporaire dédiée, contrôle les tables puis supprime uniquement cette base. Il vérifie aussi l’historique SQLite et les empreintes de tous les fichiers. Les journaux d’exécution et `last-backup.json` sont sous `%LOCALAPPDATA%/AsiaBackup`.

Les protections Tailscale, propriétaire, origine et CSRF restent actives. L'historique reste dans OpenCode sur le PC ; le contexte nécessaire est envoyé au fournisseur choisi. Le service worker ne met pas les conversations en cache.

## Limites de cette version

L'avatar est une initiale provisoire. La voix, les fichiers binaires/images, les notifications push en arrière-plan et une mémoire personnelle indépendante ne sont pas implémentés. Les fichiers visibles sont les modifications rapportées par OpenCode pour la session, pas un explorateur complet du disque. Les mêmes sessions sont disponibles dans les interfaces qui utilisent ce serveur ; chaque interface peut sélectionner une conversation différente.

## Validation effectuée

Compilation, tests de contrôle d'accès et CSRF, test réel de conversation DeepSeek, chargement des panneaux, persistance des thèmes, navigation mobile et absence de débordement de 320 à 1440 px. Le serveur HTTPS privé et le redémarrage via superviseur ont été vérifiés. Aucun essai physique n'a été effectué sur le téléphone ou le laptop distant.


## PostgreSQL et tableau de bord LiteLLM

PostgreSQL 17.11 (binaires Windows EDB) est installé dans `%LOCALAPPDATA%/Programs/AsiaPostgreSQL/pgsql`. Le cluster persistant se trouve dans `%LOCALAPPDATA%/AsiaPostgreSQL/data`. Il écoute uniquement sur `127.0.0.1:55432`, avec authentification SCRAM. Le rôle applicatif `litellm` possède sa base et n'est pas superutilisateur.

Le superviseur `gateway/start-postgres.ps1` et le raccourci de démarrage Windows `Asia PostgreSQL.lnk` relancent la base. LiteLLM charge son URL, son sel de chiffrement persistant et ses identifiants administrateur depuis `%LOCALAPPDATA%/AsiaLiteLLM/database.json`, protégé par les permissions Windows. Conserver ce fichier et le cluster ensemble lors d'une sauvegarde ; ne pas régénérer le sel de chiffrement.

Tableau de bord local : http://127.0.0.1:4000/ui/ ; utilisateur : `admin`. Pour copier le mot de passe sans l'afficher :

```powershell
(Get-Content "$env:LOCALAPPDATA\AsiaLiteLLM\database.json" | ConvertFrom-Json).ui_password | Set-Clipboard
```

La base et l'interface d'administration ne sont pas publiées sur Tailscale. Les modèles et règles de routage restent définis dans `gateway/config.yaml`. Les nouvelles statistiques de consommation sont enregistrées en base, sans contenu des messages ; les anciens compteurs JSONL d'Asia ne sont pas importés dans le tableau de bord.

Prisma Client Python a été généré à partir du schéma de `litellm_proxy_extras`. Après une mise à niveau LiteLLM, régénérer le client avec le Python du venv, `PYTHONUTF8=1` et le dossier Scripts du venv dans PATH avant de migrer la base. Les migrations sont exécutées au démarrage du proxy.

Compatibilité Windows LiteLLM 1.104.1 : `gateway/windows_prisma.py` remplace les sondes `os.kill(pid, 0)` du watchdog Prisma par `OpenProcess`/`WaitForSingleObject`, qui ne terminent pas le processus sous Windows. Correctif chargé au démarrage, sans modifier les fichiers du paquet installé. À réévaluer lors de la prochaine mise à niveau.


## Images reçues par Telegram

Audit du 11 octobre 2026 : les 13 références Gemini de conversation et `asia-auto` déclarent texte, image, audio et PDF dans OpenCode. DeepSeek Flash accepte texte et image (vérifié en réel) ; DeepSeek Pro reste textuel. Le bot Telegram transmet les photos en pièces jointes JPEG. Les requêtes Auto avec audio/PDF/vidéo ou JSON Schema strict passent par Gemini Flash-Lite. Les replis multimodaux utilisent des Gemini compatibles, y compris pour une sélection manuelle. Les replis textuels décrits plus haut restent inchangés.

Les 34 routes ont reçu des appels réels : conversation/outils, image, TTS, embeddings, transcription ou interaction textuelle selon leur mode. Les 13 Gemini conversationnels et Auto ont passé les tests image, PDF/audio et vidéo via LiteLLM. PDF/audio fonctionnent aussi via OpenCode ; l'adaptateur OpenCode testé refuse la vidéo WebM, donc la vidéo n'est pas annoncée dans ses capacités. Tests de panne simulée : replis compatibles et limite d'un repli respectés. DeepSeek accepte JSON object mais refuse le JSON Schema strict ; ses métadonnées reflètent cette limite. La génération vidéo Omni et les longueurs maximales de contexte n'ont pas été testées. Les rapports détaillés de ces essais restent conservés localement.

Les paramètres Telegram enregistrés et les valeurs par défaut du lanceur sont `litellm/asia-auto`. Le processus Telegram démarré avec des droits supérieurs a refusé le redémarrage depuis cette session Windows : sélectionner Auto dans son menu de modèles pour appliquer le changement en mémoire. Le bouton de pièces jointes de l'interface Asia reste limité aux fichiers texte ; cette modification concerne le chemin Telegram/OpenCode.
