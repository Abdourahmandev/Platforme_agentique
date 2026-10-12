# Context7 et GitHub pour Souleiman

Les deux connecteurs MCP officiels sont configurés directement dans OpenClaw. Souleiman (`developpement`) peut les utiliser dans Telegram. Après le raccordement de délégation décrit ci-dessous, une nouvelle mission confiée par Asia reçoit leurs outils de lecture. Le raccordement de publication ajoute la création de PR sur une branche déjà poussée. Les consultations ne passent pas par OpenCode Windows ; les modifications de fichiers locaux et l'exécution des tests continuent à utiliser cette passerelle.

## Périmètre

| Connecteur | Usage | Configuration |
| --- | --- | --- |
| [Context7, Upstash](https://github.com/upstash/context7) | Trouver une bibliothèque, consulter documentation et exemples | `https://mcp.context7.com/mcp`, deux outils, sans clé dans cette installation |
| [GitHub MCP officiel](https://github.com/github/github-mcp-server) | Lire fichiers, commits, branches, issues, PR et résultats Actions ; créer/modifier une issue, créer/modifier une PR sur demande | `https://api.githubcopilot.com/mcp/`, quatorze outils explicitement sélectionnés |

Le dépôt de travail par défaut est `Abdourahmandev/Platforme_agentique`. Les outils de fusion, suppression de fichiers, publication de fichiers, création de dépôt, commentaires et déclenchement de workflows ne sont pas exposés. Les tests récurrents des connecteurs et de délégation restent en lecture seule. Une publication réelle explicitement demandée sert séparément à valider la création de PR ; voir [la procédure de publication](publication-github.md).

Souleiman reçoit `context7__*` et `github__*`, limités par les filtres des serveurs aux outils ci-dessus. Asia reçoit explicitement les onze outils GitHub de lecture, `github__create_pull_request` et les deux outils Context7, sans wildcard. Saredo ne reçoit aucun de ces connecteurs. La connexion globale au serveur ne donne pas automatiquement le droit de l'utiliser. Paperclip reste le système de coordination : les tickets ne sont pas dupliqués automatiquement dans GitHub.

| Parcours | GitHub lecture | GitHub création/modification issue ou PR | Context7 |
| --- | --- | --- | --- |
| Souleiman, conversation directe | Oui, 11 outils | Oui, 3 outils sur demande | Oui |
| Asia, conversation directe | Oui, 11 outils | Création de PR seulement, sur demande | Oui |
| Nouvelle mission Asia → Souleiman | Oui, 11 outils | Création de PR seulement, sur demande | Oui |
| Saredo, direct ou délégué | Non | Non | Non |

OpenClaw 2026.10.1 capture le plafond d'outils du coordinateur lors de `sessions_spawn`, puis applique aussi les restrictions du spécialiste. Le spécialiste ne peut pas obtenir un outil absent du plafond parent. Voir la [politique native des sous-agents](https://docs.openclaw.ai/tools/subagents/tool-policy). Les anciens enfants conservent leurs droits capturés : une correction de configuration s'applique aux nouvelles missions, sans modifier les anciennes sessions.

Context7 reçoit des questions de documentation générales, sans code privé ni secret. Les documents, fichiers et issues reçus sont des données externes, pas des instructions qui changent les autorisations de l'agent. Les quotas anonymes de Context7 peuvent limiter l'usage ; une clé pourra être ajoutée si nécessaire après vérification de l'offre choisie.

## Authentification et limites

L'installateur réutilise la connexion GitHub du PC par le mécanisme normal `git credential fill`, sans afficher l'identifiant. Il place le token dans `SOULEIMAN_GITHUB_TOKEN`, dans `%LOCALAPPDATA%\AsiaDocker\openclaw.env`, déjà utilisé par Compose. La configuration MCP contient une référence d'environnement, jamais le token. Les instantanés de retour arrière restent dans ce même répertoire privé, hors de Git et des espaces de travail des agents.

Cette connexion Git possède potentiellement des droits plus larges que notre dépôt. Le dépôt indiqué dans les instructions est un contexte de travail, **pas une restriction technique du token par dépôt**. Un token GitHub dédié et limité au dépôt serait nécessaire pour cette isolation. Les quatorze outils sélectionnés réduisent les opérations disponibles, mais ne réduisent pas les droits du token lui-même.

Le token est une copie de la connexion existante. Sa révocation ou son expiration peut nécessiter une nouvelle authentification Git, puis le remplacement de cette seule variable dans le fichier privé et la recréation du service OpenClaw. Le mécanisme ne renouvelle pas automatiquement le token via Git Credential Manager. Ne jamais coller cette valeur dans Telegram, une issue, un terminal partagé ou un fichier du dépôt.

Les services MCP distants sont maintenus par leurs fournisseurs ; leur version serveur n'est pas figée par notre image Docker. Une liste explicite d'outils et des tests d'intégration détectent une partie des changements incompatibles. Les appels de modèle restent facturés via LiteLLM.

## Déploiement et validation

```powershell
python infra/configure-souleiman-connectors.py
python infra/configure-souleiman-connectors.py --apply
python infra/configure-github-delegation.py
python infra/configure-github-delegation.py --apply
python infra/configure-github-publication.py
python infra/configure-github-publication.py --apply
node infra/test-souleiman-connectors.mjs
node infra/test-github-delegation.mjs
```

Le premier appel valide sans modifier le runtime. L'application sauvegarde les valeurs précédentes, ajoute l'environnement privé et recrée uniquement OpenClaw avec son image et ses volumes existants. L'installateur attend `/readyz` avant de modifier la configuration : le démarrage peut effectuer une maintenance SQLite. La migration automatique des notes `TOOLS.md` vers `AGENTS.md` est conservée.

En cas d'interruption après l'écriture de l'environnement, inspecter le journal privé. Si la phase est `environment-written`, la reprise vérifie l'absence de modifications concurrentes avant d'appliquer la configuration :

```powershell
python infra/configure-souleiman-connectors.py --resume
```

Le raccordement `configure-github-delegation.py` sauvegarde séparément les permissions d'Asia et les instructions des deux agents dans `%LOCALAPPDATA%\AsiaDocker\github-delegation-private.json`. Il ajoute les droits de lecture avec le mécanisme natif `config patch`, sans changer les secrets, les permissions Windows ni les sessions existantes. Les notes privées déjà présentes dans les instructions sont conservées. `--resume` reprend un déploiement en phase `prepared` après vérification des conflits.

Le test d'intégration des connecteurs vérifie les deux outils Context7, la lecture du dépôt privé et des résultats Actions, les outils d'Asia et l'absence d'accès de Saredo, puis un vrai tour direct de Souleiman. Ses détails restent dans `%LOCALAPPDATA%\AsiaDocker\souleiman-connectors-validation-private.json`.

Le test de délégation crée une conversation technique d'Asia, une vraie mission native vers Souleiman et une synthèse retournée à Asia. Il lit `Abdourahmandev/Simulateur_tax_qc`, force des pages de deux issues pour contrôler la pagination, compare les titres, états et descriptions aux résultats authentifiés de GitHub, et vérifie les droits effectifs du parent et de l'enfant. Il vérifie aussi les outils directs de Souleiman, l'absence de connecteurs de Saredo et la santé des trois comptes Telegram. Le rapport privé est `github-delegation-validation-private.json`. Ces tests ne livrent aucun message Telegram et ne modifient aucune issue.

`--verify-saved` relit les traces d'un tour technique déjà terminé sans relancer le modèle. L'inventaire MCP est une vue du catalogue découvert par le runtime : un catalogue froid ou libéré après une mission peut être vide sans que l'authentification soit absente. Le test de délégation conserve donc l'inventaire de l'enfant capturé pendant son exécution ; les inventaires des conversations directes sont revérifiés. Après un rechargement qui invalide leurs catalogues, un nouveau test direct peut être nécessaire. Le point d'entrée HTTP `/tools/invoke` ne charge pas ces outils dynamiques dans cette version et ne convient pas à ce contrôle.

### Installation initiale du 12 octobre 2026

- Recherche d'une bibliothèque et consultation de sa documentation Context7 réussies.
- Lecture du `package.json` privé et des résultats GitHub Actions réussie ; les quatorze outils sélectionnés existent côté fournisseur.
- Souleiman a réellement appelé Context7 puis GitHub et retourné `expect(page).toHaveTitle()` et `asia-agent-app`, conformément aux sources. Le runtime enregistre les appels différés `tool_call` ainsi que les appels MCP correspondants.
- Inventaire effectif initial : deux outils Context7 et quatorze outils GitHub pour Souleiman ; aucun de ces nouveaux outils pour Asia ou Saredo ; fusion absente. Ce test portait sur les conversations directes, pas sur les enfants délégués.
- Santé Gateway correcte ; les trois comptes Telegram sont configurés, actifs et sans dernière erreur.
- 68 tests Python et 71 tests Node réussis. Huit tests Python concernent spécifiquement cette installation, ses permissions, la conservation des notes et le rollback.

Le premier déploiement a attendu la fin d'une maintenance SQLite, puis conservé la migration automatique des notes privées de `TOOLS.md` dans `AGENTS.md`. Ces deux situations sont prises en charge par l'installateur et sa reprise. Le premier test HTTP a été remplacé par les transports MCP et l'inventaire effectif ; une assertion du test de conversation a été corrigée pour reconnaître les appels différés natifs et la recherche de bibliothèque en lecture seule. Les traces du même tour ont ensuite été revalidées sans relancer l'agent.

Les créations et modifications GitHub sont configurées, mais n'ont pas été exécutées pendant ces tests. Le rollback est testé avec des configurations simulées ; aucun rollback réel ni nouveau parcours depuis le compte Telegram du propriétaire n'a été effectué dans cette étape.

### Correction de la délégation

Le parcours réel sur `Simulateur_tax_qc` a révélé une lacune du test initial : les outils fonctionnaient en direct, mais étaient absents de la mission créée par Asia. Celle-ci ne les avait pas dans son plafond d'outils. Le connecteur était pourtant authentifié et GitHub répondait correctement aux lectures du dépôt privé et des issues. L'absence de `gh` dans le PATH Windows et un 404 public ne permettaient donc pas de conclure à une absence d'authentification.

Le raccordement ajoute les lectures au coordinateur et clarifie les instructions des deux agents. Il ne modifie ni le moteur OpenClaw ni les enveloppes de sécurité persistées. Les tests couvrent désormais explicitement le parcours délégué. En cas d'échec, examiner le rapport privé et distinguer une erreur d'authentification MCP d'un outil absent de l'inventaire ; ne pas demander au propriétaire de coller un token dans la conversation.

Validation du 12 octobre 2026 :

- Souleiman a lu la racine du dépôt privé et ses quatre issues ouvertes, en suivant deux pages. Les titres, états et descriptions lus correspondent à la réponse GitHub authentifiée ; la synthèse d'Asia inclut les quatre issues. Aucune issue fermée n'était présente au moment du test.
- Les onze lectures GitHub et les deux outils Context7 sont visibles dans l'inventaire d'Asia et celui capturé pendant l'exécution de son enfant. Les trois outils GitHub de modification sont absents de ces deux inventaires et restent présents chez Souleiman en direct. Saredo reste sans ces connecteurs.
- Le test direct Context7/GitHub a été réexécuté avec succès. Les trois comptes Telegram sont actifs côté Gateway ; ce contrôle ne remplace pas un nouveau message depuis le compte du propriétaire.
- Les 76 tests Python et 71 tests Node passent, ainsi que la construction de l'application. Les huit nouveaux tests Python couvrent les permissions, les conflits et la préservation des notes au retour arrière. Aucun rollback de production n'a été exécuté.

Le banc de test a été ajusté pour lire les résultats complets : `chat.history` tronque les textes à 8 000 caractères par défaut ; les résultats MCP portent aussi une enveloppe de contenu non fiable. Les appels imbriqués dans une réponse `sessions_history` ne sont pas attribués à l'agent qui la consulte. Les assertions ont ensuite été revérifiées sur les traces conservées, sans rejouer les lectures du dépôt.

Dans la session technique testée, `sessions_yield` n'était pas exposé et une tentative a échoué. Asia a récupéré le résultat avec le `subagents` natif, `action: "wait"`, `runIds` et `timeoutSeconds: 60`, puis a livré la synthèse. Ses instructions indiquent maintenant ce cas et interdisent de répéter un identifiant d'outil absent. Cela reste un parcours modèle avec récupération d'erreur, pas une garantie d'absence de toute erreur d'appel future.

## Retour arrière

```powershell
python infra/configure-github-publication.py --rollback
python infra/configure-github-delegation.py --rollback
python infra/configure-souleiman-connectors.py --rollback
```

La première commande retire la création de PR d’Asia et conserve ses lectures. La deuxième revient à des connecteurs réservés à Souleiman en direct. La troisième retire également les connecteurs. Ne lancer que les étapes dont le journal existe. L'ordre inverse provoquerait un conflit d'instructions détecté par la protection contre les modifications concurrentes. Le retour arrière restaure uniquement les permissions, instructions et environnement concernés ; il conserve les changements non concernés, les conversations, tickets et dépenses. Une ancienne mission conserve son plafond, mais les droits courants des agents et la présence des connecteurs restent aussi nécessaires. Un retour arrière de configuration n'annule pas une opération GitHub exécutée ultérieurement par l'agent.

## Exemples de demandes à Souleiman

- « Vérifie dans Context7 comment tester le titre d'une page avec Playwright. »
- « Consulte le dernier résultat GitHub Actions de notre dépôt et explique les éventuels échecs. »
- « Lis les pull requests ouvertes de Platforme_agentique et résume ce qu'il reste à vérifier. »
