# Publication documentaire durable — travail en cours

Point de reprise du 12 octobre 2026. Travail suspendu à la demande de Rass pour préserver son quota Codex ; reprendre la semaine suivante sur sa demande. Cette version n'est pas validée pour la production.

## Réalisé

- Service Node 24 dans Docker, base PostgreSQL distincte `asia_publication`, adaptateur OpenClaw `asia-publication`.
- Documents complets lus depuis le workspace, manifeste immuable avec empreinte, validation humaine, idempotence, checkpoints et rapprochement GitHub après réponse incertaine.
- V1 limitée aux fichiers Markdown dans `docs/`, sans fusion de PR ni exécution de code.
- 12 tests Node et 11 contrôles PostgreSQL réussis à nouveau avant la pause.
- Essai réel de préparation par Asia : documents artificiels reçus dans Telegram ; aucune PR de cet essai publiée au dernier contrôle.

## Blocage précis à reprendre en premier

Le propriétaire confirme avoir envoyé la commande Telegram et reçu une confirmation, mais la base conserve `awaiting_approval` et `approval: null`.

- Dépôt privé de test : `Abdourahmandev/asia-publication-tests`.
- Demande : `2b9058f5-19da-4d5b-a73a-28fe08afbd92`.
- Empreinte : `408b30e42eb96301a063a915ce820645c6b7bbce8b77ee329b9acd9ad36df5e0`.
- requestId : `durable-pilot-20261012-01`.
- Session de préparation : `agent:asia:durable-publication-pilot-8e170d35-4e93-45c2-b18b-6f02e6973087`.
- Les deux notifications de préparation sont marquées envoyées. Le chargement du plugin est confirmé dans les logs OpenClaw. L'historique du chat principal ne contient pas de nouvelle entrée correspondant à la commande native ; cela ne prouve pas son absence de réception.

Vérifier le traitement natif `/publication`, son contexte réel (`channel`, `accountId`, `senderId`, `isAuthorizedSender`) et la réponse exacte. Ne pas assouplir l'authentification sans preuve, ni fabriquer une validation humaine. Après 24 heures, la demande doit expirer : préparer alors une nouvelle validation explicite et rapprocher GitHub avant toute nouvelle publication.

## État privé et reprise technique

Les secrets, la configuration et le journal de rollback restent exclusivement dans `%LOCALAPPDATA%\AsiaPublication`. Ne pas les publier sur GitHub. La base de test est `asia_publication_test` sur le PostgreSQL Paperclip ; les tables Paperclip ne sont pas modifiées.

Commandes depuis la racine du dépôt :

```powershell
node --test test/publication.test.mjs
python -X utf8 infra/publication/deploy.py provision
python -X utf8 infra/publication/deploy.py install
Get-Content -Raw infra/publication/test-store.mjs | docker exec -i asia-publication-publication-1 node --input-type=module
```

Inspecter d'abord `adapter-before.json` : `install` refuse si déjà déployé. Le rollback restaure seulement les champs et instructions qu'il a modifiés, vérifie les divergences et arrête le service ; il conserve la base et les éventuels effets GitHub :

```powershell
python -X utf8 infra/publication/deploy.py rollback
```

## Travail restant

1. Corriger et valider la commande réelle du propriétaire ; terminer la PR pilote et joindre son lien à la tâche Codex.
2. Vérifier la reprise réelle après interruption, sans duplication de branche ou PR. Les scénarios de réponse perdue sont pour l'instant testés avec des doublures.
3. Intégrer la nouvelle base et la configuration aux sauvegardes chiffrées, tester une restauration isolée. Exclure `node_modules` de la copie de code dans `ops/backup-docker.py`. Une restauration de sauvegarde ne doit pas relancer aveuglément des effets GitHub.
4. Comparer les deux documents D2 déjà écrits dans `C:\Users\Rass\Documents\OpenCode\taxqc-work` aux décisions validées : `docs/product/perimetre-mvp.md` et `docs/project/plan-de-livraison.md`. Préserver ces modifications non committées. Préparer puis faire valider leur manifeste avant publication par le service dans `Abdourahmandev/Simulateur_tax_qc`. Ne pas créer manuellement une PR pour contourner le test.
5. Compléter documentation et instructions sources des agents, exécuter les tests globaux et le build, vérifier les secrets et finaliser la revue avant intégration dans `main`.

Limites connues : pipeline de code OpenCode inchangé ; synchronisation Paperclip non implémentée ; sauvegarde spécifique au service encore absente. Ne pas présenter le problème initial comme entièrement corrigé.
