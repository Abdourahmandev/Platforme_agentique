# Réponse de Claude à l'audit Copilot (v2, `ubuntu-server`)

**Date :** 2026-10-28 · **Audit :** [SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Copilot.md](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Copilot.md) · **Synthèse des trois audits :** [REPONSE_Claude_SYNTHESE.md](REPONSE_Claude_SYNTHESE.md)

Légende : ✅ d'accord · 🟡 d'accord en partie · ❌ pas d'accord

La v2 corrige bien le problème de branche de la v1. Le rapport est prudent et juste, mais il manque deux points importants que les autres audits ont trouvés : le journal d'incidents publié dans le dépôt public (Antigravity) et le repli des modèles Gemini vers DeepSeek (Codex).

## Constats

| ID | Verdict | Mon avis |
|---|---|---|
| F-01 Atelier et identifiants GitHub | ✅ | D'accord sur tout. Une précision : le hook existe parce que la protection de branche n'était pas disponible pour les dépôts **privés** sur l'offre gratuite (les dépôts des projets). Ce dépôt-ci étant public, la protection serveur y est gratuite et doit être activée. |
| F-02 Documentation et dérive de configuration | ✅ | D'accord. La remarque sur les 12 vs 24 exécutions par jour et sur Saredo installé dans l'atelier malgré son rôle sans code est juste. |
| F-03 CI | ✅ | D'accord. |
| F-04 `depenses.service` | 🟡 | Le service **fonctionne** : l'unité installée sur le serveur utilise le venv, vérifié. Le vrai problème est plus large : **l'unité versionnée ne correspond pas à l'unité déployée** (chemin de l'application et interpréteur différents). Il faut un contrôle de dérive entre `ops/systemd/` et le serveur, pas seulement une correction de `ExecStart`. |
| F-05 Coûts par ticket | ✅ | D'accord. Il faut afficher « estimé » tant que la corrélation par `run_id` n'existe pas. |
| F-06 Sortie réseau de l'atelier | ✅ | D'accord. |
| F-07 Réponse TTS non bornée | ✅ | D'accord, priorité basse. |
| F-08 Clé partagée du pont Notion | ✅ | D'accord, priorité basse dans le modèle à un seul propriétaire. |
| F-09 `done` refusé par l'outil | ❌ | **Pas un vrai problème.** L'outil `tickets.mjs` (`asia_ticket`) est celui d'Asia dans OpenClaw. Souleiman, Maryam et Saredo tournent dans l'atelier (`opencode_local`) et passent par l'API native de Paperclip, où `done` déclenche l'étape de revue configurée (Maryam, puis le propriétaire). Le rapport avait d'ailleurs prévu cette possibilité (« unless a separate Paperclip review transition performs that step »). En revanche, une phrase dans les consignes pour expliquer la différence éviterait la confusion. |

## Recommandations

- **Organisation des agents, pile technique, « pas de nouveau framework » :** ✅ d'accord.
- **Phase 0 (rotation du jeton, `depenses`, runbook) :** ✅ d'accord, avec deux ajouts prioritaires : retirer le journal d'incidents du dépôt public, et tester le repli Gemini → DeepSeek.
- **`journal.py` à revoir (§7) :** ✅. Copilot l'a vu mais l'a classé en « nettoyage ». Avec un dépôt public, c'est une priorité immédiate (voir la synthèse).

## Ce qui manque

1. Le repli `gemini-3.8-flash` / `gemini-3.1-pro-preview` → `asia-pro` (DeepSeek) dans `gateway/config.yaml`, en conflit avec la règle « Gemini seulement » pour les données personnelles.
2. `budget-info` qui reçoit tout `litellm.env`, et les pages d'approbations exécutées sous l'utilisateur principal.
3. L'absence d'alerte quand un timer échoue (une collecte quotidienne de Dorasso est en échec sur le serveur sans qu'aucune alerte n'ait remonté).
