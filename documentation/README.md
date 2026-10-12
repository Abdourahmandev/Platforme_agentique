# Documentation de la plateforme agentique

Ce dossier décrit l'installation réelle, ses limites et les procédures de reprise. Il peut être consulté directement sur GitHub. Les fichiers contenant des secrets ou des conversations ne sont jamais inclus dans le dépôt.

**État au 11 octobre 2026 : Asia a basculé dans OpenClaw, en phase pilote.** Le propriétaire confirme les réponses Telegram des trois bots, ainsi que la photo et le vocal d'Asia. Les boutons d'approbation ont été reçus et les deux décisions vérifiées : accord unique avec exécution, refus sans exécution. La reprise après redémarrage Windows reste à valider.

**Asia conserve [son bot habituel](https://t.me/Absourahman03_bot)** ; Développement utilise [Rassdevbot](https://t.me/Rassdevbot) et Recherche [Rassresearchbot](https://t.me/Rassresearchbot). Cinq services Docker sont sains, dont Playwright. L'ancien consommateur Telegram est arrêté et sa relance bloquée par un marqueur persistant. OpenCode reste disponible comme exécuteur Windows et partage désormais le budget Docker. Voir la [bascule Asia](bascule-asia.md), ses limites et son retour arrière.

| Document | Contenu |
| --- | --- |
| [Architecture](architecture.md) | Composants, flux, agents, données et frontières de confiance |
| [Guide des composantes](composantes.md) | Rôle du code, outils MCP, ajout d'agents et limites de portabilité |
| [Catalogue des modèles](modeles.md) | Les 34 routes et leurs capacités déclarées |
| [Installation et migration](migration.md) | Reproduire le socle Docker, configurer les secrets et valider chaque étape |
| [Bascule Asia](bascule-asia.md) | Connecteurs conservés, transfert du token et du budget, intervention Windows et rollback |
| [Délégation entre agents](delegation.md) | Asia coordinatrice, missions séparées, résultats, permissions, coûts et tests |
| [Formation supervisée](formation/README.md) | Exercices sur le projet, bac à sable, budget, qualification et retour arrière |
| [Bilan du premier cycle](formation/bilan-cycle-1.md) | Résultats réels, corrections, limites et promotion revue par le superviseur |
| [Reprise ciblée](formation/bilan-reprise.md) | Réconciliation d'Asia, périmètre de Développement et formation sans redémarrer les bots |
| [Tests de robustesse](tests-robustesse.md) | Confirmation Telegram, coupures réelles de l'exécuteur, reçus durables et limites d'exécution |
| [Approbations Telegram](approbations-telegram.md) | Boutons privés, distinction expiration/refus, accord unique et preuves d'exécution |
| [Exploitation et sauvegardes](exploitation.md) | Démarrage, état, coûts, mises à jour et restauration |
| [Retour arrière](rollback.md) | Arrêter le candidat et conserver/reprendre l'installation Windows |
| [API de la future application](api.md) | Identités, sessions, streaming, annulation et reconnexion |
| [Revue et résultats](revue-et-tests.md) | Tests effectivement exécutés, défauts corrigés et travail restant |

Le [plan initial](../docs/plan-plateforme-agents.md) explique les décisions de départ. L'[exploitation Windows historique](../docs/operations.md) reste pertinente pour le retour arrière. Le code de l'ancienne interface est conservé ; aucun Dockerfile de cette application n'est créé.
