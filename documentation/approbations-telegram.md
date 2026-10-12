# Approbations d'Asia dans Telegram

Validation du 11 octobre 2026, sur la passerelle Windows OpenCode. Les boutons sont reçus dans la conversation privée du propriétaire avec Asia. Un accord unique et un refus explicite ont été vérifiés avec deux commandes `echo` distinctes et sans effet sur les fichiers.

## Incident et correction

Le premier essai n'a affiché aucun bouton chez le propriétaire. La demande native a expiré après 120 secondes et Asia a rejeté la permission OpenCode. Aucune commande n'a été exécutée. Ce cas est un **échec de présentation**, jamais une preuve de refus humain : OpenClaw enregistre aussi `decision=deny` lors d'une expiration, mais avec `terminal_reason=timeout` et `resolver_kind=system`.

Le réglage `channels.telegram.accounts.asia.execApprovals.target` est passé de `channel` à `dm`. Le mode précédent dépendait de la conversation d'origine ; le mode privé vise directement l'unique approbateur configuré. Le lanceur du test fournit aussi un destinataire explicite avec `--to`, en plus des paramètres de réponse. Les essais suivants prouvent la réussite de cette combinaison ; ils n'isolent pas laquelle de ces deux modifications était nécessaire à elle seule. [Comportement documenté par OpenClaw](https://docs.openclaw.ai/tools/exec-approvals-advanced).

Les instructions d'Asia distinguent maintenant absence de décision, expiration et refus humain. Après expiration, elle ne doit pas appeler `reject` ni relancer automatiquement la demande. Pour ces seules tâches de test, l'annulation était explicitement autorisée comme nettoyage. Cette règle de formulation est une consigne au modèle, pas une garantie déterministe sur tous ses futurs messages.

La comparaison complète de configuration, hors métadonnées natives, confirme que seul `target` a changé. Le propriétaire autorisé, les permissions, les modèles, les budgets et les deux autres comptes sont conservés. Le journal privé de correction garde les valeurs et instructions précédentes.

## Résultats observés

| Essai | Action et preuve native | Exécution vérifiée |
| --- | --- | --- |
| Initial | Aucun bouton vu ; expiration système | Une demande de commande, aucune exécution ; tâche annulée |
| `dm-1` | Le propriétaire a cliqué par erreur sur autoriser : `allowed`, `allow-once`, `user`, `channel` | Une seule exécution, sortie réelle exactement égale au marqueur attendu, tâche terminée |
| `dm-2` | Le propriétaire a cliqué sur refuser : `denied`, `deny`, `user`, `channel` | Une seule demande de commande, aucune exécution, aucune permission restante |

`dm-1` conserve son résultat attendu « refus » en échec dans le journal. Son résultat effectivement observé valide séparément l'accord unique ; il n'a pas été renommé pour masquer l'écart. Aucun troisième appel d'inférence n'est nécessaire pour répéter cet accord.

La vérification croise les enregistrements natifs `operator_approvals`, filtrés sur la session et la commande du test, avec les appels et sorties OpenCode de cette même tâche. Elle ne résout aucune approbation. Elle exige `terminal_reason=user` et `resolver_kind=channel` ; une simple réponse textuelle d'Asia ou `decision=deny` ne suffit pas. Un observateur WebSocket sans capacité de présentation n'avait reçu aucun événement lors des premiers essais ; les preuves natives persistantes sont donc lues directement, en lecture seule.

Les 61 tests Node et 48 tests Python passent, ainsi que la compilation. Les nouveaux contrôles empêchent notamment de confondre expiration et refus, accord et exécution, ou plusieurs appels et exécution unique. Les trois comptes Telegram passent leur sonde native après correction. Cette campagne utilise des appels de modèles facturés au budget commun, contrairement au simulateur de pannes précédent.

## Refaire le test

Utiliser un nom d'essai neuf ; ne pas réutiliser les journaux `dm-1` et `dm-2`. Le propriétaire doit être présent dans Telegram avant `present` : la demande expire après deux minutes.

```powershell
$env:ASIA_TELEGRAM_APPROVAL_TEST = 'nouvel-essai'
node infra/test-telegram-approvals.mjs prepare deny
node infra/test-telegram-approvals.mjs present deny
# Le propriétaire clique sur Refuser dans Telegram.
node infra/test-telegram-approvals.mjs verify deny
# Seulement après réussite du refus : nouvelle tâche, commande distincte.
node infra/test-telegram-approvals.mjs prepare allow
node infra/test-telegram-approvals.mjs present allow
# Le propriétaire clique sur Autoriser une fois.
node infra/test-telegram-approvals.mjs verify allow
Remove-Item Env:ASIA_TELEGRAM_APPROVAL_TEST
```

Vérifier le code de sortie avant chaque étape. `observe deny` permet une lecture ponctuelle de la décision ; `cancel deny` annule uniquement la tâche identifiée dans le journal. Après une interruption ou une expiration, inspecter puis réconcilier cette tâche avant de créer un autre essai. Une présentation déjà envoyée n'est jamais relancée automatiquement. Un code de sortie nul du processus agent ne remplace pas `verify`.

## Preuves et retour arrière

Les journaux `telegram-approval-test*-private.json` restent dans `%LOCALAPPDATA%/AsiaDocker` et sont inclus explicitement dans la sauvegarde chiffrée. Les traces de conversation et les logs CLI du diagnostic ne sont pas ajoutés à cette sélection. Les journaux `training/telegram-approval-routing.json` et `training/telegram-approval-result.json` conservent la correction et le bilan. Aucun de ces fichiers privés n'est publié sur GitHub.

La restauration de contrôle de `D:\AsiaBackups\docker-20261012T034619-1ae34db0.aes` a réussi : 253 fichiers vérifiés, dont les trois journaux de test d'approbation et 38 reçus de formation ; archive OpenClaw restaurée à part et 91 tables PostgreSQL restaurées dans une base temporaire. Son manifeste indique les modifications de travail présentes avant le commit. Cette vérification ne remplace aucune donnée de production.

Pour annuler le changement de routage : terminer ou annuler les tâches de test encore ouvertes, consulter le journal privé, puis rétablir uniquement la valeur précédente de `channels.telegram.accounts.asia.execApprovals.target` avec `openclaw config patch --stdin` (valider d'abord avec `--dry-run`). Ne pas remplacer toute la configuration par une ancienne copie. Rétablir les instructions précédentes depuis `before_instructions` seulement si le fichier actif correspond encore à `after_instructions` ; sinon fusionner les modifications intervenues depuis. Recontrôler les trois comptes et garder les preuves. Le retour à `channel` peut réintroduire l'absence de boutons du scénario initial.

Le [redémarrage complet de Windows](redemarrage-windows.md) a ensuite été contrôlé le 12 octobre. La veille/réveil et les autres parcours Telegram non déjà exercés restent à valider séparément.
