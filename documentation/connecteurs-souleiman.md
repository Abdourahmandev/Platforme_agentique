# Context7 et GitHub pour Souleiman

Les deux connecteurs MCP officiels sont configurés directement dans OpenClaw. Souleiman (`developpement`) peut les utiliser dans Telegram ou dans une mission confiée par Asia. Les consultations ne passent pas par OpenCode Windows ; les modifications de fichiers locaux et l'exécution des tests continuent à utiliser cette passerelle.

## Périmètre

| Connecteur | Usage | Configuration |
| --- | --- | --- |
| [Context7, Upstash](https://github.com/upstash/context7) | Trouver une bibliothèque, consulter documentation et exemples | `https://mcp.context7.com/mcp`, deux outils, sans clé dans cette installation |
| [GitHub MCP officiel](https://github.com/github/github-mcp-server) | Lire fichiers, commits, branches, issues, PR et résultats Actions ; créer/modifier une issue, créer/modifier une PR sur demande | `https://api.githubcopilot.com/mcp/`, quatorze outils explicitement sélectionnés |

Le dépôt de travail par défaut est `Abdourahmandev/Platforme_agentique`. Les outils de fusion, suppression de fichiers, publication de fichiers, création de dépôt, commentaires et déclenchement de workflows ne sont pas exposés. Les tests de cette installation restent en lecture seule et ne publient aucun ticket, PR ou commentaire.

Seul Souleiman reçoit `context7__*` et `github__*` dans sa liste d'outils. Les listes d'Asia et de Saredo restent inchangées. La connexion globale au serveur ne leur donne pas automatiquement le droit de l'utiliser. Paperclip reste le système de coordination : les tickets ne sont pas dupliqués automatiquement dans GitHub.

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
node infra/test-souleiman-connectors.mjs
```

Le premier appel valide sans modifier le runtime. L'application sauvegarde les valeurs précédentes, ajoute l'environnement privé et recrée uniquement OpenClaw avec son image et ses volumes existants. L'installateur attend `/readyz` avant de modifier la configuration : le démarrage peut effectuer une maintenance SQLite. La migration automatique des notes `TOOLS.md` vers `AGENTS.md` est conservée.

En cas d'interruption après l'écriture de l'environnement, inspecter le journal privé. Si la phase est `environment-written`, la reprise vérifie l'absence de modifications concurrentes avant d'appliquer la configuration :

```powershell
python infra/configure-souleiman-connectors.py --resume
```

Le test d'intégration vérifie les deux outils Context7, la lecture du dépôt privé et des résultats Actions, l'interdiction pour Asia et Saredo, puis un vrai tour de Souleiman avec les appels d'outils enregistrés. Cette session technique ne livre aucun message Telegram. Les détails restent dans `%LOCALAPPDATA%\AsiaDocker\souleiman-connectors-validation-private.json`.

`--verify-saved` relit les traces d'un tour technique déjà terminé et vérifie les outils actuellement disponibles, sans relancer le modèle. L'inventaire effectif des sessions prouve les permissions MCP ; le point d'entrée HTTP `/tools/invoke` ne charge pas ces outils dynamiques dans cette version et ne convient pas à ce contrôle.

### Résultats du 12 octobre 2026

- Recherche d'une bibliothèque et consultation de sa documentation Context7 réussies.
- Lecture du `package.json` privé et des résultats GitHub Actions réussie ; les quatorze outils sélectionnés existent côté fournisseur.
- Souleiman a réellement appelé Context7 puis GitHub et retourné `expect(page).toHaveTitle()` et `asia-agent-app`, conformément aux sources. Le runtime enregistre les appels différés `tool_call` ainsi que les appels MCP correspondants.
- Inventaire effectif : deux outils Context7 et quatorze outils GitHub pour Souleiman ; aucun de ces nouveaux outils pour Asia ou Saredo ; fusion absente.
- Santé Gateway correcte ; les trois comptes Telegram sont configurés, actifs et sans dernière erreur.
- 68 tests Python et 71 tests Node réussis. Huit tests Python concernent spécifiquement cette installation, ses permissions, la conservation des notes et le rollback.

Le premier déploiement a attendu la fin d'une maintenance SQLite, puis conservé la migration automatique des notes privées de `TOOLS.md` dans `AGENTS.md`. Ces deux situations sont prises en charge par l'installateur et sa reprise. Le premier test HTTP a été remplacé par les transports MCP et l'inventaire effectif ; une assertion du test de conversation a été corrigée pour reconnaître les appels différés natifs et la recherche de bibliothèque en lecture seule. Les traces du même tour ont ensuite été revalidées sans relancer l'agent.

Les créations et modifications GitHub sont configurées, mais n'ont pas été exécutées pendant ces tests. Le rollback est testé avec des configurations simulées ; aucun rollback réel ni nouveau parcours depuis le compte Telegram du propriétaire n'a été effectué dans cette étape.

## Retour arrière

```powershell
python infra/configure-souleiman-connectors.py --rollback
```

Le retour arrière retire les deux connecteurs et restaure les permissions, instructions et environnement concernés. Il refuse les conflits détectés, conserve les modifications de configuration non concernées et ne supprime ni conversations, ni tickets, ni dépenses. Un retour arrière de configuration n'annule pas une opération GitHub exécutée ultérieurement par l'agent.

## Exemples de demandes à Souleiman

- « Vérifie dans Context7 comment tester le titre d'une page avec Playwright. »
- « Consulte le dernier résultat GitHub Actions de notre dépôt et explique les éventuels échecs. »
- « Lis les pull requests ouvertes de Platforme_agentique et résume ce qu'il reste à vérifier. »
