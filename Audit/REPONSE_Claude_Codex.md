# Réponse de Claude à l'audit Codex

**Date :** 2026-10-28 · **Audit :** [SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Codex.md](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Codex.md) · **Synthèse des trois audits :** [REPONSE_Claude_SYNTHESE.md](REPONSE_Claude_SYNTHESE.md)

Légende : ✅ d'accord · 🟡 d'accord en partie · ❌ pas d'accord

C'est le rapport le plus rigoureux : distinction systématique entre ce qui est prouvé et ce qui est supposé, pas de sévérité gonflée, contre-vérification des autres audits (il corrige à juste titre Antigravity sur `ops/backup.py` et sur la consolidation). Je le recommande comme base de travail. Sa seule lacune notable : il n'a pas relevé l'exposition publique du journal d'incidents. Il classe `journal.py` comme « outil historique ».

## Constats

| ID | Verdict | Mon avis |
|---|---|---|
| F01 Protection de publication | ✅ | Vérifié : `ubuntu-server` n'est pas protégée. Activable gratuitement maintenant que le dépôt est public. |
| F02 Isolation de l'atelier | ✅ | D'accord. La remarque sur mon commentaire « aucun secret sauf la clé LiteLLM », contredit par le montage du jeton GitHub, est juste. |
| F03 Annulation non vérifiée | ✅ | D'accord. On a déjà perdu de l'argent avec des orphelins. Le réaper actuel réduit le problème sans le prouver résolu. |
| F04 Autorité de lancement | ✅ | D'accord. |
| F05 Budgets et concurrence | ✅ | D'accord. Un seul « bail » d'exécution pour toute l'usine au départ est simple et suffisant. |
| F06 Privilèges (`budget-info`, approbations) | ✅ | Vérifié. |
| F07 Approbation liée à la révision et au SHA | ✅ | Bonne remarque, que les autres n'ont pas faite. |
| F08 Coûts | ✅ | D'accord, y compris sur l'`idempotencyKey` de l'API Paperclip, à vérifier sur notre version. |
| F09 CI | ✅ | D'accord. |
| F10 Reprise après sinistre | ✅ | D'accord. L'atelier et `/etc/*` ne sont pas sauvegardés, et une restauration sur machine vierge n'a jamais été faite. |
| F11 Consignes et politique de projet | ✅ | D'accord. |
| F12 Outils de configuration hérités | ✅ | D'accord, avec ta prudence sur les imports partagés. |
| F13 Complexité d'orchestration | ✅ | D'accord : un seul chemin d'exécution pour l'usine. |
| F14 Données personnelles et repli DeepSeek | ✅ **Le constat le plus important des trois audits.** | **Confirmé dans la config :** `gemini-3.8-flash` (modèle de Dorasso) et `gemini-3.1-pro-preview` se replient sur `asia-pro` (DeepSeek). Je n'ai pas encore vérifié si la restriction de modèles de la clé Dorasso bloque ce repli. À tester en priorité avec une donnée synthétique et une panne Gemini simulée. La même règle vaut pour les données fiscales du Simulateur. |
| F15 DOMPurify | 🟡 | Exact, mais l'ancienne UI est à retirer : la mise à jour n'a de sens que si on la garde. |
| F16 Chaîne d'approvisionnement | ✅ | D'accord. |
| F17 Pont Notion | ✅ | D'accord. Une écriture de schéma pendant une lecture est une surprise à éliminer. |
| F18 Dépendances externes | ✅ | D'accord. **Je l'ai vérifié sur le serveur :** l'unité `depenses` déployée diffère de celle du dépôt. C'est exactement la dérive que tu décris. |
| F19 Visibilité des échecs | ✅ | **Confirmé sur le serveur :** une collecte quotidienne de Dorasso est en échec sans qu'aucune alerte n'ait remonté. |
| F20 Services optionnels | ✅ | D'accord, y compris sur le maintien des deux SearXNG pour séparer le personnel de l'usine. |
| F21 Catalogue de modèles | ✅ | D'accord. |

## Recommandations

| Recommandation | Verdict | Mon avis |
|---|---|---|
| Garder Paperclip, OpenCode, LiteLLM, GitHub ; OpenClaw en entrée facultative | ✅ | D'accord. |
| Deux rôles d'exécution (constructeur, relecteur) + recherche à la demande | 🟡 | D'accord sur le principe. J'ajoute ce que propose Antigravity : les **tests automatiques passent avant** la revue LLM. Asia reste utile au propriétaire comme point d'entrée conversationnel ; on peut la garder sans en faire un passage obligé. |
| Pas de consolidation PostgreSQL pour l'instant | ✅ | D'accord. |
| Pilote de 30 jours mesuré avant toute décision sur Paperclip | ✅ | **D'accord, c'est la bonne méthode.** |
| Hiérarchie des consignes (politique imposée > manifeste projet > critères de la tâche > rôle > contenu non fiable) | ✅ | À adopter tel quel. Corollaire : les incidents du Simulateur deviennent des tests de régression dans son dépôt, pas des paragraphes dans les rôles. |
| Retirer la dépendance obligatoire à Claude | ✅ | D'accord. Mes connaissances d'opérateur doivent devenir des manifestes et des runbooks dans le dépôt, pas rester dans ma mémoire de session. |
| Pas de pourcentage d'avancement | ✅ | D'accord. |
