# Souleiman et Saredo : noms et identifiants

Changement du 12 octobre 2026. Les agents existants Développement et Recherche prennent respectivement les noms **Souleiman** et **Saredo**. Asia conserve son nom. Il s'agit d'un changement d'affichage et d'instructions, sans création de nouvelles identités.

| Identité stable | Nom affiché | Fonction | Bot Telegram conservé |
| --- | --- | --- | --- |
| `asia` | Asia | Coordination et assistance personnelle | `@Absourahman03_bot` |
| `developpement` | Souleiman | Conception et revue de code | `@Rassdevbot` |
| `recherche` | Saredo | Analyse et vérification des sources | `@Rassresearchbot` |

Le [catalogue](../infra/agents/catalogue.json) associe identifiants, noms, rôles et anciens noms. Utiliser les identifiants stables dans les API et les noms dans les interfaces. Les anciens noms restent compréhensibles dans les instructions ; les archives et anciens messages ne sont pas réécrits.

## Périmètre

- OpenClaw : quatre champs d'affichage (`agents.entries.*.name` et noms des deux comptes Telegram). Les associations de canaux, espaces, clés, modèles et permissions sont conservées.
- Instructions : `AGENTS.md`, `IDENTITY.md` et références pertinentes de `PROCEDURES.md` dans les espaces existants. Asia connaît les deux nouveaux noms et leurs identifiants de délégation.
- Paperclip : renommage des profils existants, conservation des UUID, adaptateurs et politiques. Les tickets et commentaires restent attribués aux mêmes identités. L'outil expose `agentDirectory`, sans secrets, et conserve les valeurs `assignee` stables.
- Telegram : noms et descriptions par défaut, français et anglais. Les tokens, identifiants numériques et usernames sont conservés. Les méthodes utilisées sont `setMyName`, `setMyDescription` et `setMyShortDescription`, avec relecture après écriture.
- LiteLLM : seuls les alias des deux clés deviennent Souleiman et Saredo. Aucune nouvelle clé, remise à zéro de compteur, modification de budget ou modification de routage.
- Sources : configuration d'exemple, scripts d'installation et documentation courante mis à jour. Les bilans historiques de formation gardent leurs noms d'époque.

Les noms courts des fiches Paperclip sont dérivés du nom : ils deviennent `souleiman` et `saredo`. Les anciens favoris vers ces fiches peuvent demander une mise à jour. Les UUID et les liens de tickets comme EQU-5 restent inchangés. Le nom Telegram affiché est distinct de l'adresse `@...`.

## Déroulement contrôlé

Le script [rename-agents.py](../infra/rename-agents.py) conserve un snapshot privé et un journal de chaque étape. Il refuse d'écraser le snapshot ou de répéter une étape déjà tentée. Si une réponse est perdue, comparer les lectures aux valeurs attendues avant toute reprise ; ne pas effacer le journal pour contourner ce contrôle.

```powershell
python infra/rename-agents.py --stage snapshot
python infra/rename-agents.py --stage openclaw
python infra/rename-agents.py --stage paperclip
python infra/rename-agents.py --stage telegram
python infra/rename-agents.py --stage litellm
```

La sauvegarde ciblée est `%LOCALAPPDATA%\AsiaPaperclip\agent-names-before.json`. Elle contient les profils et treize fichiers runtime d'origine ; ses données privées restent hors Git. `agent-names-progress.json` enregistre les étapes et `agent-names-target-private.json` les fichiers attendus. Le snapshot inclut aussi les tickets existants, les paramètres de clés et les empreintes des fichiers des espaces. L'inventaire des sessions est conservé séparément.

Un redémarrage du seul conteneur OpenClaw charge le plugin et les nouvelles instructions ; attendre que les trois comptes Telegram soient prêts avant les essais. L'interruption concerne les trois bots, qui partagent la même Gateway.

## Validation

Les tests automatiques vérifient notamment que les noms n'altèrent ni les identifiants ni les permissions, que les noms sont reliés aux bons UUID Paperclip et qu'aucune clé n'apparaît dans le répertoire public des agents. Chaque étape opérationnelle relit ses changements et compare les champs devant rester identiques.

Le script [test-agent-names.mjs](../infra/test-agent-names.mjs) exerce les présentations des deux spécialistes et une délégation réelle par Asia utilisant uniquement leurs nouveaux noms. Les sessions de test sont privées, distinctes de Telegram. Il contrôle les destinations, les résultats, la synthèse, les sondes Telegram et la conservation des sessions existantes. Les reçus complets restent privés. Un contrôle des noms vus dans l'application Telegram par le propriétaire complète ces tests techniques.

### Résultats du 12 octobre 2026

| Étape | Preuve constatée |
| --- | --- |
| Sauvegarde ciblée | Treize fichiers et profils privés sauvegardés puis relus à l'identique |
| Configuration OpenClaw | Schéma valide ; seuls quatre champs de noms modifiés dans la configuration ; clés et politiques identiques |
| Paperclip | Deux profils renommés par leur UUID existant ; adaptateurs, rôles et permissions conservés |
| Telegram | Noms et descriptions relus pour les langues par défaut, français et anglais ; mêmes identifiants numériques et usernames |
| LiteLLM | Alias Souleiman et Saredo relus ; mêmes clés, budgets, modèles, équipe et compteurs conservés |
| Tests locaux | 68 tests Node et 54 tests Python réussis |
| Présentation directe | Souleiman et Saredo donnent leur nouveau nom dans deux sessions synthétiques |
| Délégation | Asia utilise les bons identifiants, reçoit les deux réponses et produit une synthèse avec les nouveaux noms ; réponses des sessions enfants vérifiées directement |
| Historiques et fichiers | 61 sessions recensées conservées ; 52 fichiers des espaces comparés par empreinte, avec uniquement les changements d'identité prévus |
| Tickets antérieurs | Les cinq tickets présents avant l'opération conservent leurs identifiants, attributions, statuts et champs de liste comparés |
| Nouveaux tickets de test | EQU-6 traité par Souleiman, EQU-7 par Saredo ; réponses avec marqueur et nouveau nom publiées sous les UUID attendus ; retour `in_review` au propriétaire |
| Santé finale Telegram | Trois comptes `running=true`, trois sondes `ok=true` ; les sondes donnent aussi Souleiman et Saredo comme noms des bots |

Le premier test de délégation avait sélectionné `cleanup: delete` : les réponses étaient revenues, mais les sessions enfants étaient déjà supprimées au moment du contrôle direct. Ce passage n'a pas été retenu comme validation complète. Le test a été précisé avec `cleanup: keep`, puis la seule partie délégation a été répétée avec succès. Les reçus des deux passages sont conservés ; les sessions de production n'ont pas été supprimées. Aucun message Telegram n'a été envoyé par les scripts de test. La confirmation visuelle depuis le compte Telegram du propriétaire reste distincte de ces contrôles techniques.

Une nouvelle archive chiffrée a été créée : `D:\AsiaBackups\docker-20261012T131210-31542ee5.aes`. Le contrôle a vérifié 330 fichiers et restauré OpenClaw, LiteLLM (91 tables) et Paperclip (une entreprise, trois agents, sept tickets, 23 commentaires) dans des emplacements de contrôle séparés. Les trois reçus d'approbation et 38 reçus de formation préexistants sont conservés. La production n'a pas été remplacée par ces restaurations.

## Retour arrière ciblé

Arrêter les nouvelles missions et vérifier qu'aucune exécution n'est active. Exécuter :

```powershell
python infra/rename-agents.py --stage rollback
```

Puis redémarrer OpenClaw et contrôler les canaux. Le rollback remet les anciens noms, descriptions et fichiers ; il ne restaure aucune base, aucun ancien compteur et aucune ancienne conversation. Le script refuse de remplacer un fichier runtime qui a changé depuis cette migration : réconcilier alors les modifications manuellement. Si des noms ou descriptions ont été modifiés ensuite dans les services externes, comparer également ces valeurs au snapshot avant de lancer ce rollback.

Ne pas employer le rollback intégral de la migration Docker ou celui de l'installation Paperclip pour annuler ce changement de noms.
