# Publication GitHub par Asia et Souleiman

Asia peut ouvrir une PR demandée sur une branche déjà poussée. Elle utilise le connecteur GitHub natif ; l'absence de `gh` sur Windows ne bloque pas cette étape. Les opérations sur le clone Windows passent toujours par OpenCode et ses validations humaines.

## Parcours

1. Asia lit les documents approuvés et transmet leur **contenu complet**, avec le dépôt, la branche et les chemins cibles. Un chemin de son workspace n'est pas accessible automatiquement dans celui de Souleiman ou sur Windows.
2. Souleiman prépare ou révise les changements. La consigne distingue rédaction, validation humaine, commit, push et création de PR ; une autorisation de préparer ne vaut pas autorisation de publier.
3. Pour les commandes Windows nécessitant une approbation, Asia ou Souleiman utilise sa conversation directe avec le propriétaire. Dans OpenClaw 2026.10.1, une sous-mission peut manquer du scope `operator.approvals`, sous une erreur générique `gateway unavailable`. Paperclip seul ne corrige pas cette limite. Aucun droit d'auto-approbation n'est ajouté.
4. La tâche OpenCode reçoit un objectif complet et borné : clone existant, branche, contenu exact, contrôles, commit et push autorisés. Conserver son `taskId` et un `requestId` stable pour chaque consigne, y compris `continue`. Chaque permission native reste soumise à la décision humaine.
5. Après vérification de la branche distante, Asia découvre le schéma de `github__create_pull_request`, recherche une PR existante pour le même head/base, puis crée la PR si nécessaire. Elle vérifie l'URL, le commit et la portée des fichiers. Pas de fusion automatique.

Les tests directs de Git et le MCP diagnostiquent des accès distincts : `git ls-remote` prouve une lecture Git ; il ne prouve pas l'écriture. `gh auth status` ne diagnostique ni Git Credential Manager ni le MCP. Ne pas demander un token dans une conversation quand les accès existants fonctionnent.

## Permissions et installation

Le filtre global expose quatorze outils GitHub à Souleiman. Asia reçoit les onze lectures et **un seul outil d'écriture**, `github__create_pull_request`. Les nouvelles missions d'Asia vers Souleiman héritent aussi de cette création de PR. Les anciennes missions conservent leur plafond capturé. Les outils de modification d'issue et de mise à jour de PR restent réservés à Souleiman en direct ; fusion et publication de fichiers via MCP restent absentes. Saredo n'a pas ces connecteurs.

Ces outils ne sont pas limités techniquement à un dépôt par les instructions : les droits du token GitHub restent applicables. Voir [les connecteurs](connecteurs-souleiman.md) pour l'authentification et ses limites.

Après l'installation des connecteurs et des lectures déléguées :

```powershell
python infra/configure-github-publication.py
python infra/configure-github-publication.py --apply
```

Le premier appel valide sans modifier. Le second sauvegarde le patch et les instructions précédentes dans `%LOCALAPPDATA%\AsiaDocker\github-publication-private.json`, puis applique un patch natif sans modifier secrets, canaux, sessions ou permissions Windows. Les notes privées des agents sont conservées. Un journal existant empêche de rejouer aveuglément le déploiement. Après inspection d'une interruption en phase `prepared`, utiliser `--resume`.

## Reprise après interruption

Avant tout nouvel essai, vérifier le clone, les fichiers, la branche locale et distante, les commits, les PR et les anciens exécuteurs. Ne pas laisser deux tâches modifier le même clone. Une demande annulée par le système ou expirée n'est pas un refus humain. Conserver la distinction dans la réponse au propriétaire.

Une erreur après un appel de création peut masquer un effet déjà produit. Rechercher la PR par head/base et vérifier son commit avant toute répétition. Si cette lecture échoue aussi, conserver l'état **incertain**, arrêter les écritures et expliquer ce qui reste à vérifier. Une erreur « PR already exists » appelle une lecture, pas une autre création.

### Limite observée avec Gemini et OpenClaw

Pendant la publication du 12 octobre, certains identifiants d'appel fournis via LiteLLM contenaient `__thought_` et dépassaient 1 024 caractères. Le résultat d'outil différé OpenClaw a échoué sur `details.parentToolCallId` après la création effective de la PR. L'agent a tenté une nouvelle création après une lecture elle-même en erreur ; GitHub a refusé le doublon. Une lecture ultérieure a retrouvé la PR et permis la vérification indépendante.

La PR est livrée, mais cet essai **ne prouve pas une exécution exactement une fois** : il montre une publication suivie d'une récupération. Les instructions imposent la réconciliation ; elles ne constituent pas une barrière déterministe contre les répétitions. Le défaut de corrélation de cette version d'OpenClaw reste à corriger ou à revalider lors d'une mise à jour. Aucune signature Gemini n'a été supprimée, aucun modèle ni composant moteur n'a été modifié pour masquer ce problème.

## Validation du 12 octobre 2026

- Le clone déjà créé a été repris ; la branche `docs/revision-workflow-equipe` contient le commit `1407c2cd8ff6951bb0da90698cdbbfd957eb2d12`.
- Codex a préparé et poussé les deux documents approuvés. Asia a effectué la création via son MCP dans une conversation technique sans livraison Telegram. La [PR #8 de Simulateur_tax_qc](https://github.com/Abdourahmandev/Simulateur_tax_qc/pull/8) est ouverte, non draft et non fusionnée.
- GitHub REST confirme une seule PR pour ce head/base et exactement deux fichiers : `docs/project/workflow.md` et `docs/tax/hypotheses-fiscales.md`. Chaque contenu distant correspond au blob Git local. Les liens locaux, l'encodage et `git diff --check` passent ; le registre fiscal reste vide. La publication ne vaut pas revue fiscale ni alignement de D2.
- Une note `projets/simulateur-tax-qc/publication-resultat.md` dans le workspace d'Asia conserve l'URL, le commit et l'état des anciennes tâches. Les anciens exécuteurs ont été annulés et sont inactifs ; leurs permissions historiques peuvent encore apparaître et ne doivent pas être reprises.
- Le test direct Souleiman Context7/GitHub réussit. Une nouvelle mission native Asia → Souleiman lit le dépôt privé et toutes ses issues, suit la pagination et retourne les résultats à Asia. Les inventaires du parent et de l'enfant comprennent la création de PR, sans les autres écritures GitHub. Saredo reste sans ces connecteurs. Les trois comptes Telegram sont actifs côté Gateway.
- 83 tests Python et 71 tests Node passent. Les sept nouveaux tests couvrent le patch limité, les refus explicites, les prérequis, la conservation des notes, l'idempotence et le retour arrière avec détection des conflits. Le rollback n'a pas été exécuté en production.

Les rapports détaillés restent privés : `github-publication-validation-private.json`, `pr-publication-rest-verification-private.json`, `github-delegation-validation-private.json` et `souleiman-connectors-validation-private.json`. Le test de publication n'est pas relancé automatiquement : une nouvelle création nécessite une vraie demande du propriétaire.

## Retour arrière

```powershell
python infra/configure-github-publication.py --rollback
```

Le patch restaure les permissions et instructions précédentes après vérification des conflits. Les lectures d'Asia restent disponibles. La PR, les commits, les conversations et les dépenses ne sont pas annulés. Pour retirer aussi les lectures déléguées puis les connecteurs, appliquer ensuite les deux retours arrière décrits dans [les connecteurs](connecteurs-souleiman.md), dans cet ordre.
