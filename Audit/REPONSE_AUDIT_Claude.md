# Réponse à l'audit Copilot

**Date :** 2026-10-28
**Auteur :** Claude (opérateur de la plateforme depuis la migration Ubuntu)
**Audit concerné :** [SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Copilot.md](SOFTWARE_FACTORY_ARCHITECTURE_AUDIT_Copilot.md)
**Méthode :** relecture de l'audit, puis vérification de chaque constat dans la branche `ubuntu-server` (ce qui tourne en production), avec une vérification en lecture seule de l'état du serveur (branche et conteneurs actifs, sans lire de secrets).

## 0. Avant tout : l'audit porte sur la mauvaise branche

Copilot a lu `main`. Or `main` est figée au **12 octobre 2026**, à l'époque du pilote sous Windows. Le système réel est sur la branche **`ubuntu-server`** :

| | `main` | `ubuntu-server` |
|---|---|---|
| Dernier changement de code | 12 oct. (Windows) | 27 oct. (PR #24) |
| Commits en plus | — | **105** (104 fichiers, ~5 700 lignes) |
| PR fusionnées | #25 (l'audit) | #1 à #24 |
| Ce que le serveur exécute | non | **oui**, identique à `origin/ubuntu-server` |

Composants qui existent en production mais que l'audit ne pouvait pas voir : migration Ubuntu (`ops/systemd/`, 13 unités), **atelier** (`infra/atelier/`, environnement d'exécution isolé pour Souleiman et Maryam), **Maryam** (QA), page d'approbations du propriétaire, synchronisation des coûts LiteLLM vers Paperclip, réveil des agents et nettoyage des exécutions orphelines, alertes de sauvegarde avec copie hors site, Dorasso (assistant personnel, base comptable), pont Notion, pages Dépenses et brouillons Gmail.

**Conséquence :** plusieurs constats sont déjà en partie réglés. En revanche, l'erreur de Copilot révèle elle-même le **vrai problème n° 1** : n'importe quel lecteur du dépôt (humain ou agent) tombe sur un état faux. Copilot n'a pas mal raisonné, il a lu ce que le dépôt lui montrait.

## 1. Verdict constat par constat

Légende : ✅ d'accord · 🟡 d'accord en partie / déjà partiellement réglé · ❌ pas d'accord

| ID | Sujet | Verdict | Mon avis |
|---|---|---|---|
| F-01 | Le dépôt n'implémente pas Ubuntu | 🟡 | **Faux sur le fond** : la plateforme tourne sur Ubuntu depuis le 13 oct. (systemd, timers, scripts `.sh`). **Juste sur la forme** : même dans `ubuntu-server`, le README, `documentation/README.md` et `exploitation.md` décrivent encore Windows et Docker Desktop. La décision d'hôte est déjà prise (Ubuntu) ; ce qui manque, c'est de l'écrire et de fusionner dans `main`. |
| F-02 | Pont Windows = grand rayon d'action | 🟡 | Le risque était réel sous Windows. Sur Ubuntu, le travail de code de Paperclip passe par l'**atelier** : conteneur dédié, `cap_drop ALL`, `no-new-privileges`, aucun socket Docker, limites mémoire/CPU/PID, hook `pre-push` qui refuse `main` et la suppression de branches. **Restent vrais :** le volume `/work` est persistant et partagé (pas jetable par tâche), l'accès Internet sortant est ouvert, un jeton GitHub est monté, et le hook n'est pas inviolable (le fichier l'admet). Ma recommandation : un dossier de travail par ticket, nettoyé à la fin, et un jeton GitHub limité aux dépôts de projets. |
| F-03 | Config OpenClaw réelle ≠ exemple versionné | ✅ | Toujours vrai sur Ubuntu. Un script de diff en lecture seule (config live nettoyée vs exemple) suffirait. Peu coûteux, utile. |
| F-04 | Identifiants Paperclip en clair dans le profil | ✅ | D'accord. Risque acceptable pour un seul propriétaire, à condition que les sauvegardes restent chiffrées et que la rotation soit documentée. |
| F-05 | Les limites de coût ne sont pas des garanties | 🟡 | Les budgets par clé LiteLLM (équipe et par agent) **sont** appliqués côté LiteLLM, avec un léger retard ; ils ont déjà bloqué un agent arrivé au plafond, ce qui prouve qu'ils fonctionnent. Ce qui manque vraiment : une limite de **durée** et de **relances par ticket** dans le code. On a déjà perdu de l'argent avec des exécutions orphelines avant d'ajouter le nettoyage (`reap-atelier-orphans.py`). |
| F-06 | Pas de corrélation tâche ↔ coût | 🟡 | En grande partie réglé : `paperclip-costs.timer` publie toutes les 15 min les dépenses LiteLLM comme événements de coût par exécution/ticket, et Asia peut les lire. Reste à faire : lier aussi la PR et le résultat de CI dans un reçu final. |
| F-07 | Sauvegardes sans vraie reprise après sinistre | 🟡 | Copie hors site chiffrée (rclone) et alertes Telegram (échec, échec hors site, plus de 36 h sans sauvegarde) **existent**. **Mais Copilot a raison sur le fond, et c'est pire qu'il ne le pense :** lors de la migration du 13 oct., les sauvegardes Windows se sont révélées **irrécupérables, faute de clé de récupération**. Aucune restauration sur machine vierge n'a été faite depuis. C'est pour moi la priorité n° 2. |
| F-08 | Sortie réseau de Playwright non filtrée | ✅ | Toujours vrai (`browser_egress` sans filtrage par destination). À tester depuis le conteneur : réseau local du serveur, autres conteneurs, passerelle Docker. Même remarque pour l'atelier, qui a aussi un accès sortant. |
| F-09 | Documentation contradictoire | ✅ | **Entièrement d'accord, et c'est la cause de l'erreur de l'audit lui-même.** Priorité n° 1. |
| F-10 | Ce n'est pas une livraison autonome | 🟡 | D'accord sur le constat, pas sur le ton. Le flux ticket → atelier → PR → QA (Maryam) → revue → fusion par le propriétaire **fonctionne déjà** : projet Messagerie livré en 6 lots (≈ 5 $), Simulateur en cours (30+ PR). Garder la fusion et le déploiement humains est un choix voulu, pas une lacune. |
| F-11 | Actions non épinglées par SHA | ✅ | D'accord, effort minime. J'ajoute : **la CI tourne sur `windows-latest` alors que la prod est sous Linux**. Les scripts `.sh` et les unités systemd ne sont pas testés. Il faut ajouter un job `ubuntu-latest`. |
| F-12 | Plateforme lourde pour l'hôte | 🟡 | Le constat (PC de 12 Go) ne s'applique plus. Mais la question devient plus pertinente sur Ubuntu : **16 conteneurs** en continu, plus des services hors Docker. Il faut mesurer la mémoire et couper ce qui ne sert pas. |

## 2. Recommandations d'organisation et de simplification

| Recommandation Copilot | Verdict | Mon avis |
|---|---|---|
| Garder OpenClaw, LiteLLM, Telegram, Paperclip, GitHub | ✅ | D'accord. |
| Paperclip = seule file de tâches durable | ✅ | Déjà la pratique. Une règle apprise à ajouter : **un commentaire sur un ticket assigné réveille l'agent**, donc les tickets en attente restent non assignés. |
| Réduire à Asia + un spécialiste, pas d'agent QA permanent | ❌ | Pas d'accord. Le texte est fondé sur 3 agents ; en réalité il y en a 4 et Maryam (QA) a un rôle mesuré. Elle n'attrape pas tout (des failles comme le path traversal ont été trouvées à la revue du PO), mais la séparation dev / QA / revue humaine a fait ses preuves sur deux projets. À réévaluer sur des données de coût par rôle, pas par principe. |
| Remplacer le pont Windows par un exécuteur isolé | 🟡 | Déjà fait en pratique (atelier). Il reste à **retirer** du dépôt et de la doc ce qui concerne le pont Windows, ou à le marquer comme historique, et à durcir l'atelier (voir F-02). |
| Retirer l'ancienne UI Asia / OpenChamber après période de retour arrière | ✅ | D'accord. Windows n'existe plus comme cible de retour arrière, donc la fenêtre est passée. Le code `src/`, `public/`, `server.mjs`, `start-asia.ps1`, `integrations/` (Windows) et les `.ps1` peuvent être archivés. |
| Rendre audio et navigateur optionnels | 🟡 | D'accord pour Playwright si peu utilisé. L'audio est **utilisé** (notes vocales Asia et Dorasso) : à garder. |
| Réduire le catalogue de modèles | ✅ | D'accord, à partir des données d'usage LiteLLM. |
| Pas de nouveau tableau de bord ni de nouveau framework | ✅ | D'accord. Remarque : depuis l'audit, plusieurs petites surfaces web sont apparues (approbations, Dépenses, brouillons Gmail, Messagerie). Il faut les inventorier ; certaines sont des contournements temporaires, comme la page d'approbations qui contourne un bug Paperclip en amont. Celle-ci devra être retirée quand le correctif sera publié. |

**Ce que Copilot ne pouvait pas voir et qui ajoute de la complexité :** Dorasso (Hermes, base comptable, SearXNG, QuickBooks, Gmail), le pont Notion, AdGuard sur le même serveur. Le périmètre a nettement grandi depuis `main`. La simplification n° 1 de Copilot (un seul hôte, un seul runbook) reste la bonne, mais la n° 2 devient : **séparer clairement « usine de code » et « assistant personnel »** (réseaux, clés, sauvegardes, documentation), ce qui est déjà amorcé avec le réseau `personal`.

## 3. Ce que l'audit a manqué

1. **`main` ≠ production.** Un dépôt dont la branche par défaut a deux semaines de retard trompe tous les outils, les agents et les relecteurs.
2. **Le dépôt est public.** La documentation détaille l'architecture, les noms de services, les ports et des liens vers les bots. Rien de secret n'y est (le contrôle `check:repo` existe), mais cette visibilité pèse sur tout ce qu'on y écrit, y compris les journaux d'incidents. **À décider :** le passer en privé, ou garder une version publique « vitrine » à part.
3. **Clé de récupération des sauvegardes.** Une sauvegarde chiffrée sans clé conservée hors de la machine ne sert à rien. On l'a vécu le 13 oct.
4. **Rotation des secrets.** Des incidents d'exposition ont eu lieu pendant le pilote. Ils sont consignés dans le Journal Decidata (Notion), hors de ce dépôt public. Certaines rotations restent ouvertes.
5. **Annulation Paperclip.** Un timeout ou une annulation ne tue pas le processus distant dans l'atelier. C'est compensé par un nettoyage périodique, mais cela fait partie des contrôles « dans le code » que Copilot réclame à juste titre.
6. **CI Windows pour une prod Linux** (voir F-11).

## 4. Mes priorités (ordre proposé)

| # | Action | Effort | Pourquoi |
|---|---|---|---|
| 1 | Fusionner `ubuntu-server` dans `main` (ou en faire la branche par défaut) et écrire une page « État actuel » datée : hôte Ubuntu, services actifs, ce qui est historique | 0,5 j | Corrige F-01, F-09 et la cause de cet audit |
| 2 | Clé de récupération hors serveur + **restauration réelle sur machine vierge** (VM) | 1 j | F-07 ; on a déjà perdu des sauvegardes une fois |
| 3 | Clore les rotations de secrets ouvertes ; décider public ou privé | 0,5 j | Risque concret, pas théorique |
| 4 | Job CI `ubuntu-latest` + Actions épinglées par SHA | 0,5 j | F-11 |
| 5 | Atelier : dossier par ticket nettoyé, jeton GitHub limité, durée max et relances max par ticket dans le code | 1–2 j | F-02, F-05 |
| 6 | Test de sortie réseau Playwright et atelier vers le réseau local et les autres conteneurs | 0,5 j | F-08 |
| 7 | Archiver le code Windows / ancienne UI / OpenChamber ; inventaire mémoire des 16 conteneurs | 1 j | Simplification, F-12 |
| 8 | Diff de config OpenClaw live vs versionnée | 0,5 j | F-03 |

## 5. Conclusion

L'audit est **solide dans son raisonnement** : approche prudente, pas de sur-ingénierie, distinction claire entre ce qui est prouvé et ce qui est supposé. Sa recommandation finale (pilote supervisé, fusion et déploiement humains, pas de nouveau framework) est **la bonne** et je la partage.

Mais il juge un état vieux de deux semaines. Environ la moitié de ses constats sont déjà partiellement traités dans `ubuntu-server` (atelier, coûts par ticket, sauvegarde hors site, alertes). Sa recommandation la plus forte devient donc : **faire en sorte que le dépôt dise la vérité.** Ensuite seulement, refaire un audit ciblé (sur `ubuntu-server`) pour les points 5, 6 et 8.
