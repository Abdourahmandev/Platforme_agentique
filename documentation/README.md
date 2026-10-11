# Documentation de la plateforme agentique

Ce dossier décrit l'installation réelle, ses limites et les procédures de reprise. Il peut être consulté directement sur GitHub. Les fichiers contenant des secrets ou des conversations ne sont jamais inclus dans le dépôt.

**État au 11 octobre 2026 : migration Docker en validation, ancien bot encore en production.** Les agents Asia, Développement et Recherche fonctionnent dans OpenClaw. La bascule des bots est soumise aux tests Telegram et aux écarts fonctionnels détaillés dans le bilan.

**Développement est activé seul sur Telegram**, avec le bot [Rassdevbot](https://t.me/Rassdevbot). Cinq services Docker sont démarrés, dont Playwright. Les connecteurs d'Asia sont configurés et testés dans OpenClaw, mais son bot continue sur Windows : son superviseur nécessite un arrêt administrateur avant le transfert. Recherche attend son token. Voir la [préparation de la bascule Asia](bascule-asia.md), ses limites et son retour arrière.

| Document | Contenu |
| --- | --- |
| [Architecture](architecture.md) | Composants, flux, agents, données et frontières de confiance |
| [Guide des composantes](composantes.md) | Rôle du code, outils MCP, ajout d'agents et limites de portabilité |
| [Catalogue des modèles](modeles.md) | Les 34 routes et leurs capacités déclarées |
| [Installation et migration](migration.md) | Reproduire le socle Docker, configurer les secrets et valider chaque étape |
| [Bascule Asia](bascule-asia.md) | Connecteurs conservés, transfert du token et du budget, intervention Windows et rollback |
| [Exploitation et sauvegardes](exploitation.md) | Démarrage, état, coûts, mises à jour et restauration |
| [Retour arrière](rollback.md) | Arrêter le candidat et conserver/reprendre l'installation Windows |
| [API de la future application](api.md) | Identités, sessions, streaming, annulation et reconnexion |
| [Revue et résultats](revue-et-tests.md) | Tests effectivement exécutés, défauts corrigés et travail restant |

Le [plan initial](../docs/plan-plateforme-agents.md) explique les décisions de départ. L'[exploitation Windows historique](../docs/operations.md) reste pertinente pour le retour arrière. Le code de l'ancienne interface est conservé ; aucun Dockerfile de cette application n'est créé.
