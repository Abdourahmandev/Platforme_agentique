# Guide du code et des composantes

## Services actuels et remplacement prévu

| Composante | Fonction actuelle | Candidat Docker |
| --- | --- | --- |
| Asia Web, `src/`, `public/` | Interface française, thèmes clair/sombre, sessions, approbations, différences de fichiers | Conservée côté Windows ; future application distincte |
| `server.mjs` | Accès local/Tailscale propriétaire, CSRF, API de façade, flux OpenCode | API Gateway OpenClaw pour la future application |
| `request-journal.mjs` | Journal SQLite et réconciliation des envois incertains, sans répétition aveugle | Idempotence et historique Gateway testés ; garanties après crash à approfondir |
| OpenCode et `integrations/opencode/` | Exécution d'agent et outils MCP | OpenClaw pour la conversation ; `infra/opencode-bridge/` conserve les tâches Windows d'Asia via OpenCode et ses permissions. Le spécialiste n'a pas cette passerelle |
| `integrations/telegram/` | Bot unique, correctif autorisant seulement les conversations privées | Comptes Telegram natifs, un bot distinct par agent |
| `integrations/speech/` | Transcription Whisper dans un service Python Windows | Image Speaches et volume de modèles |
| `gateway/` | LiteLLM, catalogue et routage économique | Même configuration fonctionnelle dans l'image LiteLLM |
| PostgreSQL Windows | Clés, limites et comptabilité LiteLLM | PostgreSQL 17.11, migration logique de 91 tables |
| OpenChamber | Interface alternative d'OpenCode | Conservée pendant le retour arrière |
| Tailscale | Accès privé à la machine | Service Windows conservé ; aucun nouveau port public |

## Frontend et envois

`src/app.js` construit les vues et suit les événements serveur. Le Markdown passe par DOMPurify. `src/submission.js` conserve une identité d'envoi dans le navigateur pour reconnaître une tentative répétée ; il ne conserve pas le contenu du message. Le service worker ne met en cache que l'écran hors connexion. L'interface actuelle accepte des pièces jointes texte ; cela ne décrit pas les capacités photo du bot Telegram.

`server.mjs` vérifie le compte propriétaire, l'origine des mutations et le jeton CSRF. Il transmet les demandes avec l'authentification OpenCode, conservée côté serveur. `request-journal.mjs` marque une demande interrompue comme incertaine, la recherche dans OpenCode et exige une résolution explicite lorsque son état ne peut être confirmé. Ces garanties sont couvertes par les tests Node et restent utiles pour concevoir la future application.

## Modèles et outils : deux circuits distincts

`gateway/config.yaml` déclare les modèles et leurs capacités. `routing_context.py` fournit une identité stable pendant les appels d'outils et protège les replis multimodaux. `metrics.py` journalise uniquement les métadonnées d'appel, avec rotation. La base PostgreSQL est la référence de comptabilité ; le compteur de l'interface historique couvre seulement le journal courant.

LiteLLM ne migre pas les outils MCP d'OpenCode. Ceux-ci doivent être raccordés au moteur d'agent avec une politique propre :

| Outil existant | Décision / travail restant |
| --- | --- |
| Google Workspace | Exclu de cette bascule à la demande du propriétaire : il n'était pas connecté |
| Recherche Tavily | MCP distant officiel configuré pour Asia ; recherche et extraction testées, facturation distincte des LLM |
| Playwright | Conteneur MCP officiel dédié à Asia, sans port hôte ni secrets ; nouveau contexte sans les connexions Windows, navigation et capture testées |
| Mémoire MCP | Serveur figé avec JSONL propre à Asia ; lecture/écriture et persistance testées. Le fichier Windows était absent |

Une image est publiée pour [Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp/pkgs/container/google_workspace_mcp). Cela ne prouve pas que les autorisations OAuth et l'isolation du projet y fonctionnent déjà : son intégration n'est pas activée dans ce candidat.

Le plugin natif `infra/opencode-bridge/` est chargé par l'image OpenClaw existante. Il crée uniquement ses propres sessions OpenCode, journalise les envois avant transmission et refuse de rejouer une soumission incertaine. Les identifiants sont privés, hors des workspaces. Les validations passent par les permissions natives OpenClaw : une décision `allow-once` est liée à l'appel et à la demande exacte, consommable une fois. Le modèle ne peut pas s'accorder une autorisation ; aucun `allow-always` n'est proposé. Une absence de surface d'approbation échoue fermée. Le suivi des tâches longues reste explicite ; pas de notification autonome de fin. Cette compatibilité conserve une dépendance Windows, à remplacer plus tard par un exécuteur isolé si l'on vise un déploiement entièrement Linux.

## Ajouter un agent

Définir un identifiant stable, une mission et un bot distinct. Prévoir un workspace, un répertoire d'état, une clé LiteLLM dans l'équipe budgétaire commune et une association compte Telegram–agent. Donner seulement les outils nécessaires. Tester lecture/écriture de son espace, refus d'accès aux autres sessions, attribution des dépenses et réponse sur le bon bot. Les scripts initiaux refusent d'écraser les trois agents installés ; une extension doit fusionner la configuration active, pas relancer l'initialiseur.

Les instructions `AGENTS.md` orientent le comportement du modèle. Elles ne remplacent ni les contrôles d'outils, ni les budgets, ni une séparation de processus lorsque des identités doivent être réellement isolées.

## Ce qui reste propre à Windows

Les scripts d'exploitation contiennent les chemins de l'installation de référence et utilisent les ACL Windows. Le runtime des agents est Linux dans Docker, mais **ce dépôt n'est pas encore un installateur universel pour un serveur Linux neuf**. Une prochaine étape pourra paramétrer les chemins hôte et supprimer les dépendances de migration vers les anciens services, après la bascule et sa période de retour arrière.
