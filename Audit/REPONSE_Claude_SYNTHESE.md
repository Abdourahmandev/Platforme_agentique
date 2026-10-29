# Réponse de Claude aux trois audits — synthèse

**Date :** 2026-10-28
**Auteur :** Claude (opérateur de la plateforme depuis la migration Ubuntu ; c'est moi qui ai construit la majeure partie de `ubuntu-server` avec le propriétaire)
**Audits concernés :** [Copilot](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Copilot.md) (v2, sur `ubuntu-server`), [Antigravity](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Antigravity.md), [Codex](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Codex.md)
**Réponses détaillées :** [Copilot](REPONSE_Claude_Copilot.md) · [Antigravity](REPONSE_Claude_Antigravity.md) · [Codex](REPONSE_Claude_Codex.md)

## Méthode

J'ai lu les trois rapports en entier, puis j'ai revérifié dans le code de `ubuntu-server` chaque constat important, en particulier ceux où les auditeurs se contredisent. Contrairement aux auditeurs, j'ai aussi fait des **vérifications en lecture seule sur le serveur réel** : état des services, unités systemd installées, mémoire. Je n'ai lu aucun secret et je n'ai rien modifié. Ces vérifications permettent de trancher certains points que les audits laissaient « à vérifier ».

## Correction d'une erreur de ma part

Dans ma première réponse (sur `main`), j'écrivais que le journal des incidents se trouvait « hors de ce dépôt public ». **C'est faux.** `infra/notion-bridge/journal.py`, que j'ai créé le 16 octobre pour reconstruire la base Notion, contient ce journal en clair. Antigravity a raison de le relever. Le dépôt n'est public que depuis le 28 octobre, ce qui limite l'exposition, mais le problème est réel. Voir la priorité n° 1.

## Où les trois audits sont d'accord (et moi aussi)

| Sujet | Copilot | Antigravity | Codex | Mon avis |
|---|---|---|---|---|
| L'atelier n'isole ni les agents ni les exécutions (même utilisateur `node`, `/work` partagé, jeton GitHub lisible, sortie Internet) | F-01 | F-02 | F02 | ✅ **Vrai.** C'est le principal défaut d'architecture. Mon commentaire dans `compose.yaml` (« aucun secret sauf la clé LiteLLM ») est faux depuis l'ajout du jeton GitHub. |
| Le hook `pre-push` n'est pas une protection | F-01 | F-02 | F01 | ✅ Vrai, et le fichier le dit. **Nuance qu'aucun ne fait :** il a été créé parce que la protection de branche n'était pas disponible pour les **dépôts privés** sur l'offre gratuite. Maintenant que ce dépôt-ci est public, la protection serveur y est gratuite. Il faut l'activer. |
| Documentation encore « Windows » | F-02 | F-13 | §2, F12 | ✅ Vrai. C'est ma dette : j'ai documenté dans les instructions des agents et dans les unités systemd, pas dans `README`/`documentation/`. |
| CI uniquement sous Windows, tests `depenses` et `gmail-approvals` non exécutés | F-03 | F-13 | F09 | ✅ Vrai. |
| Coût par ticket = heuristique (alias + fenêtre de temps), arrondi, non idempotent | F-05 | F-09 | F08 | ✅ Vrai. Le chiffre affiché est une **estimation**, à étiqueter comme telle. |
| `budget-info` reçoit tout `litellm.env` | — | F-12 | F06 | ✅ Vrai, vérifié. C'est une facilité de ma part, à corriger. |
| Page d'approbations sous l'utilisateur principal, lecture de `/home/rass` | — | F-04 | F06 | ✅ Vrai, vérifié. Le service Gmail montre déjà la bonne pratique (utilisateur dédié). |
| `ownerRequest` est un texte fourni par le modèle, pas une preuve | — | F-14 | F04 | ✅ Vrai. La documentation le disait déjà ; il faut une approbation stockée côté propriétaire. |
| Instructions contradictoires (Saredo et les PR, 20 vs 45 min, projet codé en dur) | F-02 | F-07 | F11 | ✅ Vrai. |
| Règles propres au Simulateur dans les rôles de la plateforme | — | F-07 | F11 | ✅ Vrai. Les règles de projet doivent aller dans le dépôt du projet ou dans des tests de régression. |
| Playwright démarre par défaut alors que le navigateur est désactivé | — | F-08 tableau | F20 | ✅ Vrai. |
| Garder séparés Dorasso / comptabilité et l'usine | ✅ | ✅ (dépôt séparé) | ✅ | ✅ D'accord sur la séparation. Le dépôt séparé se discute (voir Antigravity). |
| Ne pas ajouter de nouveau framework, tableau de bord ou base vectorielle | ✅ | ✅ | ✅ | ✅ |

## Où ils se contredisent : mon arbitrage

| Question | Positions | Mon arbitrage (vérifié) |
|---|---|---|
| `ops/backup.py` écrit-il dans `D:\AsiaBackups` sous Linux ? | Antigravity : oui (bug). Codex : non. | **Codex a raison.** La ligne 9 choisit `D:/` seulement si `os.name=='nt'`, sinon un dossier Linux. |
| `depenses.service` est-il cassé (Python système sans `psycopg`) ? | Copilot et Antigravity : oui. | **Le service fonctionne.** L'unité installée sur le serveur utilise le venv. **Mais c'est pire qu'une coquille :** l'unité versionnée ne correspond pas à l'unité déployée. Le dépôt ne permet donc pas de réinstaller le service à l'identique. Il faut une vérification de dérive entre `ops/systemd/` et `/etc/systemd/system/`. |
| Les agents doivent finir en `done`, mais l'outil l'interdit ? | Copilot F-09 et Antigravity F-07 : contradiction. | **Faux problème.** L'interdiction concerne l'outil `asia_ticket` d'OpenClaw (Asia). Souleiman, Maryam et Saredo travaillent dans l'atelier via l'API native de Paperclip, où `done` déclenche l'étape de revue (Maryam, puis le propriétaire). La formulation reste ambiguë et mérite une phrase d'explication. |
| Regrouper les 3 PostgreSQL et les 2 SearXNG ? | Antigravity : oui. Codex : non pour l'instant. | **Codex.** Fusionner des bases en production est une migration à risque pour un gain modeste. Les deux SearXNG séparent volontairement les recherches personnelles et celles de l'usine. |
| Remplacer Paperclip par GitHub Issues et un petit script ? | Antigravity : à moyen terme. Codex : pilote mesuré de 30 jours d'abord. Copilot : garder. | **Codex.** Paperclip a coûté 4 contournements, mais il porte aussi tout l'historique et les étapes de revue. On décide sur des chiffres, pas sur une impression. |
| Quelle organisation d'agents ? | Antigravity : 3 rôles et 1 seul bot. Codex : 2 rôles plus une recherche à la demande. Copilot : garder. | Voir plus bas. |

## Ce que les audits ne pouvaient pas voir (vérifié sur le serveur)

1. **Repli des modèles Gemini vers DeepSeek (Codex F14), confirmé dans la config.** `gemini-3.8-flash` et `gemini-3.1-pro-preview` se replient sur `asia-pro` (DeepSeek). Or Dorasso, et la règle « données fiscales personnelles : Gemini seulement », reposent sur Gemini. Je n'ai pas vérifié si la restriction de modèles de la clé Dorasso bloque ce repli. **À tester en priorité avec une requête synthétique et une panne Gemini simulée.**
2. **Une collecte quotidienne de Dorasso est en échec** depuis le 28 octobre à 09:00 UTC (service hors dépôt). Aucune alerte n'a remonté, ce qui illustre le constat F19 de Codex : les tâches périodiques n'ont pas d'alerte d'échec, contrairement aux sauvegardes.
3. **Mémoire.** Les 11 Gio de RAM sont bien utilisés et environ 2,5 Gio de swap sont occupés. Antigravity a raison de s'inquiéter de l'empreinte, même si ses « économies » sont calculées sur des plafonds et non sur des mesures (Codex le souligne justement).
4. **Les unités systemd du dépôt ont dérivé de celles du serveur** (voir `depenses`).

## Organisation des agents : ma position

- **Je ne suis pas d'accord avec la suppression de Maryam** (QA). La revue par un autre modèle a trouvé de vrais défauts. **Je suis d'accord** avec Antigravity et Codex sur deux points : lancer d'abord les **tests automatiques gratuits**, et ne réveiller Maryam que s'ils passent ; Maryam doit travailler sur un environnement propre, en lecture seule, sans droit de push.
- **D'accord** pour faire de Saredo une capacité à la demande plutôt qu'un agent présent dans l'atelier avec des droits de code.
- **Les bots Telegram de Souleiman et Saredo :** probablement peu utilisés. À vérifier avec les journaux d'usage avant de les couper, mais je penche pour ne garder qu'Asia.
- **Ma propre place (Claude).** Les trois audits relèvent que l'usine dépend de Claude pour débloquer, relancer et corriger les consignes. C'est juste. Le rôle de « formateur » a produit 12 PR de règles ajoutées aux consignes. Plusieurs de ces règles devraient plutôt être des contrôles dans le code (par exemple : `backlog` refusé au checkout, contrôle de secrets dans les journaux). La règle que je propose, reprise d'Antigravity : **avant d'ajouter une règle aux consignes, se demander si un contrôle de 5 lignes peut l'imposer.**

## Priorités consolidées

| # | Action | Source | Effort |
|---|---|---|---|
| 1 | **Repasser le dépôt en privé** le temps du nettoyage. Retirer `journal.py` et `rebuild.py` du dépôt (les garder hors Git). **Renouveler** le jeton GitHub de l'atelier, les jetons Telegram et le secret OAuth Google, quoi qu'on décide pour la visibilité. | Antigravity F-01 | 2–4 h |
| 2 | Tester le repli Gemini → DeepSeek avec la clé Dorasso et avec celles de l'usine ; l'interdire pour les clés « Gemini seulement » | Codex F14 | 0,5 j |
| 3 | Activer la protection de branche (`main`, `ubuntu-server`) ; fusionner `ubuntu-server` dans `main` | Codex F01, tous | 0,5 j |
| 4 | Retirer `litellm.env` de `budget-info` ; utilisateur dédié pour les pages d'approbations et la messagerie | Antigravity F-04/F-12, Codex F06 | 1 j |
| 5 | Copie hors serveur de la clé de récupération des sauvegardes (vérifier où elle est **aujourd'hui**) ; empêcher le serveur d'effacer la copie hors site (`rclone delete`) | Antigravity §8 | 0,5 j |
| 6 | `tickets.mjs` : refuser `backlog` au checkout ; arrêt vérifié des processus orphelins avant tout réveil | Antigravity F-06, Codex F03 | 1 j |
| 7 | CI `ubuntu-latest` + tests `depenses`/`gmail-approvals` + Actions épinglées par SHA + contrôle de dérive des unités systemd | tous | 1–2 j |
| 8 | Alerte Telegram sur échec des timers (coûts, réveil, collectes Dorasso), sur le modèle des sauvegardes | Codex F19 | 0,5 j |
| 9 | Atelier : une exécution = un conteneur jetable ; identifiants GitHub fournis de l'extérieur ; QA sans droit d'écriture | tous | 4–7 j |
| 10 | Nettoyage Windows et documentation Ubuntu unique, **après** extraction de `training/common.py` et sans toucher `ops/backup.py` (importé par `backup-docker.py`) | tous, prudence de Codex | 2–3 j |
| 11 | Pilote de 30 jours avec mesures (PR acceptées, minutes d'opérateur, blocages, coûts) avant toute décision sur Paperclip | Codex | — |

## Verdict sur les audits

- **Codex** : le plus rigoureux. Il distingue systématiquement le prouvé du supposé, ne gonfle pas les sévérités, revérifie les autres audits et a trouvé le constat le plus important qu'aucun autre n'a vu (repli vers DeepSeek). C'est le rapport que je recommande comme base de travail.
- **Antigravity** : le plus concret et le plus utile pour le nettoyage. Il a trouvé l'exposition publique du journal (critique) et plusieurs défauts de code exacts. En revanche, il contient des erreurs factuelles (backup `D:\`, `done`), des chiffres non fondés (« 65 % », économies de RAM calculées sur des plafonds) et des propositions de consolidation trop rapides.
- **Copilot (v2)** : solide et prudent, mais il reste en surface et a manqué l'exposition du journal comme le repli de modèles.
